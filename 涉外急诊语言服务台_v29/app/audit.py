# -*- coding: utf-8 -*-
"""审计日志：写操作与敏感读都留痕。"""
from sqlalchemy.orm import Session

from .models import AuditLog


def log(db: Session, user_id: int | None, action: str, object_type: str = "",
        object_id: str = "", ip: str = "", detail: str = "") -> None:
    db.add(AuditLog(user_id=user_id, action=action, object_type=object_type,
                    object_id=str(object_id), ip=ip, detail=detail[:500]))
    db.commit()
