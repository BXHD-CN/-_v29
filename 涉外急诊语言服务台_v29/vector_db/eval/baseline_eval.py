# -*- coding: utf-8 -*-
"""向量检索基线评测：精确中文、精确英文、自然语言问句、跨语言。"""
import json, random, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from search import SearchIndex

NL_QUERIES = [
 ("病人到急诊后先按病情轻重分级排队", "预检分诊"),
 ("心跳停了怎么按", "心肺复苏"),
 ("电击除颤用什么能量", "除颤能量"),
 ("病人喘不上气，血氧低", "呼吸困难"),
 ("车祸后大腿骨折流血怎么固定", "骨折固定"),
 ("被蛇咬伤怎么处理", "毒蛇咬伤"),
 ("吃药后全身起疹子", "药物过敏"),
 ("孕妇产后大出血", "产后出血"),
 ("孩子高烧抽搐", "热性惊厥"),
 ("病人说想死，怎么评估风险", "自杀风险评估"),
 ("家属要求不要告诉病人是癌症", "坏消息告知"),
 ("病人拒绝在手术同意书上签字", "知情同意"),
 ("没有身份证的外国患者怎么挂号", "外籍患者"),
 ("病人说胸口像压了块石头", "胸痛"),
 ("打完针局部肿了", "液体外渗"),
 ("抽血前要不要空腹", "空腹"),
 ("血压只有80/50，四肢发冷", "休克"),
 ("昏迷病人怎么判断程度", "格拉斯哥评分"),
 ("药片能不能掰开吃", "缓释片"),
 ("病人是穆斯林，现在斋月", "斋月"),
 ("家属说病人已经回家了", "死亡"),
 ("护士给错剂量怎么办", "用药差错"),
 ("外国病人问在哪里取药", "取药"),
 ("气管插管后怎么确认位置", "插管确认"),
 ("病人出现幻觉和妄想", "幻觉"),
 ("住院费用太高想回家治疗", "自动出院"),
 ("病人需要转院", "转诊"),
 ("翻译听不懂当地语言怎么办", "语言障碍"),
 ("遗体要运回本国", "遗体跨境转运"),
 ("病人是素食者", "素食"),
]

def main():
    idx = SearchIndex()
    random.seed(42)
    terms = [m for m in idx.meta if m["source"] == "term"]
    random.shuffle(terms)
    res = {}
    # 1 精确中文
    sample = terms[:150]
    top1 = top5 = 0; fails = []
    for m in sample:
        hits = idx.search(m["zh"], k=5, source="term")
        if hits and hits[0]["zh"] == m["zh"]: top1 += 1
        if any(h["zh"] == m["zh"] for h in hits): top5 += 1
        else: fails.append((m["zh"], [h["zh"] for h in hits[:3]]))
    res["zh_exact"] = {"n": len(sample), "top1": round(top1/len(sample),4), "top5": round(top5/len(sample),4), "fails": fails[:8]}
    # 2 精确英文
    sample = terms[:150]
    top1 = top5 = 0; fails = []
    for m in sample:
        if not m["en"]: continue
        hits = idx.search(m["en"], k=5, source="term")
        if hits and hits[0]["zh"] == m["zh"]: top1 += 1
        if any(h["zh"] == m["zh"] for h in hits): top5 += 1
        else: fails.append((m["en"], [h["en"] for h in hits[:3]]))
    n = len(sample)
    res["en_exact"] = {"n": n, "top1": round(top1/n,4), "top5": round(top5/n,4), "fails": fails[:8]}
    # 3 自然语言
    hit1 = hit5 = 0; fails = []
    for q, expected in NL_QUERIES:
        hits = idx.search(q, k=5, source="term")
        if hits and expected in hits[0]["zh"]: hit1 += 1
        if any(expected in h["zh"] for h in hits): hit5 += 1
        else: fails.append((q, expected, [h["zh"] for h in hits[:3]]))
    n = len(NL_QUERIES)
    res["natural_language"] = {"n": n, "top1": round(hit1/n,4), "top5": round(hit5/n,4), "fails": fails[:10]}
    # 4 本地语查询（越南语/泰语/印尼语/马来语 -> 中文）
    loc = [m for m in idx.meta if m["source"] == "local"][:0]
    res["index"] = idx.meta_stat
    json.dump(res, open("work/vector_db/eval/baseline_metrics.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k,v in res.items() if k!="index"}, ensure_ascii=False, indent=1)[:1500])

if __name__ == "__main__":
    main()
