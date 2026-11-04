# -*- coding: utf-8 -*-
import sys; sys.path.insert(0,"work/vector_db")
from search import SearchIndex
idx=SearchIndex()
for q in ["CPR","ACS","GCS","心梗","打点滴","做CT"]:
    hits=idx.search(q,k=3,source="term")
    print(q, "->", " | ".join("%s(%.2f)"%(h["zh"],h["score"]) for h in hits))
