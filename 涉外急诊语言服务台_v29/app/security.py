# -*- coding: utf-8 -*-
"""密码、JWT、CSRF 与登录限流。"""
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

settings = get_settings()

COOKIE_NAME = "session"
CSRF_COOKIE = "csrf_token"
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, str]:
    """返回 (token, jti)。"""
    jti = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), jti


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


class LoginLimiter:
    """进程内兜底限流；生产由 Nginx limit_req 承担主要职责。"""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def blocked(self, key: str) -> bool:
        now = time.time()
        window = settings.login_window_seconds
        hits = [t for t in self._hits.get(key, []) if now - t < window]
        self._hits[key] = hits
        return len(hits) >= settings.login_max_attempts

    def hit(self, key: str) -> None:
        self._hits.setdefault(key, []).append(time.time())

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


login_limiter = LoginLimiter()
