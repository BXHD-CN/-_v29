# -*- coding: utf-8 -*-
"""术语一致性检查器（译后校验）。

在「术语约束机器翻译」流水线里，本脚本位于译后环节：
    中文原句 ──(mt_demo.py 检索)──▶ 约束术语表 ──(译引擎)──▶ 英文译文
                                                                  │
                                                        term_check.py（本脚本）
                                                                  ▼
                                     未使用推荐译法 / 命中禁用译法 的术语清单 + 修改建议
                                                                  │
                                                     人工抽检 or 自动回退重译

它做两件事：
  1. 用 SearchIndex 从同一个术语表（term，4154 条）检索出该句应遵守的约束术语；
  2. 逐条检查英文译文：
       - 是否使用了库内推荐译法（容忍词形变化：triaged / defibrillated 等）；
       - 是否踩了该术语的常见错译（BANNED，按整句子串匹配）。
     未使用 → ⚠️；命中禁用译法 → ❌（优先级更高，直接拦截）。

用法：
    python term_check.py --demo                       # 跑内置 3 个示例
    python term_check.py "胸痛患者走绿色通道" "Chest pain patients go through the green channel."
    python term_check.py --file pairs.jsonl           # 每行 {"zh":..., "en":...}
    python term_check.py ... --json                   # 机器可读输出

流水线接入建议
--------------
- 译后自动跑本脚本；❌ 条目阻断发布并回退重译（带上 ❌ 的修正建议再译一次）。
- ⚠️ 条目进入人工抽检队列，按科室统计 top 错译术语，反哺术语表与提示词。
- 与 mt_demo.py 共用 K / THRESHOLD，保证「译前注入的术语」与「译后检查的术语」同源。
"""
import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_VECTOR_DB = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _VECTOR_DB)
from search import SearchIndex  # noqa: E402

K = 8
THRESHOLD = 0.45          # 与 mt_demo.py 保持一致，保证译前/译后同源
MAX_TERMS = 5             # 与 mt_demo.py 保持一致
# 精度过滤：只强制检查「原句里真的出现该中文术语」的条目，或分数极高的强匹配。
# 否则检索会带进同域近邻词（如「优先检查」之于「优先通道」），产生大量假警告。
REQUIRE_ATTESTED = True
STRONG_SCORE = 0.85

STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "with", "and", "or",
        "by", "at", "from", "as", "is", "are", "be", "it", "that", "this"}

# 每个术语的「禁用译法」：这些是真实 MT / 人工译员最常犯的错，命中即拦截。
# key 用术语表 doc_id，避免中文改名后失效。
BANNED = {
    "term-T-0001": ["pre-examination classification", "injury classification",
                    "preliminary screening", "preliminary classification"],
    "term-T-0182": ["green channel", "green passage", "green route"],
    "term-T-1153": ["electric shock", "electrical shock"],
    "term-T-1180": ["head lifting method", "chin lifting technique", "head-up chin-lift"],
    "term-T-2845": ["slow-release tablet", "slow release tablet", "sustained-release tablet"],
    "term-T-1392": ["contraindication", "contra-indication"],
    "term-T-3478": ["consent agreement", "notification consent", "informed agreement"],
    "term-T-2585": ["bad news notification", "notification of bad news"],
    "term-T-2695": ["religious contraindication", "religious prohibition"],
    "term-T-2986": ["high-risk drug", "high-risk medicine", "dangerous drug", "high-warning drug"],
    "term-T-4040": ["burning of the body", "burn the corpse", "incineration of the body"],
}


def _words(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _stem(w):
    """极简词形归并：defibrillation / defibrillated 视为同词。"""
    for suf in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def term_used(expected_en, translation):
    """译文是否覆盖推荐译法的核心词（≥80%）。"""
    ew = [_stem(w) for w in _words(expected_en) if w not in STOP]
    if not ew:
        return True
    tw = {_stem(w) for w in _words(translation)}
    tw.update({w[: max(4, len(w) - 2)] for w in _words(translation)})
    hit = sum(1 for w in ew if w in tw or any(t.startswith(w) for t in tw))
    return hit / len(ew) >= 0.8


def banned_hit(doc_id, translation):
    low = " ".join(_words(translation))
    for bad in BANNED.get(doc_id, []):
        b = " ".join(_words(bad))
        if b and b in low:
            return bad
    return None


def check(index, zh, en):
    """返回一句话的术语一致性检查结果（dict，便于流水线消费）。"""
    hits = index.search(zh, k=K, source="term")
    constraints = []
    for h in hits:
        if float(h["score"]) < THRESHOLD:
            continue
        attested = str(h["zh"]) in zh or float(h["score"]) >= STRONG_SCORE
        if REQUIRE_ATTESTED and not attested:
            continue
        constraints.append(h)
        if len(constraints) >= MAX_TERMS:
            break
    results, missing, banned = [], [], []
    for c in constraints:
        bad = banned_hit(c["doc_id"], en)
        used = term_used(c["en"], en)
        status = "banned" if bad else ("ok" if used else "missing")
        row = {
            "zh": c["zh"], "expected_en": c["en"], "doc_id": c["doc_id"],
            "score": round(float(c["score"]), 3), "status": status,
        }
        if bad:
            row["banned_phrase"] = bad
            row["suggestion"] = "把 %s 改为 %s" % (bad, c["en"])
            banned.append(row)
        elif not used:
            row["suggestion"] = "译文中加入库内推荐译法 %s" % c["en"]
            missing.append(row)
        results.append(row)
    return {
        "zh": zh, "en": en,
        "constraints": results,
        "missing": missing,
        "banned": banned,
        "ok_count": len(results) - len(missing) - len(banned),
        "pass": not missing and not banned,
    }


def render(report):
    lines = ["原句：%s" % report["zh"], "译文：%s" % report["en"], ""]
    if not report["constraints"]:
        lines.append("（本句没有达到阈值的约束术语，跳过）")
        return "\n".join(lines)
    for r in report["constraints"]:
        if r["status"] == "ok":
            lines.append("  [OK]   %s → %s（%s）已使用" % (r["zh"], r["expected_en"], r["doc_id"]))
        elif r["status"] == "missing":
            lines.append("  [WARN] %s → %s（%s）未使用；建议：%s"
                         % (r["zh"], r["expected_en"], r["doc_id"], r["suggestion"]))
        else:
            lines.append("  [FAIL] %s → 命中禁用译法 “%s”；建议：%s"
                         % (r["zh"], r["banned_phrase"], r["suggestion"]))
    lines.append("")
    lines.append("结论：%s（已用 %d / 未用 %d / 禁用 %d）"
                 % ("通过" if report["pass"] else "需修改",
                    report["ok_count"], len(report["missing"]), len(report["banned"])))
    return "\n".join(lines)


DEMO = [
    ("胸痛患者走绿色通道，优先接诊并直接送抢救室",
     "Chest pain patients go through the green channel for priority reception and are sent straight to the resuscitation room."),
    ("配伍禁忌的药物不能加在同一瓶液体里",
     "Drugs with a contraindication must not be added to the same bottle of fluid."),
    ("缓释片必须整片吞服，不能掰开或嚼碎",
     "The slow-release tablet must be swallowed whole and must not be split or chewed."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zh", nargs="?")
    ap.add_argument("en", nargs="?")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--file", help="JSONL，每行 {zh, en}")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-attested", action="store_true",
                    help="关闭精度过滤，检查全部达到阈值的检索结果")
    args = ap.parse_args()
    global REQUIRE_ATTESTED
    if args.no_attested:
        REQUIRE_ATTESTED = False

    index = SearchIndex()
    pairs = []
    if args.demo:
        pairs = DEMO
    elif args.file:
        pairs = [(r["zh"], r["en"]) for r in
                 (json.loads(l) for l in open(args.file, encoding="utf-8") if l.strip())]
    elif args.zh and args.en:
        pairs = [(args.zh, args.en)]
    else:
        ap.error("请给 --demo、--file 或「中文 英文」两个位置参数")

    reports = [check(index, zh, en) for zh, en in pairs]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=1))
        return 0
    for i, rep in enumerate(reports, 1):
        print("=" * 88)
        print("示例 %d" % i if args.demo else "检查 %d" % i)
        print(render(rep))
    bad = sum(1 for r in reports if not r["pass"])
    print("=" * 88)
    print("合计 %d 句，%d 句需修改。" % (len(reports), bad))
    # --demo 是教学示例（故意含错译），恒返回 0；正常校验按结果返回 1
    return 0 if args.demo else (1 if bad else 0)


if __name__ == "__main__":
    sys.exit(main())
