# -*- coding: utf-8 -*-
"""把 V1.3 总库的「文化表达总表」「英语变体转写」转换为站点可直接导入的 JSONL。

这两张表原先未进入站点（convert_v13.py 只读 4 张表），本脚本补齐：
  culture.jsonl           738 条  东盟文化表达与禁忌表达
  english_variants.jsonl  150 条  东盟英语变体整句改写

用法：
  python scripts/convert_culture.py --xlsx "../merge/涉外急诊与东盟文化_中英术语语料总库_V1.3.xlsx" --out data
"""
import argparse
import json
import os

import openpyxl

CULTURE_HEADER = ["序号", "编号", "类型", "子类", "国家", "原词/原表达", "语言", "字面义",
                  "直译风险", "推荐英文", "推荐中文", "使用场景", "禁忌级别",
                  "语用与禁忌提示", "中文例句", "英文例句", "来源代号", "来源文件"]
VARIANT_HEADER = ["序号", "编号", "变体", "国家", "原句", "变体特征", "直译成中文",
                  "标准英语", "医疗场景改写", "语气与礼貌提示", "中文意思", "来源代号"]

# 禁忌级别归一：表内取值为 红 / 橙 / 黄 / 无
LEVEL_ORDER = {"红": 1, "橙": 2, "黄": 3, "无": 4}


def _rows(ws, header):
    it = ws.iter_rows(values_only=True)
    head = [str(c).strip() if c is not None else "" for c in next(it)]
    idx = {name: i for i, name in enumerate(head)}
    for row in it:
        if row is None or all(c is None for c in row):
            continue
        yield {name: (row[idx[name]] if idx.get(name) is not None and idx[name] < len(row) else None)
               for name in header}


def _s(value, limit=None):
    text = "" if value is None else str(value).strip()
    if limit:
        text = text[:limit]
    return text


def convert_culture(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["文化表达总表"]
    out = []
    for r in _rows(ws, CULTURE_HEADER):
        expr_id = _s(r["编号"])
        original = _s(r["原词/原表达"])
        if not expr_id or not original:
            continue
        level = _s(r["禁忌级别"]) or "无"
        out.append({
            "expr_id": expr_id,
            "ctype": _s(r["类型"]),
            "subcategory": _s(r["子类"]),
            "country": _s(r["国家"]),
            "original": original[:255],
            "original_lang": _s(r["语言"]),
            "literal_zh": _s(r["字面义"]),
            "risk": _s(r["直译风险"]),
            "rec_en": _s(r["推荐英文"], 512),
            "rec_zh": _s(r["推荐中文"], 255),
            "scene": _s(r["使用场景"]),
            "taboo_level": level if level in LEVEL_ORDER else "无",
            "usage_note": _s(r["语用与禁忌提示"]),
            "example_zh": _s(r["中文例句"]),
            "example_en": _s(r["英文例句"]),
            "source_code": _s(r["来源代号"]),
            "source_file": _s(r["来源文件"], 255),
        })
    return out


def convert_variants(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["英语变体转写"]
    out = []
    for r in _rows(ws, VARIANT_HEADER):
        variant_id = _s(r["编号"])
        original = _s(r["原句"])
        if not variant_id or not original:
            continue
        out.append({
            "variant_id": variant_id,
            "variant": _s(r["变体"]),
            "country": _s(r["国家"]),
            "original": original,
            "features": _s(r["变体特征"]),
            "literal_zh": _s(r["直译成中文"]),
            "standard_en": _s(r["标准英语"]),
            "medical_en": _s(r["医疗场景改写"]),
            "register_note": _s(r["语气与礼貌提示"]),
            "meaning_zh": _s(r["中文意思"]),
            "source_code": _s(r["来源代号"]),
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
    ap.add_argument("--out", default="data")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    dump(os.path.join(args.out, "culture.jsonl"), convert_culture(args.xlsx))
    dump(os.path.join(args.out, "english_variants.jsonl"), convert_variants(args.xlsx))


if __name__ == "__main__":
    main()
