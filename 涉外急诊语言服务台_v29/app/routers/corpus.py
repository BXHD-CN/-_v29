# -*- coding: utf-8 -*-
"""公共平行语料库（只读，8,308 句对）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PublicCorpus
from .refs import source_bundle

router = APIRouter(prefix="/api/corpus", tags=["corpus"])


@router.get("")
def list_corpus(
    q: str = Query(default="", max_length=200),
    field: str = Query(default="all", pattern="^(all|zh|en)$"),
    lang: str = Query(default="", max_length=16),
    term_id: str = Query(default="", max_length=32),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    stmt = select(PublicCorpus)
    if q:
        like = f"%{q}%"
        if field == "zh":
            stmt = stmt.where(PublicCorpus.zh.like(like))
        elif field == "en":
            stmt = stmt.where(PublicCorpus.en.like(like))
        else:
            stmt = stmt.where(or_(PublicCorpus.zh.like(like), PublicCorpus.en.like(like)))
    if lang:
        stmt = stmt.where(PublicCorpus.lang_pair == lang)
    if term_id:
        stmt = stmt.where(PublicCorpus.term_id == term_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(PublicCorpus.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"id": r.id, "corpus_id": r.corpus_id, "term_id": r.term_id, "zh": r.zh,
                       "en": r.en, "lang_pair": r.lang_pair, "register": r.register,
                       "domain": r.domain, "source_code": r.source_code,
                       "source_file": r.source_file, "source_url": r.source_url,
                       "audit_status": r.audit_status} for r in rows]}


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    langs = db.execute(select(PublicCorpus.lang_pair, func.count()).group_by(PublicCorpus.lang_pair)).all()
    domains = db.execute(select(PublicCorpus.domain, func.count()).group_by(PublicCorpus.domain)
                         .order_by(func.count().desc()).limit(40)).all()
    total = db.scalar(select(func.count()).select_from(PublicCorpus)) or 0
    return {"total": total,
            "langs": [{"name": l, "count": c} for l, c in langs],
            "domains": [{"name": d, "count": c} for d, c in domains]}


@router.get("/{corpus_pk}")
def detail(corpus_pk: int, db: Session = Depends(get_db)):
    r = db.get(PublicCorpus, corpus_pk)
    if not r:
        raise HTTPException(404, "语料不存在")
    sources = source_bundle(db, r.source_code)
    url = r.source_url or (sources[0]["url"] if sources else "")
    return {"id": r.id, "corpus_id": r.corpus_id, "term_id": r.term_id, "zh": r.zh, "en": r.en,
            "lang_pair": r.lang_pair, "register": r.register, "domain": r.domain,
            "source_code": r.source_code, "source_file": r.source_file,
            "source_url": url, "sources": sources, "audit_status": r.audit_status}
