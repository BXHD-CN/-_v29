# -*- coding: utf-8 -*-
"""依赖注入：数据库会话、当前用户、权限。"""
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db
from .models import RevokedToken, User
from .security import COOKIE_NAME, decode_token


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User | None:
    if not session:
        return None
    payload = decode_token(session)
    if not payload:
        return None
    if db.get(RevokedToken, payload.get("jti", "")):
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        return None
    request.state.user = user
    return user


def require_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"
