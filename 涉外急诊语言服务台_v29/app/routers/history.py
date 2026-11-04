# -*- coding: utf-8 -*-
"""翻译历史：GET /api/me/translations、DELETE /api/me/translations/{id}。

历史仅本人可见；删除只允许删自己的记录（他人记录一律 404，不泄露存在性）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import log
from ..db import get_db
from ..deps import client_ip, require_user
from ..models import TranslationHistory, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/me", tags=["history"])


def _out(item: TranslationHistory) -> dict:
    return {
        "id": item.id,
        "src": item.src,
        "tgt": item.tgt,
        "source_text": item.source_text,
        "translation": item.translation,
        "chars": item.chars,
        "provider": item.provider,
        "created_at": item.created_at.isoformat() if item.created_at else "",
    }


@router.get("/translations")
def list_translations(limit: int = Query(default=20, ge=1, le=100),
                      user: User = Depends(require_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(TranslationHistory)
                      .where(TranslationHistory.user_id == user.id)) or 0
    rows = db.scalars(select(TranslationHistory)
                      .where(TranslationHistory.user_id == user.id)
                      .order_by(TranslationHistory.id.desc()).limit(limit)).all()
    return {"total": total, "items": [_out(row) for row in rows]}


@router.delete("/translations/{item_id}")
def delete_translation(item_id: int, request: Request,
                       user: User = Depends(require_user), db: Session = Depends(get_db)):
    row = db.get(TranslationHistory, item_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "历史记录不存在")
    db.delete(row)
    db.commit()
    log(db, user.id, "translation_delete", "translation_history", item_id, client_ip(request))
    return {"ok": True}
