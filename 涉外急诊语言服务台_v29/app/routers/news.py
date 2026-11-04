# -*- coding: utf-8 -*-
"""资讯聚合接口（公开只读）：列表 + 详情，数据由 scripts/crawl.py 抓取写入。"""
from datetime import timezone
from email.utils import parsedate_to_datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..i18n import lang_of
from ..models import NewsItem

router = APIRouter(prefix="/api", tags=["news"])


def _published_at(raw: str) -> str:
    """历史数据里有 RFC 822 日期，统一输出 ISO 8601，前端排序/展示一致。"""
    text = (raw or "").strip()
    if not text or text[:2].isdigit():
        return text
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    return text


SOURCE_LABELS = {"un": "联合国新闻", "reliefweb": "ReliefWeb",
                "usgs": "USGS 地震", "un_zh": "联合国新闻（中文版）"}
SOURCE_LABELS_EN = {"un": "UN News", "reliefweb": "ReliefWeb",
                    "usgs": "USGS Earthquakes", "un_zh": "UN News (Chinese)"}
METHOD_EN = {"中文版源": "Chinese-language source",
             "机器翻译": "Machine translation",
             "原文待译": "Awaiting translation"}


def _translation_method(item: NewsItem) -> str:
    """中文化方式：中文版源 / 机器翻译 / 原文待译（稳定的机器值，不随语言变化）。"""
    if item.source == "un_zh":
        return "中文版源"
    return "机器翻译" if (item.title_zh or "").strip() else "原文待译"


def _brief(item: NewsItem, lang: str = "zh") -> dict:
    """列表项：中英字段都返回；英文模式额外给出英文优先的展示字段与英文标签。

    source / status / translated_by_zh 始终是稳定机器值，供前端做样式与筛选，
    避免把「语言」混进数据主键。
    """
    en = lang == "en"
    method = _translation_method(item)
    return {
        "id": item.id,
        "source": item.source,
        "source_label": (SOURCE_LABELS_EN if en else SOURCE_LABELS).get(item.source, item.source),
        "title_zh": item.title_zh,
        "title_en": item.title_en,
        # API 层英文优先：英文标题为主显示，中文标题退为副显示
        "title": (item.title_en or item.title_zh) if en else (item.title_zh or item.title_en),
        "url": item.url,
        "published_at": _published_at(item.published_at),
        "fetched_at": item.fetched_at,
        "translated_by": METHOD_EN.get(method, method) if en else method,
        "translated_by_zh": method,
        "status": item.status,
    }


@router.get("/news")
def list_news(
    request: Request,
    source: str = Query(default="", max_length=32),
    status: str = Query(default="published", pattern="^(published|pending|all)$"),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """分页列出资讯：默认只给已中文化条目，保证页面可全中文浏览。"""
    stmt = select(NewsItem)
    if source:
        stmt = stmt.where(NewsItem.source == source)
    if status != "all":
        stmt = stmt.where(NewsItem.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    lang = lang_of(request)
    return {"total": total, "page": page, "page_size": page_size, "status": status,
            "items": [_brief(item, lang) for item in rows]}


@router.get("/news/{news_id}")
def news_detail(news_id: int, request: Request, db: Session = Depends(get_db)):
    """资讯详情：含中英文摘要、许可与抓取时间；英文模式英文摘要优先。"""
    item = db.get(NewsItem, news_id)
    if item is None:
        raise HTTPException(404, "资讯不存在")
    lang = lang_of(request)
    return {
        **_brief(item, lang),
        "summary_zh": item.summary_zh,
        "summary_en": item.summary_en,
        "summary": (item.summary_en or item.summary_zh) if lang == "en"
                   else (item.summary_zh or item.summary_en),
        "license": item.license,
        "fetched_at": item.fetched_at,
        "access_date": (item.fetched_at or "")[:10],
    }
