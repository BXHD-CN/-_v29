# -*- coding: utf-8 -*-
"""个人中心：私有术语库 / 私有语料库（只在自己账户内可见、可增删改查、可导入导出）。

设计要点：
- 公共库（public_terms / public_corpus）只读，任何人可查；
- 私有库（user_terms / user_corpus）按 user_id 隔离，接口永远带 user_id 过滤，
  别人的数据一律 404，不泄露存在性；
- 支持"从公共库复制到我的库"，复制后是独立副本，可自由编辑，不影响公共库。
"""
import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import log
from ..db import get_db
from ..deps import client_ip, require_user
from ..models import (AuditLog, Chunk, PublicCorpus, PublicTerm, User, UserCorpus,
                      UserTerm)

router = APIRouter(prefix="/api/me", tags=["me"])


class TermIn(BaseModel):
    zh: str = Field(min_length=1, max_length=255)
    en: str = Field(default="", max_length=255)
    lang_pair: str = Field(default="zh-en", max_length=16)
    domain: str = Field(default="", max_length=64)
    definition: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=1000)
    source_code: str = Field(default="", max_length=64)
    source_url: str = Field(default="", max_length=512)


class TermPatch(BaseModel):
    zh: str | None = Field(default=None, min_length=1, max_length=255)
    en: str | None = Field(default=None, max_length=255)
    lang_pair: str | None = Field(default=None, max_length=16)
    domain: str | None = Field(default=None, max_length=64)
    definition: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=1000)
    source_code: str | None = Field(default=None, max_length=64)
    source_url: str | None = Field(default=None, max_length=512)


class CorpusIn(BaseModel):
    zh: str = Field(min_length=1, max_length=2000)
    en: str = Field(min_length=1, max_length=2000)
    lang_pair: str = Field(default="zh-en", max_length=16)
    register_kind: Literal["", "书面", "口语"] = ""
    term_id: str = Field(default="", max_length=32)
    note: str = Field(default="", max_length=1000)
    source_code: str = Field(default="", max_length=64)
    source_url: str = Field(default="", max_length=512)


class CorpusPatch(BaseModel):
    zh: str | None = Field(default=None, min_length=1, max_length=2000)
    en: str | None = Field(default=None, min_length=1, max_length=2000)
    lang_pair: str | None = Field(default=None, max_length=16)
    register_kind: Literal["", "书面", "口语"] | None = None
    term_id: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=1000)
    source_code: str | None = Field(default=None, max_length=64)
    source_url: str | None = Field(default=None, max_length=512)


def _term_out(t: UserTerm) -> dict:
    return {"id": t.id, "zh": t.zh, "en": t.en, "lang_pair": t.lang_pair, "domain": t.domain,
            "definition": t.definition, "note": t.note, "source_code": t.source_code,
            "source_url": t.source_url, "source_public_id": t.source_public_id,
            "updated_at": t.updated_at.isoformat() if t.updated_at else ""}


def _corpus_out(c: UserCorpus) -> dict:
    return {"id": c.id, "zh": c.zh, "en": c.en, "lang_pair": c.lang_pair, "register": c.register,
            "term_id": c.term_id, "note": c.note, "source_code": c.source_code,
            "source_url": c.source_url, "source_public_id": c.source_public_id,
            "updated_at": c.updated_at.isoformat() if c.updated_at else ""}


def _own_term(db: Session, user: User, term_pk: int) -> UserTerm:
    t = db.get(UserTerm, term_pk)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "条目不存在")
    return t


def _own_corpus(db: Session, user: User, corpus_pk: int) -> UserCorpus:
    c = db.get(UserCorpus, corpus_pk)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "条目不存在")
    return c


@router.get("/overview")
def overview(user: User = Depends(require_user), db: Session = Depends(get_db)):
    my_terms = db.scalar(select(func.count()).select_from(UserTerm).where(UserTerm.user_id == user.id)) or 0
    my_corpus = db.scalar(select(func.count()).select_from(UserCorpus).where(UserCorpus.user_id == user.id)) or 0
    recent = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id)
                        .order_by(AuditLog.id.desc()).limit(10)).all()
    return {"user": {"id": user.id, "username": user.username, "display_name": user.display_name,
                     "email": user.email, "role": user.role},
            "my_terms": my_terms, "my_corpus": my_corpus,
            "chunks": db.scalar(select(func.count()).select_from(Chunk)) or 0,
            "recent": [{"action": r.action, "object_type": r.object_type,
                        "object_id": r.object_id, "at": r.at.isoformat()} for r in recent]}


# ---------------- 私有术语 ----------------
@router.get("/terms")
def list_my_terms(q: str = Query(default="", max_length=100), page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=20, ge=1, le=100),
                  user: User = Depends(require_user), db: Session = Depends(get_db)):
    stmt = select(UserTerm).where(UserTerm.user_id == user.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(UserTerm.zh.like(like), UserTerm.en.like(like), UserTerm.domain.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(UserTerm.updated_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "items": [_term_out(t) for t in rows]}


@router.post("/terms", status_code=201)
def create_term(data: TermIn, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    dup = db.scalar(select(UserTerm).where(UserTerm.user_id == user.id,
                                          UserTerm.zh == data.zh, UserTerm.en == data.en))
    if dup:
        raise HTTPException(409, "你的私有库里已有同名词条")
    t = UserTerm(user_id=user.id, **data.model_dump())
    db.add(t)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "你的私有库里已有同名词条")
    db.refresh(t)
    log(db, user.id, "term_create", "user_term", t.id, client_ip(request))
    return _term_out(t)


@router.put("/terms/{term_pk}")
def update_term(term_pk: int, data: TermPatch, request: Request, user: User = Depends(require_user),
                db: Session = Depends(get_db)):
    t = _own_term(db, user, term_pk)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(t, k, v)
    db.commit()
    db.refresh(t)
    log(db, user.id, "term_update", "user_term", t.id, client_ip(request))
    return _term_out(t)


@router.delete("/terms/{term_pk}")
def delete_term(term_pk: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    t = _own_term(db, user, term_pk)
    db.delete(t)
    db.commit()
    log(db, user.id, "term_delete", "user_term", term_pk, client_ip(request))
    return {"ok": True}


@router.post("/terms/import/{public_id}", status_code=201)
def import_public_term(public_id: int, request: Request, user: User = Depends(require_user),
                       db: Session = Depends(get_db)):
    src = db.get(PublicTerm, public_id)
    if not src:
        raise HTTPException(404, "公共术语不存在")
    dup = db.scalar(select(UserTerm).where(UserTerm.user_id == user.id,
                                          UserTerm.zh == src.zh, UserTerm.en == src.en))
    if dup:
        raise HTTPException(409, "该术语已在你的库中")
    t = UserTerm(user_id=user.id, zh=src.zh, en=src.en, lang_pair=src.lang_pair,
                 domain=src.domain, definition=src.definition_zh,
                 source_code=src.source_code, source_url=src.source_url,
                 source_public_id=src.id)
    db.add(t)
    db.commit()
    db.refresh(t)
    log(db, user.id, "term_import", "public_term", public_id, client_ip(request))
    return _term_out(t)


@router.get("/terms/export.csv")
def export_terms(user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserTerm).where(UserTerm.user_id == user.id)).all()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["zh", "en", "lang_pair", "domain", "definition", "note", "source_code", "source_url"])
    for t in rows:
        w.writerow([t.zh, t.en, t.lang_pair, t.domain, t.definition, t.note, t.source_code, t.source_url])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=my_terms.csv"})


# ---------------- 私有语料 ----------------
@router.get("/corpus")
def list_my_corpus(q: str = Query(default="", max_length=200), page: int = Query(default=1, ge=1),
                   page_size: int = Query(default=20, ge=1, le=100),
                   user: User = Depends(require_user), db: Session = Depends(get_db)):
    stmt = select(UserCorpus).where(UserCorpus.user_id == user.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(UserCorpus.zh.like(like), UserCorpus.en.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(UserCorpus.updated_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "items": [_corpus_out(c) for c in rows]}


@router.post("/corpus", status_code=201)
def create_corpus(data: CorpusIn, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    payload = data.model_dump()
    payload["register"] = payload.pop("register_kind", "")
    dup = db.scalar(select(UserCorpus).where(UserCorpus.user_id == user.id,
                                            UserCorpus.zh == data.zh, UserCorpus.en == data.en))
    if dup:
        raise HTTPException(409, "你的私有库里已有同一句对")
    c = UserCorpus(user_id=user.id, **payload)
    db.add(c)
    db.commit()
    db.refresh(c)
    log(db, user.id, "corpus_create", "user_corpus", c.id, client_ip(request))
    return _corpus_out(c)


@router.put("/corpus/{corpus_pk}")
def update_corpus(corpus_pk: int, data: CorpusPatch, request: Request, user: User = Depends(require_user),
                  db: Session = Depends(get_db)):
    c = _own_corpus(db, user, corpus_pk)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        if k == "register_kind":
            k = "register"
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    log(db, user.id, "corpus_update", "user_corpus", c.id, client_ip(request))
    return _corpus_out(c)


@router.delete("/corpus/{corpus_pk}")
def delete_corpus(corpus_pk: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    c = _own_corpus(db, user, corpus_pk)
    db.delete(c)
    db.commit()
    log(db, user.id, "corpus_delete", "user_corpus", corpus_pk, client_ip(request))
    return {"ok": True}


@router.post("/corpus/import/{public_id}", status_code=201)
def import_public_corpus(public_id: int, request: Request, user: User = Depends(require_user),
                         db: Session = Depends(get_db)):
    src = db.get(PublicCorpus, public_id)
    if not src:
        raise HTTPException(404, "公共语料不存在")
    dup = db.scalar(select(UserCorpus).where(UserCorpus.user_id == user.id,
                                            UserCorpus.zh == src.zh, UserCorpus.en == src.en))
    if dup:
        raise HTTPException(409, "该句对已在你的库中")
    c = UserCorpus(user_id=user.id, zh=src.zh, en=src.en, lang_pair=src.lang_pair,
                   register=src.register, term_id=src.term_id, source_code=src.source_code,
                   source_url=src.source_url, source_public_id=src.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    log(db, user.id, "corpus_import", "public_corpus", public_id, client_ip(request))
    return _corpus_out(c)


@router.get("/corpus/export.csv")
def export_corpus(user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserCorpus).where(UserCorpus.user_id == user.id)).all()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["zh", "en", "lang_pair", "register", "term_id", "note", "source_code", "source_url"])
    for c in rows:
        w.writerow([c.zh, c.en, c.lang_pair, c.register, c.term_id, c.note, c.source_code, c.source_url])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=my_corpus.csv"})


@router.get("/audit")
def my_audit(limit: int = Query(default=20, ge=1, le=100), user: User = Depends(require_user),
             db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id)
                      .order_by(AuditLog.id.desc()).limit(limit)).all()
    return {"items": [{"action": r.action, "object_type": r.object_type, "object_id": r.object_id,
                       "ip": r.ip, "at": r.at.isoformat()} for r in rows]}
