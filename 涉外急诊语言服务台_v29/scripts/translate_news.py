# -*- coding: utf-8 -*-
"""把 pending 的英文资讯逐条中文化（优先 LLM；无 LLM 时用 MyMemory 免费端口）。

用法：
  ./.venv/Scripts/python.exe scripts/translate_news.py --limit 40            # 只译标题（快）
  ./.venv/Scripts/python.exe scripts/translate_news.py --limit 20 --with-summary
"""
from __future__ import annotations

import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import NewsItem  # noqa: E402
from app.services import crawler  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--with-summary", action="store_true", help="同时翻译摘要（更慢，2 倍请求）")
    args = ap.parse_args()

    if crawler.llm_available():
        print("[mode] LLM")
    else:
        print("[mode] MyMemory（免费公共端口，逐条限速）")

    db = SessionLocal()
    done = failed = 0
    try:
        items = db.scalars(select(NewsItem).where(NewsItem.status == "pending")
                           .order_by(NewsItem.id).limit(args.limit)).all()
        print(f"[start] pending={len(items)}")
        for item in items:
            try:
                if crawler.llm_available():
                    title_zh, summary_zh = crawler._translate_with_llm(item.title_en or "", item.summary_en or "")
                else:
                    title_zh = crawler._translate_with_mymemory(item.title_en or "", 160)
                    summary_zh = (crawler._translate_with_mymemory(item.summary_en or "", 500)
                                  if args.with_summary and item.summary_en else "")
                if not title_zh:
                    raise RuntimeError("empty translation")
                item.title_zh = title_zh
                if summary_zh:
                    item.summary_zh = summary_zh
                item.status = "published"
                db.commit()
                done += 1
                print(f"[ok] {item.id} {title_zh[:40]}")
            except Exception as exc:  # 单条失败不影响整体
                db.rollback()
                failed += 1
                print(f"[fail] {item.id} {type(exc).__name__}: {exc}")
                time.sleep(0.5)
        print(f"[done] published={done} failed={failed}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
