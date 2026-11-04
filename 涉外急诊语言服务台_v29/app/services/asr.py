# -*- coding: utf-8 -*-
"""语音识别服务：把前端录制的音频转成「一段文本」。

v=27 设计边界（与语音翻译方案一致）：
- 只做 音频 → 文本；不翻译、不做医学抽取、不写库、不落盘；
- 密钥只在服务端，前端永远只连同源 /api/speech/recognize；
- mock = 课程演示模式：不联网、不落盘，返回可复现的示例文本，
  并显式返回 demo=True，前端必须标注「演示识别结果」；
  http = 服务端中转第三方 ASR，URL / Key / 超时全部走配置；
- 日志只记长度、MIME、耗时与 provider，绝不记录音频内容或患者原话。

结构化抽取、字段映射、清单生成都在前端语音模块，
本模块产出的一段文本与键盘输入完全等价，不触碰既有翻译 / 告知单链路。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 浏览器 MediaRecorder 常见输出；application/octet-stream 作为 Safari 兜底
SUPPORTED_MIME = {
    "audio/webm", "audio/webm;codecs=opus", "audio/ogg", "audio/ogg;codecs=opus",
    "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/aac",
    "application/octet-stream",
}


class ASRUnavailable(Exception):
    """ASR 服务不可用 / 返回不可用结果；上层统一转成可读错误，不 500。"""

    code = "asr_unavailable"

    def __init__(self, message: str, code: str = "asr_unavailable") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def provider() -> str:
    """当前 ASR provider：mock（默认演示）或 http（服务端中转）。"""
    return (settings.asr_provider or "mock").strip().lower()


def mime_supported(content_type: str) -> bool:
    """MIME 白名单；空值按 octet-stream 兜底，避免 Safari 传空类型被误拒。"""
    value = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    return value in {item.split(";")[0].strip().lower() for item in SUPPORTED_MIME}


def _demo_text(lang: str) -> str:
    if lang == "en":
        return (settings.asr_demo_text_en or "").strip() or \
            "The patient reports chest pain for two hours, with shortness of breath."
    return (settings.asr_demo_text or "").strip() or "患者主诉胸痛两小时，伴呼吸困难。"


def _http_recognize(audio: bytes, content_type: str, lang: str) -> str:
    """把音频 POST 给可配置的 ASR 端点；只接受 JSON 中的 text / result / data.text。"""
    url = (settings.asr_http_url or "").strip()
    if not url:
        raise ASRUnavailable("未配置 ASR_HTTP_URL", "asr_not_configured")
    headers: dict[str, str] = {}
    key = (settings.asr_http_key or "").strip()
    if key:
        headers["Authorization"] = "Bearer " + key
    timeout = float(settings.asr_http_timeout or 20.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url,
                files={"audio": ("speech.bin", audio, content_type or "application/octet-stream")},
                data={"lang": lang}, headers=headers,
            )
        response.raise_for_status()
        payload: Any = response.json()
    except ASRUnavailable:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("ASR http 调用失败：%s", type(exc).__name__)
        raise ASRUnavailable(f"ASR 调用失败：{type(exc).__name__}", "asr_http_error") from exc

    text = ""
    if isinstance(payload, dict):
        raw = payload.get("text") or payload.get("result")
        if not raw and isinstance(payload.get("data"), dict):
            raw = payload["data"].get("text")
        text = str(raw or "").strip()
    elif isinstance(payload, str):
        text = payload.strip()
    if not text:
        raise ASRUnavailable("ASR 返回空识别结果", "asr_empty_result")
    return text


def recognize(audio: bytes, content_type: str, lang: str = "zh",
              demo_text: str = "") -> dict:
    """统一入口：返回 {text, lang, confidence, duration_ms, provider, demo}。"""
    started = time.time()
    lang = "en" if lang == "en" else "zh"
    kind = provider()
    if kind == "http":
        text = _http_recognize(audio, content_type, lang)
        demo = False
        confidence = 0.9
    else:
        # mock 演示：允许联调时通过 demo_text 指定口述内容，便于验收与教学演示。
        text = (demo_text or "").strip() or _demo_text(lang)
        demo = True
        confidence = 0.95
        kind = "mock"
    duration_ms = int((time.time() - started) * 1000)
    logger.info("asr provider=%s lang=%s bytes=%s mime=%s demo=%s elapsed_ms=%s",
                kind, lang, len(audio), (content_type or "").split(";")[0], demo, duration_ms)
    return {
        "text": text,
        "lang": lang,
        "confidence": confidence,
        "duration_ms": duration_ms,
        "provider": kind,
        "demo": demo,
    }
