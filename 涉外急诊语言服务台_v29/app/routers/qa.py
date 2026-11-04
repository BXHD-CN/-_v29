# -*- coding: utf-8 -*-
"""问答接口：POST /api/qa（RAG，严格限定既有知识库）、GET /api/qa/examples、
GET /api/qa/source/{chunk_id}。限流 20 次/分钟/用户。

「库内」硬约束（本轮加固）：
- 任何异常、任何无证据、任何引用编号不存在的情况，统一降级为拒绝回答；
- 非拒答回答必须带至少一条引用，且引用的切片编号必须真实存在于 chunks 表；
- 摘要模式下答案文本逐字来自命中切片，不引入库外信息；
- 拒答时 citations 一律为空，不把不相关片段当成答案的装饰。
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..deps import client_ip, get_optional_user
from ..i18n import lang_of, tr
from ..models import Chunk, User
from ..services import rag, safety

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["qa"])

RATE_LIMIT = 20          # 每个用户每分钟最多 20 次
RATE_WINDOW = 60.0

# 示例问题：只保留医疗 / 急诊 / 语言服务相关、且知识库可支撑的预设题。
# 曾用于「演示拒答」的火锅店、汇率两条非医疗题已按业主需求删除；
# 库外拒答能力由 rag.answer() 的领域闸门与 ask() 的引用真实性校验保证，
# 不依赖任何库外演示题。界面按语言展示，但提交时一律回传 question_zh
# （规范中文问题），避免英文界面把英文问题送进中文 bigram 检索造成误拒答。
EXAMPLES: list[dict] = [
    {"id": 1, "question_zh": "急诊分诊台如何用英语向患者说明候诊顺序？",
     "question_en": "How does an emergency triage desk explain waiting order to patients in English?",
     "note_zh": "库内平行语料可直接支撑", "note_en": "Supported by in-base parallel corpus",
     "in_scope": True},
    {"id": 2, "question_zh": "“预检分诊”的标准英文术语是什么？",
     "question_en": "What is the standard English term for “pre-examination triage”?",
     "note_zh": "术语库可回答", "note_en": "Answerable from the term library", "in_scope": True},
    {"id": 3, "question_zh": "灾害现场医疗点如何进行检伤分类？",
     "question_en": "How is triage performed at a disaster-site medical point?",
     "note_zh": "灾难医学与分诊类切片", "note_en": "Disaster medicine & triage chunks", "in_scope": True},
    {"id": 4, "question_zh": "手术知情同意需要向患者说明哪些内容？",
     "question_en": "What must be explained to a patient for surgical informed consent?",
     "note_zh": "知情同意与沟通合规类切片", "note_en": "Informed consent & communication chunks", "in_scope": True},
]


class SlidingWindowLimiter:
    """进程内滑动窗口限流；生产由 Nginx limit_req 承担主要职责。"""

    def __init__(self, limit: int, window: float) -> None:
        self._limit = limit
        self._window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit_or_blocked(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self._window]
            if len(hits) >= self._limit:
                self._hits[key] = hits
                return True
            hits.append(now)
            self._hits[key] = hits
            return False


limiter = SlidingWindowLimiter(RATE_LIMIT, RATE_WINDOW)


class QAIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _refusal(reason: str, lang: str, request_id: str) -> dict:
    """统一安全兜底：任何异常 / 无证据 / 引用失效都走这里，绝不越界作答。"""
    return {
        "answer": rag.REFUSAL_TEXT["en" if lang == "en" else "zh"].get(
            reason, rag.REFUSAL_TEXT["en" if lang == "en" else "zh"]["generic"]),
        "citations": [],
        "refused": True,
        "reason": reason,
        "unsafe": False,
        "elapsed_ms": 0,
        "mode": "refusal",
        "scope": "knowledge_base_only",
        "kb_guard": "strict",
        "request_id": request_id,
    }


def _citations_exist(citations: list[dict]) -> bool:
    """引用必须逐条对应 chunks 表里真实存在的切片，杜绝凭空编号。"""
    ids: list[int] = []
    for item in citations:
        chunk_id = item.get("chunk_id")
        if isinstance(chunk_id, int) and chunk_id > 0:
            ids.append(chunk_id)
        elif isinstance(chunk_id, str) and chunk_id.isdigit():
            ids.append(int(chunk_id))
    if not ids:
        return False
    try:
        with SessionLocal() as db:
            found = db.execute(select(Chunk.id).where(Chunk.id.in_(ids))).scalars().all()
    except Exception:
        return False
    # 只要有一个编号不存在就拒绝，避免答案正文引用了查不到的来源
    return len(set(found)) == len(set(ids))


def _canonical_question(question: str) -> str:
    """英文界面手输的预设问题映射回规范中文，保证中文知识库检索命中率一致。

    预设问题 chip 提交时前端已回传 question_zh；这里覆盖「用户自己照着英文
    示例敲一遍」的情况，避免英文提问因向量语言差异被误判为库外。
    """
    normalized = " ".join((question or "").strip().lower().split())
    for item in EXAMPLES:
        if normalized == " ".join(item["question_en"].strip().lower().split()):
            return item["question_zh"]
    return question


@router.post("/qa")
def ask(data: QAIn, request: Request, user: User | None = Depends(get_optional_user)):
    lang = lang_of(request)
    request_id = getattr(request.state, "request_id", "")
    actor = str(user.id) if user else client_ip(request)
    if limiter.hit_or_blocked(f"qa:{actor}"):
        raise HTTPException(429, tr("问答请求过于频繁（每分钟最多 20 次），请稍后再试", lang))

    # 安全过滤（提示注入 / 越界内容）对所有访客一致生效，且按语言返回拒答文案
    allowed, category, message = safety.check(data.question, lang)
    if not allowed:
        logger.warning("qa blocked user=%s category=%s", actor, category)
        return {"answer": message, "citations": [], "refused": True, "reason": category,
                "unsafe": True, "scope": "knowledge_base_only", "kb_guard": "strict",
                "request_id": request_id}

    try:
        result = rag.answer(_canonical_question(data.question), lang)
    except Exception as exc:  # 任何模型 / 检索异常都不允许 500 或越界作答
        logger.exception("qa unexpected error: %s", type(exc).__name__)
        result = _refusal("retrieval_error", lang, request_id)
        return result

    result["request_id"] = request_id
    result["scope"] = "knowledge_base_only"
    result["kb_guard"] = "strict"

    if result.get("refused"):
        # 拒答一律不带引用，避免用不相关片段凑数
        result["citations"] = []
        logger.info("qa user=%s refused=%s reason=%s elapsed_ms=%s",
                    actor, True, result.get("reason"), result.get("elapsed_ms"))
        return result

    citations = result.get("citations") or []
    answer_text = str(result.get("answer") or "").strip()
    # 非拒答回答的双重闸门：必须有答案、必须有引用、引用必须真实存在于既有库
    if not answer_text or not citations or not _citations_exist(citations):
        logger.info("qa strict guard refused: answer=%s citations=%s", bool(answer_text), len(citations))
        return _refusal("insufficient_evidence", lang, request_id)

    logger.info("qa user=%s refused=False citations=%d elapsed_ms=%s",
                actor, len(citations), result.get("elapsed_ms"))
    return result


@router.get("/qa/examples")
def examples(request: Request):
    lang = lang_of(request)
    english = lang == "en"
    return {"examples": [
        {
            "id": item["id"],
            "question": item["question_en"] if english else item["question_zh"],
            "question_zh": item["question_zh"],
            "note": item["note_en"] if english else item["note_zh"],
            "in_scope": item["in_scope"],
        }
        for item in EXAMPLES
    ]}


@router.get("/qa/source/{chunk_id}")
def qa_source(chunk_id: int, request: Request, db: Session = Depends(get_db)):
    """点开参考来源：返回该条引用的知识库切片全文与出处信息。

    站内多数切片没有外链（source_url 为空），因此统一走这个站内端点，
    保证每条 [n] 引用都能点开看到「出自哪份资料的哪个章节 + 原文 + 引用要求」。
    """
    chunk = db.get(Chunk, chunk_id)
    if not chunk:
        raise HTTPException(404, tr("该来源切片不存在", lang_of(request)))
    return {
        "chunk_id": chunk.id,
        "title": chunk.title or "",
        "section": chunk.section or "",
        "page": chunk.page or "",
        "doc_id": chunk.doc_id or "",
        "source_url": chunk.source_url or "",
        "license": chunk.license or "",
        "text": chunk.text or "",
    }
