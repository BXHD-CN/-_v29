# -*- coding: utf-8 -*-
"""安全中间件：请求 ID、安全响应头、注册门禁、CSRF 双提交校验、访客会话。

鉴权策略（本轮按用户最新要求调整为「首页免登录 + 功能页注册门禁」）：
- 首页 / 与 /index.html 匿名可看：作为站点门面，展示能力入口与知识库规模；
  配套的只读统计接口 /api/public/overview 同样匿名放行，避免首页数字为空。
- 其余 HTML 页面（翻译、语言质量、告知单、资讯、云端资产、我的资产等）
  及全部功能 /api/* 仍要求有效会话：未登录页面 302 回 register.html，
  未登录接口 401，带 next 与 sharecode 原路返回。
- 注册入口 / 登录入口本身必须匿名可用；登录三件套与 /api/auth/me
  （探测登录态）也在白名单内；/api/health 供发布平台健康检查使用。
- 静态资源（css/js/vendor/图标）始终放行，否则门禁页无法渲染。
- 首次访问下发匿名 csrf_token Cookie；登录后 auth._set_auth_cookies 覆盖同名
  Cookie，CSRF 始终按「Cookie 与 X-CSRF-Token 头一致」做双提交校验。
"""
import secrets
import uuid
from urllib.parse import quote

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from .config import get_settings
from .db import SessionLocal
from .i18n import lang_of, tr
from .models import RevokedToken, User
from .security import COOKIE_NAME, CSRF_COOKIE, decode_token

settings = get_settings()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# 匿名可用的 API：注册 / 登录 / 登出 / 登录态探测 / 健康检查 / 首页只读统计
GUEST_API_PREFIXES = (
    "/api/auth/register", "/api/auth/login", "/api/auth/logout", "/api/auth/me",
    "/api/health", "/api/public/overview",
)

# 匿名可用的页面：首页（站点门面）+ 注册入口 + 已有账号的登录入口
GUEST_PAGES = {"/", "/index.html", "/register.html", "/login.html"}

# 静态资源：放行，避免门禁页样式与脚本被拦
STATIC_PREFIXES = ("/css/", "/js/", "/vendor/", "/static/", "/favicon.svg")
STATIC_SUFFIXES = (".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2", ".map")

# 这些接口不写库、不依赖会话（登录三件套本身要建/销会话）
CSRF_EXEMPT = {
    "/api/auth/login", "/api/auth/register", "/api/auth/logout",
}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # v=27：语音输入需要麦克风，按最小权限只放开本站自身；摄像头与定位仍禁用。
    "Permissions-Policy": "geolocation=(), microphone=(self), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
        # 云服务 SDK：CDN 为首选加载源；connect-src 放行云数据面与 OAuth Relay
        "script-src 'self' https://cdn.jsdelivr.net; "
        # blob: 供 MediaRecorder 本地回听，不引入任何外部媒体源
        "media-src 'self' blob:; "
        "connect-src 'self' https://*.workbuddy.cn https://*.workbuddy.host; "
        # 不声明 frame-ancestors：发布平台会为预览面板注入自己的值，
        # 若这里写 'none' 会与平台值共存，导致整条指令被浏览器忽略并报 CSP 错误；
        # 本地点击劫持防护由 X-Frame-Options: DENY 承担。
        "base-uri 'self'"
    ),
}


def is_guest_api(path: str) -> bool:
    for prefix in GUEST_API_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def is_static_asset(path: str) -> bool:
    if path in ("/favicon.svg", "/favicon.ico"):
        return True
    if path.startswith(STATIC_PREFIXES):
        return True
    return path.endswith(STATIC_SUFFIXES)


def is_registered(request: Request) -> bool:
    """有效会话 + 用户存在且启用 + 未被吊销 = 已完成注册并登录。"""
    token = request.cookies.get(COOKIE_NAME, "")
    payload = decode_token(token) if token else None
    if not payload:
        return False
    try:
        with SessionLocal() as db:
            if db.get(RevokedToken, payload.get("jti", "")):
                return False
            user = db.get(User, int(payload["sub"]))
            return bool(user and user.is_active)
    except Exception:
        return False


def ensure_anon_csrf(request: Request, response: Response) -> None:
    """访客首次访问下发匿名 CSRF Cookie，使注册页表单也能通过双提交校验。"""
    if request.cookies.get(CSRF_COOKIE):
        return
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(24),
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=60 * 60 * 24 * 30,
        path="/",
    )


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        request.state.lang = lang_of(request)

        path = request.url.path
        query = request.url.query
        suffix = ("?" + query) if query else ""

        # ---------- 注册门禁 ----------
        if path.startswith("/api/"):
            if not is_guest_api(path) and not is_registered(request):
                denied = JSONResponse(
                    {"detail": tr("请先注册并登录后再使用本站功能", request.state.lang),
                     "need_register": True},
                    status_code=401,
                )
                ensure_anon_csrf(request, denied)
                denied.headers["X-Request-ID"] = request_id
                return denied
        elif not is_static_asset(path) and path not in GUEST_PAGES:
            # 首页已在 GUEST_PAGES 放行；其余功能页面：未注册访客只放回注册入口。
            if not is_registered(request):
                # 带上原始目标（含 sharecode）与分享码，注册成功后前端原路返回
                # 到刚点的功能页，而不是退回首页。next 经 URL 编码，
                # 前端 registerUrl()/safeNext() 会解码并校验格式。
                target = (path.lstrip("/") or "index.html") + suffix
                redirect_url = "register.html?next=" + quote(target, safe="")
                sharecode = request.query_params.get("sharecode")
                if sharecode:
                    redirect_url += "&sharecode=" + quote(sharecode, safe="")
                redirect = RedirectResponse(redirect_url, status_code=302)
                ensure_anon_csrf(request, redirect)
                redirect.headers["X-Request-ID"] = request_id
                return redirect

        # ---------- CSRF 双提交 ----------
        if request.method not in SAFE_METHODS and path.startswith("/api/"):
            if path not in CSRF_EXEMPT:
                cookie_token = request.cookies.get(CSRF_COOKIE, "")
                header_token = request.headers.get("x-csrf-token", "")
                if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
                    denied = JSONResponse(
                        {"detail": tr("CSRF 校验失败，请刷新页面重试", request.state.lang)},
                        status_code=403,
                    )
                    ensure_anon_csrf(request, denied)
                    denied.headers["X-Request-ID"] = request_id
                    return denied

        response = await call_next(request)
        ensure_anon_csrf(request, response)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        response.headers["X-Request-ID"] = request_id
        return response
