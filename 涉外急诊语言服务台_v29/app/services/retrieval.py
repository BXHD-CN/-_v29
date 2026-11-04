# -*- coding: utf-8 -*-
"""检索服务：切片向量检索（SQLite 用 numpy 余弦，PostgreSQL 用 pgvector）、
术语/平行语料的轻量关键词检索。

- search_chunks：查询先 embed_texts，再按库型走不同实现；阈值过滤交给调用方（rag）。
- search_terms / search_corpus：LIKE + 长文本包含命中 + 简单打分，够用且无需分词包。
"""
from __future__ import annotations

import json
import logging
import re
import struct

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal, engine
from ..models import Chunk, PublicCorpus, PublicTerm
from .embedding import cosine, embed_texts

logger = logging.getLogger(__name__)
settings = get_settings()

try:  # numpy 可选：装了就用矩阵运算，没装则纯 Python 兜底（不新装依赖）
    import numpy as _np
except ImportError:  # pragma: no cover - 取决于环境
    _np = None
    logger.info("未安装 numpy，切片检索使用纯 Python 余弦实现")

_IS_POSTGRES = settings.database_url.startswith(("postgresql", "postgres"))

# 切片向量缓存：chunk_id -> list[float]；按需加载，条数变化时清理失效项
_VECTOR_CACHE: dict[int, list[float]] = {}
_VECTOR_CACHED_COUNT = -1

# 术语索引缓存：[(id, zh_lower, en_lower)]，用于长文本（整句）包含命中
_TERM_INDEX: list[tuple[int, str, str]] = []
_TERM_INDEX_COUNT = -1


# ---------------------------------------------------------------- 切片检索
def _refresh_vector_cache(rows: list) -> None:
    global _VECTOR_CACHED_COUNT
    if len(rows) != _VECTOR_CACHED_COUNT:
        alive = {r.id for r in rows}
        for chunk_id in list(_VECTOR_CACHE):
            if chunk_id not in alive:
                _VECTOR_CACHE.pop(chunk_id, None)
        _VECTOR_CACHED_COUNT = len(rows)
    for row in rows:
        if row.id in _VECTOR_CACHE:
            continue
        raw = (row.embedding or "").strip()
        if not raw:
            continue
        try:
            vec = json.loads(raw)
            if isinstance(vec, list) and vec:
                _VECTOR_CACHE[row.id] = [float(x) for x in vec]
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("chunk %s 的 embedding 不是合法 JSON，已跳过", row.id)


def _row_brief(row) -> dict:
    return {
        "chunk_id": row.id,
        "title": row.title or "",
        "text": row.text or "",
        "source_url": row.source_url or "",
        "section": row.section or "",
        "page": row.page or "",
        "license": row.license or "",
        "doc_id": row.doc_id or "",
    }


def _sqlite_search(qvec: list[float], top_k: int) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(Chunk.id, Chunk.title, Chunk.text, Chunk.source_url, Chunk.section,
                   Chunk.page, Chunk.license, Chunk.doc_id, Chunk.embedding)
            .where(Chunk.embedding != "")
        ).all()
    _refresh_vector_cache(rows)

    pairs = [(row, _VECTOR_CACHE.get(row.id)) for row in rows]
    pairs = [(row, vec) for row, vec in pairs if vec]
    if not pairs:
        return []

    if _np is not None:
        matrix = _np.asarray([vec for _, vec in pairs], dtype=_np.float32)
        query = _np.asarray(qvec, dtype=_np.float32)
        denom = _np.linalg.norm(matrix, axis=1) * _np.linalg.norm(query)
        scores = (matrix @ query) / _np.maximum(denom, 1e-12)
        scored = [(float(scores[i]), pairs[i][0]) for i in range(len(pairs))]
    else:
        scored = [(cosine(qvec, vec), row) for row, vec in pairs]

    scored.sort(key=lambda item: item[0], reverse=True)
    out = []
    for score, row in scored[:top_k]:
        item = _row_brief(row)
        item["score"] = round(float(score), 6)
        out.append(item)
    return out


def _pg_search(qvec: list[float], top_k: int) -> list[dict]:
    """PostgreSQL + pgvector：embedding <=> :q 走 HNSW 索引。"""
    qlit = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"
    sql = text(
        """
        SELECT c.id AS chunk_id, c.title, c.text, c.source_url, c.section, c.page, c.license,
               c.doc_id, 1 - (v.embedding <=> CAST(:q AS vector)) AS score
        FROM chunk_vectors v
        JOIN chunks c ON c.id = v.chunk_id
        ORDER BY v.embedding <=> CAST(:q AS vector)
        LIMIT :k
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"q": qlit, "k": int(top_k)}).mappings().all()
    out = []
    for row in rows:
        out.append({
            "chunk_id": row["chunk_id"],
            "title": row["title"] or "",
            "text": row["text"] or "",
            "source_url": row["source_url"] or "",
            "section": row["section"] or "",
            "page": row["page"] or "",
            "license": row["license"] or "",
            "doc_id": row["doc_id"] or "",
            "score": round(float(row["score"] or 0.0), 6),
        })
    return out


def search_chunks(query: str, top_k: int = 5, threshold: float = 0.0) -> list[dict]:
    """按余弦相似度检索切片，score 降序；threshold 在返回前过滤。"""
    q = (query or "").strip()
    if not q:
        return []
    query_vec = embed_texts([q])[0]  # EmbeddingUnavailable 由上层降级
    top_k = max(1, int(top_k))
    candidates = _pg_search(query_vec, top_k * 3) if _IS_POSTGRES else _sqlite_search(query_vec, top_k * 3)
    candidates = [c for c in candidates if c["score"] >= threshold]
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:top_k]


# ---------------------------------------------------------------- 术语检索
def _load_term_index(db: Session) -> list[tuple[int, str, str]]:
    global _TERM_INDEX, _TERM_INDEX_COUNT
    total = db.scalar(select(func.count()).select_from(PublicTerm)) or 0
    if total != _TERM_INDEX_COUNT:
        rows = db.execute(select(PublicTerm.id, PublicTerm.zh, PublicTerm.en)).all()
        _TERM_INDEX = [(r.id, (r.zh or "").lower(), (r.en or "").lower()) for r in rows]
        _TERM_INDEX_COUNT = total
    return _TERM_INDEX


def _contains_word(haystack: str, needle: str) -> bool:
    """英文术语按词边界匹配，避免 tri 命中 triage。"""
    start = haystack.find(needle)
    while start >= 0:
        before = haystack[start - 1] if start > 0 else " "
        end = start + len(needle)
        after = haystack[end] if end < len(haystack) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = haystack.find(needle, start + 1)
    return False


def _like_score(term: PublicTerm, query_lower: str) -> float:
    zh = (term.zh or "").lower()
    en = (term.en or "").lower()
    best = 0.0
    for value in (zh, en):
        if not value:
            continue
        if value == query_lower:
            best = max(best, 60.0)
        elif value.startswith(query_lower):
            best = max(best, 50.0)
        elif query_lower in value:
            best = max(best, 40.0)
    return best


def search_terms(query: str, limit: int = 10) -> list[PublicTerm]:
    """术语检索：短查询走 LIKE；整句查询走长文本包含命中（术语锁定主力）。"""
    q = (query or "").strip()
    if not q:
        return []
    lowered = q.lower()
    scores: dict[int, float] = {}

    with SessionLocal() as db:
        # ① LIKE：查询本身是关键词时命中释义/译名
        if len(q) <= 40 and "\n" not in q:
            like = f"%{q}%"
            for term in db.scalars(
                select(PublicTerm)
                .where(or_(PublicTerm.zh.like(like), PublicTerm.en.like(like)))
                .limit(max(limit * 3, 30))
            ).all():
                score = _like_score(term, lowered)
                if score > 0:
                    scores[term.id] = max(scores.get(term.id, 0.0), score)

        # ② 包含命中：text 里出现了术语的中文/英文写法
        for term_id, zh, en in _load_term_index(db):
            hit = 0.0
            if len(zh) >= 2 and zh in lowered:
                hit = 1000.0 + len(zh)
            elif len(en) >= 3 and _contains_word(lowered, en):
                hit = 1000.0 + len(en) * 2
            if hit > scores.get(term_id, 0.0):
                scores[term_id] = hit

        if not scores:
            return []
        wanted = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:max(limit, 1) * 2]
        rows = db.scalars(select(PublicTerm).where(PublicTerm.id.in_([tid for tid, _ in wanted]))).all()
        rows.sort(key=lambda term: scores.get(term.id, 0.0), reverse=True)
        return rows[:max(limit, 1)]


# ---------------------------------------------------------------- 语料检索
def _query_keys(query: str) -> list[str]:
    """抽取语料检索用的关键词：先取命中术语，再补英文词与中文 2–4 字片段。"""
    keys: list[str] = []
    for term in search_terms(query, limit=4):
        if term.zh:
            keys.append(term.zh)
        if term.en:
            keys.append(term.en)
    keys.extend(re.findall(r"[A-Za-z][A-Za-z\-]{2,}", query)[:4])
    zh_chars = "".join(re.findall(r"[\u4e00-\u9fff]+", query))
    if len(zh_chars) >= 2:
        keys.extend(zh_chars[i:i + 2] for i in range(0, min(len(zh_chars), 12) - 1, 2))
    seen: list[str] = []
    for key in keys:
        key = key.strip()
        if key and key.lower() not in {k.lower() for k in seen}:
            seen.append(key)
    return seen[:6]


def search_corpus(query: str, lang_pair: str = "", limit: int = 3) -> list[PublicCorpus]:
    """平行语料检索：LIKE 取候选，再按关键词命中数与长度接近度打分。"""
    q = (query or "").strip()
    if not q:
        return []
    keys = _query_keys(q)
    if not keys:
        return []

    conditions = []
    for key in keys:
        conditions.append(PublicCorpus.zh.like(f"%{key}%"))
        conditions.append(PublicCorpus.en.like(f"%{key}%"))

    with SessionLocal() as db:
        stmt = select(PublicCorpus).where(or_(*conditions))
        if lang_pair:
            stmt = stmt.where(PublicCorpus.lang_pair == lang_pair)
        rows = db.scalars(stmt.limit(80)).all()
        if not rows and lang_pair:
            return []  # 指定语种对无命中时不跨语种凑数

        lowered_keys = [k.lower() for k in keys]
        scored: list[tuple[float, int, PublicCorpus]] = []
        for row in rows:
            zh = (row.zh or "").lower()
            en = (row.en or "").lower()
            hit = sum(1 for key in lowered_keys if key in zh or key in en)
            if hit == 0:
                continue
            closeness = 1.0 / (1.0 + abs(len(row.zh or "") - len(q)) / 50.0)
            scored.append((hit * 10.0 + closeness, hit, row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [row for _, _, row in scored[:max(limit, 1)]]


# ---------------------------------------------------------------- 语料句对向量检索
def _corpus_brief(row: dict) -> dict:
    """corpus_vectors JOIN public_corpus 的一行 → 对外字段（不含向量）。"""
    return {
        "id": row["id"],
        "corpus_id": row["corpus_id"],
        "zh": row["zh"] or "",
        "en": row["en"] or "",
        "lang_pair": row["lang_pair"] or "",
        "source_code": row["source_code"] or "",
        "source_url": row["source_url"] or "",
    }


def _sqlite_corpus_search(qvec: list[float], lang_pair: str, limit: int) -> list[dict]:
    """SQLite：读 corpus_vectors 的 float32 BLOB，用 numpy 做余弦（无 numpy 时纯 Python 兜底）。"""
    where = "WHERE c.lang_pair = :lang_pair" if lang_pair else ""
    sql = text(
        f"""
        SELECT c.id, c.corpus_id, c.zh, c.en, c.lang_pair, c.source_code, c.source_url, v.vector
        FROM corpus_vectors v
        JOIN public_corpus c ON c.id = v.corpus_id
        {where}
        """
    )
    params: dict = {}
    if lang_pair:
        params["lang_pair"] = lang_pair
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    if not rows:
        return []

    if _np is not None:
        # float32 小端 BLOB 直接拼成 (n, 1024) 矩阵，一次矩阵乘算完所有余弦
        blobs = b"".join(row["vector"] for row in rows)
        try:
            matrix = _np.frombuffer(blobs, dtype="<f4")
            matrix = matrix.reshape(len(rows), -1).astype(_np.float32, copy=False)
        except (ValueError, TypeError):
            logger.warning("corpus_vectors 中存在长度不一致的向量，已跳过该批")
            return []
        query = _np.asarray(qvec, dtype=_np.float32)
        query_norm = float(_np.linalg.norm(query))
        denom = _np.linalg.norm(matrix, axis=1) * max(query_norm, 1e-12)
        scores = (matrix @ query) / _np.maximum(denom, 1e-12)
        order = _np.argsort(scores)[::-1][:limit]
        out = []
        for index in order:
            item = _corpus_brief(rows[int(index)])
            item["score"] = round(float(scores[int(index)]), 6)
            out.append(item)
        return out

    scored: list[tuple[float, int]] = []
    for index, row in enumerate(rows):
        raw = row["vector"] or b""
        if len(raw) % 4:
            continue
        vec = list(struct.unpack("<%df" % (len(raw) // 4), raw))
        scored.append((cosine(qvec, vec), index))
    scored.sort(key=lambda item: item[0], reverse=True)
    out = []
    for score, index in scored[:limit]:
        item = _corpus_brief(rows[index])
        item["score"] = round(float(score), 6)
        out.append(item)
    return out


def _pg_corpus_search(qvec: list[float], lang_pair: str, limit: int) -> list[dict]:
    """PostgreSQL + pgvector 接口（“留接口”）：生产迁移后 corpus_vectors 增加
    embedding vector(1024) 列与 HNSW 索引，生成侧改为写向量列即可替换 SQLite 分支。"""
    qlit = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"
    where = "WHERE c.lang_pair = :lang_pair" if lang_pair else ""
    sql = text(
        f"""
        SELECT c.id, c.corpus_id, c.zh, c.en, c.lang_pair, c.source_code, c.source_url,
               1 - (v.embedding <=> CAST(:q AS vector)) AS score
        FROM corpus_vectors v
        JOIN public_corpus c ON c.id = v.corpus_id
        {where}
        ORDER BY v.embedding <=> CAST(:q AS vector)
        LIMIT :k
        """
    )
    params: dict = {"q": qlit, "k": int(limit)}
    if lang_pair:
        params["lang_pair"] = lang_pair
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except Exception as exc:  # 生产未迁移时降级为空结果，不阻断调用方
        logger.warning("PostgreSQL 语料向量检索待迁移（corpus_vectors.embedding）：%s", exc)
        return []
    out = []
    for row in rows:
        item = _corpus_brief(row)
        item["score"] = round(float(row["score"] or 0.0), 6)
        out.append(item)
    return out


def search_corpus_vector(query: str, lang_pair: str = "", limit: int = 5) -> list[dict]:
    """语料句对向量检索：query 先 embed_texts，再按库型做余弦。

    返回 [{id, corpus_id, zh, en, lang_pair, source_code, source_url, score}]，score 降序。
    SQLite 读 corpus_vectors 的 float32 BLOB（numpy 余弦）；PostgreSQL 走 pgvector 接口。
    """
    q = (query or "").strip()
    if not q:
        return []
    query_vec = embed_texts([q])[0]  # EmbeddingUnavailable 由上层降级
    top_k = max(1, int(limit))
    if _IS_POSTGRES:
        return _pg_corpus_search(query_vec, lang_pair, top_k)
    return _sqlite_corpus_search(query_vec, lang_pair, top_k)
