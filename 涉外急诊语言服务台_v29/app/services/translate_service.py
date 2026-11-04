# -*- coding: utf-8 -*-
"""翻译编排：术语锁定 → 平行语料上下文 → MT（mock/deepseek/generic/mymemory）→ 译后校验。

设计原则：
- 所有函数同步；任何模型侧异常都降级为 mock 译文并标 degraded=True，绝不 500；
- mock 模式只做「术语替换 + 句对拼装」，不发起任何网络请求；
- 目标语为 vi/th/id/ms 时用 local_terms（东盟本地语对照，1,040 条）锁定 must_use=local_text；
- 返回结构固定，前端按 locked_terms 做 <mark> 高亮。
"""
from __future__ import annotations

import copy
import html
import json
import logging
import os
import re
import time
from collections import OrderedDict

import httpx
from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..models import LocalTerm
from . import llm
from .llm import LLMUnavailable
from .retrieval import search_corpus, search_corpus_vector, search_terms

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_RESULT_LEN = 4000
MT_TIMEOUT = 20.0

# MyMemory 免费公共端口：GET /get?q=...&langpair=zh-CN|vi
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
MYMEMORY_TIMEOUT = 8.0
MYMEMORY_MAX_CHARS = 450          # 单次请求字符上限（公共端口的实际上限约 500 字节/字符）
MYMEMORY_LANG = {
    "zh": "zh-CN",
    "en": "en-GB",
    "vi": "vi-VN",
    "th": "th-TH",
    "id": "id-ID",
    "ms": "ms-MY",
}
# HTTP 头必须是 ASCII，中文备注会触发 UnicodeEncodeError（不要改成中文）
MYMEMORY_UA = "AIT-CourseBot/1.0 (+ait-course-demo)"
MYMEMORY_MIN_INTERVAL = 1.2         # 全局最小调用间隔（秒），公共端口 QPS 很低
MYMEMORY_RETRY_SLEEP = 2.5          # 命中 429 后等待再重试 1 次
MYMEMORY_COOLDOWN_SECONDS = 20.0    # 重试仍失败后的冷却时间
_MYMEMORY_COOLDOWN_UNTIL = 0.0
_MYMEMORY_LAST_CALL_AT = 0.0
_MYMEMORY_LAST_STATUS = 0

LANGS: list[dict] = [
    {"code": "zh", "name": "中文"},
    {"code": "en", "name": "英语"},
    {"code": "vi", "name": "越南语"},
    {"code": "th", "name": "泰语"},
    {"code": "id", "name": "印尼语"},
    {"code": "ms", "name": "马来语"},
]
LANG_NAMES = {item["code"]: item["name"] for item in LANGS}
LANG_CODES = set(LANG_NAMES)
LOCAL_TARGETS = ("vi", "th", "id", "ms")   # 使用 local_terms 做术语锁定的目标语

# 本地语术语索引缓存：lang_code -> list[dict]，避免每次请求扫表
_LOCAL_TERM_CACHE: dict[str, list[dict]] = {}

# 进程内 LRU 翻译缓存：(src,tgt,text) -> (result, 时间戳)；容量 500，演示时避免重复打公共端口
_TRANSLATE_CACHE: "OrderedDict[tuple, tuple[dict, float]]" = OrderedDict()
_TRANSLATE_CACHE_MAX = 500
_CACHE_DEGRADED_TTL = 30.0          # 降级结果只缓存 30s，配额恢复后能自动重新请求


class UnsupportedLanguage(ValueError):
    """语种或翻译方向不支持（路由返回 400）。"""


class MTUnavailable(LLMUnavailable):
    """MT 服务不可用；继承 LLMUnavailable 便于上层统一降级。"""

    code = "mt_unavailable"


def mt_provider() -> str:
    """当前机器翻译 provider：mock / deepseek / generic / mymemory。"""
    return (settings.mt_provider or "mock").strip().lower()


def providers() -> dict:
    """给 /api/translate/languages 用：三个模型侧 provider。"""
    return {
        "mt": mt_provider(),
        "embedding": (settings.embedding_provider or "local").strip().lower(),
        "llm": (settings.llm_provider or "mock").strip().lower(),
    }


# ---------------------------------------------------------------- 文本匹配
def _find_spans(text: str, needle: str, lang: str) -> list[tuple[int, int]]:
    """找出 needle 在 text 中的全部出现位置；英文按词边界匹配。"""
    if not needle:
        return []
    if lang == "zh":
        if len(needle) < 2:
            return []
        spans: list[tuple[int, int]] = []
        start = text.find(needle)
        while start >= 0:
            spans.append((start, start + len(needle)))
            start = text.find(needle, start + 1)
        return spans
    if len(needle) < 3:
        return []
    lowered = text.lower()
    target = needle.lower()
    spans = []
    start = lowered.find(target)
    while start >= 0:
        end = start + len(target)
        before = lowered[start - 1] if start > 0 else " "
        after = lowered[end] if end < len(lowered) else " "
        if not before.isalnum() and not after.isalnum():
            spans.append((start, end))
        start = lowered.find(target, start + 1)
    return spans


def _pick_longest(spans: list[dict]) -> list[dict]:
    """最长匹配优先、互不重叠，并保持出现顺序。"""
    spans.sort(key=lambda s: (-(s["end"] - s["start"]), s["start"]))
    chosen: list[dict] = []
    for span in spans:
        if any(not (span["end"] <= c["start"] or span["start"] >= c["end"]) for c in chosen):
            continue
        chosen.append(span)
    chosen.sort(key=lambda s: s["start"])
    return chosen


def _lock_terms(text: str, tgt: str, candidates: list) -> list[dict]:
    """公共术语（zh-en）：最长匹配优先、互不重叠地锁定。"""
    spans: list[dict] = []
    for term in candidates:
        for lang, value in (("zh", term.zh or ""), ("en", term.en or "")):
            for start, end in _find_spans(text, value, lang):
                spans.append({"start": start, "end": end, "lang": lang, "term": term})
    chosen = _pick_longest(spans)
    for span in chosen:
        term = span["term"]
        span["must_use"] = (term.zh or "") if tgt == "zh" else (term.en or "")
        span["matched"] = text[span["start"]:span["end"]]
        span.update({
            "term_id": term.term_id,
            "zh": term.zh,
            "en": term.en,
            "domain": term.domain,
            "source_url": term.source_url,
        })
    return chosen


# ---------------------------------------------------------------- 本地语术语（local_terms）
def _local_term_index(lang_code: str) -> list[dict]:
    """读取 local_terms（只读，按 lang_code 缓存）。"""
    cached = _LOCAL_TERM_CACHE.get(lang_code)
    if cached is not None:
        return cached
    items: list[dict] = []
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(LocalTerm).where(LocalTerm.lang_code == lang_code)
            ).all()
            items = [{
                "local_id": row.local_id,
                "lang": row.lang,
                "lang_code": row.lang_code,
                "category": row.category,
                "domain": row.domain,
                "scene": row.scene,
                "zh": row.zh or "",
                "en": row.en or "",
                "local_text": row.local_text or "",
                "romanization": row.romanization or "",
                "pron_hint": row.pron_hint or "",
                "usage_note": row.usage_note or "",
                "source_code": row.source_code or "",
                "audit_status": row.audit_status or "",
            } for row in rows]
    except Exception as exc:  # 表缺失/数据库异常都不能拖垮翻译
        logger.warning("local_terms 读取失败（%s）：%s", lang_code, type(exc).__name__)
        items = []
    _LOCAL_TERM_CACHE[lang_code] = items
    return items


def _lock_local_terms(text: str, tgt: str) -> list[dict]:
    """目标语为 vi/th/id/ms 时，用 local_terms 锁定 zh/en → local_text。"""
    spans: list[dict] = []
    for term in _local_term_index(tgt):
        if not term.get("local_text"):
            continue
        for lang, value in (("zh", term.get("zh") or ""), ("en", term.get("en") or "")):
            for start, end in _find_spans(text, value, lang):
                spans.append({"start": start, "end": end, "lang": lang, "term": term})
    chosen = _pick_longest(spans)
    for span in chosen:
        term = span["term"]
        span["must_use"] = term["local_text"]
        span["matched"] = text[span["start"]:span["end"]]
        span.update({
            "term_id": term["local_id"],
            "zh": term["zh"],
            "en": term["en"],
            "domain": term.get("domain", ""),
            "source_url": "",
            "lang_code": term["lang_code"],
            "local_text": term["local_text"],
            "romanization": term.get("romanization", ""),
            "pron_hint": term.get("pron_hint", ""),
            "usage_note": term.get("usage_note", ""),
            "audit_status": term.get("audit_status", ""),
        })
    return chosen


def _locked_public(spans: list[dict]) -> list[dict]:
    """把内部 span 去重成对外的 locked_terms 列表（同一术语只出现一次）。"""
    locked: list[dict] = []
    seen: set[tuple] = set()
    for span in spans:
        key = (span.get("term_id"), span["lang"], span["matched"].lower())
        if key in seen:
            continue
        seen.add(key)
        item = {
            "term_id": span.get("term_id", ""),
            "zh": span.get("zh", ""),
            "en": span.get("en", ""),
            "matched": span["matched"],
            "matched_lang": span["lang"],
            "domain": span.get("domain", ""),
            "source_url": span.get("source_url", ""),
            "must_use": span["must_use"],
        }
        if span.get("lang_code"):   # 本地语术语：附带 lang 与本地写法
            item.update({
                "lang": span["lang_code"],
                "local_text": span["local_text"],
                "romanization": span.get("romanization", ""),
                "pron_hint": span.get("pron_hint", ""),
                "audit_status": span.get("audit_status", ""),
            })
        locked.append(item)
    return locked


# ---------------------------------------------------------------- mock MT
def _render(span: dict, tgt: str) -> str:
    """术语在目标语中的写法：锁定阶段已算好 must_use（en 或 local_text）。"""
    return span.get("must_use") or span.get("en") or span.get("zh") or ""


def _substitute(text: str, spans: list[dict], tgt: str) -> str:
    if not spans:
        return text
    parts: list[str] = []
    cursor = 0
    for span in spans:
        parts.append(text[cursor:span["start"]])
        parts.append(_render(span, tgt))
        cursor = span["end"]
    parts.append(text[cursor:])
    return "".join(parts)


def _bigrams(value: str) -> set[str]:
    value = "".join(value.split()).lower()
    return {value[i:i + 2] for i in range(len(value) - 1)}


def _overlap_ratio(text: str, candidate: str) -> float:
    a = _bigrams(text)
    b = _bigrams(candidate)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def _pair_value(item, key: str) -> str:
    """语料对象可能是 dict（向量检索）或 ORM 行（关键词检索）。"""
    if isinstance(item, dict):
        return item.get(key) or ""
    return getattr(item, key, "") or ""


def _mock_translate(text: str, src: str, tgt: str, spans: list[dict],
                    pairs: list) -> str:
    """术语替换 + 句对拼装：不联网、确定性可复现。"""
    if src in ("zh", "en") and tgt in ("zh", "en"):
        if not spans and pairs:
            best = pairs[0]
            source_text = _pair_value(best, "zh" if src == "zh" else "en")
            target_text = _pair_value(best, "en" if tgt == "en" else "zh")
            if target_text and _overlap_ratio(text, source_text) >= 0.35:
                return target_text
        return _substitute(text, spans, tgt)
    # 本地语方向：术语替换为 local_text，其余片段保留原文并标演示模式
    return f"[{tgt.upper()} 演示] {_substitute(text, spans, tgt)}"


# ---------------------------------------------------------------- 语料上下文
def _pair_public(item) -> dict:
    """把语料检索结果（dict 或 ORM）统一成 context_pairs 元素，保留 score。"""
    if isinstance(item, dict):
        return {
            "corpus_id": item.get("corpus_id") or item.get("id"),
            "zh": item.get("zh", ""),
            "en": item.get("en", ""),
            "lang_pair": item.get("lang_pair", ""),
            "register": item.get("register", ""),
            "domain": item.get("domain", ""),
            "source_url": item.get("source_url", ""),
            "score": round(float(item.get("score") or 0.0), 4),
        }
    return {
        "corpus_id": item.corpus_id,
        "zh": item.zh,
        "en": item.en,
        "lang_pair": item.lang_pair,
        "register": item.register,
        "domain": item.domain,
        "source_url": item.source_url,
        "score": 0.0,
    }


def _context_pairs(query: str, src: str, tgt: str, limit: int = 3) -> list[dict]:
    """平行语料上下文：优先语料句向量检索，失败/无命中再回退关键词检索。"""
    if {src, tgt} == {"zh", "en"}:
        candidates = ["zh-en"]           # 库内语料只有 zh-en，反向也按 zh-en 取
    else:
        candidates = [f"{src}-{tgt}", "zh-en"]
    for pair in candidates:
        items: list = []
        try:
            items = search_corpus_vector(query, pair, limit)
        except Exception as exc:  # 向量表缺失/依赖异常都不能拖垮翻译
            logger.warning("语料向量检索失败（%s）：%s，回退关键词检索",
                           pair, type(exc).__name__)
            items = []
        if not items:
            try:
                items = search_corpus(query, pair, limit=limit)
            except Exception as exc:
                logger.warning("语料关键词检索失败（%s）：%s", pair, type(exc).__name__)
                items = []
        if items:
            return [_pair_public(item) for item in items[:limit]]
    return []


# ---------------------------------------------------------------- 真实 MT
def _deepseek_translate(text: str, src: str, tgt: str, locked: list[dict],
                        pairs: list) -> str:
    # 术语必须用“目标语写法”：zh->en 用 en，zh->vi/th/id/ms 用本地语 local_text
    term_lines = "\n".join(
        f"- {item['zh']} => {item.get('must_use') or item.get('en') or item.get('local_text', '')}"
        for item in locked[:20]) or "-（无）"
    # 平行语料目前只有中英；非英语目标语时不塞英文句对，避免把译文带偏
    if tgt == "en" and pairs:
        pair_lines = "\n".join(
            f"{i + 1}) {_pair_value(pair, 'zh')} || {_pair_value(pair, 'en')}"
            for i, pair in enumerate(pairs[:3])
        )
    else:
        pair_lines = "（无；目标语非英语，术语以本地语对照为准）"
    messages = [
        {"role": "system",
         "content": "你是涉外急诊语言服务台的专业医学翻译。只输出译文，不要解释；"
                    "必须使用给定术语表中的译法，并参考平行语料保持语气与敬语。"},
        {"role": "user",
         "content": f"源语言：{LANG_NAMES.get(src, src)}；目标语言：{LANG_NAMES.get(tgt, tgt)}\n"
                    f"必须使用的术语：\n{term_lines}\n"
                    f"参考平行语料：\n{pair_lines}\n"
                    f"待译文本：\n{text}"},
    ]
    return llm.chat(messages, temperature=0.2, max_tokens=1200, force_provider="deepseek").strip()


def _split_for_mymemory(text: str, limit: int = MYMEMORY_MAX_CHARS) -> list[str]:
    """MyMemory 单次请求有长度上限，按句切成 ≤limit 的片段。"""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[。！？!?；;\n])", text):
        while len(sentence) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:limit])
            sentence = sentence[limit:]
        if len(current) + len(sentence) > limit:
            chunks.append(current)
            current = ""
        current += sentence
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


def _parse_mymemory(payload: dict) -> str:
    """解析 MyMemory 响应；限额/空结果/格式异常统一抛 MTUnavailable。"""
    status = payload.get("responseStatus")
    data = payload.get("responseData") or {}
    translated = str(data.get("translatedText") or "")
    upper = translated.upper()
    if str(status) != "200":
        raise MTUnavailable(f"MyMemory 返回状态 {status}")
    if not translated.strip():
        raise MTUnavailable("MyMemory 返回空译文")
    if "MYMEMORY WARNING" in upper or "NO QUERY SPECIFIED" in upper or "QUERY LENGTH LIMIT" in upper:
        raise MTUnavailable(f"MyMemory 限额/查询异常：{translated[:80]}")
    return html.unescape(translated).strip()


def _mymemory_throttle() -> None:
    """全局最小间隔 1.2s：连续请求公共端口会被立即限流。"""
    global _MYMEMORY_LAST_CALL_AT
    wait = MYMEMORY_MIN_INTERVAL - (time.time() - _MYMEMORY_LAST_CALL_AT)
    if wait > 0:
        time.sleep(wait)
    _MYMEMORY_LAST_CALL_AT = time.time()


def _mymemory_email() -> str:
    """可选 &de= 邮箱参数（config.mymemory_email 或环境变量 MYMEMORY_EMAIL）。"""
    return (getattr(settings, "mymemory_email", "") or os.environ.get("MYMEMORY_EMAIL", "")).strip()


def _mymemory_request(chunk: str, langpair: str) -> str:
    """单次请求：节流 → 429 等待 2.5s 重试 1 次 → 仍失败进 20s 冷却。

    失败信息统一带 HTTP 状态码，便于排查（429=限流/额度、403=被封、0=网络异常）。
    """
    global _MYMEMORY_COOLDOWN_UNTIL, _MYMEMORY_LAST_STATUS
    if time.time() < _MYMEMORY_COOLDOWN_UNTIL:
        raise MTUnavailable(f"MyMemory 冷却中（上次 HTTP {_MYMEMORY_LAST_STATUS}）")
    params = {"q": chunk, "langpair": langpair}
    email = _mymemory_email()
    if email:
        params["de"] = email
    status = 0
    for attempt in (1, 2):
        _mymemory_throttle()
        try:
            with httpx.Client(timeout=MYMEMORY_TIMEOUT) as client:
                resp = client.get(MYMEMORY_URL, params=params,
                                  headers={"User-Agent": MYMEMORY_UA})
            status = resp.status_code
            _MYMEMORY_LAST_STATUS = status
            if status != 200:
                raise MTUnavailable(f"MyMemory 返回 HTTP {status}")
            return _parse_mymemory(resp.json())
        except MTUnavailable as exc:
            _MYMEMORY_LAST_STATUS = status or _MYMEMORY_LAST_STATUS
            # 429 可能是瞬时限流：等待 2.5s 重试一次（只在第一次尝试时）
            if attempt == 1 and (status == 429 or "429" in str(exc)):
                logger.warning("MyMemory HTTP 429（%s），%.1fs 后重试一次",
                               langpair, MYMEMORY_RETRY_SLEEP)
                time.sleep(MYMEMORY_RETRY_SLEEP)
                continue
            if status in (403, 429) or "429" in str(exc):
                _MYMEMORY_COOLDOWN_UNTIL = time.time() + MYMEMORY_COOLDOWN_SECONDS
            logger.warning("MyMemory 失败（%s）：%s", langpair, exc)
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            _MYMEMORY_LAST_STATUS = status
            logger.warning("MyMemory 调用失败（%s）：%s", langpair, type(exc).__name__)
            raise MTUnavailable(
                f"MyMemory 调用失败：{type(exc).__name__}（HTTP {status or '无响应'}）"
            ) from exc
    raise MTUnavailable(f"MyMemory 重试后仍失败（HTTP {_MYMEMORY_LAST_STATUS}）")


def _mymemory_translate(text: str, src: str, tgt: str) -> str:
    """调用 MyMemory 公共端口；超时 8s，任何失败抛 MTUnavailable 由上层降级。"""
    src_code = MYMEMORY_LANG.get(src)
    tgt_code = MYMEMORY_LANG.get(tgt)
    if not src_code or not tgt_code:
        raise MTUnavailable(f"MyMemory 不支持的语言对：{src}->{tgt}")
    langpair = f"{src_code}|{tgt_code}"
    pieces = [_mymemory_request(chunk, langpair) for chunk in _split_for_mymemory(text)]
    result = "".join(pieces).strip()
    if not result:
        raise MTUnavailable("MyMemory 返回空译文")
    return result


def _dig(data, path: str):
    """按 generic_mt_result_path（如 trans_result.0.dst）取值。"""
    current = data
    for part in (path or "").split("."):
        if part == "":
            continue
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _generic_translate(text: str, src: str, tgt: str) -> str:
    url = (settings.generic_mt_url or "").strip()
    if not url:
        raise MTUnavailable("未配置 GENERIC_MT_URL")
    tpl = settings.generic_mt_payload_tpl or '{"q": "{text}", "source": "{src}", "target": "{tgt}"}'
    raw = tpl.replace("{text}", text).replace("{src}", src).replace("{tgt}", tgt)
    headers = {"Content-Type": "application/json"}
    key = (settings.generic_mt_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    method = (settings.generic_mt_method or "POST").strip().upper()
    try:
        with httpx.Client(timeout=MT_TIMEOUT) as client:
            if method == "GET":
                resp = client.get(url, params={"q": text, "source": src, "target": tgt}, headers=headers)
            else:
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    resp = client.post(url, content=raw.encode("utf-8"), headers=headers)
                else:
                    resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        result = _dig(resp.json(), settings.generic_mt_result_path)
        result = str(result or "").strip()
        if not result:
            raise MTUnavailable("MT 返回结果为空")
        return result
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("generic MT 调用失败：%s: %s", type(exc).__name__, exc)
        raise MTUnavailable(f"MT 服务调用失败：{type(exc).__name__}") from exc


# ---------------------------------------------------------------- 译后校验
def _post_check(translation: str, spans: list[dict], notes: list[str]) -> str:
    """强制替换缺失术语，并写 notes: term_fixed:{zh}->{must_use}。

    must_use 在 zh/en 方向是英文（或中文）术语，在 vi/th/id/ms 方向是 local_text。
    """
    fixed: set[str] = set()
    for span in spans:
        want = span.get("must_use") or ""
        if not want or want.lower() in translation.lower():
            continue
        source = span.get("matched") or ""
        if source and source in translation:
            translation = translation.replace(source, want, 1)
        else:
            translation = translation.rstrip() + f"（术语补正：{span.get('zh', '')} = {want}）"
        key = f"term_fixed:{span.get('zh', '')}->{want}"
        if key not in fixed:
            fixed.add(key)
            notes.append(key)
    return translation


# ---------------------------------------------------------------- 进程内 LRU 缓存
def _cache_get(key: tuple) -> dict | None:
    item = _TRANSLATE_CACHE.get(key)
    if not item:
        return None
    result, stamp = item
    if result.get("degraded") and time.time() - stamp > _CACHE_DEGRADED_TTL:
        _TRANSLATE_CACHE.pop(key, None)   # 降级结果过期，配额恢复后重新请求
        return None
    _TRANSLATE_CACHE.move_to_end(key)
    return copy.deepcopy(result)


def _cache_put(key: tuple, result: dict) -> None:
    _TRANSLATE_CACHE[key] = (copy.deepcopy(result), time.time())
    _TRANSLATE_CACHE.move_to_end(key)
    while len(_TRANSLATE_CACHE) > _TRANSLATE_CACHE_MAX:
        _TRANSLATE_CACHE.popitem(last=False)


def cache_clear() -> None:
    """测试/运维用：清空翻译缓存。"""
    _TRANSLATE_CACHE.clear()


# ---------------------------------------------------------------- 主流程
def translate(text: str, src: str, tgt: str) -> dict:
    """翻译入口：返回 {translation, provider, degraded, locked_terms, context_pairs, notes}。"""
    src = (src or "").strip().lower()
    tgt = (tgt or "").strip().lower()
    raw_text = (text or "").strip()
    if src not in LANG_CODES:
        raise UnsupportedLanguage(f"不支持的源语言：{src}")
    if tgt not in LANG_CODES:
        raise UnsupportedLanguage(f"不支持的目标语言：{tgt}")
    if src == tgt:
        raise UnsupportedLanguage("源语言与目标语言不能相同")
    if not raw_text:
        raise UnsupportedLanguage("待译文本不能为空")
    if len(raw_text) > settings.max_text_len:
        raise UnsupportedLanguage(f"文本长度不能超过 {settings.max_text_len} 字")

    # ⓪ 进程内 LRU 缓存：(src, tgt, text) 命中则直接返回，避免重复打公共 MT 端口
    cache_key = (src, tgt, raw_text)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    notes: list[str] = []
    degraded = False

    # ① 术语锁定：vi/th/id/ms 用 local_terms（must_use=local_text），其余用公共 zh-en 术语
    if tgt in LOCAL_TARGETS:
        used_spans = _lock_local_terms(raw_text, tgt)
        locked = _locked_public(used_spans)
        if locked:
            notes.append(f"local_terms:{tgt}:{len(locked)}")
    else:
        candidates = search_terms(raw_text, limit=20)
        used_spans = _lock_terms(raw_text, tgt, candidates)
        locked = _locked_public(used_spans)

    # ② 平行语料上下文：优先句向量检索（带 score），失败回退关键词检索
    pairs = _context_pairs(raw_text, src, tgt, limit=3)

    # ③ MT
    provider_used = mt_provider()
    if provider_used == "mymemory":
        try:
            translation = _mymemory_translate(raw_text, src, tgt)
        except LLMUnavailable as exc:
            notes.append(f"mt_degraded:mymemory->mock({exc.code})")
            translation = _mock_translate(raw_text, src, tgt, used_spans, pairs)
            provider_used, degraded = "mock", True
    elif provider_used == "deepseek":
        try:
            translation = _deepseek_translate(raw_text, src, tgt, locked, pairs)
        except LLMUnavailable as exc:
            notes.append(f"mt_degraded:deepseek->mock({exc.code})")
            translation = _mock_translate(raw_text, src, tgt, used_spans, pairs)
            provider_used, degraded = "mock", True
    elif provider_used == "generic":
        try:
            translation = _generic_translate(raw_text, src, tgt)
        except LLMUnavailable as exc:
            notes.append(f"mt_degraded:generic->mock({exc.code})")
            translation = _mock_translate(raw_text, src, tgt, used_spans, pairs)
            provider_used, degraded = "mock", True
    else:
        # mock 只是术语替换 + 句对拼接，不是真实机器翻译，按联调口径标记为降级
        provider_used, degraded = "mock", True
        translation = _mock_translate(raw_text, src, tgt, used_spans, pairs)
        notes.append("演示降级：未配置 MT 服务（术语替换+句对拼接，非真实翻译）")

    # ④ 译后校验：强制替换缺失术语（本地语方向用 local_text）
    translation = _post_check(translation, used_spans, notes)

    translation = translation.strip()
    if len(translation) > MAX_RESULT_LEN:
        translation = translation[:MAX_RESULT_LEN]
        notes.append(f"truncated:{MAX_RESULT_LEN}")

    result = {
        "translation": translation,
        "provider": provider_used,
        "degraded": degraded,
        "locked_terms": locked,
        "context_pairs": pairs,          # 元素含 score（语料向量相似度）
        "notes": notes,
        "src": src,
        "tgt": tgt,
    }
    _cache_put(cache_key, result)
    return result
