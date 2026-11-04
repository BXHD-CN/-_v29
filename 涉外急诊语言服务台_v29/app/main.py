# -*- coding: utf-8 -*-
"""应用入口：uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .i18n import lang_of, tr_detail
from .shield import SecurityMiddleware
from .routers import (admin, auth, corpus, culture, health, history, me, news, patient_check,
                      public, qa, refs, speech, terms, transfer, translate)

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(BASE_DIR / "data").mkdir(exist_ok=True)
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/api/docs",
              redoc_url=None, lifespan=lifespan)
app.add_middleware(SecurityMiddleware)


@app.exception_handler(HTTPException)
async def localized_http_exception(request: Request, exc: HTTPException):
    """全站错误信息按 X-Lang 双语返回；只翻译文案，不动结构化字段。"""
    return JSONResponse(
        {"detail": tr_detail(exc.detail, lang_of(request))},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def localized_validation_exception(request: Request, exc: RequestValidationError):
    lang = lang_of(request)
    errors = []
    for item in exc.errors():
        entry = dict(item)
        if isinstance(entry.get("msg"), str):
            entry["msg"] = tr_detail(entry["msg"], lang)
        errors.append(entry)
    return JSONResponse({"detail": errors}, status_code=422)


app.include_router(health.router)
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(terms.router)
app.include_router(refs.router)
app.include_router(culture.router)
app.include_router(patient_check.router)
app.include_router(corpus.router)
app.include_router(translate.router)
app.include_router(speech.router)
app.include_router(qa.router)
app.include_router(news.router)
app.include_router(me.router)
app.include_router(history.router)
app.include_router(transfer.router)
app.include_router(admin.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    # 静态页面走站点根路径（/login.html 等）；放在所有 /api 路由之后，API 优先匹配
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="site")


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"app": settings.app_name, "docs": "/api/docs"}
