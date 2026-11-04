# 站点开发契约（所有成员必读）

> 项目：work/site —— 涉外急诊语言服务台（课程实训作业站）
> 技术栈：FastAPI 0.115 + SQLAlchemy 2.0（同步 Session）+ SQLite（本地）/ PostgreSQL 15 + pgvector（生产）+ 原生 HTML/JS（无构建步骤）
> 运行：`cd work/site && ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000`
> 依赖已装在 .venv；**不要新增 pip 包**（确需新增，先写进本文件并告知 Lead）。

## 1. 目录与文件归属（只改自己名下的文件）

| 目录/文件 | 归属 | 说明 |
| --- | --- | --- |
| app/config.py, db.py, models.py, security.py, deps.py, shield.py, audit.py, main.py | Lead | 已定稿，不要改 |
| app/routers/auth.py, health.py, terms.py, corpus.py, me.py | Lead | 已定稿，不要改 |
| app/services/embedding.py, llm.py, retrieval.py, translate_service.py, rag.py | ai-core | 你要实现 |
| app/routers/translate.py, qa.py | ai-core | 你要实现 |
| app/services/crawler.py；scripts/crawl.py, build_slices.py, embed_chunks.py | data-pipeline | 你要实现 |
| app/routers/news.py, admin.py | data-pipeline | 你要实现 |
| static/*.html, static/css/style.css, static/js/app.js | frontend | 你要实现 |
| scripts/convert_v13.py, seed_public.py, data/*.jsonl | Lead | Lead 负责 |
| tests/*.py | Lead | Lead 负责 |

## 2. 已实现的数据模型（app/models.py，字段名必须对齐）

- User(id,email,username,password_hash,display_name,role,is_active,created_at,last_login_at)
- PublicTerm(id,term_id,zh,en,lang_pair,domain,subdomain,abbreviation,definition_zh,definition_en,source_code,source_file,source_url,audit_status,samples)
- PublicCorpus(id,corpus_id,term_id,zh,en,lang_pair,register,domain,source_code,source_file,source_url,audit_status)
- UserTerm / UserCorpus：用户私有，字段见 models.py；只能通过 /api/me/* 访问
- Chunk(id,doc_id,chunk_no,title,text,source_url,section,page,lang,license,fetched_at,doc_fingerprint,version,embedding)
- NewsItem(id,source,url,title_en,title_zh,summary_en,summary_zh,published_at,fetched_at,license,status)
- AuditLog / RevokedToken

## 3. 已实现的公共接口（不要改）

- POST /api/auth/register {email,username,password,display_name} → 201
- POST /api/auth/login {account,password} → set-cookie session(HttpOnly)+csrf_token，返回 {user,csrf_token}
- POST /api/auth/logout；GET /api/auth/me
- GET /api/terms?q=&lang=&domain=&status=&page=&page_size= → {total,page,page_size,items[]}
- GET /api/terms/meta；GET /api/terms/{pk}
- GET /api/corpus?q=&field=all|zh|en&lang=&term_id=&page= → {total,page,page_size,items[]}
- GET /api/corpus/meta；GET /api/corpus/{pk}
- 私有库：GET/POST /api/me/terms，PUT/DELETE /api/me/terms/{id}，POST /api/me/terms/import/{public_id}，GET /api/me/terms/export.csv；corpus 同上；GET /api/me/overview、/api/me/audit
- 全局中间件已做：安全响应头、CSRF 双提交（非 GET 的 /api/* 需带 X-CSRF-Token，登录/注册/登出除外）、请求 ID

## 4. 你要实现的接口契约

### 4.1 ai-core

**services/embedding.py**
- `embed_texts(texts: list[str]) -> list[list[float]]`：返回 1024 维、已 L2 归一化；provider=local 时用确定性哈希（字符 2–3 gram + 英文词，md5 分桶到 1024，TF 加权后归一化），provider=bigmodel 时 POST {base}/embeddings（model=embedding-3，input=texts，Authorization: Bearer key），超时 20s，失败重试 1 次后抛 EmbeddingUnavailable；**禁止打印 Key**。
- `embedding_dim() -> int`；`cosine(a,b) -> float`

**services/llm.py**
- `chat(messages: list[dict], temperature=0.2, max_tokens=800) -> str`
- provider=mock：返回 "（当前未配置生成模型，仅提供检索结果）"；deepseek：POST {base}/chat/completions；generic：OpenAI 兼容 base（需在 config 加 generic_base/generic_api_key/generic_model，可加字段但不要改已有字段名）
- 超时 25s；失败抛 LLMUnavailable

**services/retrieval.py**
- `search_chunks(query: str, top_k=5, threshold=0.0) -> list[dict]`：返回 [{chunk_id, score, text, title, source_url, section, page, license}]，按 score 降序；SQLite 用 numpy 余弦（从 chunks.embedding JSON 读），Postgres 用 pgvector SQL（`embedding <=> :q`）；查询词先 embed_texts。
- `search_terms(query, limit=10) -> list[PublicTerm]`；`search_corpus(query, lang_pair, limit=3) -> list[PublicCorpus]`（用 LIKE + 简单打分即可）

**services/translate_service.py**
- `translate(text, src, tgt) -> dict{translation, provider, degraded, locked_terms[], context_pairs[], notes[]}`
- 流程：① 术语锁定：search_terms(text) 命中中文/英文做最长匹配，得到 must_use；② 语料上下文：search_corpus(text, tgt) top3；③ MT：mock=把 must_use 与非术语片段拼成译文（并标 degraded=false, provider=mock）；deepseek=prompt 里给 must_use 与 3 条参考句对，temperature 0.2；generic=调用 config.generic_mt_url（模板替换 {text}/{src}/{tgt}，按 generic_mt_result_path 取值）；④ 译后校验：must_use 译法未出现则替换并 notes 记 "term_fixed:{zh}->{en}"；⑤ 结果长度截断 4000 字。
- 语种：zh/en/vi/th/id/ms（5 语 + 中文），不支持的方向抛 400。

**services/rag.py**
- `answer(question) -> dict{answer, citations[], refused, reason, elapsed_ms}`
- 检索 top_k=5；最高分 < config.refuse_threshold 或为空 → refused=true, reason="no_relevant_chunk"；否则 LLM 生成，要求"只依据给定片段，句末标 [n]"；引用校验：答案中 [n] 必须在 1..len(citations)；不通过→重试 1 次→仍失败则 answer=片段摘录拼接（最多 3 片），citations 保留；LLM 不可用→摘录模式，answer 前缀"（未配置生成模型）"。
- citations 元素：{index, chunk_id, title, section, page, source_url, score, snippet(≤120 字)}

**routers/translate.py**
- POST /api/translate（require_user）：body {text(1..2000), src, tgt}；返回 translate() 结果 + request_id；对同一用户简单限流（内存字典，10 次/分钟，超出 429）。
- GET /api/translate/languages → {languages:[{code,name}...], providers:{mt,embedding,llm}}

**routers/qa.py**
- POST /api/qa（require_user）：body {question(1..500)}；返回 answer() + request_id。
- GET /api/qa/examples → 6 条预置问题（其中 2 条是库外问题，用于演示拒答）。

### 4.2 data-pipeline

**services/crawler.py + scripts/crawl.py**
- 3 源：UN News RSS（https://news.un.org/en/rss）、ReliefWeb API（https://api.reliefweb.int/v1/reports?appname=ait-course&limit=20）、USGS GeoJSON（https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson）
- 每源抓 ≤20 条，字段映射到 NewsItem；url 去重；超时 15s、UA=“AIT-CourseBot/1.0 (+教学演示)”；失败跳过并打印计数（不要抛栈）
- 有 LLM 时调用 services.llm.chat 中文化 title/summary（≤500 字，prompt 要求"只翻译事实，不加评论"）；无 LLM 则 title_zh=""，status="pending"
- scripts/crawl.py 支持 --source all|un|reliefweb|usgs、--limit、--translate（默认无 Key 自动跳过翻译）；打印写入/跳过条数

**scripts/build_slices.py**
- 生成 data/chunks.jsonl，≥120 条，每条：{doc_id, chunk_no, title, text(300–500 字), source_url, section, page, lang, license, fetched_at, doc_fingerprint}
- 来源优先级：① data/real_corpus.jsonl（160 条，有 URL）按 4 条一组切成 40 片，section=类别，page=""；② 若 data/docs/*.md 存在则按标题分节 + 段落累积 300–500 字切分；③ 其余用 data/public_terms.jsonl 的"术语 + 释义 + 例句"组片（80 片），source_url 可空、section=领域、license 写"来源见 source_code"
- 同 doc 内 chunk_no 从 0 递增；doc_fingerprint=sha256(text)[:16]；禁止切片跨文档
- 运行：`./.venv/Scripts/python.exe scripts/build_slices.py --out data/chunks.jsonl`

**scripts/embed_chunks.py**
- 读 data/chunks.jsonl（或 --from-db），写入/更新 chunks 表：按 doc_id+chunk_no 去重；调用 embed_texts 批量 32；embedding 存 JSON 字符串；支持 --limit 120 --force；打印成功/失败数；失败条目 embedding 留空并计数

**routers/news.py**
- GET /api/news?source=&page=&page_size= → {total,items[{id,source,title_zh,title_en,url,published_at,status}]}
- GET /api/news/{id} → 详情含 summary_zh/en

**routers/admin.py**（admin 才能访问）
- GET /api/admin/stats → 用户数、私有条目数、切片数、已向量化数、资讯数、近 7 天登录数
- GET /api/admin/users?page= → 用户列表（不含密码）
- PATCH /api/admin/users/{id} {role?:user|admin, is_active?:bool}（admin）
- GET /api/admin/audit?limit=100

### 4.3 frontend（static/）

页面（全部中文、移动端可用、同一套 CSS）：
- index.html：首屏"一句话定位 + 三个入口（翻译/术语/问答）+ 数据条（术语/语料/切片/资讯计数，来自 /api/health）+ 最近资讯 3 条"；底部声明"教学演示数据，非真实病例/灾情"
- login.html / register.html：表单 + 错误提示；登录成功后写 localStorage 的 csrf_token 并跳 account（或回跳 ?next=）
- account.html：个人中心 —— 私有术语库、私有语料库两个标签页；表格（增删改、搜索、分页）；"从公共库复制"入口（在 terms/corpus 页面点"加入我的库"）；导出 CSV 按钮；显示"仅本人可见"标识
- translate.html：源/目标语言下拉（zh,en,vi,th,id,ms）、输入框（≤2000 字计数）、翻译按钮、结果区（术语高亮 <mark>）、锁定术语列表、参考语料折叠、复制/清空按钮、降级提示条
- terms.html：搜索框 + 语种/领域/状态筛选 + 列表（术语/译法/语种/来源/审核状态）+ 详情抽屉（释义、例句、来源可点）+ "加入我的库"按钮
- corpus.html：原文/译文分开搜索 + 列表（原文/译文/语种对/来源/审核状态）+ 详情 + "加入我的库"
- qa.html：提问框 + 预置问题 + 答案区（引用 [n] 可点开浮层显示来源）+ 拒答提示 + 反馈按钮（POST /api/feedback 可选，若无接口则仅前端提示）
- news.html：资讯列表（来源徽标/时间/中文标题）+ 详情展开 + 原文链接 + 访问日期
- 需要登录的页面：未登录访问 account 时跳 login.html?next=account.html

全局（static/js/app.js）：
- fetch 封装：自动带 credentials:"same-origin"，非 GET 自动加 X-CSRF-Token（从 localStorage 或 cookie 读），401 统一跳登录，403 提示"无权访问"，429 提示"操作过快"
- 顶部导航（首页/翻译/术语/语料/问答/资讯/我的），登录态显示用户名与退出
- 统一 toast、加载骨架、空态文案
- 颜色：#0E6E6E 主色、#B45309 强调、#FAF8F4 底色、#111827 文字；字体：系统中文 + Inter；间距 8 的倍数；移动端 <768 单列 + 底部导航

## 5. 验收（Lead 会跑）

- 启动无报错；GET /api/health 返回 counts；注册→登录→访问 account→增删改私有术语/语料→导出 CSV；用户 A 不能读写用户 B 的条目（404）；未带 CSRF 的写请求返回 403；翻译返回术语锁定；问答库外问题 refused=true；管理接口 user 角色 403。
- 所有页面在 375px 宽度无横向滚动。

## 6. 纪律

- 只改自己名下的文件；需要改别人的接口先发消息给 Lead。
- 不要打印或硬编码 API Key；不得把 Key 写进前端。
- 代码注释用中文；函数写类型标注；不要用 print 输出用户内容（用 logging）。
- 完成后在任务卡 complete，并给 Lead 回：文件清单、跑通的命令、遗留问题、需要 Lead 决策的点。
