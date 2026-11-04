# -*- coding: utf-8 -*-
"""把 data/*.jsonl 导入数据库（幂等：按业务编号 upsert）。

用法： ./.venv/Scripts/python.exe scripts/seed_public.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import (CultureExpr, EnglishVariant, LocalTerm, PublicCorpus, PublicTerm,
                        SourceRef)  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load_jsonl(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        print("missing", name)
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    init_db()
    db = SessionLocal()
    try:
        terms = load_jsonl("public_terms.jsonl")
        existing = {t.term_id: t for t in db.scalars(select(PublicTerm)).all()}
        added = updated = 0
        for row in terms:
            obj = existing.get(row["term_id"])
            if obj is None:
                db.add(PublicTerm(**row))
                added += 1
            else:
                for k, v in row.items():
                    setattr(obj, k, v)
                updated += 1
        db.commit()
        print(f"terms: +{added} ~{updated}")

        corpus = load_jsonl("public_corpus.jsonl")
        existing_c = {c.corpus_id: c for c in db.scalars(select(PublicCorpus)).all()}
        added = updated = 0
        for row in corpus:
            obj = existing_c.get(row["corpus_id"])
            if obj is None:
                db.add(PublicCorpus(**row))
                added += 1
            else:
                for k, v in row.items():
                    setattr(obj, k, v)
                updated += 1
        db.commit()
        print(f"corpus: +{added} ~{updated}")

        sources = load_jsonl("sources.jsonl")
        existing_s = {s.code: s for s in db.scalars(select(SourceRef)).all()}
        added = updated = 0
        for row in sources:
            obj = existing_s.get(row["code"])
            if obj is None:
                db.add(SourceRef(**row))
                added += 1
            else:
                for k, v in row.items():
                    setattr(obj, k, v)
                updated += 1
        db.commit()
        print(f"sources: +{added} ~{updated}")

        local = load_jsonl("local_terms.jsonl")
        existing_l = {t.local_id: t for t in db.scalars(select(LocalTerm)).all()}
        added = updated = 0
        for row in local:
            obj = existing_l.get(row["local_id"])
            if obj is None:
                db.add(LocalTerm(**row))
                added += 1
            else:
                for k, v in row.items():
                    setattr(obj, k, v)
                updated += 1
        db.commit()
        print(f"local_terms: +{added} ~{updated}")

        culture = load_jsonl("culture.jsonl")
        existing_ce = {t.expr_id: t for t in db.scalars(select(CultureExpr)).all()}
        added = updated = 0
        for row in culture:
            obj = existing_ce.get(row["expr_id"])
            if obj is None:
                db.add(CultureExpr(**row))
                added += 1
            else:
                for k, v in row.items():
                    setattr(obj, k, v)
                updated += 1
        db.commit()
        print(f"culture: +{added} ~{updated}")

        variants = load_jsonl("english_variants.jsonl")
        existing_ev = {t.variant_id: t for t in db.scalars(select(EnglishVariant)).all()}
        added = updated = 0
        for row in variants:
            obj = existing_ev.get(row["variant_id"])
            if obj is None:
                db.add(EnglishVariant(**row))
                added += 1
            else:
                for k, v in row.items():
                    setattr(obj, k, v)
                updated += 1
        db.commit()
        print(f"english_variants: +{added} ~{updated}")
    finally:
        db.close()


if __name__ == "__main__":
    main()