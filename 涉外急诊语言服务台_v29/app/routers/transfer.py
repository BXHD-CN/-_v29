# -*- coding: utf-8 -*-
"""私有库导入导出：Excel（openpyxl）/ JSON。

- GET  /api/me/terms/export.xlsx?format=xlsx|json
- GET  /api/me/corpus/export.xlsx?format=xlsx|json
- POST /api/me/terms/import   （multipart，.xlsx / .json）
- POST /api/me/corpus/import  （multipart，.xlsx / .json）

所有接口 require_user；写请求由全局中间件做 CSRF 双提交校验。
导入按 (zh, en) 去重，重复/空行计入 skipped；单次最多 2000 行、文件最大 5MB。
"""
from __future__ import annotations

import io
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import log
from ..db import get_db
from ..deps import client_ip, require_user
from ..models import User, UserCorpus, UserTerm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/me", tags=["transfer"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 2000
MAX_ERRORS = 20

TERM_COLUMNS = ["zh", "en", "lang_pair", "domain", "definition", "note",
                "source_code", "source_url"]
CORPUS_COLUMNS = ["zh", "en", "lang_pair", "register", "term_id", "note",
                  "source_code", "source_url"]

# 字段 -> 最大长度（与 models.py 对齐）
TERM_LIMITS = {"zh": 255, "en": 255, "lang_pair": 16, "domain": 64, "definition": 2000,
               "note": 1000, "source_code": 64, "source_url": 512}
CORPUS_LIMITS = {"zh": 2000, "en": 2000, "lang_pair": 16, "register": 16, "term_id": 32,
                 "note": 1000, "source_code": 64, "source_url": 512}
TERM_DEFAULTS = {"lang_pair": "zh-en"}
CORPUS_DEFAULTS = {"lang_pair": "zh-en"}


def _rows_for_terms(db: Session, user: User) -> list[dict]:
    rows = db.scalars(select(UserTerm).where(UserTerm.user_id == user.id)
                      .order_by(UserTerm.id)).all()
    return [{key: (getattr(row, key) or "") for key in TERM_COLUMNS} for row in rows]


def _rows_for_corpus(db: Session, user: User) -> list[dict]:
    rows = db.scalars(select(UserCorpus).where(UserCorpus.user_id == user.id)
                      .order_by(UserCorpus.id)).all()
    return [{key: (getattr(row, key) or "") for key in CORPUS_COLUMNS} for row in rows]


def _xlsx_response(rows: list[dict], columns: list[str], filename: str) -> StreamingResponse:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(columns)
    for row in rows:
        ws.append([row.get(key, "") for key in columns])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _json_response(rows: list[dict], filename: str) -> JSONResponse:
    return JSONResponse(
        content=rows,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export(rows: list[dict], columns: list[str], fmt: str, stem: str):
    if (fmt or "xlsx").lower() == "json":
        return _json_response(rows, f"{stem}.json")
    return _xlsx_response(rows, columns, f"{stem}.xlsx")


@router.get("/terms/export.xlsx")
def export_terms(format: Literal["xlsx", "json"] = Query(default="xlsx"),
                 user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = _rows_for_terms(db, user)
    return _export(rows, TERM_COLUMNS, format, "my_terms")


@router.get("/corpus/export.xlsx")
def export_corpus(format: Literal["xlsx", "json"] = Query(default="xlsx"),
                  user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = _rows_for_corpus(db, user)
    return _export(rows, CORPUS_COLUMNS, format, "my_corpus")


def _clip(value, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:limit]


def _read_json_rows(raw: bytes) -> list[dict]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, f"JSON 解析失败：{type(exc).__name__}") from exc
    if isinstance(data, dict):
        data = data.get("items") or data.get("rows") or []
    if not isinstance(data, list):
        raise HTTPException(400, "JSON 需为对象数组（或 {items:[...]}）")
    return [item for item in data if isinstance(item, dict)]


def _read_xlsx_rows(raw: bytes) -> list[dict]:
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl 对坏文件会抛多种异常
        raise HTTPException(400, f"Excel 解析失败：{type(exc).__name__}") from exc
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = [str(cell or "").strip() for cell in next(rows_iter, [])]
        if not header:
            return []
        rows: list[dict] = []
        for values in rows_iter:
            row = {}
            for index, name in enumerate(header):
                if name:
                    row[name] = values[index] if index < len(values) else None
            rows.append(row)
        return rows
    finally:
        wb.close()


def _parse_upload(file: UploadFile) -> list[dict]:
    filename = (file.filename or "").lower()
    raw = file.file.read()
    if not raw:
        raise HTTPException(400, "上传文件为空")
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "文件超过 5MB 上限")
    if filename.endswith(".json"):
        rows = _read_json_rows(raw)
    elif filename.endswith((".xlsx", ".xlsm")):
        rows = _read_xlsx_rows(raw)
    else:
        # 未按扩展名时按内容猜：JSON 文本 vs xlsx(zip) 魔数
        if raw.lstrip()[:1] in (b"[", b"{"):
            rows = _read_json_rows(raw)
        elif raw[:2] == b"PK":
            rows = _read_xlsx_rows(raw)
        else:
            raise HTTPException(400, "仅支持 .xlsx / .json 文件")
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(400, f"单次最多导入 {MAX_IMPORT_ROWS} 行")
    return rows


def _clean_row(row: dict, limits: dict, defaults: dict) -> dict:
    payload: dict = {}
    for key, limit in limits.items():
        payload[key] = _clip(row.get(key), limit)
    for key, value in defaults.items():
        if not payload.get(key):
            payload[key] = value
    return payload


def _import_terms_rows(rows: list[dict], user: User, request: Request | None,
                       db: Session) -> dict:
    existing = {(t.zh, t.en) for t in db.scalars(
        select(UserTerm).where(UserTerm.user_id == user.id)).all()}
    imported = skipped = 0
    errors: list[dict] = []
    for index, row in enumerate(rows, start=2):
        payload = _clean_row(row, TERM_LIMITS, TERM_DEFAULTS)
        if not payload["zh"]:
            skipped += 1
            if len(errors) < MAX_ERRORS:
                errors.append({"row": index, "reason": "zh 为空"})
            continue
        key = (payload["zh"], payload["en"])
        if key in existing:
            skipped += 1
            continue
        try:
            with db.begin_nested():
                db.add(UserTerm(user_id=user.id, **payload))
            existing.add(key)
            imported += 1
        except IntegrityError:      # 并发/重复导入：按 skipped 处理，不返回 500
            skipped += 1
    db.commit()
    log(db, user.id, "term_bulk_import", "user_term", "",
        client_ip(request) if request else "", detail=f"imported={imported} skipped={skipped}")
    logger.info("term import user=%s imported=%s skipped=%s", user.id, imported, skipped)
    return {"ok": True, "imported": imported, "skipped": skipped, "errors": errors}


def _import_corpus_rows(rows: list[dict], user: User, request: Request | None,
                        db: Session) -> dict:
    existing = {(c.zh, c.en) for c in db.scalars(
        select(UserCorpus).where(UserCorpus.user_id == user.id)).all()}
    imported = skipped = 0
    errors: list[dict] = []
    for index, row in enumerate(rows, start=2):
        payload = _clean_row(row, CORPUS_LIMITS, CORPUS_DEFAULTS)
        if not payload["zh"] or not payload["en"]:
            skipped += 1
            if len(errors) < MAX_ERRORS:
                errors.append({"row": index, "reason": "zh/en 不能为空"})
            continue
        key = (payload["zh"], payload["en"])
        if key in existing:
            skipped += 1
            continue
        try:
            with db.begin_nested():
                db.add(UserCorpus(user_id=user.id, **payload))
            existing.add(key)
            imported += 1
        except IntegrityError:
            skipped += 1
    db.commit()
    log(db, user.id, "corpus_bulk_import", "user_corpus", "",
        client_ip(request) if request else "", detail=f"imported={imported} skipped={skipped}")
    logger.info("corpus import user=%s imported=%s skipped=%s", user.id, imported, skipped)
    return {"ok": True, "imported": imported, "skipped": skipped, "errors": errors}


@router.post("/terms/import")
def import_terms(request: Request, file: UploadFile = File(...),
                 user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _import_terms_rows(_parse_upload(file), user, request, db)


@router.post("/corpus/import")
def import_corpus(request: Request, file: UploadFile = File(...),
                  user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _import_corpus_rows(_parse_upload(file), user, request, db)
