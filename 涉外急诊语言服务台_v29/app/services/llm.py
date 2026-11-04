# -*- coding: utf-8 -*-
"""生成服务：mock=不调模型；deepseek / generic=OpenAI 兼容 chat/completions。

失败统一抛 LLMUnavailable，由上层（rag、translate_service）降级为摘录/术语替换模式。
"""
from __future__ import annotations

import logging

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

CHAT_TIMEOUT = 25.0
MOCK_TEXT = "（当前未配置生成模型，仅提供检索结果）"


class LLMUnavailable(RuntimeError):
    """生成模型不可用：未配置 Key、网络超时、返回格式异常等。"""

    code = "llm_unavailable"

    def __init__(self, message: str = "生成模型暂时不可用") -> None:
        super().__init__(message)
        self.message = message


def provider() -> str:
    """当前生成 provider：mock / deepseek / generic。"""
    return (settings.llm_provider or "mock").strip().lower()


def is_mock() -> bool:
    """是否处于无生成模型状态（需要走摘录模式）。"""
    return provider() == "mock"


def _endpoint(provider_name: str | None = None) -> tuple[str, str, str]:
    """返回 (url, api_key, model)。"""
    p = provider_name or provider()
    if p == "deepseek":
        base = (settings.deepseek_base or "").rstrip("/")
        return f"{base}/chat/completions", settings.deepseek_api_key.strip(), settings.deepseek_model
    if p == "generic":
        base = (settings.generic_base or "").rstrip("/")
        return f"{base}/chat/completions", settings.generic_api_key.strip(), settings.generic_model
    return "", "", ""


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 800,
         force_provider: str | None = None) -> str:
    """同步对话补全，超时 25s；mock 直接返回固定提示语。

    force_provider 供翻译模块在 MT_PROVIDER=deepseek 而 LLM_PROVIDER=mock 时显式指定。
    """
    p = (force_provider or provider()).strip().lower()
    if p == "mock":
        return MOCK_TEXT
    if p not in ("deepseek", "generic"):
        raise LLMUnavailable(f"不支持的 LLM provider：{p}")

    url, api_key, model = _endpoint(p)
    if not url or not model:
        raise LLMUnavailable(f"{p} 的 base/model 未配置")
    if not api_key:
        raise LLMUnavailable(f"未配置 {p} 的 API Key")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=CHAT_TIMEOUT) as client:
            resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        content = (content or "").strip()
        if not content:
            raise ValueError("模型返回内容为空")
        return content
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        # 只记错误类型，不回显 Key
        logger.warning("LLM 调用失败：%s: %s", type(exc).__name__, exc)
        raise LLMUnavailable(f"{p} 生成服务调用失败：{type(exc).__name__}") from exc
