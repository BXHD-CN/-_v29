# -*- coding: utf-8 -*-
"""患者情况告知单（一级功能，与翻译平级；需注册登录后使用）。

定位（与原有「检查结论」版本完全不同）：
- 把患者圈选 / 输入的内容**结构化整理后转达给医生**，让医生在接诊前
  一眼看清「哪里不舒服、怎么不舒服、多久多疼什么样、患者原话怎么说」；
- 覆盖「问诊沟通」与「病例录入」两个场景；
- **不是**语言质量评估：不输出准确性 / 清晰度 / 跨文化适配性等级，
  不给「建议补充 / 待澄清」这类信息问题，也不做文化风险澄清；
- **不产出任何译文**：不调用 /api/translate，不下发 translation / rec_en /
  standard_en / medical_en / example_en / target_text / segments 等字段；
- 患者原话与圈选标签一律照录、不翻译；界面文案按 X-Lang 输出中 / 英两套。
"""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..i18n import lang_of

router = APIRouter(prefix="/api", tags=["patient-handoff"])

SCENE_LABEL = {"consultation": "问诊沟通", "record": "病例录入"}
SCENE_LABEL_EN = {"consultation": "Consultation", "record": "Case documentation"}
SCENE_PURPOSE = {
    "consultation": "供医生在面对面分诊 / 病史采集前快速浏览",
    "record": "供病历文书客观记录与留痕",
}
SCENE_PURPOSE_EN = {
    "consultation": "For the clinician to skim before face-to-face triage / history taking",
    "record": "For objective documentation and audit trail in medical records",
}

# 症状细节 -> 临床交接分组（与前端圈选项逐字一致）
DETAIL_GROUP: Dict[str, str] = {
    "突发": "time", "持续性": "time", "间歇性": "time", "慢性疼痛": "time",
    "反复发作": "time", "夜间加重": "time", "逐渐加重": "time",
    "轻微": "degree", "中度": "degree", "剧痛": "degree", "难以忍受": "degree",
    "钝痛": "nature", "刺痛/锐痛": "nature", "胀痛": "nature", "烧灼痛": "nature",
    "绞痛": "nature", "压迫感": "nature", "放射痛": "nature",
    "活动后加重": "trigger", "休息缓解": "trigger", "按压加重": "trigger",
    "体位相关": "trigger", "进食相关": "trigger",
    "伴发热": "associated", "伴呕吐": "associated", "伴出汗": "associated",
    "伴麻木": "associated", "伴呼吸困难": "associated",
}
GROUP_ORDER = ["time", "degree", "nature", "trigger", "associated"]
GROUP_LABEL = {
    "time": "时间进程", "degree": "程度", "nature": "性质",
    "trigger": "诱因 / 缓解", "associated": "伴随症状",
}
GROUP_LABEL_EN = {
    "time": "Time course", "degree": "Severity", "nature": "Nature",
    "trigger": "Triggers / relief", "associated": "Associated symptoms",
    "other": "Other",
}

# 同语言内的部位书写规范化，仅用于让「主诉」读起来像临床交接用语，不是翻译。
PART_NORM = {
    "胸": "胸部", "上腹": "上腹部", "下腹": "下腹部", "腰背": "腰背部",
    "眼": "眼部", "耳": "耳部", "颈": "颈部", "肩": "肩部",
    "手/腕": "手 / 腕部", "足/踝": "足 / 踝部", "膝": "膝部", "髋": "髋部",
}

DISCLAIMER = (
    "本单只是把患者自述内容按临床交接习惯整理后转达给医生，"
    "不翻译、不诊断、不评估表达质量、不澄清文化或信息问题；"
    "患者原话照录，未作改写。本单不替代医护问诊、病史核实与专业判断。"
)
DISCLAIMER_EN = (
    "This sheet only organises the patient's own account following clinical handoff "
    "conventions and relays it to the clinician. It does not translate, diagnose, "
    "judge expression quality, or clarify cultural or information issues. The patient's "
    "own words are recorded verbatim. It does not replace clinical interviewing, "
    "history verification or professional judgement."
)

TEXT = {
    "zh": {
        "title": "患者情况告知单",
        "empty": "尚未采集到患者内容，请先圈选或填写至少一项，再生成给医生的告知单。",
        "not_mentioned": "未提及", "not_filled": "未填写", "not_specified": "未限定",
        "no_complaint": "患者尚未描述具体不适",
        "handoff_title": "【患者情况告知单 · {scene}】",
        "chief": "主诉：", "part": "01  不适部位：", "symptom": "02  不适症状：",
        "detail": "03  症状细节：", "quote": "04  患者原话（照录）：",
        "country": "05  沟通对象文化 / 国家：", "other": "其他：",
        "relay": "患者自述的结构化转达，未翻译、未诊断。",
        "section_part": "不适部位", "section_symptom": "不适症状",
        "section_detail": "症状细节", "section_quote": "患者原话（照录）",
        "section_country": "沟通对象文化 / 国家",
        "chief_prefix": "自述", "chief_part": "不适", "chief_with": "，伴",
        "chief_features": "症状特征：",
        "separator": "；", "period": "。", "joiner": "、",
    },
    "en": {
        "title": "Patient Handoff Sheet",
        "empty": "Nothing collected yet. Select or type at least one item before generating the handoff sheet for the clinician.",
        "not_mentioned": "Not mentioned", "not_filled": "Not provided", "not_specified": "Not specified",
        "no_complaint": "Patient has not described a specific complaint",
        "handoff_title": "[Patient Handoff Sheet · {scene}]",
        "chief": "Chief complaint: ", "part": "01  Affected areas: ", "symptom": "02  Symptoms: ",
        "detail": "03  Symptom details:", "quote": "04  Patient's own words (verbatim): ",
        "country": "05  Communication partner culture / country: ", "other": "Other: ",
        "relay": "Structured relay of the patient's own account; not translated, not diagnosed.",
        "section_part": "Affected areas", "section_symptom": "Symptoms",
        "section_detail": "Symptom details", "section_quote": "Patient's own words (verbatim)",
        "section_country": "Communication partner culture / country",
        "chief_prefix": "Reports ", "chief_part": " discomfort", "chief_with": ", with ",
        "chief_features": "Symptom features: ",
        "separator": "; ", "period": ".", "joiner": ", ",
    },
}


def _t(lang: str) -> dict:
    return TEXT["en" if lang == "en" else "zh"]


class HandoffIn(BaseModel):
    """与前端采集表逐字段对应；路径沿用 /api/patient-check 以兼容已发布链接。"""
    scene: str = Field(default="consultation", max_length=24)
    parts: List[str] = Field(default_factory=list, max_length=24)
    part_other: str = Field(default="", max_length=200)
    symptoms: List[str] = Field(default_factory=list, max_length=24)
    symptom_other: str = Field(default="", max_length=200)
    details: List[str] = Field(default_factory=list, max_length=48)
    detail_other: str = Field(default="", max_length=200)
    free_text: str = Field(default="", max_length=1000)
    country: str = Field(default="", max_length=32)


def _merge(items: List[str], other: str) -> List[str]:
    merged = [str(x).strip() for x in (items or []) if str(x).strip()]
    extra = (other or "").strip()
    if extra:
        merged.append(extra)
    return merged


def _join(items: List[str], lang: str) -> str:
    t = _t(lang)
    return t["joiner"].join(items) if items else t["not_mentioned"]


def _norm_parts(parts: List[str]) -> str:
    return "、".join(PART_NORM.get(p, p) for p in parts) if parts else ""


def _group_details(details: List[str], detail_other: str) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {key: [] for key in GROUP_ORDER}
    extra: List[str] = []
    for item in details:
        key = DETAIL_GROUP.get(item)
        if key:
            grouped[key].append(item)
        else:
            extra.append(item)
    other = (detail_other or "").strip()
    if other:
        extra.append(other)
    if extra:
        grouped.setdefault("other", []).extend(extra)
    return grouped


def _chief_complaint(parts: List[str], symptoms: List[str],
                     details: List[str], detail_other: str, lang: str) -> str:
    """把散乱的自述拼成一句医生能直接读的主诉（同语言，不翻译患者内容）。"""
    t = _t(lang)
    segments: List[str] = []
    part_text = _norm_parts(parts)
    symptom_text = _join(symptoms, lang) if symptoms else ""
    if part_text and symptom_text:
        segments.append(part_text + t["chief_part"] + t["chief_with"] + symptom_text)
    elif part_text:
        segments.append(part_text + t["chief_part"])
    elif symptom_text:
        segments.append(t["chief_prefix"] + symptom_text)
    detail_all = _merge(details, detail_other)
    if detail_all:
        segments.append(t["chief_features"] + _join(detail_all, lang))
    return t["separator"].join(segments) + t["period"] if segments else ""


def _build_lines(payload: HandoffIn, parts: List[str], symptoms: List[str],
                 grouped: Dict[str, List[str]], chief: str, lang: str,
                 scene: str) -> List[str]:
    t = _t(lang)
    lines = [
        t["handoff_title"].format(scene=scene),
        "────────────────────────",
        t["chief"] + (chief or t["no_complaint"]),
        "",
        t["part"] + _join(parts, lang),
        t["symptom"] + _join(symptoms, lang),
        t["detail"],
    ]
    any_detail = False
    for key in GROUP_ORDER:
        values = grouped.get(key) or []
        if values:
            any_detail = True
            label = GROUP_LABEL_EN[key] if lang == "en" else GROUP_LABEL[key]
            lines.append("      " + label + "：" + t["joiner"].join(values))
    other = grouped.get("other") or []
    if other:
        any_detail = True
        lines.append("      " + t["other"] + t["joiner"].join(other))
    if not any_detail:
        lines.append("      " + t["not_mentioned"])
    quote = (payload.free_text or "").strip() or t["not_filled"]
    country = (payload.country or "").strip() or t["not_specified"]
    lines.append(t["quote"] + quote)
    lines.append(t["country"] + country)
    lines.append("────────────────────────")
    purpose = (SCENE_PURPOSE_EN if lang == "en" else SCENE_PURPOSE).get(
        payload.scene if payload.scene in SCENE_LABEL else "consultation", "")
    lines.append(purpose + t["period"])
    lines.append(t["relay"])
    return lines


@router.post("/patient-check")
def patient_handoff(payload: HandoffIn, request: Request):
    """生成给医生的患者情况告知单（不产出译文、不做任何质量评估）。"""
    lang = lang_of(request)
    t = _t(lang)
    parts = _merge(payload.parts, payload.part_other)
    symptoms = _merge(payload.symptoms, payload.symptom_other)
    details = _merge(payload.details, payload.detail_other)
    quote = (payload.free_text or "").strip()
    country = (payload.country or "").strip()

    if not parts and not symptoms and not details and not quote:
        return {
            "empty": True,
            "title": t["title"],
            "message": t["empty"],
            "disclaimer": DISCLAIMER_EN if lang == "en" else DISCLAIMER,
        }

    grouped = _group_details(payload.details, payload.detail_other)
    chief = _chief_complaint(parts, symptoms, details, payload.detail_other, lang)
    scene_key = payload.scene if payload.scene in SCENE_LABEL else "consultation"
    scene = SCENE_LABEL_EN[scene_key] if lang == "en" else SCENE_LABEL[scene_key]
    purpose = (SCENE_PURPOSE_EN if lang == "en" else SCENE_PURPOSE)[scene_key]

    sections = [
        {"no": "01", "label": t["section_part"], "text": _join(parts, lang)},
        {"no": "02", "label": t["section_symptom"], "text": _join(symptoms, lang)},
    ]
    detail_lines: List[str] = []
    for key in GROUP_ORDER:
        values = grouped.get(key) or []
        if values:
            label = GROUP_LABEL_EN[key] if lang == "en" else GROUP_LABEL[key]
            detail_lines.append(label + "：" + t["joiner"].join(values))
    other = grouped.get("other") or []
    if other:
        detail_lines.append(t["other"] + t["joiner"].join(other))
    sections.append({"no": "03", "label": t["section_detail"],
                     "text": t["separator"].join(detail_lines) if detail_lines else t["not_mentioned"]})
    sections.append({"no": "04", "label": t["section_quote"], "text": quote or t["not_filled"]})
    if country:
        sections.append({"no": "05", "label": t["section_country"], "text": country})

    lines = _build_lines(payload, parts, symptoms, grouped, chief, lang, scene)

    return {
        "empty": False,
        "title": t["title"],
        "scene": scene,
        "scene_key": scene_key,
        "purpose": purpose,
        "chief_complaint": chief,
        "sections": sections,
        "patient_quote": quote,
        "country": country,
        "handoff_text": "\n".join(lines),
        "submitted": {
            "scene": scene,
            "parts": parts,
            "symptoms": symptoms,
            "details": details,
            "details_by_group": {
                (GROUP_LABEL_EN.get(k, GROUP_LABEL_EN["other"]) if lang == "en"
                 else GROUP_LABEL.get(k, "其他")): v
                for k, v in grouped.items() if v
            },
            "free_text": quote,
            "country": country,
        },
        "disclaimer": DISCLAIMER_EN if lang == "en" else DISCLAIMER,
        # 显式声明：本接口不做翻译、不做语言质量评估、不澄清文化或信息问题
        "no_translation": True,
        "no_quality_judgement": True,
    }
