# -*- coding: utf-8 -*-
"""跨文化表达与英语变体（只读：738 条文化表达 + 150 条变体整句）。

术语库回答「这个医学概念怎么说」，本模块回答「这话能不能说、怎么说才不失礼」。
两块数据同属 V1.3 总库，此前未进入站点。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CultureExpr, EnglishVariant
from .refs import source_bundle

router = APIRouter(prefix="/api", tags=["culture"])

LEVEL_ORDER = {"红": 0, "橙": 1, "黄": 2, "无": 3}


def _culture_item(r: CultureExpr) -> dict:
    return {
        "id": r.id, "expr_id": r.expr_id, "ctype": r.ctype, "subcategory": r.subcategory,
        "country": r.country, "original": r.original, "original_lang": r.original_lang,
        "literal_zh": r.literal_zh, "risk": r.risk, "rec_en": r.rec_en, "rec_zh": r.rec_zh,
        "scene": r.scene, "taboo_level": r.taboo_level, "usage_note": r.usage_note,
        "example_zh": r.example_zh, "example_en": r.example_en,
        "source_code": r.source_code, "source_file": r.source_file,
    }


def _variant_item(r: EnglishVariant) -> dict:
    return {
        "id": r.id, "variant_id": r.variant_id, "variant": r.variant, "country": r.country,
        "original": r.original, "features": r.features, "literal_zh": r.literal_zh,
        "standard_en": r.standard_en, "medical_en": r.medical_en,
        "register_note": r.register_note, "meaning_zh": r.meaning_zh,
        "source_code": r.source_code,
    }


@router.get("/culture/meta")
def culture_meta(db: Session = Depends(get_db)):
    countries = db.execute(select(CultureExpr.country, func.count())
                           .group_by(CultureExpr.country)
                           .order_by(func.count().desc())).all()
    types = db.execute(select(CultureExpr.ctype, func.count())
                       .group_by(CultureExpr.ctype).order_by(func.count().desc())).all()
    levels = db.execute(select(CultureExpr.taboo_level, func.count())
                        .group_by(CultureExpr.taboo_level)).all()
    scenes = db.execute(select(CultureExpr.scene, func.count())
                        .group_by(CultureExpr.scene).order_by(func.count().desc())).all()
    level_map = {lv: c for lv, c in levels}
    return {
        "total": db.scalar(select(func.count()).select_from(CultureExpr)) or 0,
        "countries": [{"name": n or "未标注", "count": c} for n, c in countries],
        "types": [{"name": n or "未分类", "count": c} for n, c in types],
        "levels": [{"name": lv, "count": level_map.get(lv, 0)}
                   for lv in sorted(LEVEL_ORDER, key=lambda k: LEVEL_ORDER[k])],
        "scenes": [{"name": n or "未标注", "count": c} for n, c in scenes[:12]],
    }


@router.get("/culture")
def list_culture(
    q: str = Query(default="", max_length=100),
    country: str = Query(default="", max_length=32),
    ctype: str = Query(default="", max_length=32),
    level: str = Query(default="", max_length=8),
    scene: str = Query(default="", max_length=64),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    stmt = select(CultureExpr)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(CultureExpr.original.like(like), CultureExpr.rec_en.like(like),
                              CultureExpr.rec_zh.like(like), CultureExpr.literal_zh.like(like),
                              CultureExpr.usage_note.like(like),
                              CultureExpr.subcategory.like(like)))
    if country:
        stmt = stmt.where(CultureExpr.country == country)
    if ctype:
        stmt = stmt.where(CultureExpr.ctype == ctype)
    if level:
        stmt = stmt.where(CultureExpr.taboo_level == level)
    if scene:
        stmt = stmt.where(CultureExpr.scene == scene)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(CultureExpr.expr_id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_culture_item(r) for r in rows]}


@router.get("/culture/{expr_id}")
def culture_detail(expr_id: str, db: Session = Depends(get_db)):
    row = db.scalar(select(CultureExpr).where(CultureExpr.expr_id == expr_id))
    if not row:
        raise HTTPException(404, "文化表达编号不存在")
    data = _culture_item(row)
    data["sources"] = source_bundle(db, row.source_code)
    return data


@router.get("/variants/meta")
def variants_meta(db: Session = Depends(get_db)):
    variants = db.execute(select(EnglishVariant.variant, func.count())
                          .group_by(EnglishVariant.variant)
                          .order_by(func.count().desc())).all()
    countries = db.execute(select(EnglishVariant.country, func.count())
                           .group_by(EnglishVariant.country)
                           .order_by(func.count().desc())).all()
    return {
        "total": db.scalar(select(func.count()).select_from(EnglishVariant)) or 0,
        "variants": [{"name": n or "未标注", "count": c} for n, c in variants],
        "countries": [{"name": n or "未标注", "count": c} for n, c in countries],
    }


@router.get("/variants")
def list_variants(
    q: str = Query(default="", max_length=100),
    variant: str = Query(default="", max_length=32),
    country: str = Query(default="", max_length=32),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    stmt = select(EnglishVariant)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(EnglishVariant.original.like(like),
                              EnglishVariant.standard_en.like(like),
                              EnglishVariant.medical_en.like(like),
                              EnglishVariant.meaning_zh.like(like),
                              EnglishVariant.features.like(like)))
    if variant:
        stmt = stmt.where(EnglishVariant.variant == variant)
    if country:
        stmt = stmt.where(EnglishVariant.country == country)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(EnglishVariant.variant_id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_variant_item(r) for r in rows]}


@router.get("/variants/{variant_id}")
def variant_detail(variant_id: str, db: Session = Depends(get_db)):
    row = db.scalar(select(EnglishVariant).where(EnglishVariant.variant_id == variant_id))
    if not row:
        raise HTTPException(404, "变体编号不存在")
    data = _variant_item(row)
    data["sources"] = source_bundle(db, row.source_code)
    return data
