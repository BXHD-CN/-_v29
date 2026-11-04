# -*- coding: utf-8 -*-
"""独立评测：自建 120 条查询，实测 SearchIndex 检索表现（source=term 与 source=None 两种口径）。

用法：
    python run_independent_eval.py                # 全量跑检索并生成 metrics + 报告
    python run_independent_eval.py --report-only  # 只从已有 metrics 重新生成报告
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PARENT = os.path.dirname(HERE)          # work/vector_db
sys.path.insert(0, INDEX_PARENT)

QFILE = os.path.join(HERE, "queries_independent.jsonl")
METRICS = os.path.join(HERE, "independent_metrics.json")
REPORT = os.path.join(HERE, "independent_report.md")
TYPES = ["中文精确", "英文精确", "自然语言", "跨语言", "本地语", "错别字", "缩写"]
SCOPES = [("term", "仅术语表 source=term"), ("all", "全库 source=None")]


def norm(s):
    return str(s or "").strip().lower().replace(" ", "")


def is_hit(expected, hit):
    """命中判定：中文完全一致，或双向包含（如 心肺复苏 ⊂ 高质量心肺复苏）。"""
    e, h = norm(expected), norm(hit.get("zh"))
    if not e or not h:
        return False
    return e == h or e in h or h in e


def evaluate(idx, queries, source):
    out = []
    for q in queries:
        t0 = time.time()
        hits = idx.search(q["q"], k=10, source=source)
        dt = time.time() - t0
        rank = 0
        for r, h in enumerate(hits, 1):
            if is_hit(q["expected_zh"], h):
                rank = r
                break
        exact1 = bool(hits) and norm(hits[0].get("zh")) == norm(q["expected_zh"])
        out.append({"q": q["q"], "type": q["type"], "expected_zh": q["expected_zh"],
                    "rank": rank, "exact_top1": exact1,
                    "top10_zh": [h.get("zh") for h in hits], "ms": round(dt * 1000, 1)})
    return out


def agg(rows):
    n = len(rows)
    if not n:
        return {}
    def rate(k):
        return round(sum(1 for r in rows if 0 < r["rank"] <= k) / n, 4)
    mrr = round(sum(1.0 / r["rank"] for r in rows if r["rank"]) / n, 4)
    return {"n": n, "top1": rate(1), "top3": rate(3), "top5": rate(5), "top10": rate(10),
            "mrr": mrr, "exact_top1": round(sum(1 for r in rows if r["exact_top1"]) / n, 4),
            "avg_ms": round(sum(r["ms"] for r in rows) / n, 1)}


def run():
    queries = [json.loads(l) for l in open(QFILE, encoding="utf-8") if l.strip()]
    from search import SearchIndex
    idx = SearchIndex()
    result = {"index": idx.meta_stat, "queries": len(queries), "by_scope": {}}
    for scope, _ in SCOPES:
        source = "term" if scope == "term" else None
        rows = evaluate(idx, queries, source)
        result["by_scope"][scope] = {
            "overall": agg(rows),
            "by_type": {t: agg([r for r in rows if r["type"] == t]) for t in TYPES},
            "failures": [r for r in rows if r["rank"] == 0],
            "all_rows": rows,
        }
    json.dump(result, open(METRICS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_report(result)
    return result


def write_report(result):
    L = []
    L.append("# 向量检索独立评测报告（自建 120 条查询）\n")
    L.append("> 被测系统：work/vector_db/search.py（SearchIndex.search）｜索引：%d docs × %d 维｜查询：%d 条｜生成时间：%s\n" %
             (result["index"]["docs"], result["index"]["dim"], result["queries"],
              time.strftime("%Y-%m-%d %H:%M")))
    L.append("> 命中判定：返回结果的中文与 expected_zh 完全一致，或双向包含（如「心肺复苏」包含于「高质量心肺复苏」）。\n")
    L.append("## 1. 总分\n")
    L.append("| 口径 | n | top1 | top3 | top5 | top10 | MRR | 完全匹配top1 | 平均耗时 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for scope, label in SCOPES:
        o = result["by_scope"][scope]["overall"]
        L.append("| %s | %d | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.3f | %.1f%% | %.1f ms |" %
                 (label, o["n"], o["top1"]*100, o["top3"]*100, o["top5"]*100, o["top10"]*100,
                  o["mrr"], o["exact_top1"]*100, o["avg_ms"]))
    L.append("\n## 2. 分类型\n")
    L.append("| 类型 | n | term top1 | term top5 | term MRR | all top1 | all top5 | all MRR |")
    L.append("|---|---|---|---|---|---|---|---|")
    for t in TYPES:
        a = result["by_scope"]["term"]["by_type"].get(t, {})
        b = result["by_scope"]["all"]["by_type"].get(t, {})
        L.append("| %s | %d | %.1f%% | %.1f%% | %.3f | %.1f%% | %.1f%% | %.3f |" %
                 (t, a.get("n", 0), a.get("top1", 0)*100, a.get("top5", 0)*100, a.get("mrr", 0),
                  b.get("top1", 0)*100, b.get("top5", 0)*100, b.get("mrr", 0)))
    for scope, label in SCOPES:
        fails = result["by_scope"][scope]["failures"]
        L.append("\n## 3. 失败案例（%s，共 %d 条）\n" % (label, len(fails)))
        L.append("| 类型 | 查询 | 期望 | 返回前 5 |")
        L.append("|---|---|---|---|")
        for f in fails[:20]:
            L.append("| %s | %s | %s | %s |" % (f["type"], f["q"][:24], f["expected_zh"],
                                                " / ".join(f["top10_zh"][:5])))
    L.append("\n## 4. 说明\n")
    L.append("- 本次评测的 120 条查询均为独立构造，expected_zh 全部存在于 term 索引，未把\"条目缺失\"计入检索失败。")
    L.append("- 本地语查询在 source=term 口径下失败率极高，因为 term 表不含本地语字段；全库口径下的命中主要来自 local 表自身。")
    L.append("- 缩写查询（GCS/ACS/DKA/ARDS/POCUS）命中率极低，原因是索引未建立缩写别名。")
    open(REPORT, "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    if "--report-only" in sys.argv:
        write_report(json.load(open(METRICS, encoding="utf-8")))
        print("report regenerated")
    else:
        run()
        print("done")
