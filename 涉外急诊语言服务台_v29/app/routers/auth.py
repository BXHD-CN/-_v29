# -*- coding: utf-8 -*-
"""注册、登录、登出、当前用户。Cookie 只放 HttpOnly JWT；CSRF 走双提交。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import log
from ..config import get_settings
from ..db import get_db
from ..deps import client_ip, get_optional_user, require_user
from ..models import RevokedToken, User
from ..security import (COOKIE_NAME, CSRF_COOKIE, create_access_token, decode_token,
                        hash_password, login_limiter, new_csrf_token, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

PUBLIC_ROLES = {"user"}


class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(default="", max_length=32)


class LoginIn(BaseModel):
    account: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=72)


def _set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=settings.cookie_secure,
                        samesite=settings.cookie_samesite, max_age=settings.access_token_minutes * 60,
                        path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=settings.cookie_secure,
                        samesite=settings.cookie_samesite, max_age=settings.access_token_minutes * 60,
                        path="/")


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def user_public(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }


@router.post("/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(or_(User.email == data.email, User.username == data.username)))
    if exists:
        raise HTTPException(409, "邮箱或用户名已被占用")
    user = User(email=data.email, username=data.username,
                password_hash=hash_password(data.password),
                display_name=data.display_name or data.username, role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    log(db, user.id, "register", "user", user.id)
    return {"user": user_public(user)}


@router.post("/login")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    key = f"{ip}:{data.account.lower()}"
    if login_limiter.blocked(key):
        raise HTTPException(429, "登录失败次数过多，请 5 分钟后再试")
    user = db.scalar(select(User).where(or_(User.email == data.account, User.username == data.account)))
    if not user or not verify_password(data.password, user.password_hash):
        login_limiter.hit(key)
        log(db, getattr(user, "id", None), "login_failed", "user", data.account, ip)
        raise HTTPException(401, "账号或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已停用")
    login_limiter.reset(key)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token, jti = create_access_token(user.id, user.role)
    csrf = new_csrf_token()
    _set_auth_cookies(response, token, csrf)
    log(db, user.id, "login", "user", user.id, ip)
    return {"user": user_public(user), "csrf_token": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           user: User | None = Depends(get_optional_user)):
    token = request.cookies.get(COOKIE_NAME, "")
    payload = decode_token(token) if token else None
    if payload:
        db.add(RevokedToken(jti=payload.get("jti", ""),
                            expires_at=datetime.now(timezone.utc)))
        db.commit()
    _clear_cookies(response)
    if user:
        log(db, user.id, "logout", "user", user.id, client_ip(request))
    return {"ok": True}


@router.get("/me")
def me(user: User | None = Depends(get_optional_user)):
    # 注册前置门禁：本接口是白名单内的探测端点，匿名访客返回 user=null 而不是 401；
    # 前端据此判断是否需要回注册入口，不产生控制台错误。其余功能由 shield.py 硬性拦截。
    return {"user": user_public(user) if user else None, "csrf_token": ""}
