# -*- coding: utf-8 -*-
"""服务端轻量 i18n：与前端共用 i18n_data.py（同一份中英对照）。

前端在每次请求带 X-Lang: zh|en；服务端只对「界面 / 错误 / 问答文案」调用 tr()，
知识库语料、术语、资讯与引用原文属于数据，保持原语种、不做翻译。
"""
from __future__ import annotations

import re

from fastapi import Request

from . import i18n_data

RE_CJK = re.compile(r"[\u4e00-\u9fff]")

# 服务端独有的文案（不在前端 UI 字典里）：问答拒答、检索降级、安全拒答、鉴权错误、门禁提示
EXTRA = {
    "请先注册并登录后再使用本站功能":
        "Please register and sign in before using any feature on this site.",
    "CSRF 校验失败，请刷新页面重试":
        "CSRF check failed, please refresh the page and retry.",
    "该功能涉及个人数据，请先登录":
        "This feature involves personal data; please sign in first.",
    "账号已停用": "This account has been disabled.",
    "登录失败次数过多，请 5 分钟后再试":
        "Too many failed sign-in attempts, please try again in 5 minutes.",
    "需要管理员权限": "Administrator permission required.",
    "问答请求过于频繁（每分钟最多 20 次），请稍后再试":
        "Too many Q&A requests (max 20 per minute), please try again later.",
    "该来源切片不存在": "This source chunk does not exist.",
    "知识库检索暂时不可用，已拒绝回答，请稍后重试或咨询人工。":
        "Knowledge-base retrieval is temporarily unavailable; answer refused. Please retry later or consult a human.",
    "抱歉，当前没有足够可追溯的资料，已拒绝回答，请换一种问法或咨询人工。":
        "Sorry, there is not enough traceable material; answer refused. Please rephrase or consult a human.",
    "这个问题不在本站知识库覆盖范围内（急诊术语、平行语料、来源文献与流程规范）。为避免编造，已拒绝回答。请改问与急诊沟通、术语、流程或可溯源来源相关的问题。":
        "This question is outside the site's knowledge base (emergency terminology, parallel corpus, source documents and procedure guidelines). To avoid fabrication, the answer has been refused. Please ask about emergency communication, terminology, procedures or traceable sources.",
    "知识库中没有与这个问题足够相关、可追溯的片段，已拒绝回答，不会拿不相关内容拼凑答案。请换一种问法或咨询人工。":
        "The knowledge base has no sufficiently relevant, traceable chunks for this question; the answer has been refused rather than stitched together from unrelated material. Please rephrase or consult a human.",
    "（当前为检索摘录模式，以下均来自知识库片段）":
        "(Excerpt mode: everything below comes from knowledge-base chunks. Source text is in the original language.)",
    "（引用校验未通过，以下为检索片段摘录）":
        "(Citation validation failed; the following are retrieved chunk excerpts.)",
    "（知识库暂无可用片段）": "(No usable chunks in the knowledge base.)",
    "检测到问题中包含试图修改系统指令的内容，已拒绝处理。如需查询术语、语料或流程，请直接用正常问题提问。":
        "The question contains an attempt to modify system instructions and has been refused. To look up terms, corpus or procedures, please ask a normal question.",
    "抱歉，这个问题涉及{label}，超出本平台的服务范围，我不能提供相关回答。本平台只处理涉外急诊场景下的语言、术语、语料与流程类问题；如遇紧急医疗情况，请立即联系 120 或现场医护人员。":
        "Sorry, this question concerns {label}, which is outside this platform's scope, so I cannot answer it. This platform only handles language, terminology, corpus and procedure questions for cross-border emergency care. In a medical emergency, call 120 or on-site clinical staff immediately.",
    "听到你这样说，我很担心你的安全。你现在的痛苦是真实的，也值得被认真对待，请不要独自承受。请立即联系身边可信任的人，或拨打心理援助热线 12356（全国）／010-82951332（北京）；如果情况紧急，请直接拨打 120。本平台是语言服务工具，不能替代专业心理援助，但希望你先照顾好自己。":
        "I'm concerned about your safety. What you're going through is real and deserves to be taken seriously — please don't face it alone. Reach out to someone you trust, or call a crisis hotline (12356 nationwide / 010-82951332 in Beijing, China); in an emergency call 120. This platform is a language-service tool and cannot replace professional mental-health support, but please take care of yourself first.",
    "武器与爆炸物": "weapons and explosives",
    "自伤与自杀": "self-harm and suicide",
    "暴力与伤害他人": "violence and harming others",
    "毒品与违禁品": "illegal drugs and controlled substances",
    "网络攻击": "cyberattacks",
    "仇恨与歧视": "hate and discrimination",
    "未成年人性内容": "sexual content involving minors",
    "试图修改系统指令": "attempts to modify system instructions",
    "该功能需要登录": "Please sign in to use this feature.",
}


def lang_of(request: Request | None = None) -> str:
    """语言优先级：X-Lang 头 > ?lang= > Accept-Language > 中文。"""
    if request is not None:
        header = (request.headers.get("x-lang") or "").strip().lower()
        if header in i18n_data.LANGS:
            return header
        query = (request.query_params.get("lang") or "").strip().lower()
        if query in i18n_data.LANGS:
            return query
        accept = (request.headers.get("accept-language") or "").lower()
        if accept.startswith("en") or ",en" in accept or "en-us" in accept:
            return "en"
    return "zh"


def apply_vars(text: str, variables: dict | None) -> str:
    if not variables:
        return text
    def repl(match):
        key = match.group(1)
        return str(variables[key]) if key in variables else match.group(0)
    return re.sub(r"\{(\w+)\}", repl, text)


def tr(zh: str, lang: str = "zh", variables: dict | None = None) -> str:
    """把一条中文界面文案翻成当前语言；无对应条目时按长键短语替换。"""
    source = str(zh or "")
    if lang != "en" or not RE_CJK.search(source):
        return source
    extra = EXTRA.get(source)
    if extra is not None:
        return apply_vars(extra, variables)
    exact = i18n_data.DICT.get(source)
    if exact is not None:
        return apply_vars(exact, variables)
    template = i18n_data.TEMPLATES.get(source)
    if template is not None:
        return apply_vars(template, variables)
    out = source
    for zh_phrase, en_phrase in i18n_data.PHRASES:
        if zh_phrase in out:
            out = out.replace(zh_phrase, en_phrase)
    return out


def tr_detail(detail, lang: str = "zh"):
    """HTTPException.detail 可能是 str / list / dict；只翻译其中的字符串。"""
    if isinstance(detail, str):
        return tr(detail, lang)
    if isinstance(detail, list):
        return [tr_detail(item, lang) for item in detail]
    if isinstance(detail, dict):
        return {key: tr_detail(value, lang) for key, value in detail.items()}
    return detail
