# -*- coding: utf-8 -*-
"""向量服务：local=确定性哈希（离线兜底，演示用）；bigmodel=智谱 embedding-3。

统一约定：
- 输出 1024 维（settings.embedding_dim）、已做 L2 归一化的 list[float]；
- 任何网络/鉴权/解析异常都包装成 EmbeddingUnavailable，由调用方降级，不向上抛裸异常；
- 严禁把 API Key 写进日志或响应。
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from collections import Counter

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_DIM: int = settings.embedding_dim
BATCH_SIZE = 32                 # 单次请求最多 32 条，避免超长请求被拒
EMBED_TIMEOUT = 20.0            # 秒
MAX_RETRY = 1                   # 失败重试 1 次
MOCK_HINT = "（向量服务未配置，使用本地哈希向量）"


class EmbeddingUnavailable(RuntimeError):
    """向量服务不可用：网络超时、鉴权失败、返回格式异常等。"""

    code = "embedding_unavailable"

    def __init__(self, message: str = "向量服务暂时不可用") -> None:
        super().__init__(message)
        self.message = message


def embedding_dim() -> int:
    """返回向量维度（契约固定 1024）。"""
    return EMBEDDING_DIM


def provider() -> str:
    """当前向量 provider：local / bigmodel。"""
    return (settings.embedding_provider or "local").strip().lower()


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0.0:
        return vec
    return [x / norm for x in vec]


def _tokens(text: str) -> list[str]:
    """生成特征：字符 1/2/3 gram（去空白）+ 英文/数字词。"""
    lowered = text.lower().strip()
    if not lowered:
        return []
    chars = re.sub(r"\s+", "", lowered)
    feats: list[str] = []
    for n in (1, 2, 3):
        for i in range(len(chars) - n + 1):
            feats.append(chars[i:i + n])
    feats.extend(f"w:{w}" for w in re.findall(r"[a-z0-9]+", lowered))
    return feats


def _bucket(token: str) -> int:
    """md5 前 8 位十六进制取模分桶，保证跨进程/跨机器确定性。"""
    return int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16) % EMBEDDING_DIM


def _local_embed_one(text: str) -> list[float]:
    counts = Counter(_tokens(text))
    vec = [0.0] * EMBEDDING_DIM
    for token, count in counts.items():
        # sublinear TF：1 + ln(tf)，抑制高频 gram 主导
        vec[_bucket(token)] += 1.0 + math.log(count)
    return _l2_normalize(vec)


def _bigmodel_embed(texts: list[str]) -> list[list[float]]:
    """调用智谱 /embeddings，批量 32，超时 20s，失败重试 1 次。"""
    api_key = settings.bigmodel_api_key.strip()
    if not api_key:
        raise EmbeddingUnavailable("未配置 BIGMODEL_API_KEY，无法调用 bigmodel 向量服务")
    base = settings.bigmodel_base.rstrip("/")
    url = f"{base}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    vectors: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        payload = {"model": settings.bigmodel_embedding_model or "embedding-3", "input": batch}
        last_error = "未知错误"
        for attempt in range(MAX_RETRY + 1):
            try:
                with httpx.Client(timeout=EMBED_TIMEOUT) as client:
                    resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                items = sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
                if len(items) != len(batch):
                    raise ValueError(f"返回条数 {len(items)} 与请求条数 {len(batch)} 不一致")
                for item in items:
                    vec = [float(x) for x in (item.get("embedding") or [])]
                    if len(vec) != EMBEDDING_DIM:
                        raise ValueError(f"返回维度 {len(vec)} != {EMBEDDING_DIM}")
                    vectors.append(_l2_normalize(vec))
                break
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                # 只记录错误类型与状态，绝不打印请求头里的 Key
                logger.warning("bigmodel embedding 第 %s 次尝试失败：%s", attempt + 1, last_error)
                if attempt >= MAX_RETRY:
                    raise EmbeddingUnavailable(
                        f"bigmodel 向量服务调用失败（已重试 {MAX_RETRY} 次）：{last_error}"
                    ) from exc
                time.sleep(0.5 * (attempt + 1))
    return vectors


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把文本批量转成 1024 维归一化向量。provider 由配置决定。"""
    if not texts:
        return []
    clean = ["" if t is None else str(t)[:8000] for t in texts]
    if provider() == "bigmodel":
        return _bigmodel_embed(clean)
    return [_local_embed_one(t) for t in clean]


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度；任一为零向量或维度不一致时返回 0.0。"""
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        dot += a[i] * b[i]
        na += a[i] * a[i]
        nb += b[i] * b[i]
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)
