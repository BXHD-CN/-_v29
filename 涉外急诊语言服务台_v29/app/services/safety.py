# -*- coding: utf-8 -*-
"""问答安全过滤：有害内容与提示注入。

只拦截明确越界的问题（暴力/武器/自伤/违法/黑客/仇恨/未成年人性内容/提示注入），
正常医疗、急救、翻译、文化类问题一律放行，避免误伤。
"""
from __future__ import annotations

import re

CATEGORIES: list[tuple[str, str, str]] = [
    ("weapons", "武器与爆炸物",
     r"(制作|制造|合成|自制).{0,6}(炸弹|爆炸物|燃烧瓶|地雷)|炸弹.{0,6}(配方|教程|制作)|"
     r"(枪|枪支|弹药).{0,6}(自制|改装|购买渠道)|how\s+to\s+make\s+(a\s+)?bomb|explosive\s+(recipe|device)"),
    ("self_harm", "自伤与自杀",
     r"自杀.{0,6}(方法|方式|怎么|如何)|怎么(样)?(才能)?(自杀|自残|轻生)|割腕|上吊|跳楼.{0,4}(死|自杀)|"
     r"我想(要)?自杀|不想活了?|活着没(意思|意义)|结束(自己的)?生命|轻生(念头|想法)|想死|"
     r"(painless|quick)\s+(way|method)\s+to\s+(die|kill\s+myself)|suicide\s+method|want\s+to\s+die"),
    ("violence", "暴力与伤害他人",
     r"(怎么|如何).{0,6}(杀人|杀死|弄死|毒死|下毒)|(毒药|砒霜|氰化物).{0,6}(配方|剂量|获取)|"
     r"(绑架|劫持).{0,6}(方法|教程)|恐怖袭击.{0,6}(策划|教程)|how\s+to\s+kill\s+(someone|a\s+person)"),
    ("illegal_drugs", "毒品与违禁品",
     r"(冰毒|海洛因|可卡因|摇头丸).{0,6}(制作|合成|配方|购买)|制毒.{0,4}(工艺|流程|配方)"),
    ("hacking", "网络攻击",
     r"(黑进|入侵|破解).{0,8}(网站|系统|账号|密码|数据库)|(ddos|sql\s*注入|勒索软件).{0,8}(教程|方法|工具)|"
     r"how\s+to\s+hack|bypass\s+(login|authentication)"),
    ("hate", "仇恨与歧视",
     r"(灭绝|清洗|屠杀).{0,6}(种族|民族|宗教)|(种族|民族).{0,6}(优越|低劣)"),
    ("minor_sexual", "未成年人性内容",
     r"(儿童|未成年|幼女|幼童).{0,8}(色情|性行为|裸照)"),
    ("prompt_injection", "试图修改系统指令",
     r"忽略(以上|之前|前面|全部).{0,6}(指令|规则|提示)|ignore\s+(all\s+)?(previous|above)\s+instructions?|"
     r"(开发者|developer)\s*mode|越狱模式|jailbreak|输出(你的)?(系统)?(提示词|prompt)|"
     r"你现在是.{0,10}(不受限制|无限制)"),
]

_COMPILED = [(code, label, re.compile(pattern, re.I)) for code, label, pattern in CATEGORIES]

CRISIS_REPLY = (
    "听到你这样说，我很担心你的安全。你现在的痛苦是真实的，也值得被认真对待，请不要独自承受。"
    "请立即联系身边可信任的人，或拨打心理援助热线 12356（全国）／010-82951332（北京）；"
    "如果情况紧急，请直接拨打 120。本平台是语言服务工具，不能替代专业心理援助，但希望你先照顾好自己。"
)

SAFE_REFUSAL = (
    "抱歉，这个问题涉及{label}，超出本平台的服务范围，我不能提供相关回答。"
    "本平台只处理涉外急诊场景下的语言、术语、语料与流程类问题；"
    "如遇紧急医疗情况，请立即联系 120 或现场医护人员。"
)

INJECTION_REFUSAL = (
    "检测到问题中包含试图修改系统指令的内容，已拒绝处理。"
    "如需查询术语、语料或流程，请直接用正常问题提问。"
)

CRISIS_REPLY_EN = (
    "I'm concerned about your safety. What you're going through is real and deserves to be taken "
    "seriously — please don't face it alone. Reach out to someone you trust, or call a crisis hotline "
    "(12356 nationwide / 010-82951332 in Beijing, China); in an emergency call 120. This platform is a "
    "language-service tool and cannot replace professional mental-health support, but please take care of yourself first."
)

SAFE_REFUSAL_EN = (
    "Sorry, this question concerns {label}, which is outside this platform's scope, so I cannot answer it. "
    "This platform only handles language, terminology, corpus and procedure questions for cross-border "
    "emergency care. In a medical emergency, call 120 or on-site clinical staff immediately."
)

INJECTION_REFUSAL_EN = (
    "The question contains an attempt to modify system instructions and has been refused. "
    "To look up terms, corpus or procedures, please ask a normal question."
)

LABEL_EN = {
    "武器与爆炸物": "weapons and explosives",
    "自伤与自杀": "self-harm and suicide",
    "暴力与伤害他人": "violence and harming others",
    "毒品与违禁品": "illegal drugs and controlled substances",
    "网络攻击": "cyberattacks",
    "仇恨与歧视": "hate and discrimination",
    "未成年人性内容": "sexual content involving minors",
    "试图修改系统指令": "attempts to modify system instructions",
}


def check(text: str, lang: str = "zh") -> tuple[bool, str, str]:
    """返回 (是否安全, 类别码, 提示文案)；lang=en 时直接返回英文安全拒答。"""
    value = (text or "").strip()
    if not value:
        return True, "", ""
    english = lang == "en"
    for code, label, pattern in _COMPILED:
        if pattern.search(value):
            if code == "prompt_injection":
                return False, code, INJECTION_REFUSAL_EN if english else INJECTION_REFUSAL
            if code == "self_harm":
                return False, code, CRISIS_REPLY_EN if english else CRISIS_REPLY
            if english:
                return False, code, SAFE_REFUSAL_EN.format(label=LABEL_EN.get(label, label))
            return False, code, SAFE_REFUSAL.format(label=label)
    return True, "", ""