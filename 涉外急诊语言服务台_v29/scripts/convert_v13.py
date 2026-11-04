# -*- coding: utf-8 -*-
"""把 V1.3 总库与真实语料转换为站点可直接导入的 JSONL。

用法（用带 openpyxl 的解释器）：
  python scripts/convert_v13.py --xlsx "../merge/涉外急诊与东盟文化_中英术语语料总库_V1.3.xlsx" --out data
"""
import argparse
import json
import os

import openpyxl

TERM_HEADER = ["序号", "术语编号", "领域", "子领域", "使用场景", "中文术语", "英文术语", "缩写",
               "词性", "中文释义", "英文释义", "语料条数", "来源代号", "来源文件", "备注"]
CORPUS_HEADER = ["语料编号", "术语编号", "中文术语", "英文术语", "语体", "中文语料", "英文语料",
                 "领域", "使用场景", "来源代号"]


def _rows(ws, header):
    it = ws.iter_rows(values_only=True)
    head = [str(c).strip() if c is not None else "" for c in next(it)]
    idx = {name: i for i, name in enumerate(head)}
    for row in it:
        if row is None or all(c is None for c in row):
            continue
        yield {name: (row[idx[name]] if idx.get(name) is not None and idx[name] < len(row) else None)
               for name in header}


def convert_terms(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["专业术语总表"]
    out = []
    for r in _rows(ws, TERM_HEADER):
        zh = (r["中文术语"] or "").strip()
        en = (r["英文术语"] or "").strip()
        if not zh or not en:
            continue
        out.append({
            "term_id": (r["术语编号"] or "").strip(),
            "zh": zh, "en": en, "lang_pair": "zh-en",
            "domain": (r["领域"] or "").strip(),
            "subdomain": (r["子领域"] or "").strip(),
            "abbreviation": (r["缩写"] or "").strip(),
            "definition_zh": (r["中文释义"] or "").strip(),
            "definition_en": (r["英文释义"] or "").strip(),
            "source_code": (r["来源代号"] or "").strip(),
            "source_file": (r["来源文件"] or "").strip(),
            "source_url": "",
            "audit_status": "来源核验",
            "samples": int(r["语料条数"] or 0),
        })
    return out


def convert_corpus(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["术语语料库"]
    out = []
    for r in _rows(ws, CORPUS_HEADER):
        zh = (r["中文语料"] or "").strip()
        en = (r["英文语料"] or "").strip()
        if not zh or not en:
            continue
        out.append({
            "corpus_id": (r["语料编号"] or "").strip(),
            "term_id": (r["术语编号"] or "").strip(),
            "zh": zh, "en": en, "lang_pair": "zh-en",
            "register": (r["语体"] or "").strip(),
            "domain": (r["领域"] or "").strip(),
            "source_code": (r["来源代号"] or "").strip(),
            "source_file": "", "source_url": "",
            "audit_status": "来源核验",
        })
    return out


def convert_real(src):
    out = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append({
                "id": d.get("id", ""), "category": d.get("category", ""),
                "zh": d.get("zh", ""), "en": d.get("en", ""),
                "source_file": d.get("src_name", ""), "source_url": d.get("url", ""),
                "source_code": d.get("source_code", ""), "license": d.get("license", ""),
                "access_date": d.get("access_date", ""),
            })
    return out




SOURCE_HEADER = ["代号", "来源名称", "发布机构", "等级", "可核查入口", "适用内容"]
LOCAL_HEADER = ["序号", "编号", "语种", "类型", "领域", "使用场景", "中文", "英文",
                "本地语写法", "罗马化", "中文近似发音", "语用提示", "来源代号", "审校状态"]
LANG_CODE = {"越南语": "vi", "泰语": "th", "印尼语": "id", "马来语": "ms"}


def convert_sources(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["来源清单"]
    out, seen = [], set()
    for r in _rows(ws, SOURCE_HEADER):
        code = (r["代号"] or "").strip()
        if not code or code in seen:
            continue
        if not (len(code) >= 3 and code[0].isalpha() and code[1:].isdigit()):
            continue  # 跳过分组标题行
        seen.add(code)
        out.append({
            "code": code,
            "name": (r["来源名称"] or "").strip(),
            "org": (r["发布机构"] or "").strip(),
            "level": (r["等级"] or "").strip(),
            "url": (r["可核查入口"] or "").strip(),
            "applies": (r["适用内容"] or "").strip()[:255],
        })
    return out


def convert_local_terms(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["东盟本地语对照"]
    out = []
    for r in _rows(ws, LOCAL_HEADER):
        zh = (r["中文"] or "").strip()
        if not zh:
            continue
        lang = (r["语种"] or "").strip()
        out.append({
            "local_id": (r["编号"] or "").strip(),
            "lang": lang,
            "lang_code": LANG_CODE.get(lang, ""),
            "category": (r["类型"] or "").strip(),
            "domain": (r["领域"] or "").strip(),
            "scene": (r["使用场景"] or "").strip(),
            "zh": zh,
            "en": (r["英文"] or "").strip(),
            "local_text": (r["本地语写法"] or "").strip(),
            "romanization": (r["罗马化"] or "").strip(),
            "pron_hint": (r["中文近似发音"] or "").strip(),
            "usage_note": (r["语用提示"] or "").strip(),
            "source_code": (r["来源代号"] or "").strip(),
            "audit_status": (r["审校状态"] or "").strip() or "待母语审校",
        })
    return out

def dump(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(os.path.basename(path), len(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--real", default="../medterm_asean2/data/RC_final.jsonl")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    dump(os.path.join(args.out, "public_terms.jsonl"), convert_terms(args.xlsx))
    dump(os.path.join(args.out, "public_corpus.jsonl"), convert_corpus(args.xlsx))
    if os.path.exists(args.real):
        dump(os.path.join(args.out, "real_corpus.jsonl"), convert_real(args.real))
    else:
        print("skip real_corpus: not found", args.real)
    dump(os.path.join(args.out, "sources.jsonl"), convert_sources(args.xlsx))
    dump(os.path.join(args.out, "local_terms.jsonl"), convert_local_terms(args.xlsx))


if __name__ == "__main__":
    main()