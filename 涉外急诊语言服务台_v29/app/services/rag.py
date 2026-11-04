# -*- coding: utf-8 -*-
"""RAG 问答：检索 → 混合排序（余弦 + 词面重合）→ 拒答判定 → 强制 [n] 引用生成 →
引用校验（不合法重试 1 次，仍失败用片段摘录）→ 无生成模型走摘录模式。

为什么需要混合排序：EMBEDDING_PROVIDER=local 的哈希向量没有语义能力，库内/库外问题的
余弦分布高度重叠（实测 top1 都在 0.15–0.30）。因此在余弦之外再算字符 bigram 重合率
lex = |bigrams(q) ∩ bigrams(chunk)| / max(1, |bigrams(q)|)，用
hybrid = 0.6*cos + 0.4*lex 排序；只有“hybrid 低且 lex 也低”才拒答，避免把
“预检分诊是什么？”这类短句误拒，同时拦住“美元汇率”这类纯库外问题。
"""
from __future__ import annotations

import logging
import re
import time

from sqlalchemy import or_, select

from ..config import get_settings
from ..db import SessionLocal
from ..models import Chunk
from . import llm
from .embedding import EmbeddingUnavailable
from .llm import LLMUnavailable
from .retrieval import search_chunks

logger = logging.getLogger(__name__)
settings = get_settings()

EXCERPT_PREFIX = "（当前为检索摘录模式，以下均来自知识库片段）"
EXCERPT_PREFIX_EN = (
    "(Excerpt mode: everything below comes from knowledge-base chunks. "
    "Source text is shown in its original language.)"
)
EXCERPT_FALLBACK_PREFIX = "（引用校验未通过，以下为检索片段摘录）"
EXCERPT_FALLBACK_PREFIX_EN = "(Citation validation failed; the following are retrieved chunk excerpts.)"
NO_CHUNK_TEXT = "（知识库暂无可用片段）"
NO_CHUNK_TEXT_EN = "(No usable chunks in the knowledge base.)"
SNIPPET_LEN = 120
MAX_EXCERPT_CHUNKS = 3

# 拒答文案（中英两套，内容一一对应）
REFUSAL_TEXT = {
    "zh": {
        "out_of_knowledge_base":
            "这个问题不在本站知识库覆盖范围内（急诊术语、平行语料、来源文献与流程规范）。"
            "为避免编造，已拒绝回答。请改问与急诊沟通、术语、流程或可溯源来源相关的问题。",
        "insufficient_evidence":
            "知识库中没有与这个问题足够相关、可追溯的片段，已拒绝回答，"
            "不会拿不相关内容拼凑答案。请换一种问法或咨询人工。",
        "retrieval_error":
            "知识库检索暂时不可用，已拒绝回答，请稍后重试或咨询人工。",
        "embedding_unavailable":
            "知识库检索暂时不可用，已拒绝回答，请稍后重试或咨询人工。",
        "empty_question":
            "问题为空，已拒绝回答。",
        "generic":
            "抱歉，当前没有足够可追溯的资料，已拒绝回答，请换一种问法或咨询人工。",
    },
    "en": {
        "out_of_knowledge_base":
            "This question is outside the site's knowledge base (emergency terminology, parallel corpus, "
            "source documents and procedure guidelines). To avoid fabrication, the answer has been refused. "
            "Please ask about emergency communication, terminology, procedures or traceable sources.",
        "insufficient_evidence":
            "The knowledge base has no sufficiently relevant, traceable chunks for this question; the answer "
            "has been refused rather than stitched together from unrelated material. Please rephrase or consult a human.",
        "retrieval_error":
            "Knowledge-base retrieval is temporarily unavailable; answer refused. Please retry later or consult a human.",
        "embedding_unavailable":
            "Knowledge-base retrieval is temporarily unavailable; answer refused. Please retry later or consult a human.",
        "empty_question":
            "The question is empty; answer refused.",
        "generic":
            "Sorry, there is not enough traceable material; answer refused. Please rephrase or consult a human.",
    },
}

# local 哈希向量专用口径（语义向量仍用 config.refuse_threshold 的纯余弦阈值）
DEFAULT_LOCAL_REFUSE_THRESHOLD = 0.15
HYBRID_COS_WEIGHT = 0.6
HYBRID_LEX_WEIGHT = 0.4
HYBRID_REFUSE_THRESHOLD = 0.16   # hybrid 低于此值…
LEX_REFUSE_THRESHOLD = 0.25      # …且词面重合率也低于此值，才拒答
CANDIDATE_MULTIPLIER = 3         # 先多取候选，再按 hybrid 重排回 top_k

# 库外问题闸门
LEX_MIN_EVIDENCE = 0.12          # 连最基本的词面重合都没有 → 一定不是库内问题
CONTENT_HYBRID_BYPASS = 0.30     # 只剩通用词命中时，hybrid 要足够高才放行
# 疑问词 / 站内通用词：这些 bigram 命中不能当作「问题属于知识库」的证据。
GENERIC_GRAMS = {
    "急诊", "患者", "医院", "医护", "医生", "护士", "病人", "什么", "怎么", "如何",
    "请问", "是否", "可以", "哪些", "术语", "英文", "中文", "翻译", "说法", "表达",
    "意思", "是什", "有哪", "告诉", "知识", "识库", "服务", "务台", "一下", "需要",
    "相关", "关于", "多少", "用语", "对照", "标准", "是什", "么意", "请问",
}

# 英文问题闸门：中文 bigram 对英文问题会「虚高假重合」——中文切片里少量
# 英文缩写 / 医学词被拆成字母 bigram 后，可能让「火锅店 / 汇率 / 世界杯」
# 等库外英文问题拿到非零 lex，进而被误判为库内并返回无关片段摘录。
# 因此纯英文问题改用「整词命中 + 领域锚点」判定，不再依赖字符 bigram。
EN_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "which", "when",
    "where", "who", "how", "why", "are", "was", "were", "does", "did", "can",
    "could", "should", "would", "will", "have", "has", "had", "is", "it", "its",
    "into", "about", "best", "please", "tell", "give", "show", "recommend",
    "today", "now", "much", "many", "some", "any", "not", "but", "you", "your",
    "they", "their", "there", "here", "than", "then", "also", "use", "used",
    "using", "want", "need", "like", "most", "more", "very", "just", "get",
}
# 与本站知识库主题（急诊沟通 / 术语 / 语料 / 来源 / 流程）相关的英文锚点
EN_DOMAIN_ANCHORS = {
    "emergency", "triage", "patient", "patients", "clinical", "medical", "medicine",
    "hospital", "nurse", "doctor", "physician", "airway", "resuscitation", "cpr",
    "consent", "informed", "surgery", "surgical", "anaesthesia", "anesthesia",
    "terminology", "term", "terms", "corpus", "translation", "translate",
    "interpreter", "interpreting", "language", "communication", "diagnosis",
    "symptom", "symptoms", "vital", "signs", "wound", "trauma", "burn", "sepsis",
    "infection", "isolation", "vaccination", "vaccine", "discharge", "admission",
    "referral", "handover", "documentation", "certificate", "consular", "source",
    "sources", "citation", "licence", "license", "guideline", "guidelines",
    "procedure", "procedures", "protocol", "dispensing", "medication", "dosage",
    "asean", "cultural", "culture", "taboo", "honorific", "variant",
}


def english_terms(question: str) -> list[str]:
    """提取英文问题里的实词（去停用词、去重、保持顺序）。"""
    words = re.findall(r"[a-z][a-z'-]{2,}", (question or "").lower())
    return [w for w in dict.fromkeys(words) if w not in EN_STOPWORDS]


def english_chunk_hits(question: str, chunk: dict) -> int:
    """英文实词在切片正文 / 标题里的整词命中数（不做字母 bigram）。"""
    terms = english_terms(question)
    if not terms:
        return 0
    text = ((chunk.get("text", "") or "") + " " + (chunk.get("title", "") or "")).lower()
    return sum(1 for term in terms
               if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text))


def english_in_scope(question: str, ranked: list[dict]) -> bool:
    """纯英文问题是否属于知识库主题域且确有可追溯的整词证据。

    中文问题 / 中英混排问题直接返回 True，沿用既有中文 bigram 规则；
    纯英文问题必须同时满足：① 至少 1 个主题域锚点；② 命中切片里有足量整词重合。
    """
    if re.search(r"[\u4e00-\u9fff]", question or ""):
        return True
    terms = english_terms(question)
    if not terms:
        return False
    anchors = [term for term in terms if term in EN_DOMAIN_ANCHORS]
    if not anchors:
        return False
    best = max((english_chunk_hits(question, chunk) for chunk in ranked[:6]), default=0)
    if len(terms) <= 2:
        return best >= 1
    return (len(anchors) >= 1 and best >= 2) or (len(anchors) >= 2 and best >= 1)


SYSTEM_PROMPT = (
    "你是涉外急诊语言服务台的问答助手。严格规则：\n"
    "1) 只能依据【资料片段】回答，不得引入片段之外的任何信息；\n"
    "2) 每个结论句的句末必须标注来源编号，格式如 [1]、[2]；\n"
    "3) 片段不足以回答时，直接说明资料不足，不要编造；\n"
    "4) 用中文回答，语气专业、简洁。"
)
SYSTEM_PROMPT_EN = (
    "You are the Q&A assistant of the Emergency Language Desk. Strict rules:\n"
    "1) Answer ONLY from the [SOURCE CHUNKS]; never add anything outside them;\n"
    "2) End every conclusion sentence with a source marker such as [1] or [2];\n"
    "3) If the chunks are insufficient, say so plainly; never fabricate;\n"
    "4) Answer in English, professionally and concisely. Source chunks may remain in their original language."
)


def embedding_provider() -> str:
    return (settings.embedding_provider or "local").strip().lower()


def is_local_embedding() -> bool:
    return embedding_provider() == "local"


def refuse_threshold() -> float:
    """语义向量 provider 的余弦拒答阈值；local 走 hybrid 规则（见 should_refuse）。"""
    if is_local_embedding():
        return float(getattr(settings, "refuse_threshold_local", DEFAULT_LOCAL_REFUSE_THRESHOLD))
    return float(settings.refuse_threshold)


def _bigrams(text: str) -> set[str]:
    """字符 bigram 集合：去掉空白、标点与数字（年份/日期不作为词面依据）。"""
    value = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", (text or "").lower())
    value = re.sub(r"[0-9]+", "", value)
    if len(value) < 2:
        return {value} if value else set()
    return {value[i:i + 2] for i in range(len(value) - 1)}


def lexical_overlap(question: str, chunk: dict) -> float:
    """词面重合率 lex：问题 bigram 有多少比例出现在切片（标题 + 正文）里。"""
    question_grams = _bigrams(question)
    if not question_grams:
        return 0.0
    chunk_grams = _bigrams(chunk.get("text", "")) | _bigrams(chunk.get("title", ""))
    return len(question_grams & chunk_grams) / len(question_grams)


def content_overlap(question: str, chunk: dict) -> float:
    """剔除疑问词 / 站内通用词后，问题「实词」bigram 在切片中的重合率。

    用于拦住「急诊室附近有咖啡店」这类蹭了通用词、但知识库根本没有对应内容的问题。
    """
    core = _bigrams(question) - GENERIC_GRAMS
    if not core:
        return 0.0
    chunk_grams = _bigrams(chunk.get("text", "")) | _bigrams(chunk.get("title", ""))
    return len(core & chunk_grams) / len(core)


def rank_hybrid(question: str, chunks: list[dict]) -> list[dict]:
    """给候选切片补 lex / content_lex / hybrid 并按 hybrid 降序；保留原始 cosine 分。"""
    ranked: list[dict] = []
    for chunk in chunks:
        item = dict(chunk)
        lex = lexical_overlap(question, chunk)
        cosine_score = float(chunk.get("score", 0.0))
        item["lex"] = round(lex, 4)
        item["content_lex"] = round(content_overlap(question, chunk), 4)
        item["hybrid"] = round(HYBRID_COS_WEIGHT * cosine_score + HYBRID_LEX_WEIGHT * lex, 4)
        ranked.append(item)
    ranked.sort(key=lambda c: c["hybrid"], reverse=True)
    return ranked


def should_refuse(ranked: list[dict], question: str = "") -> bool:
    """拒答判定：知识库外 / 证据不足的问题一律不回答，不拿不相关片段凑数。

    - local 哈希向量（部署默认）：先要求最基本的词面重合；再剔除疑问/通用词后
      要求仍有实质证据；最后用「hybrid 低且词面重合也低」双低兜底。
    - 语义向量 provider：维持契约的纯余弦阈值。
    """
    if not ranked:
        return True
    top = ranked[0]
    if is_local_embedding():
        lex = float(top.get("lex", 0.0))
        hybrid = float(top.get("hybrid", 0.0))
        core = float(top.get("content_lex", content_overlap(question, top)))
        # ① 连通用词都没重合 → 明显是知识库外问题
        if lex < LEX_MIN_EVIDENCE:
            return True
        # ② 只蹭到「急诊 / 术语 / 怎么」这类通用词，没有实质证据 → 库外问题
        if core <= 0.0 and hybrid < CONTENT_HYBRID_BYPASS:
            return True
        # ③ 综合相关性双低
        return hybrid < HYBRID_REFUSE_THRESHOLD and lex < LEX_REFUSE_THRESHOLD
    return float(top.get("score", 0.0)) < float(settings.refuse_threshold)


def keyword_evidence(question: str, limit: int = 6) -> list[dict]:
    """词面兜底：用问题里的中文实词直接查切片正文 / 标题。

    local 哈希向量没有语义能力，库内问题可能被漏召回。这里把「知识库里是否
    真有能回答这个问题的可追溯片段」作为硬证据：命中即放行，不命中才判库外。
    """
    zh = "".join(re.findall(r"[\u4e00-\u9fff]+", question or ""))
    grams: list[str] = []
    for size in (4, 3, 2):
        for i in range(len(zh) - size + 1):
            gram = zh[i:i + size]
            if gram in GENERIC_GRAMS or gram in grams:
                continue
            grams.append(gram)
        if len(grams) >= 8:
            break
    grams = grams[:8]
    # 英文问题：用主题域实词做整词 LIKE（SQLite 对 ASCII 默认不区分大小写），
    # 避免中文 bigram 在英文问题上产生的假重合把库外问题带进候选。
    en_terms = [term for term in english_terms(question or "")
                if term in EN_DOMAIN_ANCHORS][:6]
    if not grams and not en_terms:
        return []
    try:
        with SessionLocal() as db:
            conds = []
            for gram in grams:
                conds.append(Chunk.text.like("%" + gram + "%"))
                conds.append(Chunk.title.like("%" + gram + "%"))
            for term in en_terms:
                conds.append(Chunk.text.like("%" + term + "%"))
                conds.append(Chunk.title.like("%" + term + "%"))
            rows = db.execute(select(Chunk).where(or_(*conds)).limit(limit)).scalars().all()
    except Exception as exc:  # 数据库异常不阻断问答主流程
        logger.warning("词面兜底检索失败：%s", type(exc).__name__)
        return []
    out: list[dict] = []
    for row in rows:
        out.append({
            "chunk_id": row.id, "title": row.title or "", "text": row.text or "",
            "source_url": row.source_url or "", "section": row.section or "",
            "page": row.page or "", "license": row.license or "", "doc_id": row.doc_id or "",
            "score": 0.0,
        })
    return out


def _snippet(text: str) -> str:
    value = re.sub(r"\s+", " ", (text or "")).strip()
    if len(value) <= SNIPPET_LEN:
        return value
    return value[:SNIPPET_LEN - 1] + "…"


def _build_citations(chunks: list[dict]) -> list[dict]:
    citations: list[dict] = []
    for index, chunk in enumerate(chunks, start=1):
        citations.append({
            "index": index,
            "chunk_id": chunk.get("chunk_id"),
            "title": chunk.get("title", ""),
            "section": chunk.get("section", ""),
            "page": chunk.get("page", ""),
            "source_url": chunk.get("source_url", ""),
            "doc_id": chunk.get("doc_id", ""),
            "license": chunk.get("license", ""),
            "score": chunk.get("score", 0.0),        # 保留 cosine 分
            "hybrid": chunk.get("hybrid", 0.0),      # 排序用的混合分
            "lex": chunk.get("lex", 0.0),            # 词面重合率
            "snippet": _snippet(chunk.get("text", "")),
        })
    return citations


def _build_messages(question: str, citations: list[dict], lang: str = "zh") -> list[dict]:
    blocks = []
    for item in citations:
        blocks.append(
            f"[{item['index']}] 标题：{item['title']}｜章节：{item['section']}｜"
            f"来源：{item['source_url'] or '（无）'}\n{item['snippet']}"
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT_EN if lang == "en" else SYSTEM_PROMPT},
        {"role": "user",
         "content": "【资料片段】\n" + "\n\n".join(blocks) + f"\n\n【问题】\n{question}"},
    ]


def _refs(answer_text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\[(\d+)\]", answer_text or "")]


def _citations_valid(answer_text: str, total: int) -> bool:
    """引用校验：至少 1 个引用，且所有编号都在 1..total 内。"""
    refs = _refs(answer_text)
    if not refs:
        return False
    return all(1 <= ref <= total for ref in refs)


def _excerpt_answer(citations: list[dict], prefix: str = "", lang: str = "zh") -> str:
    lines = [
        f"[{item['index']}] {item['snippet']}"
        for item in citations[:MAX_EXCERPT_CHUNKS]
    ]
    body = "\n".join(lines) or (NO_CHUNK_TEXT_EN if lang == "en" else NO_CHUNK_TEXT)
    return f"{prefix}{body}"


def _refused(reason: str, started: float, lang: str = "zh") -> dict:
    table = REFUSAL_TEXT["en" if lang == "en" else "zh"]
    text = table.get(reason, table["generic"])
    return {
        "answer": text,
        "citations": [],
        "refused": True,
        "reason": reason,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def answer(question: str, lang: str = "zh") -> dict:
    """RAG 主流程；所有模型侧异常都降级，不向上抛。"""
    started = time.perf_counter()
    english = lang == "en"
    q = (question or "").strip()
    if not q:
        return _refused("empty_question", started, lang)

    prefix = EXCERPT_PREFIX_EN if english else EXCERPT_PREFIX
    fallback_prefix = EXCERPT_FALLBACK_PREFIX_EN if english else EXCERPT_FALLBACK_PREFIX

    # ① 检索（多取候选，供 hybrid 重排）
    try:
        pool_size = max(int(settings.qa_top_k) * CANDIDATE_MULTIPLIER, int(settings.qa_top_k))
        chunks = search_chunks(q, top_k=pool_size, threshold=0.0)
    except EmbeddingUnavailable as exc:
        logger.warning("问答检索降级：%s", exc.message)
        return _refused("embedding_unavailable", started, lang)
    except Exception as exc:  # 数据库/向量库异常也不允许 500
        logger.exception("问答检索异常：%s", type(exc).__name__)
        return _refused("retrieval_error", started, lang)

    # ② 混合排序 + 拒答判定
    ranked = rank_hybrid(q, chunks)
    # ②-a 纯英文问题的主题域闸门：中文 bigram 对英文会产生虚高假重合，
    # 必须在进入「词面兜底 / 摘录作答」之前先拦住库外英文问题。
    if not english_in_scope(q, ranked):
        logger.info("问答拒答（英文问题不在知识库主题域或缺少整词证据）：%s", q[:80])
        return _refused("out_of_knowledge_base", started, lang)
    if should_refuse(ranked, q):
        # 向量证据不足时，再确认知识库里是否真的存在可追溯的词面命中：
        # 有 → 库内问题，把命中片段并入候选重新排序；没有 → 判定为库外问题，拒答。
        evidence = keyword_evidence(q)
        # 只认「强证据」：命中切片与问题的实词重合要足够高，避免「北京今天天气」
        # 这类库外问题因为蹭到「今天 / 北京」等字眼被误放行。
        strong = [item for item in evidence
                  if lexical_overlap(q, item) >= 0.28 or content_overlap(q, item) >= 0.25]
        if not strong:
            top = ranked[0] if ranked else {}
            logger.info("问答拒答（库外/无证据）：top_hybrid=%s top_lex=%s top_content=%s",
                        top.get("hybrid"), top.get("lex"), top.get("content_lex"))
            reason = ("out_of_knowledge_base"
                      if float(top.get("lex", 0.0)) < LEX_MIN_EVIDENCE
                      else "insufficient_evidence")
            return _refused(reason, started, lang)
        merged = {item.get("chunk_id"): item for item in chunks}
        for item in strong:
            merged.setdefault(item["chunk_id"], item)
        ranked = rank_hybrid(q, list(merged.values()))
        # 词面命中已是「库内确有可追溯内容」的硬证据，不再用余弦阈值二次否决：
        # 这些切片没有向量分，若再套 should_refuse 会把库内问题误判为库外。
        logger.info("问答词面兜底命中 %d 条强证据切片", len(strong))

    citations = _build_citations(ranked[:int(settings.qa_top_k)])
    total = len(citations)

    # ③ 无生成模型：摘录模式
    if llm.is_mock():
        return {
            "answer": _excerpt_answer(citations, prefix + "\n", lang),
            "citations": citations,
            "refused": False,
            "reason": "",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "mode": "excerpt",
        }

    # ④ 生成 + 引用校验（失败重试 1 次）
    messages = _build_messages(q, citations, lang)
    try:
        answer_text = llm.chat(messages, temperature=0.2, max_tokens=800)
        if not _citations_valid(answer_text, total):
            logger.info("答案引用校验未通过，重试一次")
            retry_messages = messages + [
                {"role": "assistant", "content": answer_text},
                {"role": "user",
                 "content": f"引用标注不合格：每个结论句末必须带 [n]，且 n 只能是 1 到 {total}，"
                            f"不得出现其他编号。请重写答案。"},
            ]
            answer_text = llm.chat(retry_messages, temperature=0.2, max_tokens=800)
    except LLMUnavailable as exc:
        logger.warning("生成模型不可用，降级为摘录模式：%s", exc.message)
        return {
            "answer": _excerpt_answer(citations, prefix + "\n", lang),
            "citations": citations,
            "refused": False,
            "reason": "",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "mode": "excerpt",
        }

    # ⑤ 仍不合法：用片段摘录拼接
    if not _citations_valid(answer_text, total):
        logger.info("两次引用校验均未通过，改用片段摘录")
        return {
            "answer": _excerpt_answer(citations, fallback_prefix + "\n", lang),
            "citations": citations,
            "refused": False,
            "reason": "",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "mode": "excerpt",
        }

    return {
        "answer": answer_text.strip(),
        "citations": citations,
        "refused": False,
        "reason": "",
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "mode": "llm",
    }
