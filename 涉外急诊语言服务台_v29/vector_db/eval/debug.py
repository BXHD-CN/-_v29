# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0,"work/vector_db")
from search import SearchIndex
idx=SearchIndex()
for q in ["心肺复苏 胸外按压","心肺复苏","预检分诊 分级"]:
    print("Q:", q)
    for h in idx.search(q, k=6, source="term", hybrid=True):
        print("  %.3f %s | %s" % (h["score"], h["zh"], h["en"]))
    print(" -- no hybrid --")
    for h in idx.search(q, k=6, source="term", hybrid=False):
        print("  %.3f %s | %s" % (h["score"], h["zh"], h["en"]))
