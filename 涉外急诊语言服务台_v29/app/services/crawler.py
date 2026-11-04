# -*- coding: utf-8 -*-
"""三源资讯抓取（UN News RSS / ReliefWeb API / USGS GeoJSON）。

要点：
- httpx 超时 15s、UA=AIT-CourseBot/1.0 (+教学演示)；
- 解析只用标准库（xml.etree 解析 RSS，json 解析 API / GeoJSON），不引入额外依赖；
- 单源失败只记录错误、不向上抛栈（失败跳过，计数打印）；
- 有 LLM 配置才做中文化（services.llm.chat），否则 title_zh/summary_zh 留空、status="pending"；
- 写入 NewsItem 按 url 去重：已存在则更新英文事实字段，不覆盖已有的中文译文。
"""
from __future__ import annotations

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import NewsItem

logger = logging.getLogger(__name__)

# 契约要求的 UA 为 “AIT-CourseBot/1.0 (+教学演示)”；HTTP 头只允许 ASCII，
# 因此中文说明按 UTF-8 百分号编码后发送（等价、可解码），避免 httpcore 报 ascii 编码错误。
USER_AGENT = "AIT-CourseBot/1.0 (+%E6%95%99%E5%AD%A6%E6%BC%94%E7%A4%BA)"
TIMEOUT_SECONDS = 15.0
PER_SOURCE_LIMIT = 20

SOURCE_URLS: dict[str, str] = {
    "un": "https://news.un.org/en/rss",
    "reliefweb": "https://api.reliefweb.int/v1/reports?appname=ait-course&limit=20",
    "usgs": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson",
    "un_zh": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml",
}

SOURCE_LABELS: dict[str, str] = {"un": "联合国新闻", "reliefweb": "ReliefWeb", "usgs": "USGS 地震",
                                 "un_zh": "联合国新闻（中文版）"}

# 契约给定的源 URL 可能失效/被拦截：保留为主源，失败时自动切官方 RSS 后备源（输出结构一致）
# - https://news.un.org/en/rss 现会 302 到 RSS 索引页（机器人 UA 403 / 浏览器 UA 406）
# - ReliefWeb API v1 已下线（410 Gone），v2 需申请的 appname（403）
SOURCE_FALLBACKS: dict[str, str] = {
    "un": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
    "reliefweb": "https://reliefweb.int/updates/rss.xml",
}

_TRANSLATE_SYSTEM = "你是新闻翻译，只翻译事实，不加评论、不扩写，中文简洁准确。"


# ---------------------------------------------------------------- 工具函数
def _now_iso() -> str:
    """当前 UTC 时间（ISO 8601，秒级）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_html(raw: str | None) -> str:
    """去掉脚本/样式与标签，合并空白；失败也不抛异常。"""
    text = raw or ""
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _iso_published(raw: str | None) -> str:
    """RSS 的 RFC 822 日期统一转成 ISO 8601（解析失败则原样截断），便于跨源排序。"""
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    return text[:32]


def fetch_text(url: str) -> str:
    """GET 一个 URL，返回文本；超时/HTTP 错误抛异常，由调用方按源捕获。"""
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT_SECONDS), follow_redirects=True,
                      headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


# ---------------------------------------------------------------- 各源解析
def parse_rss(raw: str, source: str, license_text: str) -> list[dict]:
    """通用 RSS 2.0 解析（xml.etree）：UN News 与 ReliefWeb RSS 后备源共用。"""
    root = ET.fromstring(raw)
    channel = root.find("channel")
    nodes = channel.findall("item") if channel is not None else root.findall(".//item")
    items: list[dict] = []
    for node in nodes:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        items.append({
            "source": source,
            "url": link,
            "title_en": _clip(title, 512),
            "summary_en": _clip(_clean_html(node.findtext("description")), 2000),
            "published_at": _iso_published(node.findtext("pubDate")),
            "license": license_text,
        })
    return items


def parse_un_rss(raw: str) -> list[dict]:
    """UN News RSS（契约主源）。"""
    return parse_rss(raw, "un", "© United Nations（联合国新闻），教学演示引用")


def parse_reliefweb_rss(raw: str) -> list[dict]:
    """ReliefWeb 官方 RSS（API v1 下线后的后备源）。"""
    return parse_rss(raw, "reliefweb", "ReliefWeb；按 ReliefWeb 使用条款引用")


def parse_reliefweb(raw: str) -> list[dict]:
    """ReliefWeb API v1（JSON）：data[].fields。"""
    payload = json.loads(raw)
    items: list[dict] = []
    for entry in payload.get("data") or []:
        fields = entry.get("fields") or {}
        title = (fields.get("title") or "").strip()
        url = (fields.get("url") or entry.get("href") or "").strip()
        if not title or not url:
            continue
        date = fields.get("date") or {}
        published = (date.get("created") or date.get("original") or "").strip()
        sources = [s.get("name", "") for s in (fields.get("source") or []) if isinstance(s, dict)]
        origin = "、".join(name for name in sources if name)
        body = _clean_html(fields.get("body") or fields.get("body-html"))
        items.append({
            "source": "reliefweb",
            "url": url,
            "title_en": _clip(title, 512),
            "summary_en": _clip(body, 2000),
            "published_at": published[:32],
            "license": _clip(f"ReliefWeb；原始来源：{origin}；按 ReliefWeb 使用条款引用" if origin
                             else "ReliefWeb；按 ReliefWeb 使用条款引用", 255),
        })
    return items


def parse_usgs(raw: str) -> list[dict]:
    """USGS 地震 GeoJSON：features[].properties。"""
    payload = json.loads(raw)
    items: list[dict] = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        url = (props.get("url") or "").strip()
        if not url:
            continue
        title = (props.get("title") or props.get("place") or "").strip()
        epoch_ms = props.get("time") or 0
        published = ""
        if epoch_ms:
            published = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        magnitude = props.get("mag")
        depth = props.get("depth")
        summary = (f"类型：{props.get('type') or ''}；"
                   f"震级：{'M' + str(magnitude) if magnitude is not None else '未知'}；"
                   f"地点：{props.get('place') or ''}；"
                   f"深度：{str(depth) + ' km' if depth is not None else '未知'}")
        items.append({
            "source": "usgs",
            "url": url,
            "title_en": _clip(title or "USGS earthquake", 512),
            "summary_en": _clip(summary, 2000),
            "published_at": published[:32],
            "license": "USGS 数据属公共领域（Public Domain），教学演示引用",
        })
    return items


def parse_un_zh_rss(raw: str) -> list[dict]:
    """联合国新闻中文版 RSS：内容本身就是中文，直接作为已中文化条目。"""
    items = parse_rss(raw, "un_zh", "© United Nations（联合国新闻中文版），教学演示引用")
    for item in items:
        item["title_zh"] = item["title_en"]
        item["summary_zh"] = item["summary_en"]
        item["native_zh"] = True
    return items


PARSERS = {"un": parse_un_rss, "reliefweb": parse_reliefweb, "usgs": parse_usgs,
           "un_zh": parse_un_zh_rss}
FALLBACK_PARSERS = {"un": parse_un_rss, "reliefweb": parse_reliefweb_rss}


# ---------------------------------------------------------------- 中文化
def llm_available() -> bool:
    """是否配置了可用的生成模型（mock 视为不可用）。"""
    settings = get_settings()
    provider = (settings.llm_provider or "mock").lower()
    if provider == "deepseek":
        return bool(settings.deepseek_api_key)
    if provider == "generic":
        return bool(settings.generic_base and settings.generic_api_key)
    return False


def _translate_with_llm(title_en: str, summary_en: str) -> tuple[str, str]:
    """调用 services.llm.chat 做中文化；失败抛异常由调用方计数。"""
    from .llm import chat  # 延迟导入：LLM 模块异常不影响抓取

    title_prompt = ("把下面的英文新闻标题翻译成中文，只翻译事实，不加评论，不超过 80 字：\n"
                    f"{_clip(title_en, 400)}")
    title_zh = chat([{"role": "system", "content": _TRANSLATE_SYSTEM},
                     {"role": "user", "content": title_prompt}],
                    temperature=0.2, max_tokens=200).strip()
    summary_zh = ""
    if summary_en:
        summary_prompt = ("把下面的英文新闻摘要翻译成中文，只翻译事实，不加评论，不超过 500 字：\n"
                          f"{_clip(summary_en, 1500)}")
        summary_zh = chat([{"role": "system", "content": _TRANSLATE_SYSTEM},
                           {"role": "user", "content": summary_prompt}],
                          temperature=0.2, max_tokens=800).strip()[:500]
    return _clip(title_zh, 512), summary_zh


_MYMEMORY_URL = "https://api.mymemory.translated.net/get"
# MyMemory 匿名额度按 IP 计（用尽后返回 429）；官方支持 de=<email> 参数按邮箱计额度，
# 演示环境用项目占位邮箱（可用环境变量 MYMEMORY_DE 覆盖），避免配额耗尽时整批中文化失败。
_MYMEMORY_DE = os.environ.get("MYMEMORY_DE", "ait-course-demo@example.com")


def _translate_with_mymemory(text: str, limit: int = 500) -> str:
    """免费公共 MT 端口（MyMemory），仅用于演示兜底；失败抛异常由调用方计数。"""
    import time

    settings = get_settings()
    if (settings.news_mt_provider or "").lower() != "mymemory":
        raise RuntimeError("mymemory disabled")
    with httpx.Client(timeout=httpx.Timeout(8.0), headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(_MYMEMORY_URL, params={"q": _clip(text, 450), "langpair": "en|zh-CN",
                                               "de": _MYMEMORY_DE})
        resp.raise_for_status()
        payload = resp.json()
    translated = ((payload.get("responseData") or {}).get("translatedText") or "").strip()
    if not translated or "MYMEMORY WARNING" in translated.upper():
        raise RuntimeError("mymemory no result")
    time.sleep(1.1)  # 公共接口限速，避免被封
    return translated[:limit]


def _translate_item(item: dict) -> bool:
    """就地写入 title_zh/summary_zh；成功返回 True。优先 LLM，无 LLM 时用免费 MT 端口。"""
    if item.get("native_zh"):
        return bool(item.get("title_zh"))
    if not item.get("title_en"):
        return False
    try:
        if llm_available():
            title_zh, summary_zh = _translate_with_llm(item["title_en"], item.get("summary_en", ""))
        else:
            title_zh = _translate_with_mymemory(item["title_en"], 160)
            summary_zh = (_translate_with_mymemory(item["summary_en"], 500)
                          if item.get("summary_en") else "")[:500]
    except Exception as exc:  # 翻译失败按 pending 处理，不影响落库
        logger.warning("中文化失败（%s）：%s", item.get("url"), exc)
        return False
    if not title_zh:
        return False
    item["title_zh"] = title_zh
    item["summary_zh"] = summary_zh
    return True


# ---------------------------------------------------------------- 落库
def upsert_items(db: Session, items: list[dict], translate: bool) -> dict:
    """按 url upsert NewsItem，返回本条源的写入/跳过统计。"""
    stats = {"fetched": len(items), "written": 0, "updated": 0, "skipped": 0,
             "translated": 0, "translate_failed": 0}
    seen: set[str] = set()
    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            stats["skipped"] += 1
            continue
        seen.add(url)
        existing = db.scalar(select(NewsItem).where(NewsItem.url == url))
        status, title_zh, summary_zh = "pending", "", ""
        if item.get("native_zh"):
            status, title_zh, summary_zh = "published", item.get("title_zh", ""), item.get("summary_zh", "")
            stats["translated"] += 1
        need_translate = (not item.get("native_zh")) and translate and not (existing and existing.title_zh)
        if need_translate:
            if _translate_item(item):
                status = "published"
                title_zh, summary_zh = item["title_zh"], item["summary_zh"]
                stats["translated"] += 1
            else:
                stats["translate_failed"] += 1
        if existing is None:
            db.add(NewsItem(
                source=item.get("source", ""), url=url,
                title_en=_clip(item.get("title_en", ""), 512),
                title_zh=title_zh,
                summary_en=_clip(item.get("summary_en", ""), 4000),
                summary_zh=summary_zh,
                published_at=(item.get("published_at") or "")[:32],
                fetched_at=_now_iso(),
                license=_clip(item.get("license", ""), 255),
                status=status,
            ))
            stats["written"] += 1
        else:
            existing.title_en = _clip(item.get("title_en", ""), 512)
            existing.summary_en = _clip(item.get("summary_en", ""), 4000)
            existing.published_at = (item.get("published_at") or "")[:32]
            existing.fetched_at = _now_iso()
            existing.license = _clip(item.get("license", ""), 255)
            if status == "published" and not existing.title_zh:
                existing.title_zh = title_zh
                existing.summary_zh = summary_zh
                existing.status = "published"
            stats["updated"] += 1
    db.commit()
    return stats


def crawl(db: Session, sources: Iterable[str] | None = None, limit: int = PER_SOURCE_LIMIT,
          translate: bool | None = None) -> dict[str, dict]:
    """抓取指定来源并落库。translate=None 表示有 LLM 配置就中文化。"""
    names = list(sources) if sources else list(SOURCE_URLS)
    settings = get_settings()
    mt_fallback = (settings.news_mt_provider or "").lower() == "mymemory"
    if translate is None:
        translate = llm_available() or mt_fallback
    translate = bool(translate and (llm_available() or mt_fallback))
    per_source = max(1, min(int(limit or PER_SOURCE_LIMIT), 60))
    result: dict[str, dict] = {}
    for name in names:
        stats = {"fetched": 0, "written": 0, "updated": 0, "skipped": 0,
                 "translated": 0, "translate_failed": 0, "error": "", "note": ""}
        url = SOURCE_URLS.get(name)
        if not url:
            stats["error"] = f"未知来源：{name}"
            result[name] = stats
            continue
        items: list[dict] = []
        try:
            items = PARSERS[name](fetch_text(url))[:per_source]
        except Exception as primary_exc:  # 主源失败：尝试官方 RSS 后备源，仍失败则记错跳过
            logger.warning("主源 %s 抓取失败（%s: %s），尝试后备源", name,
                           type(primary_exc).__name__, primary_exc)
            fallback_url = SOURCE_FALLBACKS.get(name)
            if not fallback_url:
                db.rollback()
                stats["error"] = f"{type(primary_exc).__name__}: {primary_exc}"
                result[name] = stats
                continue
            try:
                items = FALLBACK_PARSERS[name](fetch_text(fallback_url))[:per_source]
                stats["note"] = f"主源失败（{type(primary_exc).__name__}），已改用后备源 {fallback_url}"
            except Exception as fallback_exc:
                db.rollback()
                stats["error"] = (f"主源失败（{type(primary_exc).__name__}: {primary_exc}）；"
                                  f"后备源失败（{type(fallback_exc).__name__}: {fallback_exc}）")
                logger.warning("抓取来源 %s 主备源均失败，已跳过：%s", name, fallback_exc)
                result[name] = stats
                continue
        try:
            stats.update(upsert_items(db, items, translate))
        except Exception as exc:  # 落库失败也不抛栈
            db.rollback()
            stats["error"] = f"落库失败：{type(exc).__name__}: {exc}"
            logger.warning("来源 %s 落库失败，已跳过：%s", name, exc)
        result[name] = stats
    return result
