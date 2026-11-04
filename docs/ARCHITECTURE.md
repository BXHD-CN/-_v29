# 站点架构与请求流程

## 1. 进程与分层

```
            ┌──────────────────────────── Nginx（生产）───────────────────────────┐
            │ TLS1.2/1.3 · HSTS · 安全头 · limit_req · /api/admin IP 白名单          │
            └───────────────────────────────────┬──────────────────────────────────┘
                                                │ 127.0.0.1:8000
┌───────────────────────────────────────────────▼──────────────────────────────────┐
│ FastAPI（app/main.py）                                                             │
│  SecurityMiddleware：请求ID · 安全头 · CSRF 双提交校验                              │
│  routers: auth / health / terms / corpus / me / translate / qa / news / admin      │
│  services: embedding · llm · retrieval · translate_service · rag · crawler         │
└───────────────┬───────────────────────────────────┬──────────────────────────────┘
                │ SQLAlchemy                        │ httpx（服务端）
        ┌───────▼────────┐                  ┌───────▼───────────────────────┐
        │ SQLite（开发）  │                  │ BigModel embedding-3           │
        │ PostgreSQL+vec  │                  │ DeepSeek / 任意 MT 端口        │
        │ （生产）        │                  │ UN News / ReliefWeb / USGS     │
        └────────────────┘                  └───────────────────────────────┘
```

## 2. 三类数据的读写路径

| 数据 | 写 | 读 | 隔离 |
| --- | --- | --- | --- |
| 公共术语/语料（4,154 / 8,308） | 只能由导入脚本 `seed_public.py` 写 | `/api/terms`、`/api/corpus` 只读 | 全员可见 |
| 用户私有术语/语料 | `/api/me/*` 增删改（带 CSRF + 登录态） | 同左，永远带 `user_id` 过滤 | 他人 404 |
| 知识切片（≥120） | `build_slices.py` + `embed_chunks.py` | `/api/qa` 检索 | 全员可问，引用可溯源 |

## 3. 一次翻译请求

```
POST /api/translate {text, src, tgt}
  → 登录校验（require_user）+ CSRF + 限流（10 次/分钟）
  → translate_service.translate()
      ① 术语锁定：search_terms(text) 最长匹配 → must_use 列表
      ② 语料上下文：search_corpus(text, lang_pair) top-3
      ③ MT：deepseek / generic（百度/腾讯/DeepL 端口）/ mock（术语+句对拼装）
      ④ 译后校验：must_use 译法缺失则强制替换，记 notes
  → 返回 {translation, locked_terms, context_pairs, provider, degraded}
```

## 4. 一次问答请求

```
POST /api/qa {question}
  → 登录 + CSRF + 限流（20 次/分钟）
  → rag.answer()
      ① embed(question)（local 或 BigModel）
      ② 余弦检索 top-5（SQLite: numpy；PG: pgvector <=>）
      ③ 最高分 < 0.35 → refused=true（不调模型）
      ④ LLM 生成，要求句末 [n]；引用校验失败→重试 1 次→摘录模式
  → 返回 {answer, citations[{index,title,section,page,source_url,score,snippet}], refused, reason}
```

## 5. 一次私有库写入

```
POST /api/me/terms {zh,en,...}
  → 必须登录；中间件校验 X-CSRF-Token == cookie
  → 唯一约束 (user_id, zh, en) 冲突 → 409
  → 写 user_terms 并记审计日志
GET /api/me/terms 只返回 user_id == 当前用户 的行；PUT/DELETE 他人 id → 404
```

## 6. 安全边界

- 浏览器永远不直接调用 BigModel/DeepSeek：Key 只在服务端 `.env`，前端只调本站 `/api/*`；
- 所有 SQL 走 SQLAlchemy 参数化；所有用户输入有长度上限；
- 私有数据不进入公共检索：`/api/qa` 只查 chunks 表，不查 user_terms / user_corpus；
- 管理接口双重保护：`require_admin` + Nginx IP 白名单；
- 审计日志记录写操作（谁、什么、哪个对象、IP）。
