# -*- coding: utf-8 -*-
"""CLI：抓取三源资讯并写入 news_items 表。

用法：
  ./.venv/Scripts/python.exe scripts/crawl.py --source all --limit 20
  ./.venv/Scripts/python.exe scripts/crawl.py --source usgs --limit 20
  ./.venv/Scripts/python.exe scripts/crawl.py --source reliefweb --translate   # 有 Key 才真正中文化
"""
from __future__ import annotations

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import NewsItem  # noqa: E402
from app.services import crawler  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 UN News / ReliefWeb / USGS 资讯并落库")
    parser.add_argument("--source", choices=["all", "un", "reliefweb", "usgs", "un_zh"], default="all",
                        help="抓取来源，默认 all（un_zh=联合国新闻中文版，内容本身为中文）")
    parser.add_argument("--limit", type=int, default=20, help="每源最多条数（≤20），默认 20")
    parser.add_argument("--translate", action="store_true",
                        help="开启中文化（无 LLM Key 时自动跳过，状态记 pending）")
    parser.add_argument("--no-translate", action="store_true", help="关闭中文化，全部标 pending")
    args = parser.parse_args()

    translate: bool | None = None
    if args.no_translate:
        translate = False
    elif args.translate:
        translate = True

    if args.translate and not crawler.llm_available():
        from app.config import get_settings
        if (get_settings().news_mt_provider or "").lower() == "mymemory":
            print("[提示] 未配置生成模型，改用免费公共 MT 端口（MyMemory）做中文化，速度较慢")
        else:
            print("[提示] 未配置生成模型（llm_provider=mock 或缺少 Key），本次跳过中文化，状态记 pending")

    names = list(crawler.SOURCE_URLS) if args.source == "all" else [args.source]
    init_db()
    db = SessionLocal()
    try:
        result = crawler.crawl(db, sources=names, limit=args.limit, translate=translate)
        total = {"fetched": 0, "written": 0, "updated": 0, "skipped": 0,
                 "translated": 0, "translate_failed": 0}
        for name, stats in result.items():
            label = crawler.SOURCE_LABELS.get(name, name)
            print(f"[{name}/{label}] 抓到 {stats['fetched']} 条：写入 {stats['written']}，"
                  f"更新 {stats['updated']}，跳过 {stats['skipped']}，中文化 {stats['translated']}，"
                  f"翻译失败 {stats['translate_failed']}"
                  + (f"，错误：{stats['error']}" if stats["error"] else "")
                  + (f"，备注：{stats['note']}" if stats.get("note") else ""))
            for key in total:
                total[key] += stats[key]
        news_total = db.scalar(select(func.count()).select_from(NewsItem)) or 0
        print(f"合计：写入 {total['written']}，更新 {total['updated']}，跳过 {total['skipped']}，"
              f"中文化 {total['translated']}，翻译失败 {total['translate_failed']}；"
              f"news_items 现有 {news_total} 条")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
