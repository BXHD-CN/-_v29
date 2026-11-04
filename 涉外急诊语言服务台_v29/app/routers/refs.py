# -*- coding: utf-8 -*-
"""来源清单、东盟本地语对照、知识库统计。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Chunk, LocalTerm, NewsItem, PublicCorpus, PublicTerm, SourceRef

router = APIRouter(prefix="/api", tags=["refs"])
settings = get_settings()


@router.get("/sources")
def list_sources(q: str = Query(default="", max_length=100), db: Session = Depends(get_db)):
    stmt = select(SourceRef).order_by(SourceRef.code)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(SourceRef.name.like(like), SourceRef.code.like(like),
                              SourceRef.org.like(like)))
    rows = db.scalars(stmt).all()
    return {"total": len(rows),
            "items": [{"code": r.code, "name": r.name, "org": r.org, "level": r.level,
                       "url": r.url, "applies": r.applies} for r in rows]}


@router.get("/sources/{code}")
def source_detail(code: str, db: Session = Depends(get_db)):
    row = db.get(SourceRef, code.upper())
    if not row:
        raise HTTPException(404, "来源编号不存在")
    term_count = db.scalar(select(func.count()).select_from(PublicTerm)
                           .where(PublicTerm.source_code.like(f"%{row.code}%"))) or 0
    corpus_count = db.scalar(select(func.count()).select_from(PublicCorpus)
                             .where(PublicCorpus.source_code.like(f"%{row.code}%"))) or 0
    return {"code": row.code, "name": row.name, "org": row.org, "level": row.level,
            "url": row.url, "applies": row.applies,
            "term_count": term_count, "corpus_count": corpus_count}


def _source_url(db: Session, codes: str) -> tuple[str, str]:
    """把“T03、T04”这类来源代号映射到第一个可核查入口。"""
    for code in [c.strip() for c in (codes or "").replace("，", "、").split("、") if c.strip()]:
        row = db.get(SourceRef, code)
        if row and row.url:
            return row.url, row.name
    return "", ""


def source_bundle(db: Session, codes: str) -> list[dict]:
    out = []
    for code in [c.strip() for c in (codes or "").replace("，", "、").split("、") if c.strip()]:
        row = db.get(SourceRef, code)
        if row:
            out.append({"code": row.code, "name": row.name, "org": row.org,
                        "url": row.url, "level": row.level})
    return out


@router.get("/local-terms")
def list_local_terms(
    q: str = Query(default="", max_length=100),
    lang: str = Query(default="", max_length=8),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    stmt = select(LocalTerm)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(LocalTerm.zh.like(like), LocalTerm.en.like(like),
                              LocalTerm.local_text.like(like)))
    if lang:
        stmt = stmt.where(LocalTerm.lang_code == lang)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(LocalTerm.local_id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page,
            "items": [{"id": r.id, "local_id": r.local_id, "lang": r.lang, "lang_code": r.lang_code,
                       "zh": r.zh, "en": r.en, "local_text": r.local_text,
                       "romanization": r.romanization, "pron_hint": r.pron_hint,
                       "usage_note": r.usage_note, "category": r.category,
                       "domain": r.domain, "scene": r.scene,
                       "source_code": r.source_code, "audit_status": r.audit_status} for r in rows]}


@router.get("/local-terms/meta")
def local_meta(db: Session = Depends(get_db)):
    rows = db.execute(select(LocalTerm.lang, LocalTerm.lang_code, func.count())
                      .group_by(LocalTerm.lang, LocalTerm.lang_code)).all()
    return {"langs": [{"name": n, "code": c, "count": k} for n, c, k in rows],
            "total": db.scalar(select(func.count()).select_from(LocalTerm)) or 0}


@router.get("/kb/stats")
def kb_stats(db: Session = Depends(get_db)):
    docs = db.scalar(select(func.count(func.distinct(Chunk.doc_id)))) or 0
    chunks = db.scalar(select(func.count()).select_from(Chunk)) or 0
    embedded = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding != "")) or 0
    news_total = db.scalar(select(func.count()).select_from(NewsItem)) or 0
    news_zh = db.scalar(select(func.count()).select_from(NewsItem)
                        .where(NewsItem.status == "published")) or 0
    return {"docs": docs, "chunks": chunks, "embedded_chunks": embedded,
            "news_total": news_total, "news_zh": news_zh,
            "local_terms": db.scalar(select(func.count()).select_from(LocalTerm)) or 0,
            "sources": db.scalar(select(func.count()).select_from(SourceRef)) or 0,
            "providers": {"embedding": settings.embedding_provider, "llm": settings.llm_provider,
                          "mt": settings.mt_provider,
                          "news_mt": settings.news_mt_provider}}
