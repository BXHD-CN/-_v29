# -*- coding: utf-8 -*-
"""术语约束的机器翻译演示（MT + terminology constraints demo）。

用途
----
本脚本从总库 V1.3 的「术语」表（4154 条，work/vector_db/index）中，针对 30 句真实
急诊中文句子检索出「约束术语表」，作为译前术语注入（pre-translation term anchoring）
的输入。它不调用真实翻译 API（本环境没有 key），但保留了可直接替换的
translate_stub() 接口。

流程（与平台翻译流水线一一对应）
--------------------------------
    中文原句
      │  ① SearchIndex().search(sentence, k=8, source="term")   ← 本脚本
      │  ② score >= THRESHOLD 的术语 → 约束术语表（zh / en / doc_id）
      ▼
    译前：把约束术语表作为 glossary 注入翻译引擎
      │  ③ translate_stub()  ← 换成 DeepL / Google / 本地模型
      ▼
    英文译文
      │  ④ term_check.py：译后校验是否真的用上了库内推荐译法、是否踩了禁用译法
      ▼
    发布

依赖
----
    python work/vector_db/integration/mt_demo/mt_demo.py            # 表格输出
    python work/vector_db/integration/mt_demo/mt_demo.py --json     # JSON 输出
    python work/vector_db/integration/mt_demo/mt_demo.py --write    # 另存 mt_demo_output.json

如何把 translate_stub 换成真实引擎（按现有约束术语表接口）
----------------------------------------------------------
（1）DeepL
    import deepl
    tr = deepl.Translator(os.environ["DEEPL_KEY"])
    # 约束术语表先上传成 DeepL Glossary（CSV: 源词,目标词），每次任务复用
    glossary_id = tr.create_glossary(
        "ed-mt-terms", "ZH", "EN-US",
        entries={t["zh"]: t["en"] for t in constraints},
    ).glossary_id
    out = tr.translate_text(zh, source_lang="ZH", target_lang="EN-US",
                            glossary=glossary_id).text
    # 注意：DeepL 只对 glossary 中出现的源词做强制替换，句子改写仍由引擎完成；
    # 因此译后必须再跑 term_check.py 复核。

（2）Google Cloud Translation v3
    from google.cloud import translate_v3 as translate
    client = translate.TranslationServiceClient()
    glossary = translate.Glossary(
        name=glossary_path, language_codes_set={"language_codes": ["zh", "en"]},
        glossary_config=translate.GlossaryConfig(glossary=glossary_path),
    )
    resp = client.translate_text(
        request={
            "contents": [zh], "source_language_code": "zh",
            "target_language_code": "en",
            "parent": f"projects/{project}/locations/global",
            "glossary_config": translate.GlossaryConfig(glossary=glossary.name),
        }
    )
    out = resp.translations[0].translated_text

（3）本地模型（Opus-MT / NLLB / Qwen 等）
    # 方式 A：提示词注入（通用）
    system = "你是急诊医学翻译。必须严格使用给定术语译法，不得替换：\n" + \
             "\n".join(f"- {t['zh']} => {t['en']}" for t in constraints)
    user = f"把下面的急诊中文翻成英文：{zh}"
    out = local_llm.chat(system, user)
    # 方式 B：受限解码（更强约束，需模型 tokenizer 支持）
    #   HF: model.generate(..., force_words_ids=tokenizer(list_of_en_terms).input_ids)
    # 方式 C：译后用 term_check.py 做术语替换/回译校验（成本最低，兜底必做）

阈值（THRESHOLD）
------------------
0.45 是本次在 30 句上按「至少命中 1 条、平均 3–4 条」标定的经验值：
  - 调高 → 约束更少但更准，漏掉必要术语的风险上升；
  - 调低 → 召回更多，但会把同域近邻词（如「分诊记录」之于「分诊护士」）也塞进
    glossary，反而干扰译引擎。
上线时建议按科室/场景分别标定，并记录阈值版本号，便于回溯。
"""
import argparse
import json
import os
import sys

# 允许从任意工作目录运行：把 work/vector_db 加入 sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
# mt_demo/ -> integration/ -> vector_db/（search.py 所在目录）
_VECTOR_DB = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _VECTOR_DB)
from search import SearchIndex  # noqa: E402

K = 8                 # 每句召回候选术语数
THRESHOLD = 0.45      # 进入约束术语表的最低分（经验值，见文件头说明）
MAX_TERMS = 5         # 单句最多注入的术语数，防止 glossary 过长干扰译引擎

# 30 句，覆盖派单要求的五类：分诊 / 急救 / 用药 / 知情同意 / 文化禁忌
SENTENCES = [
    ("分诊", "高热患者到急诊先做预检分诊，护士按病情紧急程度安排就诊顺序"),
    ("分诊", "分诊护士需要记录患者到院时间和分级结果"),
    ("分诊", "胸痛患者走绿色通道，优先接诊并直接送抢救室"),
    ("分诊", "候诊患者病情加重时要重新评估并调整分级"),
    ("分诊", "患者没有家属陪同，需要确认身份并完成挂号"),
    ("分诊", "批量伤员到院时启动快速分诊，按颜色分级贴腕带"),
    ("急救", "患者心搏骤停，立即开始心肺复苏并胸外按压"),
    ("急救", "室颤患者需要电除颤，能量按双相波设定"),
    ("急救", "气道梗阻时用仰头抬颏法开放气道，必要时置入口咽通气管"),
    ("急救", "建立静脉通路并给予肾上腺素，随后气管插管"),
    ("急救", "复苏成功后转入目标温度管理并监测自主循环恢复"),
    ("急救", "救护车到达前先行院前急救，到院后交接病情"),
    ("用药", "缓释片必须整片吞服，不能掰开或嚼碎"),
    ("用药", "静脉滴注速度过快会引起不良反应，需要调整滴速"),
    ("用药", "患者服用华法林期间加用抗菌药物，注意药物相互作用"),
    ("用药", "配伍禁忌的药物不能加在同一瓶液体里"),
    ("用药", "用药交代要说明餐前还是餐后服用，以及漏服怎么处理"),
    ("用药", "高警示药品给药前须双人核对，胰岛素剂量要精确"),
    ("知情同意", "手术前要向患者说明手术风险、替代方案并签署手术知情同意书"),
    ("知情同意", "患者无民事行为能力，需要法定代理人签字"),
    ("知情同意", "病情危重时应及时下达病危通知并告知家属"),
    ("知情同意", "患者拒绝治疗，医生要说明后果并记录"),
    ("知情同意", "家属要求不要告诉患者癌症诊断，需要沟通告知策略"),
    ("知情同意", "输血前要签署输血知情同意书并完成交叉配血"),
    ("文化禁忌", "患者是穆斯林，要求清真饮食，用药前需要确认辅料来源并避免酒精"),
    ("文化禁忌", "患者正值斋月，白天禁食，降糖药需要调整到日出前和日落后"),
    ("文化禁忌", "耶和华见证人患者拒绝输血，需要提前说明并签署拒绝输血的文书"),
    ("文化禁忌", "患者信仰佛教长期素食，住院配餐不要给荤食"),
    ("文化禁忌", "医护人员需要了解宗教禁忌，查体前先说明避免冒犯患者"),
    ("文化禁忌", "家属希望遗体尽快火化，需要开具死亡证明并联系殡仪馆"),
]


def build_constraints(index, sentence):
    """① 检索候选术语 → ② 按阈值整理成约束术语表。"""
    hits = index.search(sentence, k=K, source="term")
    constraints = []
    for h in hits:
        if float(h["score"]) < THRESHOLD:
            continue
        constraints.append({
            "zh": h["zh"],
            "en": h["en"],
            "doc_id": h["doc_id"],
            "source": h["source"],      # 固定为 "term"
            "score": round(float(h["score"]), 3),
        })
        if len(constraints) >= MAX_TERMS:
            break
    return constraints


def translate_stub(zh, constraints):
    """占位翻译器：真实场景替换成 DeepL / Google / 本地模型（见文件头）。

    返回 (text, engine)。此处不做真实翻译，只把「译前句 + 约束术语」拼成可读占位，
    保证流水线其余环节（术语表注入、译后校验）可直接跑通。
    """
    glossary = "; ".join("%s => %s" % (c["zh"], c["en"]) for c in constraints) or "(无约束术语)"
    text = "[STUB] %s || glossary: %s" % (zh, glossary)
    return text, "stub-v0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="以 JSON 输出全部结果")
    ap.add_argument("--write", action="store_true", help="另存 mt_demo_output.json")
    args = ap.parse_args()

    index = SearchIndex()
    rows = []
    for i, (cat, sent) in enumerate(SENTENCES, 1):
        cons = build_constraints(index, sent)
        trans, engine = translate_stub(sent, cons)
        rows.append({
            "no": i, "category": cat, "source_zh": sent,
            "constraints": cons, "stub_translation": trans, "engine": engine,
        })

    total_terms = sum(len(r["constraints"]) for r in rows)
    covered = sum(1 for r in rows if r["constraints"])
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(len(r["constraints"]))
    summary = {
        "sentences": len(rows),
        "k": K,
        "threshold": THRESHOLD,
        "max_terms_per_sentence": MAX_TERMS,
        "total_constraint_terms": total_terms,
        "avg_terms_per_sentence": round(total_terms / len(rows), 2),
        "sentences_with_constraints": covered,
        "avg_terms_by_category": {k: round(sum(v) / len(v), 2) for k, v in by_cat.items()},
        "index_docs": len(index.meta),
        "term_docs": len([m for m in index.meta if m["source"] == "term"]),
    }

    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1))
    else:
        print("=" * 96)
        print("术语约束机器翻译演示｜索引 %d 条（term 表 %d 条）｜k=%d 阈值=%.2f 单句上限=%d"
              % (summary["index_docs"], summary["term_docs"], K, THRESHOLD, MAX_TERMS))
        print("=" * 96)
        print("%-4s %-8s %s" % ("序号", "类别", "译前（中文原句）"))
        print("-" * 96)
        for r in rows:
            print("%-4d %-8s %s" % (r["no"], r["category"], r["source_zh"]))
            if r["constraints"]:
                for c in r["constraints"]:
                    print("            ├─ %s → %s  [%s, %.3f]" % (c["zh"], c["en"], c["doc_id"], c["score"]))
            else:
                print("            └─ （无术语达到阈值 %.2f）" % THRESHOLD)
        print("-" * 96)
        print("汇总：%d 句；约束术语 %d 条；平均每句 %.2f 条；有约束句 %d/%d"
              % (summary["sentences"], total_terms, summary["avg_terms_per_sentence"],
                 covered, len(rows)))
        print("分类平均：", "；".join("%s %.2f 条" % (k, v) for k, v in summary["avg_terms_by_category"].items()))
        print("提示：当前 translate_stub 为占位实现，替换方式见文件头 docstring。")

    if args.write:
        out = os.path.join(_HERE, "mt_demo_output.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=1)
        print("\n已写出：%s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
