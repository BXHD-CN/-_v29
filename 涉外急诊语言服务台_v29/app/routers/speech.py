# -*- coding: utf-8 -*-
"""语音识别接口：POST /api/speech/recognize、GET /api/speech/status。

v=27 设计边界（与「语音是输入旁路适配层」方案一致）：
- 只做 音频 → 文本；不翻译、不做医学抽取、不写库、不落盘；
- 接口受全局注册门禁 + CSRF 双提交保护，密钥只在服务端；
- 前端永远只连同源 /api/speech/recognize，不接触第三方 ASR 地址；
- 识别文本与键盘输入完全等价，后续翻译 / 告知单链路零改动；
- 日志只记长度、MIME、耗时、provider 与错误码，绝不记录音频内容或患者原话。

返回结构保持极小且稳定：{text, lang, confidence, duration_ms, provider,
demo, request_id}。demo=True 表示课程演示识别结果，前端必须显式标注。
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..config import get_settings
from ..deps import client_ip
from ..i18n import lang_of, tr
from ..services import asr

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/speech", tags=["speech"])

# 面向前端的错误码 → 中文文案（英文由 i18n 字典 / EXTRA 统一翻译）
ERRORS = {
    "asr_no_audio": "没有收到录音音频，请重新录制",
    "asr_too_large": "录音文件过大，请缩短录音后重试",
    "asr_too_long": "录音时长超过上限，请分段录制",
    "asr_bad_type": "不支持的录音格式，请换用 Chrome 或 Edge 浏览器重试",
    "asr_rate_limited": "语音识别请求过于频繁，请稍后再试",
    "asr_not_configured": "语音识别服务尚未配置，请联系管理员",
    "asr_http_error": "语音识别服务暂时不可用，请稍后重试",
    "asr_empty_result": "没有识别到清晰语音，请靠近麦克风再说一遍",
    "asr_failed": "语音识别失败，请重试或改用键盘输入",
}


class Limiter:
    """进程内滑动窗口限流；与 translate.py 同思路，避免语音接口被刷。"""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = max(1, limit)
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return True
            hits.append(now)
            self._hits[key] = hits
            # 顺手清理长期不用的 key，避免进程内存无限增长
            if len(self._hits) > 2048:
                self._hits = {k: v for k, v in self._hits.items() if now - v[-1] < self.window}
            return False


limiter = Limiter(settings.asr_rate_limit, 60.0)


def fail(code: str, lang: str, status: int = 400) -> HTTPException:
    """统一错误出口：中文原文 → 按 lang 翻译；附带稳定 code 供前端分支处理。"""
    message = ERRORS.get(code, ERRORS["asr_failed"])
    return HTTPException(status_code=status,
                         detail={"message": tr(message, lang), "code": code})


@router.get("/status")
def speech_status(request: Request):
    """前端能力探测：provider / 是否演示 / 大小与时长上限。不暴露密钥与 URL。"""
    kind = asr.provider()
    if kind != "http":
        kind = "mock"
    return {
        "available": True,
        "provider": kind,
        "demo": kind == "mock",
        "max_audio_bytes": int(settings.asr_max_audio_bytes),
        "max_duration_ms": int(settings.asr_max_duration_ms),
        "rate_limit": int(settings.asr_rate_limit),
        "lang": lang_of(request),
        "request_id": getattr(request.state, "request_id", ""),
    }


@router.post("/recognize")
async def recognize(
    request: Request,
    audio: UploadFile = File(..., description="浏览器 MediaRecorder 录制的音频片段"),
    lang: str = Form(default="zh"),
    duration_ms: int = Form(default=0),
    demo_text: str = Form(default=""),
):
    """把一段录音识别成文本；不改动任何既有翻译 / 告知单行为。"""
    lang_code = lang_of(request)                       # 界面语言：决定错误文案
    # 口述语种可与界面语言不同（中文界面下患者说英语）：表单 lang 优先，仅允许 zh / en。
    hint_lang = (lang or "").strip().lower()[:2]
    speech_lang = hint_lang if hint_lang in ("zh", "en") else lang_code
    client = client_ip(request)
    if limiter.blocked(client):
        raise fail("asr_rate_limited", lang_code, 429)

    content_type = (audio.content_type or "").strip().lower()
    if not asr.mime_supported(content_type):
        logger.info("asr rejected mime=%s client=%s", content_type.split(";")[0], client)
        raise fail("asr_bad_type", lang_code, 415)

    if duration_ms and duration_ms > int(settings.asr_max_duration_ms):
        raise fail("asr_too_long", lang_code, 413)

    max_bytes = int(settings.asr_max_audio_bytes)
    # 只读「上限 + 1」字节：超限直接拒绝，不把大文件读进内存
    body = await audio.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise fail("asr_too_large", lang_code, 413)
    if not body:
        raise fail("asr_no_audio", lang_code, 400)

    # mock 演示模式允许联调时指定口述内容（仅供本地验收 / 教学演示）；
    # http 模式一律忽略，避免前端伪造识别文本绕过真实 ASR。
    hint = demo_text if asr.provider() != "http" else ""
    try:
        result = asr.recognize(body, content_type, lang=speech_lang, demo_text=hint[:1000])
    except asr.ASRUnavailable as exc:
        logger.info("asr unavailable code=%s client=%s", exc.code, client)
        code = exc.code if exc.code in ERRORS else "asr_failed"
        status = 503 if code in ("asr_http_error", "asr_not_configured") else 502
        raise fail(code, lang_code, status) from exc
    except Exception as exc:  # 任何意外都收敛成可读错误，绝不把堆栈 / 音频回给前端
        logger.warning("asr unexpected error: %s", type(exc).__name__)
        raise fail("asr_failed", lang_code, 502) from exc

    text = str(result.get("text") or "").strip()
    if not text:
        raise fail("asr_empty_result", lang_code, 422)

    result["text"] = text
    result["request_id"] = getattr(request.state, "request_id", "")
    return result
