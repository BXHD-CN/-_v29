# -*- coding: utf-8 -*-
"""健康检查：数据库、切片、向量与模型供应商状态。"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import (Chunk, CultureExpr, EnglishVariant, NewsItem, PublicCorpus,
                      PublicTerm)

router = APIRouter(prefix="/api", tags=["health"])
settings = get_settings()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    counts = {
        "terms": db.scalar(select(func.count()).select_from(PublicTerm)) or 0,
        "corpus": db.scalar(select(func.count()).select_from(PublicCorpus)) or 0,
        "chunks": db.scalar(select(func.count()).select_from(Chunk)) or 0,
        "news": db.scalar(select(func.count()).select_from(NewsItem)) or 0,
        "culture": db.scalar(select(func.count()).select_from(CultureExpr)) or 0,
        "variants": db.scalar(select(func.count()).select_from(EnglishVariant)) or 0,
    }
    embedded = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding != "")) or 0
    return {
        "status": "ok",
        "app": settings.app_name,
        "counts": counts,
        "embedded_chunks": embedded,
        "providers": {
            "embedding": settings.embedding_provider,
            "llm": settings.llm_provider,
            "mt": settings.mt_provider,
        },
    }
