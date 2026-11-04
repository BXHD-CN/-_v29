# -*- coding: utf-8 -*-
"""公共术语库（只读，4,154 条）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PublicCorpus, PublicTerm
from .refs import source_bundle

router = APIRouter(prefix="/api/terms", tags=["terms"])


@router.get("")
def list_terms(
    q: str = Query(default="", max_length=100),
    lang: str = Query(default="", max_length=16),
    domain: str = Query(default="", max_length=64),
    status: str = Query(default="", max_length=16),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    stmt = select(PublicTerm)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(PublicTerm.zh.like(like), PublicTerm.en.like(like),
                              PublicTerm.abbreviation.like(like)))
    if lang:
        stmt = stmt.where(PublicTerm.lang_pair == lang)
    if domain:
        stmt = stmt.where(PublicTerm.domain == domain)
    if status:
        stmt = stmt.where(PublicTerm.audit_status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(PublicTerm.zh).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"id": r.id, "term_id": r.term_id, "zh": r.zh, "en": r.en,
                       "lang_pair": r.lang_pair, "domain": r.domain, "subdomain": r.subdomain,
                       "abbreviation": r.abbreviation, "source_code": r.source_code,
                       "audit_status": r.audit_status} for r in rows]}


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    domains = db.execute(select(PublicTerm.domain, func.count()).group_by(PublicTerm.domain)
                         .order_by(func.count().desc()).limit(40)).all()
    langs = db.execute(select(PublicTerm.lang_pair, func.count()).group_by(PublicTerm.lang_pair)).all()
    statuses = db.execute(select(PublicTerm.audit_status, func.count()).group_by(PublicTerm.audit_status)).all()
    return {"domains": [{"name": d, "count": c} for d, c in domains],
            "langs": [{"name": l, "count": c} for l, c in langs],
            "statuses": [{"name": s, "count": c} for s, c in statuses]}


@router.get("/{term_pk}")
def detail(term_pk: int, db: Session = Depends(get_db)):
    r = db.get(PublicTerm, term_pk)
    if not r:
        raise HTTPException(404, "术语不存在")
    sources = source_bundle(db, r.source_code)
    url = r.source_url or (sources[0]["url"] if sources else "")
    return {"id": r.id, "term_id": r.term_id, "zh": r.zh, "en": r.en, "lang_pair": r.lang_pair,
            "domain": r.domain, "subdomain": r.subdomain, "abbreviation": r.abbreviation,
            "definition_zh": r.definition_zh, "definition_en": r.definition_en,
            "source_code": r.source_code, "source_file": r.source_file,
            "source_url": url, "sources": sources,
            "audit_status": r.audit_status, "samples": r.samples}

@router.get("/{term_pk}/corpus")
def term_corpus(term_pk: int, limit: int = 20, db: Session = Depends(get_db)):
    """术语关联语料：公共语料按 term_id，返回原文/译文/来源/语种对/审核状态。"""
    row = db.get(PublicTerm, term_pk)
    if not row:
        raise HTTPException(404, "术语不存在")
    rows = db.scalars(select(PublicCorpus).where(PublicCorpus.term_id == row.term_id)
                       .order_by(PublicCorpus.id).limit(min(limit, 50))).all()
    return {"term_id": row.term_id, "zh": row.zh, "en": row.en, "total": len(rows),
            "items": [{"id": c.id, "corpus_id": c.corpus_id, "zh": c.zh, "en": c.en,
                       "lang_pair": c.lang_pair, "register": c.register,
                       "source_code": c.source_code, "audit_status": c.audit_status} for c in rows]}
