# -*- coding: utf-8 -*-
"""把 public_corpus 的 8,308 条句对向量化，写入 corpus_vectors 表（float32 BLOB，1024 维）。

- 复用 app.services.embedding.embed_texts（与 chunks 同一套 provider；local 哈希离线确定性）；
- 向量按 corpus_id（= public_corpus.id）upsert；批量 32；
- 存储格式：float32 小端 BLOB（1024*4=4096 字节），供 retrieval.search_corpus_vector 做余弦；
- 支持 --limit（只处理前 N 条待处理）/ --force（重算已有向量）。

用法：
  ./.venv/Scripts/python.exe scripts/embed_corpus.py
  ./.venv/Scripts/python.exe scripts/embed_corpus.py --limit 100 --force
"""
from __future__ import annotations

import argparse
import logging
import os
import struct
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import CorpusVector, PublicCorpus  # noqa: E402
from app.services.embedding import embed_texts, embedding_dim  # noqa: E402

BATCH_SIZE = 32


def _to_blob(vector: list[float]) -> bytes:
    """list[float] → float32 小端 BLOB。"""
    return struct.pack("<%df" % len(vector), *vector)


def _corpus_text(zh: str, en: str) -> str:
    """句对向量化文本：中英同时入向量，中/英查询都能命中。"""
    return f"{zh or ''} {en or ''}".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="public_corpus 句对向量化 → corpus_vectors")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数（0=全部）")
    parser.add_argument("--force", action="store_true", help="重算已有向量")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    dim = int(embedding_dim())
    db = SessionLocal()
    try:
        total_corpus = db.scalar(select(func.count()).select_from(PublicCorpus)) or 0
        existing = {row.corpus_id: row for row in db.scalars(select(CorpusVector)).all()}
        print(f"[corpus] public_corpus={total_corpus} 条，corpus_vectors 已有 {len(existing)} 条，"
              f"dim={dim}，force={args.force}")

        written = updated = skipped = failed = 0
        last_id = 0
        stop = False
        batch_no = 0
        while not stop:
            rows = db.execute(
                select(PublicCorpus.id, PublicCorpus.zh, PublicCorpus.en)
                .where(PublicCorpus.id > last_id)
                .order_by(PublicCorpus.id)
                .limit(BATCH_SIZE)
            ).all()
            if not rows:
                break
            last_id = rows[-1].id
            todo = []
            for corpus_pk, zh, en in rows:
                if not args.force and corpus_pk in existing:
                    skipped += 1
                    continue
                todo.append((corpus_pk, zh, en))
            if args.limit:
                remaining = args.limit - (written + updated)
                todo = todo[: max(0, remaining)]
                if remaining <= 0:
                    stop = True
            if todo:
                texts = [_corpus_text(zh, en) for _, zh, en in todo]
                try:
                    vectors = embed_texts(texts)
                except Exception as exc:  # 单批失败不中断，计数后继续
                    failed += len(todo)
                    print(f"[fail] 第 {batch_no + 1} 批（{len(todo)} 条）向量化失败：{type(exc).__name__}: {exc}")
                    continue
                if not isinstance(vectors, list) or len(vectors) != len(todo):
                    failed += len(todo)
                    print(f"[fail] 第 {batch_no + 1} 批返回数量不匹配，按失败计")
                    continue
                for (corpus_pk, _zh, _en), vector in zip(todo, vectors):
                    if not vector or len(vector) != dim:
                        failed += 1
                        continue
                    blob = _to_blob(vector)
                    obj = existing.get(corpus_pk)
                    if obj is None:
                        obj = CorpusVector(corpus_id=corpus_pk, vector=blob)
                        db.add(obj)
                        existing[corpus_pk] = obj
                        written += 1
                    else:
                        obj.vector = blob
                        updated += 1
                db.commit()
                batch_no += 1
                done = written + updated
                if batch_no % 10 == 0:
                    print(f"[progress] 已处理 {done} 条（新增 {written} / 更新 {updated} / 跳过 {skipped} / 失败 {failed}）")
            if stop:
                break

        total_vectors = db.scalar(select(func.count()).select_from(CorpusVector)) or 0
        print(f"[corpus] 新增 {written}，更新 {updated}，已有跳过 {skipped}，失败 {failed}；"
              f"corpus_vectors 现有 {total_vectors} 条（期望 {total_corpus}）")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
