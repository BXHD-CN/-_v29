# -*- coding: utf-8 -*-
import sys
sys.path.insert(0,"work/vector_db")
from search import SearchIndex
idx=SearchIndex()
for q in ["心肺复苏 胸外按压","病人喘不上气血氧低"]:
    print("Q:", q)
    for h in idx.search(q, k=5, source="term"):
        print("  %.3f %s | %s" % (h["score"], h["zh"], h["en"]))
