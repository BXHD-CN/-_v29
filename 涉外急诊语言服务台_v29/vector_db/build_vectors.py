# -*- coding: utf-8 -*-
"""从总库 V1.3 读取全部条目并向量化（char/word n-gram feature hashing + TF-IDF）。"""
import json, os, re, hashlib, math
import numpy as np
from openpyxl import load_workbook

DIM = 1024
OUT = "work/vector_db/index"
SRC = "work/merge/涉外急诊与东盟文化_中英术语语料总库_V1.3.xlsx"
os.makedirs(OUT, exist_ok=True)

CJK = re.compile(r"[\u4e00-\u9fff]+")
THAI = re.compile(r"[\u0E00-\u0E7F]+")
WORD = re.compile(r"[A-Za-z][A-Za-z\-]{1,30}")

def tokens(text):
    text = text or ""
    out = []
    for run in CJK.findall(text):
        L = len(run)
        for n in (2, 3):
            for i in range(L - n + 1):
                out.append("zh:" + run[i:i+n])
        if L == 1: out.append("zh1:" + run)
    for run in THAI.findall(text):
        L = len(run)
        for n in (2, 3):
            for i in range(L - n + 1):
                out.append("th:" + run[i:i+n])
    words = WORD.findall(text)
    low = [w.lower() for w in words]
    out.extend("en:" + w for w in low)
    for i in range(len(low) - 1):
        out.append("en2:" + low[i] + "_" + low[i+1])
    return out

def s(v):
    return "" if v is None else str(v)

def load_docs():
    wb = load_workbook(SRC, read_only=True, data_only=True)
    docs = []
    ws = wb["专业术语总表"]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[5]: continue
        zh, en = s(row[5]), s(row[6])
        txt = " ".join([zh, en, s(row[9]), s(row[10]), s(row[3]), s(row[4]), s(row[14])])
        docs.append(dict(source="term", doc_id="term-" + s(row[1]), zh=zh, en=en, text=txt,
                         domain=s(row[2]), scene=s(row[4]), parent=""))
    ws = wb["术语语料库"]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[5]: continue
        docs.append(dict(source="corpus", doc_id="corpus-" + s(row[0]), zh=s(row[2]), en=s(row[3]),
                         text=s(row[5]) + " " + s(row[6]), domain="", scene=s(row[8]), parent=s(row[1])))
    ws = wb["文化表达总表"]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[5]: continue
        txt = " ".join(s(x) for x in (row[5], row[9], row[10], row[7], row[8], row[13], row[14], row[15], row[4]))
        docs.append(dict(source="culture", doc_id="culture-" + s(row[1]), zh=s(row[10]), en=s(row[9]),
                         text=txt, domain=s(row[2]), scene=s(row[11]), country=s(row[4]), parent=""))
    ws = wb["东盟本地语对照"]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[6]: continue
        txt = " ".join(s(x) for x in (row[6], row[7], row[8], row[9], row[10], row[11], row[2]))
        docs.append(dict(source="local", doc_id="local-" + s(row[1]), zh=s(row[6]), en=s(row[7]),
                         text=txt, domain=s(row[2]), scene=s(row[5]), parent=""))
    ws = wb["真实语料试点"]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[3]: continue
        docs.append(dict(source="real", doc_id="real-" + s(row[1]), zh=s(row[3]), en=s(row[4]),
                         text=s(row[3]) + " " + s(row[4]) + " " + s(row[2]), domain=s(row[2]), scene="", parent=""))
    return docs

def main():
    docs = load_docs()
    N = len(docs)
    print("文档数", N)
    counts = []
    for d in docs:
        h = {}
        for t in tokens(d["text"] + " " + d["zh"] + " " + d["en"]):
            b = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16) % DIM
            h[b] = h.get(b, 0) + 1
        counts.append(h)
    df = np.zeros(DIM, dtype=np.float64)
    for h in counts:
        for b in h: df[b] += 1
    idf = (np.log((1.0 + N) / (1.0 + df)) + 1.0).astype(np.float32)
    V = np.zeros((N, DIM), dtype=np.float32)
    for i, h in enumerate(counts):
        row = V[i]
        for b, c in h.items():
            row[b] = (1.0 + math.log(c)) * idf[b]
        n = np.linalg.norm(row)
        if n > 0: row /= n
    np.save(os.path.join(OUT, "idf.npy"), idf)
    np.save(os.path.join(OUT, "vectors.npy"), V.astype(np.float16))
    with open(os.path.join(OUT, "meta.jsonl"), "w", encoding="utf-8") as f:
        for i, d in enumerate(docs):
            f.write(json.dumps({k: d.get(k, "") for k in ("source","doc_id","zh","en","domain","scene","country","parent")} | {"i": i, "text": d["text"][:400]}, ensure_ascii=False) + "\n")
    from collections import Counter
    stat = Counter(d["source"] for d in docs)
    json.dump({"dim": DIM, "docs": N, "sources": dict(stat),
               "method": "char/word n-gram feature hashing(md5,1024) + sublinear TF-IDF + L2",
               "source_workbook": SRC},
              open(os.path.join(OUT, "index_meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已保存", OUT, "维度", DIM, "MB", round(os.path.getsize(os.path.join(OUT,"vectors.npy"))/1024/1024,1))
    print(dict(stat))

if __name__ == "__main__":
    main()
