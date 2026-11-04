# -*- coding: utf-8 -*-
"""逐句对照：把原文切句 → 调一次 DeepSeek 返回逐句译文（JSON 数组）→
生成 segments:[{src,tgt,terms[],pairs[]}]；失败降级为整段翻译后按句对齐。

设计原则：
- 不抛异常给上层：任何失败都降级（整段译文按句切分），最差返回空 tgt 的句子对；
- 一次模型调用只处理一份文本，句子数量与译文数量严格对齐；
- terms/pairs 只保留与该句真正相关的条目，避免前端弹窗噪音。
"""
from __future__ import annotations

import json
import logging
import re

from . import llm
from .llm import LLMUnavailable
from .translate_service import translate

logger = logging.getLogger(__name__)

MAX_SENTENCES = 200
MAX_TERMS_PER_SEGMENT = 8
MAX_PAIRS_PER_SEGMENT = 2
PAIR_MIN_OVERLAP = 0.25

# 中文句末标点直接切；英文句号只在“后接空白或文本结尾”时切，避免切开 3.5、Dr. 之类
_SENTENCE_RE = re.compile(r"[^。！？!?；;\n.]+(?:[。！？!?；;\n]|\.(?=\s|$))?", re.S)


def split_sentences(text: str, limit: int = MAX_SENTENCES) -> list[str]:
    """按中英文句末标点/分号/换行切句，保留原标点；超长句数时把尾部合并。"""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in _SENTENCE_RE.findall(raw) if part.strip()]
    if not parts:
        parts = [raw]
    if len(parts) > limit:
        parts = parts[:limit - 1] + ["".join(parts[limit - 1:])]
    return parts


def _bigrams(value: str) -> set[str]:
    compact = "".join((value or "").split()).lower()
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i:i + 2] for i in range(len(compact) - 1)}


def _overlap(source: str, candidate: str) -> float:
    a = _bigrams(source)
    b = _bigrams(candidate)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def _parse_json_array(raw: str, expected: int) -> list[str] | None:
    """从模型输出里抠出 JSON 数组；必须是 expected 条非空字符串。"""
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, list) or len(data) != expected:
        return None
    if not all(isinstance(item, str) and item.strip() for item in data):
        return None
    return [item.strip() for item in data]


def _translate_sentences(sentences: list[str], src: str, tgt: str) -> list[str] | None:
    """一次 DeepSeek 调用，要求返回与 sentences 等长的 JSON 数组译文。"""
    payload = json.dumps({"src": src, "tgt": tgt, "sentences": sentences}, ensure_ascii=False)
    messages = [
        {"role": "system",
         "content": "你是涉外急诊语言服务台的专业医学翻译。把 sentences 数组里的每一句"
                    "按 src→tgt 翻译，逐句一一对应，不合并、不拆分、不加解释。"
                    "只输出 JSON 字符串数组，元素个数必须等于输入句子个数。"},
        {"role": "user", "content": payload},
    ]
    max_tokens = min(4000, 60 * len(sentences) + 200)
    raw = llm.chat(messages, temperature=0.2, max_tokens=max_tokens, force_provider="deepseek")
    return _parse_json_array(raw, len(sentences))


def _split_translated(translation: str, count: int) -> list[str]:
    """降级路径：把整段译文按句切分，并对齐到 count 句。"""
    parts = split_sentences(translation, limit=count) if translation else []
    if not parts:
        parts = []
    if len(parts) < count:
        # 句数不足：把剩余译文都并进最后一句，避免前端错位
        parts = parts[:count - 1] + ["".join(parts[count - 1:])] if len(parts) >= count - 1 else parts + [""] * (count - len(parts))
    elif len(parts) > count:
        parts = parts[:count - 1] + ["".join(parts[count - 1:])]
    return parts


def _terms_for(sentence: str, locked_terms: list[dict]) -> list[dict]:
    lowered = sentence.lower()
    out: list[dict] = []
    seen: set[tuple] = set()
    for item in locked_terms or []:
        matched = (item.get("matched") or "").strip()
        if not matched or matched.lower() not in lowered:
            continue
        key = (item.get("term_id"), item.get("must_use"))
        if key in seen:
            continue
        seen.add(key)
        entry = {k: item[k] for k in
                 ("term_id", "zh", "en", "matched", "must_use", "lang", "local_text")
                 if item.get(k) is not None}
        out.append(entry)
        if len(out) >= MAX_TERMS_PER_SEGMENT:
            break
    return out


def _pairs_for(sentence: str, pairs: list[dict], src: str) -> list[dict]:
    scored: list[tuple[float, dict]] = []
    for pair in pairs or []:
        reference = pair.get("zh") if src == "zh" else pair.get("en")
        reference = reference or pair.get("en") or pair.get("zh") or ""
        ratio = _overlap(sentence, reference)
        if ratio >= PAIR_MIN_OVERLAP:
            scored.append((ratio, pair))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [{k: pair[k] for k in ("corpus_id", "zh", "en", "score") if k in pair}
            for _, pair in scored[:MAX_PAIRS_PER_SEGMENT]]


def build_segments(text: str, src: str, tgt: str, result: dict | None = None) -> list[dict]:
    """返回逐句对照 segments；result 为整段翻译结果（可选，避免重复调用）。"""
    sentences = split_sentences(text)
    if not sentences:
        return []

    translations: list[str] | None = None
    try:
        if not llm.is_mock():
            translations = _translate_sentences(sentences, src, tgt)
    except LLMUnavailable as exc:
        logger.warning("逐句翻译降级（%s）", exc.message)
    except Exception as exc:  # 解析/网络异常都不能影响主流程
        logger.warning("逐句翻译异常，降级为整段切分：%s", type(exc).__name__)

    if translations is None:
        base = (result or {}).get("translation") or ""
        if not base:
            try:
                base = translate(text, src, tgt).get("translation", "")
            except Exception as exc:
                logger.warning("降级整段翻译失败：%s", type(exc).__name__)
                base = ""
        translations = _split_translated(base, len(sentences))

    locked_terms = (result or {}).get("locked_terms") or []
    pairs = (result or {}).get("context_pairs") or []
    segments: list[dict] = []
    for sentence, translation in zip(sentences, translations):
        segments.append({
            "src": sentence,
            "tgt": translation,
            "terms": _terms_for(sentence, locked_terms),
            "pairs": _pairs_for(sentence, pairs, src),
        })
    return segments
