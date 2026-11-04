# -*- coding: utf-8 -*-
"""管理后台接口（仅 admin 角色）：统计、用户管理、审计日志。"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import log
from ..db import get_db
from ..deps import client_ip, require_admin
from ..models import (AuditLog, Chunk, NewsItem, User, UserCorpus, UserTerm)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserPatch(BaseModel):
    """管理员可改的账号字段：角色与启用状态。"""
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None


def _count(db: Session, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    if conditions:
        stmt = stmt.where(*conditions)
    return db.scalar(stmt) or 0


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _user_out(user: User, terms: int, corpus: int) -> dict:
    """用户输出：绝不包含 password_hash。"""
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": _iso(user.created_at),
        "last_login_at": _iso(user.last_login_at),
        "terms": terms,
        "corpus": corpus,
    }


@router.get("/stats")
def stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """站点概览：用户、私有库、切片、向量化、资讯、近 7 天登录。"""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    return {
        "users": _count(db, User),
        "active_users": _count(db, User, User.is_active.is_(True)),
        "user_terms": _count(db, UserTerm),
        "user_corpus": _count(db, UserCorpus),
        "chunks": _count(db, Chunk),
        "embedded_chunks": _count(db, Chunk, Chunk.embedding != ""),
        "news": _count(db, NewsItem),
        "logins_7d": _count(db, AuditLog, AuditLog.action == "login", AuditLog.at >= cutoff),
        "new_users_7d": _count(db, User, User.created_at >= cutoff),
    }


@router.get("/users")
def list_users(
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """分页列出用户（不含密码），附私有术语/语料条数。"""
    total = _count(db, User)
    rows = db.scalars(select(User).order_by(User.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    term_counts = dict(db.execute(select(UserTerm.user_id, func.count())
                                  .group_by(UserTerm.user_id)).all())
    corpus_counts = dict(db.execute(select(UserCorpus.user_id, func.count())
                                    .group_by(UserCorpus.user_id)).all())
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_user_out(user, term_counts.get(user.id, 0), corpus_counts.get(user.id, 0))
                  for user in rows],
    }


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserPatch, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """修改用户角色或启用状态；不能把当前登录的管理员降级/停用。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "没有可更新的字段")
    if user.id == admin.id:
        if payload.get("role", user.role) != "admin" or payload.get("is_active", True) is False:
            raise HTTPException(400, "不能降级或停用当前登录的管理员账号")
    changed: list[str] = []
    if "role" in payload and payload["role"] is not None:
        user.role = payload["role"]
        changed.append(f"role={payload['role']}")
    if "is_active" in payload and payload["is_active"] is not None:
        user.is_active = bool(payload["is_active"])
        changed.append(f"is_active={user.is_active}")
    db.commit()
    db.refresh(user)
    log(db, admin.id, "admin_user_update", "user", user.id, client_ip(request),
        detail=",".join(changed))
    terms = _count(db, UserTerm, UserTerm.user_id == user.id)
    corpus = _count(db, UserCorpus, UserCorpus.user_id == user.id)
    return _user_out(user, terms, corpus)


@router.get("/audit")
def list_audit(limit: int = Query(default=100, ge=1, le=500),
               admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """最近的审计日志（写操作留痕），带用户名便于排查。"""
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    user_ids = {row.user_id for row in rows if row.user_id}
    usernames = {user.id: user.username for user in
                 db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    return {"total": _count(db, AuditLog),
            "items": [{"id": row.id, "user_id": row.user_id,
                       "username": usernames.get(row.user_id, ""),
                       "action": row.action, "object_type": row.object_type,
                       "object_id": row.object_id, "ip": row.ip,
                       "detail": row.detail, "at": _iso(row.at)} for row in rows]}
