# -*- coding: utf-8 -*-
"""读取 data/chunks.jsonl（或库内切片）→ 调用向量服务 → 写入 chunks 表。

- 按 (doc_id, chunk_no) 去重 upsert；
- 批量 32 条调用 app.services.embedding.embed_texts（ai-core 实现：1024 维、已 L2 归一化）；
- embedding 以 JSON 字符串写入 chunks.embedding；
- 支持 --limit / --force / --from-db；失败条目 embedding 留空并计数。

用法：
  ./.venv/Scripts/python.exe scripts/embed_chunks.py
  ./.venv/Scripts/python.exe scripts/embed_chunks.py --limit 120
  ./.venv/Scripts/python.exe scripts/embed_chunks.py --force
  ./.venv/Scripts/python.exe scripts/embed_chunks.py --from-db --force
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import sys
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Chunk  # noqa: E402

BATCH_SIZE = 32
DEFAULT_CHUNKS = os.path.join(BASE_DIR, "data", "chunks.jsonl")
FIELDS = ("doc_id", "chunk_no", "title", "text", "source_url", "section", "page",
          "lang", "license", "fetched_at", "doc_fingerprint")


def _local_embed_texts(texts: list[str], dim: int = 1024) -> list[list[float]]:
    """兜底向量：与 CONTRACT §4.1 一致的确定性 local 哈希（字符 2–3 gram + 英文词 + TF 加权 + L2 归一化）。"""
    def tokens(text: str) -> list[str]:
        lowered = (text or "").lower().strip()
        chars = re.sub(r"\s+", "", lowered)
        feats = [chars[i:i + n] for n in (2, 3) for i in range(len(chars) - n + 1)]
        feats.extend("w:" + word for word in re.findall(r"[a-z0-9]+", lowered))
        return feats

    vectors: list[list[float]] = []
    for text in texts:
        counts = Counter(tokens(text))
        vec = [0.0] * dim
        for token, tf in counts.items():
            bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
            vec[bucket] += 1.0 + math.log(tf)
        norm = math.sqrt(sum(value * value for value in vec))
        vectors.append([value / norm for value in vec] if norm > 0 else vec)
    return vectors


def get_embedder():
    """优先复用 ai-core 的 app.services.embedding；不可用时退回内置 local 哈希兜底。"""
    try:
        from app.services.embedding import embed_texts, embedding_dim
        dim = int(embedding_dim())
        print(f"[embed] 使用 app.services.embedding（dim={dim}）")
        return embed_texts, dim
    except Exception as exc:
        print(f"[warn] app.services.embedding 不可用（{type(exc).__name__}: {exc}），"
              "改用内置 local 哈希兜底；若之后 ai-core 实现可用，请重跑 --force")
        return (lambda texts: _local_embed_texts(texts)), 1024


def load_rows(from_db: bool, db, jsonl_path: str) -> list[dict]:
    """从 jsonl 或数据库读取切片行。"""
    if from_db:
        rows = db.scalars(select(Chunk).order_by(Chunk.id)).all()
        keys = ("doc_id", "chunk_no", "title", "text", "source_url", "section", "page",
                "lang", "license", "fetched_at", "doc_fingerprint")
        return [{key: getattr(row, key) for key in keys} for row in rows]
    if not os.path.exists(jsonl_path):
        raise SystemExit(f"找不到切片文件：{jsonl_path}")
    rows: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="把 chunks.jsonl 灌入 chunks 表并写入向量")
    parser.add_argument("--in", dest="input", default=DEFAULT_CHUNKS, help="切片 jsonl 路径")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数（0=全部）")
    parser.add_argument("--force", action="store_true", help="强制重算向量（覆盖已有 embedding）")
    parser.add_argument("--from-db", action="store_true", help="从库里已有 chunks 读入而非 jsonl")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    db = SessionLocal()
    try:
        rows = load_rows(args.from_db, db, args.input)
        if args.limit and args.limit > 0:
            rows = rows[:args.limit]
        print(f"[embed] 待处理切片 {len(rows)} 条（force={args.force}, from_db={args.from_db}）")
        embed_texts, dim = get_embedder()
        existing = {(row.doc_id, row.chunk_no): row for row in db.scalars(select(Chunk)).all()}

        written = updated = skipped = 0
        pending: list[Chunk] = []
        for row in rows:
            try:
                doc_id = str(row["doc_id"])
                chunk_no = int(row.get("chunk_no", 0) or 0)
                text = str(row["text"] or "")
            except (KeyError, TypeError, ValueError):
                print("[warn] 跳过一条字段不完整的切片")
                skipped += 1
                continue
            payload = {key: ("" if row.get(key) is None else row.get(key)) for key in FIELDS}
            payload["text"] = text
            payload["doc_fingerprint"] = payload.get("doc_fingerprint") or hashlib.sha256(
                text.encode("utf-8")).hexdigest()[:16]
            obj = existing.get((doc_id, chunk_no))
            if obj is None:
                obj = Chunk(chunk_no=chunk_no,
                            **{key: payload[key] for key in FIELDS if key != "chunk_no"})
                db.add(obj)
                existing[(doc_id, chunk_no)] = obj
                written += 1
            else:
                for key in FIELDS:
                    if key == "chunk_no":
                        continue
                    setattr(obj, key, payload.get(key, ""))
                if args.force:
                    obj.version = (obj.version or 1) + 1
                updated += 1
            if args.force or not (obj.embedding or "").strip():
                pending.append(obj)
            else:
                skipped += 1
        db.flush()

        embed_ok = embed_fail = 0
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start:start + BATCH_SIZE]
            try:
                vectors = embed_texts([chunk.text for chunk in batch])
            except Exception as exc:
                print(f"[warn] 第 {start // BATCH_SIZE + 1} 批向量化失败（{len(batch)} 条）："
                      f"{type(exc).__name__}: {exc}")
                embed_fail += len(batch)
                continue
            if not isinstance(vectors, list) or len(vectors) != len(batch):
                print(f"[warn] 第 {start // BATCH_SIZE + 1} 批返回数量不匹配，按失败计")
                embed_fail += len(batch)
                continue
            batch_ok = 0
            for chunk, vector in zip(batch, vectors):
                if not vector or len(vector) != dim:
                    embed_fail += 1
                    continue
                chunk.embedding = json.dumps([round(float(value), 6) for value in vector])
                embed_ok += 1
                batch_ok += 1
            db.commit()
            print(f"[embed] 第 {start // BATCH_SIZE + 1} 批：成功 {batch_ok}/{len(batch)}")
        db.commit()

        total_db = db.scalar(select(func.count()).select_from(Chunk)) or 0
        embedded_db = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding != "")) or 0
        print(f"[embed] 写入 {written}，更新 {updated}，已有向量跳过 {skipped}；"
              f"向量成功 {embed_ok}，失败 {embed_fail}")
        print(f"[embed] chunks 表：{total_db} 行，已向量化 {embedded_db} 行")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
