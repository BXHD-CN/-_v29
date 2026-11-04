# -*- coding: utf-8 -*-
"""切片增量更新：data/chunks.jsonl ↔ chunks 表（按 doc_fingerprint 比对）。

规则：
- 新增：库内没有 (doc_id, chunk_no) → 插入，version=1；
- 变更：同 (doc_id, chunk_no) 但 doc_fingerprint 不同 → 更新字段并把 version+1（写新版本）；
- 删除：库内有、jsonl 里已没有 → 删除该行（源数据下线）；
- 打印 diff（计数 + 明细摘要），--dry-run 只报告不写库。

用法：
  ./.venv/Scripts/python.exe scripts/update_slices.py
  ./.venv/Scripts/python.exe scripts/update_slices.py --dry-run
  ./.venv/Scripts/python.exe scripts/update_slices.py --file data/chunks.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Chunk  # noqa: E402

DEFAULT_CHUNKS = os.path.join(BASE_DIR, "data", "chunks.jsonl")
FIELDS = ("doc_id", "chunk_no", "title", "text", "source_url", "section", "page",
          "lang", "license", "fetched_at", "doc_fingerprint")
DETAIL_LIMIT = 20


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise SystemExit(f"找不到切片文件：{path}")
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _key(row: dict) -> tuple[str, int]:
    return str(row.get("doc_id", "")), int(row.get("chunk_no", 0) or 0)


def _payload(row: dict) -> dict:
    """jsonl 行 → Chunk 字段（fingerprint 缺失时按 text 补算）。"""
    payload = {key: row.get(key, "") for key in FIELDS}
    payload["doc_id"] = str(payload["doc_id"])
    payload["chunk_no"] = int(payload["chunk_no"] or 0)
    payload["text"] = str(payload["text"] or "")
    payload["doc_fingerprint"] = payload.get("doc_fingerprint") or hashlib.sha256(
        payload["text"].encode("utf-8")).hexdigest()[:16]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="切片增量更新（jsonl ↔ chunks 表）")
    parser.add_argument("--file", default=DEFAULT_CHUNKS, help="切片 jsonl 路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印 diff，不写库")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        jsonl_rows = load_jsonl(os.path.abspath(args.file))
        incoming: dict[tuple[str, int], dict] = {}
        for row in jsonl_rows:
            key = _key(row)
            if key in incoming:
                print(f"[warn] jsonl 中 {key[0]}#{key[1]} 重复，保留最后一条")
            incoming[key] = _payload(row)

        existing = {(row.doc_id, row.chunk_no): row for row in db.scalars(select(Chunk)).all()}
        added = [key for key in incoming if key not in existing]
        deleted = [key for key in existing if key not in incoming]
        changed = [key for key in incoming
                   if key in existing and incoming[key]["doc_fingerprint"] != (existing[key].doc_fingerprint or "")]
        unchanged = len(incoming) - len(added) - len(changed)

        print(f"[diff] jsonl={len(incoming)} 条，DB={len(existing)} 条；"
              f"新增 {len(added)}，变更 {len(changed)}，删除 {len(deleted)}，未变 {unchanged}")
        for label, keys in (("新增", added), ("变更", changed), ("删除", deleted)):
            if not keys:
                continue
            print(f"  {label}（{len(keys)}）:")
            for key in keys[:DETAIL_LIMIT]:
                doc_id, chunk_no = key
                if label == "变更":
                    old = (existing[key].doc_fingerprint or "")[:8]
                    new = incoming[key]["doc_fingerprint"][:8]
                    print(f"    + {doc_id}#{chunk_no}  fingerprint {old} → {new}  version {existing[key].version} → {existing[key].version + 1}")
                elif label == "新增":
                    print(f"    + {doc_id}#{chunk_no}  fingerprint {incoming[key]['doc_fingerprint'][:8]}  version 1")
                else:
                    print(f"    - {doc_id}#{chunk_no}  fingerprint {(existing[key].doc_fingerprint or '')[:8]}  version {existing[key].version}")
            if len(keys) > DETAIL_LIMIT:
                print(f"    … 其余 {len(keys) - DETAIL_LIMIT} 条省略")

        if args.dry_run:
            print("[dry-run] 未写库")
            return 0

        for key in added:
            db.add(Chunk(**{k: v for k, v in incoming[key].items() if k != "chunk_no"},
                         chunk_no=incoming[key]["chunk_no"], version=1))
        for key in changed:
            obj = existing[key]
            for field in FIELDS:
                if field == "chunk_no":
                    continue
                setattr(obj, field, incoming[key].get(field, ""))
            obj.version = (obj.version or 1) + 1
        for key in deleted:
            db.delete(existing[key])
        db.commit()

        total = db.scalar(select(func.count()).select_from(Chunk)) or 0
        embedded = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding != "")) or 0
        print(f"[apply] 新增 {len(added)}，变更 {len(changed)}，删除 {len(deleted)}；"
              f"chunks 表现有 {total} 条（已向量化 {embedded} 条）")
        if added or changed:
            print("[next] 请运行 scripts/embed_chunks.py 为新增/变更切片补向量")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
