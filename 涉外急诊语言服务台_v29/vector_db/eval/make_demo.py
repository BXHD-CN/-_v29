# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0,"work/vector_db")
from search import SearchIndex
idx=SearchIndex()
queries=[("预检分诊","term"),("绿色通道","term"),("病人喘不上气血氧低",None),("triage","term"),
         ("配伍禁忌","term"),("斋月","culture"),("遗体跨境转运","term"),("缓释片","term"),
         ("家属说病人已经回家了",None),("bệnh nhân sốt cao","local")]
out=[]
for q,src in queries:
    hits=idx.search(q,k=5,source=src)
    out.append("### 查询：%s（source=%s）" % (q, src or "全部"))
    for h in hits:
        out.append("- %.3f [%s] %s / %s  (%s)" % (h["score"], h["source"], h["zh"], h["en"], h["doc_id"]))
    out.append("")
cmp=idx.compare("绿色通道", top_k=3)
out.append("### 译法对比：绿色通道")
for s,hits in cmp.items():
    out.append("[%s]" % s)
    for h in hits:
        out.append("  - %.3f %s / %s (%s)" % (h["score"], h["zh"], h["en"], h["doc_id"]))
open("work/vector_db/eval/demo_results.md","w",encoding="utf-8").write("\n".join(out))
print("ok", len(queries))
