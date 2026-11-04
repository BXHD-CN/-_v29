# -*- coding: utf-8 -*-
"""公开概览：未登录也能看的聚合数据（不含正文内容）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import (Chunk, CultureExpr, EnglishVariant, LocalTerm, NewsItem, PublicCorpus,
                      PublicTerm, SourceRef)

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    settings = get_settings()
    counts = {
        "terms": db.scalar(select(func.count()).select_from(PublicTerm)) or 0,
        "corpus": db.scalar(select(func.count()).select_from(PublicCorpus)) or 0,
        "local_terms": db.scalar(select(func.count()).select_from(LocalTerm)) or 0,
        "culture": db.scalar(select(func.count()).select_from(CultureExpr)) or 0,
        "variants": db.scalar(select(func.count()).select_from(EnglishVariant)) or 0,
        "sources": db.scalar(select(func.count()).select_from(SourceRef)) or 0,
        "chunks": db.scalar(select(func.count()).select_from(Chunk)) or 0,
        "embedded_chunks": db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding != "")) or 0,
        "news": db.scalar(select(func.count()).select_from(NewsItem).where(NewsItem.status == "published")) or 0,
    }
    domains = db.execute(select(PublicTerm.domain, func.count()).group_by(PublicTerm.domain)
                         .order_by(func.count().desc()).limit(10)).all()
    langs = db.execute(select(LocalTerm.lang_code, func.count()).group_by(LocalTerm.lang_code)).all()
    latest = db.scalars(select(NewsItem).where(NewsItem.status == "published")
                        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc()).limit(3)).all()
    return {
        "counts": counts,
        "domains": [{"name": d or "未分类", "count": c} for d, c in domains],
        "langs": [{"code": l, "count": c} for l, c in langs],
        # 同时返回中英标题：首页英文模式以 title_en 为主显示，中文标题作副行。
        # 保留 title 字段兼容旧前端；数据库内容一律不改写。
        "latest": [{"id": n.id, "title": n.title_zh or n.title_en,
                    "title_zh": n.title_zh, "title_en": n.title_en, "source": n.source,
                    "published_at": n.published_at} for n in latest],
        "providers": {"embedding": settings.embedding_provider,
                      "llm": settings.llm_provider, "mt": settings.mt_provider},
    }
