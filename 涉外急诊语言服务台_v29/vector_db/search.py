# -*- coding: utf-8 -*-
"""统一向量检索：术语、语料、文化表达、本地语、真实语料。
用法：
    python search.py "预检分诊" --k 8
    python search.py "triage" --source term --k 5
    python search.py "分诊" --compare
"""
import json, os, re, hashlib, math, argparse
import numpy as np

CJK = re.compile(r"[\u4e00-\u9fff]+")
THAI = re.compile(r"[\u0E00-\u0E7F]+")
WORD = re.compile(r"[A-Za-z][A-Za-z\-]{1,30}")
SOURCES = ("term", "corpus", "culture", "local", "real")

def _tokens(text):
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
    low = [w.lower() for w in WORD.findall(text)]
    out.extend("en:" + w for w in low)
    for i in range(len(low) - 1):
        out.append("en2:" + low[i] + "_" + low[i+1])
    return out

class SearchIndex:
    def __init__(self, index_dir=None):
        self.dir = index_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "index")
        self.idf = np.load(os.path.join(self.dir, "idf.npy"))
        self.V = np.load(os.path.join(self.dir, "vectors.npy")).astype(np.float32)
        self.meta = [json.loads(l) for l in open(os.path.join(self.dir, "meta.jsonl"), encoding="utf-8") if l.strip()]
        self.dim = self.V.shape[1]
        self.by_source = {}
        for m in self.meta:
            self.by_source.setdefault(m["source"], []).append(m["i"])
        self.meta_stat = json.load(open(os.path.join(self.dir, "index_meta.json"), encoding="utf-8"))
        ap = os.path.join(self.dir, "aliases.json")
        self.aliases = json.load(open(ap, encoding="utf-8")) if os.path.exists(ap) else {}
        self.term_zh = {str(m["zh"]).strip() for m in self.meta if m["source"] == "term"}
        self.term_en = {str(m["en"]).strip().lower() for m in self.meta if m["source"] == "term"}
        self._tok_idf = None

    def _build_tok_idf(self):
        """为词面重合打分准备 token 级 IDF，压制高频道字噪声（如 血氧/血压/素）。"""
        import math as _m
        texts = [m["text"] for m in self.meta if m["source"] == "term"]
        df = {}
        for t in texts:
            for tok in set(self._lex_tokens(t)):
                df[tok] = df.get(tok, 0) + 1
        N = len(texts)
        self._tok_idf = {k: _m.log((1.0 + N) / (1.0 + v)) + 1.0 for k, v in df.items()}

    def expand(self, query):
        """口语/别名扩展：把患者口语映射到规范术语，拼进检索词；精确术语查询不扩展。"""
        qn = query.strip()
        if qn in self.term_zh or qn.lower() in self.term_en:
            return query
        extra = []
        for k, vals in getattr(self, "aliases", {}).items():
            if k in query:
                extra.extend(vals)
        return query + (" " + " ".join(dict.fromkeys(extra)) if extra else "")

    def _lex_tokens(self, text):
        text = text or ""
        toks = []
        for run in CJK.findall(text):
            L = len(run)
            for n in (1, 2, 3):
                for i in range(L - n + 1):
                    toks.append("z" + str(n) + ":" + run[i:i+n])
        low = [w.lower() for w in WORD.findall(text)]
        toks.extend("e:" + w for w in low)
        return toks

    def _lex_score(self, query, doc_text):
        q = self._lex_tokens(query)
        if not q: return 0.0
        if self._tok_idf is None:
            self._build_tok_idf()
        d = {}
        for t in self._lex_tokens(doc_text):
            d[t] = d.get(t, 0) + 1
        s = 0.0
        for t in q:
            c = d.get(t, 0)
            if c:
                w = 1.0 if t.startswith(("z2", "z3", "e")) else 0.35
                s += w * self._tok_idf.get(t, 1.0) * (1.0 + math.log(c))
        return s / ((len(q) ** 0.5) * (len(d) ** 0.25 + 1e-6))

    def _norm(self, a):
        m = float(np.max(a)) if len(a) else 0.0
        return a / m if m > 0 else a

    def encode(self, text):
        h = {}
        for t in _tokens(text):
            b = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16) % self.dim
            h[b] = h.get(b, 0) + 1
        v = np.zeros(self.dim, dtype=np.float32)
        for b, c in h.items():
            v[b] = (1.0 + math.log(c)) * self.idf[b]
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def search(self, query, k=10, source=None, min_score=0.0, boost_exact=True, hybrid=True):
        query = self.expand(query)
        q = self.encode(query)
        if source and source in self.by_source:
            idx = np.array(self.by_source[source])
        else:
            idx = np.arange(len(self.meta))
        if len(idx) == 0: return []
        vec = self.V[idx] @ q
        scores = 0.45 * vec + 0.55 * self._norm(vec) * 0.0 + 0.0 * vec  # placeholder overwritten below
        scores = 0.45 * vec
        if hybrid:
            topn = min(300, len(idx))
            top_idx = np.argsort(-vec)[:topn]
            lex = np.array([self._lex_score(query, self.meta[int(idx[j])]["text"]) for j in top_idx], dtype=np.float32)
            mx = lex.max() if len(lex) and lex.max() > 0 else 1.0
            lexn = lex / mx
            scores = 0.45 * vec
            scores[top_idx] = 0.45 * vec[top_idx] + 0.55 * lexn * 0.9
        if boost_exact:
            qn = query.strip().lower()
            for j, i in enumerate(idx):
                m = self.meta[i]
                zh = str(m["zh"]).strip().lower(); en = str(m["en"]).strip().lower()
                if qn and (qn == zh or qn == en):
                    scores[j] += 0.35
                elif zh and len(zh) >= 2 and zh in qn:
                    scores[j] += min(0.45, 0.10 * len(zh))
                elif en and len(en) >= 3 and en in qn:
                    scores[j] += 0.25
                elif qn and (qn in zh or qn in en):
                    scores[j] += 0.12
        order = np.argsort(-scores)[:k]
        out = []
        for j in order:
            sc = float(scores[j])
            if sc < min_score: continue
            m = dict(self.meta[int(idx[j])])
            m["score"] = round(sc, 4)
            out.append(m)
        return out

    def get(self, doc_id):
        for m in self.meta:
            if m["doc_id"] == doc_id: return m
        return None

    def compare(self, term, top_k=5):
        """同一概念在五张表中的不同说法，用于译法对比与一致性核查。"""
        groups = {}
        for src in SOURCES:
            hits = self.search(term, k=top_k, source=src, boost_exact=True)
            if hits:
                groups[src] = hits
        return groups

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--source", default=None, choices=SOURCES + (None,))
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    idx = SearchIndex()
    if a.compare:
        res = idx.compare(a.query, top_k=a.k)
        for src, hits in res.items():
            print("[%s]" % src)
            for h in hits:
                print("   %.3f  %s | %s | %s" % (h["score"], h["zh"], h["en"], h["doc_id"]))
    else:
        hits = idx.search(a.query, k=a.k, source=a.source)
        if a.json:
            print(json.dumps(hits, ensure_ascii=False, indent=1))
        else:
            for h in hits:
                print("%.3f\t%s\t%s\t%s\t%s" % (h["score"], h["source"], h["zh"], h["en"], h["doc_id"]))
