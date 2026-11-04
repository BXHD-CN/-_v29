# -*- coding: utf-8 -*-
"""构建知识库切片 data/chunks.jsonl（目标 ≥120 片）。

数据组成：
- data/real_corpus.jsonl：160 条真实语料。按（source_file, category）排序后每 4 条合成 1 片 → 40 片；
  text = 中文原句拼接（不足 300 字补英文摘要，最终 300–500 字），section=category，license 原样。
- data/public_terms.jsonl：按领域分组，每 15 条术语合成 1 片（术语+释义+英文）→ 80 片；
  section=领域，source_url 可空，license 写“来源见 source_code”。
每片字段：doc_id/chunk_no/title/text/source_url/section/page/lang/license/fetched_at/doc_fingerprint。
同 doc 内 chunk_no 从 0 递增；doc_fingerprint=sha256(text)[:16]；切片不跨文档（真实语料按来源文件归组）。

用法：
  ./.venv/Scripts/python.exe scripts/build_slices.py --out data/chunks.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

REAL_PER_CHUNK = 4          # 真实语料每片合并 4 条
TERMS_PER_CHUNK = 15        # 术语片每片合并 15 条
MAX_TERM_CHUNKS = 80        # 术语片总数（约 80 片）
TEXT_MIN, TEXT_MAX = 300, 500
PASSEND = "。！？；.!?;"


def load_jsonl(name: str) -> list[dict]:
    """读取 data/ 下的 jsonl；文件缺失时打印告警并返回空列表。"""
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        print(f"[warn] 缺少数据文件：{path}")
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def fingerprint(text: str) -> str:
    """切片指纹：sha256(text) 前 16 位。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fit_text(text: str, hi: int = TEXT_MAX) -> str:
    """正文超过上限时截断并补省略号，保证 ≤ hi。"""
    text = text.strip()
    if len(text) > hi:
        return text[: hi - 1].rstrip() + "…"
    return text


def build_real_text(rows: list[dict]) -> str:
    """中文原句拼接；不足 300 字用英文摘要补足，最终控制在 300–500 字。"""
    zh = "".join((row.get("zh") or "").strip() for row in rows)
    if zh and zh[-1] not in PASSEND:
        zh += "。"
    text = zh
    if len(text) < TEXT_MIN:
        for row in rows:
            en = (row.get("en") or "").strip()
            if not en:
                continue
            text = text + " " + en
            if len(text) >= TEXT_MIN:
                break
    return fit_text(text)


def build_real_chunks(rows: list[dict]) -> list[dict]:
    """真实语料：按（来源文件, 类别）分组后每 4 条一片；切片不跨文档，约 42 片。"""
    from itertools import groupby

    order = sorted(rows, key=lambda r: (r.get("source_file", ""), r.get("category", "")))
    doc_ids: dict[str, str] = {}
    doc_seq: dict[str, int] = {}
    chunks: list[dict] = []
    for (file_name, category), grouped in groupby(
            order, key=lambda r: (r.get("source_file", ""), r.get("category", ""))):
        items = list(grouped)
        for start in range(0, len(items), REAL_PER_CHUNK):
            group = items[start:start + REAL_PER_CHUNK]
            if not group:
                continue
            head = group[0]
            doc_id = doc_ids.setdefault(file_name, f"RCL-F{len(doc_ids) + 1:02d}")
            chunk_no = doc_seq.get(doc_id, 0)
            doc_seq[doc_id] = chunk_no + 1
            text = build_real_text(group)
            chunks.append({
                "doc_id": doc_id,
                "chunk_no": chunk_no,
                "title": f"{file_name}｜{category}"[:255],
                "text": text,
                "source_url": head.get("source_url", ""),
                "section": category,
                "page": "",
                "lang": "zh",
                "license": head.get("license", ""),
                "fetched_at": head.get("access_date", ""),
                "doc_fingerprint": fingerprint(text),
            })
    return chunks


def _term_entry(term: dict, def_cap: int | None) -> str:
    """一条术语：中文（英文）：释义；def_cap 控制释义长度以适配整片 300–500 字。"""
    definition = (term.get("definition_zh") or "").strip()
    if def_cap is not None and len(definition) > def_cap:
        definition = (definition[: def_cap - 1] + "…") if def_cap > 1 else "…"
    return f"{term.get('zh', '')}（{term.get('en', '')}）：{definition}"


def build_term_text(window: list[dict]) -> str:
    """15 条术语组片：术语+释义+英文，整片控制在 300–500 字（释义过长时截断）。"""
    text = ""
    for cap in (None, 40, 30, 24, 20, 16, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2):
        text = "；".join(_term_entry(term, cap) for term in window)
        if len(text) <= TEXT_MAX:
            break
    if len(text) < TEXT_MIN:
        # 兜底：术语片正文一般不会低于 300 字，极端情况补英文全称
        text = text + "；英文术语：" + "，".join(term.get("en", "") for term in window)
    return fit_text(text)


def build_term_chunks(rows: list[dict], max_chunks: int = MAX_TERM_CHUNKS) -> list[dict]:
    """公共术语：按领域分组，每 15 条一片，取前 max_chunks 片（约 80 片）。"""
    domains: dict[str, list[dict]] = {}
    for row in rows:
        domains.setdefault(row.get("domain") or "未分类", []).append(row)
    today = date.today().isoformat()
    doc_seq: dict[str, int] = {}
    chunks: list[dict] = []
    for domain_index, (domain, terms) in enumerate(domains.items(), start=1):
        if len(chunks) >= max_chunks:
            break
        doc_id = f"PT-D{domain_index:02d}"
        for start in range(0, len(terms), TERMS_PER_CHUNK):
            if len(chunks) >= max_chunks:
                break
            window = terms[start:start + TERMS_PER_CHUNK]
            chunk_no = doc_seq.get(doc_id, 0)
            doc_seq[doc_id] = chunk_no + 1
            text = build_term_text(window)
            chunks.append({
                "doc_id": doc_id,
                "chunk_no": chunk_no,
                "title": f"{domain}术语组 {chunk_no + 1}"[:255],
                "text": text,
                "source_url": window[0].get("source_url", ""),
                "section": domain,
                "page": "",
                "lang": "zh",
                "license": "来源见 source_code",
                "fetched_at": today,
                "doc_fingerprint": fingerprint(text),
            })
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 data/chunks.jsonl 知识库切片")
    parser.add_argument("--out", default=os.path.join(DATA_DIR, "chunks.jsonl"))
    parser.add_argument("--max-term-chunks", type=int, default=MAX_TERM_CHUNKS)
    args = parser.parse_args()

    real_rows = load_jsonl("real_corpus.jsonl")
    term_rows = load_jsonl("public_terms.jsonl")
    real_chunks = build_real_chunks(real_rows)
    term_chunks = build_term_chunks(term_rows, max_chunks=args.max_term_chunks)
    chunks = real_chunks + term_chunks

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    lengths = [len(chunk["text"]) for chunk in chunks]
    docs = {chunk["doc_id"] for chunk in chunks}
    in_range = sum(1 for n in lengths if TEXT_MIN <= n <= TEXT_MAX)
    print(f"真实语料切片：{len(real_chunks)} 片（{len(real_rows)} 条 / 每 {REAL_PER_CHUNK} 条一片）")
    print(f"术语切片：{len(term_chunks)} 片（每 {TERMS_PER_CHUNK} 条术语一片）")
    print(f"合计 {len(chunks)} 片，doc {len(docs)} 个；text 长度 {min(lengths)}–{max(lengths)} 字，"
          f"300–500 字合规 {in_range}/{len(chunks)}")
    print(f"输出：{out_path}")
    if len(chunks) < 120:
        print("[error] 切片不足 120 片，请检查数据文件")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
