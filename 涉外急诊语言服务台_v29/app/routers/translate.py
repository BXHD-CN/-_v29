# -*- coding: utf-8 -*-
"""翻译接口：POST /api/translate（术语锁定 + 语料 + MT + 译后校验）、
GET /api/translate/languages。带进程内滑动窗口限流（10 次/分钟/用户）。
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import client_ip, get_optional_user
from ..models import TranslationHistory, User
from ..services import sentence_align, translate_service

settings = get_settings()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["translate"])

RATE_LIMIT = 10          # 每个用户每分钟最多 10 次
RATE_WINDOW = 60.0


class SlidingWindowLimiter:
    """进程内滑动窗口限流；生产由 Nginx limit_req 承担主要职责。"""

    def __init__(self, limit: int, window: float) -> None:
        self._limit = limit
        self._window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit_or_blocked(self, key: str) -> bool:
        """未超限则记一次并返回 False；超限返回 True。"""
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self._window]
            if len(hits) >= self._limit:
                self._hits[key] = hits
                return True
            hits.append(now)
            self._hits[key] = hits
            return False


limiter = SlidingWindowLimiter(RATE_LIMIT, RATE_WINDOW)


class TranslateIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    src: str = Field(default="zh", max_length=8)
    tgt: str = Field(default="en", max_length=8)


def _save_history(db: Session, user: User | None, data: TranslateIn, result: dict) -> int | None:
    """保存翻译历史；匿名访客不写个人历史，失败也不影响本次翻译结果。"""
    if not user:
        return None
    try:
        item = TranslationHistory(user_id=user.id, src=result.get("src", data.src),
                                  tgt=result.get("tgt", data.tgt),
                                  source_text=data.text,
                                  translation=result.get("translation", ""),
                                  chars=len(data.text),
                                  provider=result.get("provider", ""))
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id
    except Exception as exc:  # 历史是附属功能，不能因它 500
        db.rollback()
        logger.warning("保存翻译历史失败：%s", type(exc).__name__)
        return None


@router.post("/translate")
def translate(data: TranslateIn, request: Request,
              user: User | None = Depends(get_optional_user),
              db: Session = Depends(get_db)):
    # 注册前置门禁由 shield.py 保证：能调用本接口的用户均已登录。
    # 仍保留 IP 限流兜底（会话异常时按来源限流），且不写匿名个人翻译历史。
    actor = str(user.id) if user else client_ip(request)
    if limiter.hit_or_blocked(f"translate:{actor}"):
        raise HTTPException(429, "翻译请求过于频繁（每分钟最多 10 次），请稍后再试")
    try:
        result = translate_service.translate(data.text, data.src, data.tgt)
    except (translate_service.UnsupportedLanguage, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

    # 逐句对照（失败自动降级为整段译文按句切分，不抛异常）
    result["segments"] = sentence_align.build_segments(data.text, data.src, data.tgt,
                                                       result=result)
    result["history_id"] = _save_history(db, user, data, result)
    result["request_id"] = getattr(request.state, "request_id", "")
    logger.info("translate user=%s src=%s tgt=%s provider=%s degraded=%s segments=%s",
                actor, result["src"], result["tgt"], result["provider"],
                result["degraded"], len(result["segments"]))
    return result


@router.get("/translate/languages")
def languages():
    return {
        "languages": translate_service.LANGS,
        "providers": translate_service.providers(),
    }
