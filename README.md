# 涉外急诊语言服务台（课程实训作业站）

面向涉外急诊场景的**术语 · 语料 · 翻译 · 可溯源问答**站点。前后端同仓、无构建步骤；本地 SQLite 开箱即跑，生产切 PostgreSQL + pgvector。

## 1. 五项核心功能与评分点

| 评分点 | 站内实现 | 入口 |
| --- | --- | --- |
| 外语信息聚合 | 4 源爬虫（UN News / ReliefWeb / USGS / 联合国新闻中文版）→ 中文化 → 资讯列表；当前 62 条、全部中文 | `/news.html`、`/api/news` |
| 多语种翻译 | 中/英/越/泰/印尼/马来 6 语种 10 方向；术语锁定 + 语料向量上下文 + 译后校验 + 降级链 | `/translate.html`、`POST /api/translate` |
| 术语管理 | 公共 4,154 条（来源 100%、审核状态 100%、按语种/领域/状态筛选）；**个人私有术语库可增删改查** | `/terms.html`、`/account.html` |
| 平行语料 | 公共 8,308 句对；句级向量化 8,308 条；**个人私有语料库可编辑** | `/corpus.html`、`/account.html` |
| 可追溯问答 | 124 个知识切片 → hybrid 重排 → 强证据门槛 → 库外 / 证据不足**明确拒答**；库内回答带 `[n]` 引用，且每条引用可点开查看切片全文、章节、页码、来源编号与许可 | 全站右下角悬浮球、`POST /api/qa`、`GET /api/qa/source/{chunk_id}` |
| 东盟本地语 | 1,040 条对照（越/泰/印尼/马来），罗马化、发音提示、语用提示、待母语审校标注 | `/quality.html?tab=local` |
| 跨文化表达（语言质量子功能） | 738 条文化负载词/礼仪称谓/宗教禁忌，按国家与禁忌级别（红/橙/黄/无）检索，含直译风险与语用提示；已并入紫色「语言质量」成为第 4 个子功能 Tab | `/quality.html?tab=culture`、`GET /api/culture*` |
| 英语变体改写（语言质量子功能） | 150 条东盟英语变体整句（Singlish/Manglish 等），原句 → 标准英语 + 医疗场景改写 | `/quality.html?tab=culture` 第二页签、`GET /api/variants*` |
| 患者情况告知单（与翻译平级的一级功能） | 面向病患、注册登录后可用：圈选/输入不适部位、不适症状、症状细节（乏力、疼痛、慢性疼痛、剧痛等）与患者原话，覆盖「问诊沟通 / 病例录入」两场景；把患者自述按临床交接习惯**结构化整理后转达给医生**，输出主诉、编号分项与可复制/可编辑的交接单全文。**不翻译、不诊断、不评估表达质量、不澄清文化或信息问题**，与翻译、语言质量检查都是独立流程 | `/check.html`、`POST /api/patient-check` |
| 用户系统 | 注册/登录/登出、JWT HttpOnly Cookie、CSRF、登录限流、管理员后台 | `/login.html`、`/api/admin/*` |

> **私有库设计**：公共库（public_terms / public_corpus）所有人只读；用户在“我的库”里新建或从公共库复制的条目（user_terms / user_corpus）**只在该账户内可见、可编辑、可导出 CSV**，别人访问一律 404。

逐项验收自查见 [docs/RUBRIC_AUDIT.md](docs/RUBRIC_AUDIT.md)，交付快照见 [docs/SITE_STATUS.md](docs/SITE_STATUS.md)。

## 2. 目录结构

```
work/site/
├── app/
│   ├── main.py / config.py / db.py / models.py
│   ├── security.py / shield.py / deps.py / audit.py
│   ├── routers/    auth health terms corpus culture me translate qa news admin refs patient_check
│   └── services/   embedding llm retrieval translate_service rag crawler
├── static/         10 个页面 + css/style.css + js/app.js（原生，无构建）
├── scripts/        convert_v13 convert_culture seed_public build_slices embed_chunks embed_corpus
│                   update_slices crawl translate_news create_admin
├── data/           JSONL 数据 + SQLite（db 已 git 忽略）
├── deploy/         nginx.conf（TLS/安全头/限流/管理白名单）
├── docs/           ARCHITECTURE / SITE_STATUS / RUBRIC_AUDIT / SELFTEST_*
├── tests/          8 项接口测试
├── Dockerfile / docker-compose.yml / requirements.txt
└── start.ps1 / start.sh
```

## 3. 本地运行

```bash
cd work/site
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
cp .env.example .env                                            # 至少改 SECRET_KEY

./.venv/Scripts/python.exe scripts/seed_public.py        # 术语/语料/来源/本地语/文化表达/英语变体
./.venv/Scripts/python.exe scripts/build_slices.py       # 124 片
./.venv/Scripts/python.exe scripts/embed_chunks.py --force
./.venv/Scripts/python.exe scripts/embed_corpus.py       # 8,308 句向量
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

建管理员：

```bash
./.venv/Scripts/python.exe scripts/create_admin.py --username admin --email admin@example.com --password 'StrongPass!23'
```

## 4. 环境变量（.env）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| SECRET_KEY | JWT 签名密钥，生产必须 ≥32 字节随机 | dev-only-change-me |
| DATABASE_URL | SQLite 或 PostgreSQL+pgvector | sqlite:///./data/app.db |
| EMBEDDING_PROVIDER | local（离线哈希）/ bigmodel（智谱 embedding-3） | local |
| BIGMODEL_API_KEY | 智谱 Key（只在服务端） | 空 |
| LLM_PROVIDER | mock / deepseek / generic | mock |
| DEEPSEEK_API_KEY | DeepSeek Key | 空 |
| MT_PROVIDER | mymemory（免费端口）/ deepseek / generic（百度、腾讯、DeepL 等任意 MT 端口）/ mock | mymemory |
| GENERIC_MT_URL / KEY / METHOD / PAYLOAD_TPL / RESULT_PATH | 通用 MT 端口配置（见下） | 空 |
| MYMEMORY_EMAIL | 可选，MyMemory 官方 de= 参数，提高免费额度 | 空 |
| REFUSE_THRESHOLD | 问答拒答阈值（语义向量）；local 另有 `refuse_threshold_local=0.15` | 0.35 |

### 接驳一个现成翻译端口（示例：百度翻译）

```env
MT_PROVIDER=generic
GENERIC_MT_URL=https://fanyi-api.baidu.com/api/trans/vip/translate
GENERIC_MT_METHOD=POST
GENERIC_MT_KEY=你的appid:密钥
GENERIC_MT_PAYLOAD_TPL={"q":"{text}","from":"{src}","to":"{tgt}","appid":"{appid}","salt":"{salt}","sign":"{sign}"}
GENERIC_MT_RESULT_PATH=trans_result.0.dst
```

（百度/腾讯需要签名参数的，可在 `app/services/translate_service.py` 的 generic 分支按自家文档拼 sign；DeepL/自建 LibreTranslate 直接改 URL 与 payload 即可。）

> 没有 Key 也能跑：embedding 走本地 1024 维哈希、翻译走 MyMemory 免费端口（额度用尽时自动降级 mock 并在页面标注）、问答走检索摘录模式。

## 5. 数据管线

```bash
# 1) 从 V1.3 总库转换（需要 openpyxl，用系统 Python 跑一次）
python scripts/convert_v13.py --xlsx "../merge/涉外急诊与东盟文化_中英术语语料总库_V1.3.xlsx" --out data
python scripts/convert_culture.py --xlsx "../merge/涉外急诊与东盟文化_中英术语语料总库_V1.3.xlsx" --out data   # 文化表达 738 + 英语变体 150

# 2) 入库（幂等：术语 4,154 / 语料 8,308 / 来源 69 / 本地语 1,040 / 文化表达 738 / 英语变体 150）
./.venv/Scripts/python.exe scripts/seed_public.py

# 3) 知识库切片 + 向量
./.venv/Scripts/python.exe scripts/build_slices.py          # 124 片
./.venv/Scripts/python.exe scripts/embed_chunks.py --force  # 切片向量
./.venv/Scripts/python.exe scripts/embed_corpus.py          # 语料句级向量

# 4) 切片增量更新（新增/变更 version+1/删除）
./.venv/Scripts/python.exe scripts/update_slices.py --dry-run

# 5) 爬虫：四源，有 LLM 用 LLM，无 LLM 用 MyMemory 免费端口
./.venv/Scripts/python.exe scripts/crawl.py --source all --limit 30 --translate
./.venv/Scripts/python.exe scripts/translate_news.py --limit 20   # 补译 pending
```

## 6. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/health | 数据量、向量化数量、模型供应商 |
| POST | /api/auth/register /login /logout；GET /api/auth/me | 用户系统（HttpOnly Cookie + CSRF） |
| GET | /api/terms、/meta、/{id} | 公共术语（详情含 `sources[]` 与可核查 URL） |
| GET | /api/corpus、/meta、/{id} | 公共语料（同上） |
| GET | /api/local-terms、/meta | 东盟本地语对照（1,040 条） |
| GET | /api/sources、/api/sources/{code} | 来源清单（69 个编号） |
| GET | /api/kb/stats | 知识库统计（docs/chunks/embedded/news_zh/local_terms） |
| GET/POST/PUT/DELETE | /api/me/terms、/api/me/corpus | **私有库 CRUD（仅本人）** |
| POST | /api/me/terms/import/{public_id} | 从公共库复制到我的库 |
| GET | /api/me/terms/export.csv 等 | 导出 CSV |
| POST | /api/translate | 术语约束翻译（6 语种，含降级链） |
| POST | /api/patient-check | 患者情况告知单：返回 `chief_complaint`、`sections`、`handoff_text`、`submitted`、`disclaimer`，并显式回传 `no_translation: true` / `no_quality_judgement: true`；**不产出译文、不做任何质量评估** |
| POST | /api/qa | 可溯源问答；库外 / 证据不足返回 `refused: true` 与 `reason`，库内回答返回带 `chunk_id` 的 `citations` |
| GET | /api/qa/source/{chunk_id} | 点开 `[n]` 引用：返回该切片全文与 `title` / `section` / `page` / `doc_id` / `source_url` / `license` |
| GET | /api/news、/api/news/{id} | 资讯（默认只返回已中文化） |
| GET/PATCH | /api/admin/stats、users、audit | 管理员 |

非 GET 的 `/api/*` 需要请求头 `X-CSRF-Token`；首次访问（含注册页）由 `SecurityMiddleware.ensure_anon_csrf()` 下发非 HttpOnly 的 `csrf_token` Cookie，使注册表单也能通过双提交校验。仅登录 / 注册 / 登出三个 auth 端点在 `CSRF_EXEMPT` 中；`/api/patient-check` 与其余所有功能接口均需注册登录后携带有效 CSRF Token 调用。

## 7. 安全设计

- 密码 bcrypt cost 12；JWT HttpOnly + SameSite；登出撤销 jti；
- CSRF 双提交（中间件全局校验）；登录失败 5 次/5 分钟锁定；
- 全局安全响应头（CSP、X-Frame-Options、nosniff、Referrer-Policy、Permissions-Policy）；
- 私有数据按 `user_id` 过滤，越权返回 404；管理接口 `require_admin`；
- 所有写操作写审计日志；Key 只在服务端 `.env`，不写日志；
- 生产 Nginx：TLS/HSTS/限流/管理后台 IP 白名单，见 `deploy/nginx.conf`。

## 8. 测试

```bash
./.venv/Scripts/python.exe -m pytest tests -q     # 8 passed
```

覆盖：健康检查、注册登录、错误密码、CSRF 拦截、私有库跨用户隔离、公共库只读、来源/本地语接口、术语详情来源包。

## 9. 生产部署（Docker Compose + pgvector）

```bash
cp .env.example .env      # 填 Key 与 SECRET_KEY
docker compose up -d --build
# 首次启动：进入 app 容器执行 seed/build_slices/embed 脚本
```

- `db` 用 `pgvector/pgvector:pg16`，启动时自动 `CREATE EXTENSION vector` 并建 `chunk_vectors`（HNSW）；
- `app` 只监听 127.0.0.1:8000，由 Nginx 反代；
- 生产必须 `COOKIE_SECURE=true`。

## 10. 已知限制

- MyMemory 免费端口有每日额度，用尽后翻译自动降级（页面标 degraded）；正式演示请配 DeepSeek 或自有 MT 端口；
- 本地哈希向量只做词面相近；配 BigModel embedding-3 后显著改善；
- 本地语 1,040 条为“待母语审校”，页面如实标注；
- PostgreSQL/pgvector 分支未在本机实跑（无 PG 环境）。

## 11. V2 界面与交互（颜色即功能）

| 板块 | 页面 | 主色 | 一眼识别 |
| --- | --- | --- | --- |
| 首页 | /index.html | 青 #0E7490（深色 Hero） | 深色科技首页 + 知识库流动图 |
| 翻译 | /translate.html | 蓝 #2563EB | 蓝色顶部条与按钮，DeepL 式左右对照 |
| 语言质量维护 | /quality.html | 紫 #7C3AED | 术语 / 平行语料 / 东盟本地语 / **跨文化表达**四 Tab |
| 跨文化表达（子功能） | /quality.html?tab=culture | 紫 #7C3AED | 随语言质量同色；首页另有紫色 `.cx-subentry` 子功能直达条 |
| 患者情况告知单 | /check.html | 玫红 #BE123C | 与「翻译」平级的一级功能；玫红单栏「采集表 → 交接单」，不出现译文栏、不出现检查结论 |
| 资讯 | /news.html | 橙 #EA580C | 橙色来源徽标与时间 |
| 问答 | 全站右下角悬浮球 | 绿 #059669 | 绿色悬浮球，任何页面可开，注册登录后可用 |
| 我的 | /account.html | 灰 #475569 | 私有术语/语料库（仍需登录） |

**登录策略（注册前置全站门禁）**：未注册 / 未登录访客仅可访问 `register.html`（注册入口）与 `login.html`（登录入口），以及静态资源、健康检查与 auth 三件套；其余 HTML 页面由 `app/shield.py` 一律 302 回 `register.html`，其余 `/api/*` 一律 401（响应体带 `need_register: true`）。注册并登录后开放翻译、语言质量、患者情况告知单、资讯、可溯源问答、云端资产、我的资产等全站功能；服务端门禁是硬约束，前端 `app.js` 的 `GUEST_PAGES` 守卫只做平滑跳转。`/api/auth/me` 作为白名单探测端点匿名返回 `user: null`；匿名 CSRF Cookie 仍保留，保证注册表单可通过双提交校验。详见第 16 节。

**首页**：深色 Hero + Canvas 轻 3D 知识库流动图（6 类节点、粒子连线、悬停显示数量、点击跳板块，移动端降级静态环形图）+ 板块入口卡片 + 最新资讯 teaser；已按需求删除“关于本站/教学演示”说明文字。

**翻译页（DeepL 风格）**：左右两栏、6 语种、5000 字硬上限（前后端同时校验，超额 422/前端拦截）；历史侧栏（可载入、可删除，当前草稿存 localStorage 不会被顶掉）；鼠标悬停译文句高亮对应原文句、反之亦然，点击句段弹窗显示该句命中的术语与参考语料；provider 徽标与降级提示。

**语言质量维护**：术语 / 平行语料 / 东盟本地语 / **跨文化表达**四 Tab；前三 Tab 为左侧检索筛选列表、右侧详情；术语详情自动带出该术语的关联语料（`/api/terms/{id}/corpus`），语料详情带关联术语；登录用户可增删改“我的条目”，支持 **Excel/JSON 导入导出**（`/api/me/terms|corpus/export.xlsx?format=xlsx|json`、`POST /api/me/terms|corpus/import`，≤5MB/2000 行，重复行计 skipped）。第 4 Tab「跨文化表达」由原独立 `culture.html` 整块嵌入，主色随语言质量改为紫色 `#7C3AED`（`culture.css` 局部作用域 `.cx-page`），`culture.js` 改为 `window.CulturePage = { mount, unmount }` 由 `quality.js` 调度；旧 `culture.html` 保留为重定向桩。

**患者情况告知单（一级功能页 `check.html`）**：与翻译页「原文 → 译文」左右双栏、语言质量「检查结论」都完全不同，是玫红单栏「表单采集 → 交接单」。患者可圈选或输入不适部位、不适症状、症状细节（时间进程 / 程度 / 性质 / 诱因缓解 / 伴随症状，含 `乏力`、`疼痛`、`慢性疼痛`、`剧痛`、`钝痛` 等），并填患者原话与沟通对象国家；场景切换「问诊沟通 / 病例录入」。提交后输出主诉、编号分项（01 不适部位 / 02 不适症状 / 03 症状细节 / 04 患者原话 / 05 沟通对象）、可复制且可编辑的交接单全文、采集内容回显、免责声明与云端留档入口。**不调用 `/api/translate`，不做准确性 / 清晰度 / 跨文化适配性评估，不给「建议补充 / 待澄清」，不做文化风险澄清**；响应体显式带 `no_translation: true` 与 `no_quality_judgement: true`，前端还加了一道双保险：若接口意外回传译文或质量评估字段则拒绝渲染。患者原话照录不改写，本单只用于把患者自述转达给医生，不替代医护问诊、病史核实与专业判断。详见第 15 节。

**可溯源问答**：`app/services/rag.py` 在 hybrid 排序之外新增 `content_overlap()` / `keyword_evidence()` 与通用词 bigram 集合 `GENERIC_GRAMS`，只有命中「强证据」（词面重合 ≥0.28 或实词重合 ≥0.25）才放行；库外问题返回 `refused: true` + `reason: out_of_knowledge_base`，证据不足返回 `insufficient_evidence`。库内回答的每条 `[n]` 引用都渲染为 `<details>`，展开时调用 `GET /api/qa/source/{chunk_id}` 拉取切片全文与出处（标题、章节、页码、来源编号、许可、外链）；`retrieval.py` 的 `_row_brief()` 与 PG/SQLite 查询已补 `doc_id`。问答悬浮球仅对注册登录用户注入与开放（此前会误跳登录页，现已按注册门禁统一收口）。

**问答安全**：`app/services/safety.py` 对武器/自伤/暴力/毒品/黑客/仇恨/未成年人性内容/提示注入做拦截；自伤类问题返回危机干预提示（心理援助热线 12356、急救 120），不返回任何危险内容；正常医疗问题不受影响。

**本轮新增接口**：`GET /api/public/overview`、`POST /api/translate`（新增 `segments` 与 `history_id`）、`GET|DELETE /api/me/translations`、`GET /api/me/{terms,corpus}/export.xlsx`、`POST /api/me/{terms,corpus}/import`、`GET /api/terms/{id}/corpus`、`GET /api/culture*`、`GET /api/variants*`、`POST /api/patient-check`、`GET /api/qa/source/{chunk_id}`。

**验收快照（本轮）**：`python -m compileall` 与 `node --check` 全绿；本地 8100 Python 冒烟 30+ 项全通过（health、匿名 CSRF Cookie、公共页 200、`/api/patient-check` 新告知单结构且无译文/质量字段、匿名翻译、库内问答带 chunk_id、3 个库外问题拒答、来源端点、受保护接口 401、公共读接口 200）；Playwright 端到端：首页玫红入口 → `check.html` → 圈选 6 项提交 → 交接单渲染且无译文/检查结论字样、原话照录、sharecode 透传；`quality.html?tab=culture` 紫色子功能 738 条加载；问答库内 5 条引用可点开加载 487 字原文、库外明确拒答且 0 引用；翻译页 Enter 直接出译文、译文可编辑、匿名历史提示；旧链接 `quality.html?tab=patient-check` → `check.html`、`culture.html` → `quality.html?tab=culture`；各公共页 0 errors / 0 warnings。

## 12. 首页视觉 V4（复古气质 + 3D 交互）

- **复古视觉**：米纸底 + 噪点纸纹 + 网点半调；墨黑/铁锈红/芥末黄/橄榄绿配色；衬线大标题（Georgia/宋体）+ 等宽全大写标签；粗边框、硬阴影、印章贴纸、黄色跑马灯。
- **3D 交互**：① 手写线框知识球（Canvas 2D 经纬投影，自转 + 拖拽）；② 6 张能力卡片组成的 3D 圆环（透视 1500px，自动旋转 + 拖拽 + 左右键 + 点击进入）；③ 知识库流动图（椭圆轨道、粒子流动、悬停数量、点击跳转）。
- **降级**：移动端卡片环变单列、球体/知识图只画一帧、跑马灯停止；`prefers-reduced-motion` 全量降级；页面隐藏暂停 rAF。
- 设计说明与可调参数见 [docs/DESIGN_V4.md](docs/DESIGN_V4.md)；截图见 `docs/screenshots/home.png`、`home_mobile.png`、`home_capabilities.png`、`home_knowledge.png`。

## 13. 云服务接入（WorkBuddy Cloud Service）

应用 `wbapp_xp3kbiaDkp2BQ4HnqFvZbl` 已激活云服务（`billingStatus=normal`、`provisionStatus=assigned`），四个模块共用一个环境，数据与其它应用完全隔离。公开配置集中在 `static/js/cloud-config.js`（`endpoint` / `oauthRelayBaseUrl` / `publishableKey` / `resourceId`，均来自激活返回的 `publicConfig`）；全站只在 `static/js/cloud-client.js` 里初始化**一个** `createWorkBuddyCloud` 实例，Auth / Database / Storage / LLM 共用它。

| 模块 | 站内入口 | 云端资源 | 对应现有功能 |
| --- | --- | --- | --- |
| Auth | `/cloud.html` 01 云端身份 | 邮箱验证码注册/登录、会话、登出 | 云端数据归属；与站内 JWT 账号相互独立 |
| Database | `/cloud.html` 02 交接单记录 | 表 `patient_check_records`（RLS，owner 隔离） | 「患者情况告知单」主诉与全文持久化 |
| Storage | `/cloud.html` 03 交接单文件 | `runtime` 私有路径 `users/<uid>/reports/` | 告知单导出 JSON（`patient-handoff-sheet.json`）+ 短时效签名链接 |
| LLM API | `/cloud.html` 04 交接要点整理 | `cloud.llm.models.list()` + 流式 `chat.completions.create()` | 独立可选云端工具：把患者自述整理成便于医生阅读的 3 条交接要点；不评判表达质量、不做文化澄清、不翻译、不诊断 |

**接入点**：`check.html` 生成告知单后，报告底部出现「保存到云端 →」，交接单经 `sessionStorage`（`er_last_check`）带到 `cloud.html`；`account.html` 也提供「云端资产」入口。云端页归入灰色「我的资产」，不新增第 8 种功能色，不破坏颜色-功能唯一映射。云端 02/03/04 的文案与 `cloud.js` 的 `reportObject()` 已随告知单语义改写：只带 `chief_complaint` / `sections` / `handoff_text` / `submitted` / `disclaimer`，不再带 `overall` / `dimensions` / `missing_elements` / `culture_notes`；`overall_level` 列沿用云端表既有列名，只作「交接单 / 手动录入」类型标签，不表示任何评级。

**SDK 形态**：原生静态前端无构建步骤 → CDN `<script>`（`@tencent-ai/workbuddy-cloud-sdk@dev` 的 IIFE 全局 `WorkBuddyCloud`）；`static/vendor/workbuddy-cloud-sdk.global.js` 是同一份 `@dev` 构建的同源副本，CDN 不可达时由 `cloud-client.js` 自动回退，避免整站云功能失效。`app/shield.py` 的 CSP 已相应放行 `script-src https://cdn.jsdelivr.net` 与 `connect-src https://*.workbuddy.cn https://*.workbuddy.host`。

**数据库约定**：`patient_check_records` 含 `id` / `owner_id TEXT DEFAULT auth.uid()` / `owner_name` / `scene` / `overall_level` / `summary` / `missing_elements JSONB` / `payload JSONB` / `created_at`；RLS 开启，SELECT/INSERT/UPDATE/DELETE 四条 owner 策略，UPDATE 同时带 `USING` 与 `WITH CHECK`。应用代码**不传 `owner_id`**，归属由服务端决定；跨账号写入会被 RLS 过滤为空数组，页面明确提示而不当作成功。

**门禁与失败路径**：用户级数据库/存储读写前统一走 `ERCloud.requireSession()`，未登录时 UI 显示门禁提示，不做匿名登录、不伪造本地身份、不静默降级。网络失败、未登录、权限不足、额度不足、模型不可用都有明确文案；签名链接不写入日志；邮箱、用户 ID、令牌、文件路径均不出现在日志与回复中。

**验证结论**：环境激活正常；表与 4 条 RLS 策略经管理面确认；`INSERT ... RETURNING` 与 SDK `select()` 写入读回通过；模型目录返回 33 个可用模型；`auto` 模型流式调用真实返回 479 字（`total_tokens=550`）；未登录数据库写入/读回、存储路径校验与上传拒绝路径均如实呈现。邮箱验证码登录需要终端用户用本人邮箱完成，Agent 无法代收验证码，故这一步留给用户自助验证。

## 14. 患者快速检查表 · 首页直达与免登录（历史记录，已被第 15、16 节取代）

> ⚠️ **本节描述的是上一轮「线上可见性修复」的历史状态**：当时患者快速检查表还是语言质量第 4 Tab、输出三维检查结论、入口为 `quality.html?tab=patient-check`。**当前架构以第 15 节为准**：患者快速检查表已升级为与翻译平级的「患者情况告知单」一级功能页 `check.html`，跨文化表达已并入语言质量成为紫色子功能，旧链接只做平滑重定向。保留本节仅为追溯修复过程。

**问题**：功能代码早已在站内，但线上版本看不到——首页第 3 张「跨文化表达」能力卡指向 `culture.html`（738 条文化词条 + 150 条英语变体），不是患者快速检查表；唯一的检查表入口藏在语言质量第 4 Tab，且被站内登录守卫挡住，匿名病患无法进入。

**修复后的完整链路**：首页 7 张能力卡下方新增玫红 `.pc-entry` 直达入口「跨文化表达 · 患者快速检查表」→ `quality.html?tab=patient-check` → 玫红单栏采集表 → `POST /api/patient-check` → 三维检查结论报告。入口仍用玫红 `#BE123C`（= 跨文化），不新增第 8 种功能色，不破坏「颜色即功能」唯一映射。

| 层 | 改动 | 文件 |
| --- | --- | --- |
| 后端放行 | `/api/patient-check` 加入 `PUBLIC_PATHS` 与 `CSRF_EXEMPT`（该接口只读 `culture_exprs`、不写库、不依赖会话） | `app/shield.py` |
| 全局前端守卫 | `boot()` 对 `state.page === "quality" && tab === "patient-check"` 设 `needsAuth = false`；新增 `propagateSharecode()` 把线上分享链接的 `sharecode` 透传到站内 `.html` 链接 | `static/js/app.js?v=15` |
| 质量页调度 | `boot()` 在 `state.tab === "patient-check"` 时跳过 `requireAuth()` / `loadMyCounts()`；`updateUrl()` 改为只覆盖 `tab`、保留 `sharecode` 等原有参数 | `static/js/quality.js?v=13` |
| 报告内云端入口 | 「保存到云端」链接透传 `sharecode` | `static/js/patient-check.js?v=14` |
| 首页入口 | 新增 `.pc-entry` 结构与样式（`.pc-entry` / `__stamp` / `__body` / `__go`，玫红硬阴影） | `static/index.html`、`static/css/home-v4.css?v=11` |

**验证**：匿名 `POST /api/patient-check` 返回 200（不再是 401/403），`overall` + 准确性/清晰度/跨文化适配性三维结论、`missing_elements`、8 条可溯源文化提示、免责声明齐全，forbidden 译文字段为空；空采集返回 `empty: true`；`consultation` 与 `record` 场景结论不同；`/api/terms`、`/api/culture/meta`、`/api/me/overview` 等受保护接口匿名仍 401。浏览器端到端：首页入口可见（`display:flex`、3px 墨框、玫红硬阴影、7 张能力卡不变）→ 点击后 URL 带 `sharecode` 且**未跳登录** → 面板可见、`ql-body`/工具条隐藏、16 个症状 chip 就位 → 圈选 6 项 + 患者原话 + 国家后提交 → 报告渲染三维结论、建议补充、可溯源提示、采集回显、免责声明、云端留档入口；清空 Cookie 后全新访客 0 errors / 0 warnings；点击「术语」Tab 仍跳 `login.html`，受保护资产不外泄。

> 云服务的 `endpoint` 绑定应用发布域名，浏览器端完整体验请在发布域名打开；本地 `127.0.0.1` 预览时数据面可能给出连接提示，页面会如实展示而非假装成功。

## 15. 信息架构重构 · 告知单一级化 / 跨文化子功能化 / 公共功能免登录 / 问答强拒答（历史；免登录部分已被第 16 节取代）

### 15.1 需求与定位纠正

用户明确要求三条结构性调整：

1. **「把跨文化表达的整个板块塞进去语言质量里面，做成子功能」**——原独立 `culture.html` 不再是玫红一级页，整块嵌入 `quality.html` 第 4 Tab，主色随语言质量改为紫色。
2. **「把患者快速检查表拎出来与翻译平级」**——新建 `check.html`，与 `translate.html` 同为一级功能，导航中占玫红一席。
3. **「快速检查表是要把患者的内容告知医生，不是要澄清文化或者信息问题」**——这是关键的语义纠正：旧版输出「准确性 / 清晰度 / 跨文化适配性」三维检查结论、`missing_elements` 待补充、`culture_notes` 文化风险提示；新版改为**患者内容 → 医生的结构化交接告知单**，不评估、不澄清、不翻译。

### 15.2 当前信息架构与颜色映射

| 层级 | 功能 | 页面 | 功能色 | 说明 |
| --- | --- | --- | --- | --- |
| 一级 | 首页总览 | `index.html` | 青 #0E7490 | 7 张能力卡 + 知识球 / 流动图 |
| 一级 | 多语翻译 | `translate.html` | 蓝 #2563EB | Enter 直出译文、译文可随时编辑 |
| 一级 | **患者情况告知单** | `check.html` | 玫红 #BE123C | 面向病患、注册登录后可用、单栏采集 → 交接单 |
| 一级 | 语言质量维护 | `quality.html` | 紫 #7C3AED | 4 Tab：术语 / 平行语料 / 东盟本地语 / **跨文化表达** |
| ├ 子功能 | 跨文化表达 + 英语变体 | `quality.html?tab=culture` | 紫 #7C3AED | 738 条文化表达 + 150 条英语变体，同色不串玫红 |
| 一级 | 国际资讯 | `news.html` | 橙 #EA580C | 四源公开资讯 |
| 一级 | 可溯源问答 | 全站悬浮球 | 绿 #059669 | 库外拒答、`[n]` 可点开原文 |
| 一级 | 我的资产 | `account.html` | 灰 #475569 | 私有术语/语料（唯一仍需登录的页面） |

首页同步调整：第 3 张能力卡由「跨文化表达」改为「患者情况告知单」并指向 `check.html`；能力区新增紫色 `.cx-subentry` 子功能直达条「语言质量 · 子功能：跨文化表达」→ `quality.html?tab=culture`；玫红 `.pc-entry` 改为「患者情况告知单」→ `check.html`。`app.js` 的 `SECTIONS.culture` 标签改为「患者检查表」、`href` 改为 `check.html`，`FUNC_LEGEND` 玫红改「患者检查表」、紫色改「语言质量（含跨文化表达）」；`PAGE_SECTION.check = "culture"`（玫红）、`PAGE_SECTION.culture = "quality"`（紫色）。**7 种功能色不增不减，颜色与功能一一对应**。

### 15.3 告知单前后端

`app/routers/patient_check.py` 整体重写（保留 `POST /api/patient-check` 路径以兼容已发布链接）：

- 输入 `HandoffIn`：`scene` / `parts` / `part_other` / `symptoms` / `symptom_other` / `details` / `detail_other` / `free_text` / `country`；
- `DETAIL_GROUP` 把症状细节按「时间进程 / 程度 / 性质 / 诱因缓解 / 伴随症状」分组，与前端圈选项逐字一致；`PART_NORM` 只做同语言书写规范化（如「胸」→「胸部」），**不是翻译**；
- 输出 `chief_complaint`、`sections`、`handoff_text`、`submitted`、`disclaimer`、`patient_quote`、`country`、`purpose`，以及 `no_translation: true` / `no_quality_judgement: true`；
- 空采集返回 `empty: true` + `message`；患者原话照录，`DISCLAIMER` 明确「不翻译、不诊断、不评估表达质量、不澄清文化或信息问题」。

`static/check.html` + `static/css/patient-check.css` + `static/js/patient-check.js` 重写：玫红单栏 5 组采集（部位 / 症状 / 细节 / 原话 / 沟通对象）、场景切换、生成按钮、可编辑交接单全文 `<textarea>` + 一键复制、折叠的采集回显、边界标签（不翻译 / 不诊断 / 不评估表达质量 / 不澄清文化或信息问题）、免责声明、云端留档入口（透传 `sharecode`）。前端双保险：若响应意外含 `translation` / `overall` / `dimensions` / `culture_notes` / `missing_elements` 等字段，直接阻止渲染并报错。

### 15.4 兼容与重定向

| 旧入口 | 当前行为 |
| --- | --- |
| `culture.html` | meta refresh + `app.js PAGE_INIT.culture` 双重跳转 → `quality.html?tab=culture`（保留 sharecode） |
| `quality.html?tab=patient-check` | `quality.js boot()` 直接 `location.replace("check.html" + query)`（保留 sharecode） |
| `quality.html?tab=check` | 同上 |
| 首页 `.pc-entry` / 第 3 张能力卡 | 直接 `check.html` |

`quality.js` 的 `TABS` 改为 `["terms", "corpus", "local", "culture"]`；`setTab("culture")` 隐藏 `#ql-body`、显示 `#cx-panel` 并调用 `window.CulturePage.mount()`；`culture.js` 不再自启动、改为幂等 `mount/unmount`。`culture.css` 主色由玫红改紫、移除全局 `html, body` 样式污染，改为 `.cx-page` 局部作用域。

### 15.5 公共功能免登录（历史，已被第 16 节注册前置门禁取代）

> ⚠️ 本节描述的是上一轮状态：**当前以第 16 节为准**。

- `app/shield.py` 反向白名单：仅 `/api/me`、`/api/history`、`/api/transfer`、`/api/admin` 要求登录；`ensure_anon_csrf()` 首次访问下发匿名 `csrf_token` Cookie；保留 CSP、`X-Frame-Options: DENY` 等安全头。
- `app/routers/auth.py` `/me` 匿名返回 `user: null`（不再 401）；`translate.py` / `qa.py` 改用 `get_optional_user`，匿名按 IP 限流、不写个人历史。
- `app.js`：`PRIVATE_PAGES = { account: true }`；`api()` 401 默认不跳登录；`requireLogin()` 只读取登录态；**问答悬浮球与 `openQa()` 移除 `!state.user` 登录拦截**（此前点击悬浮球会误跳登录页，本轮修复）；`submitQa()` 改 `authOptional: true`。
- `translate.js` / `quality.js`：匿名访客**不发起** `/api/me/translations`、`/api/me/overview` 等个人数据请求，直接给出「登录后可在我的资产查看」提示，公共页 0 errors / 0 warnings。

### 15.6 问答机器人：库外拒答 + 参考来源可点开

- `rag.py`：`GENERIC_GRAMS` 过滤「急诊 / 患者 / 今天 / 北京 / 请问」等通用词；新增 `content_overlap()`、`keyword_evidence()`、`LEX_MIN_EVIDENCE`、`CONTENT_HYBRID_BYPASS`；`should_refuse()` 增加库外 / 证据不足闸门；向量证据不足时只允许「强证据」词面命中兜底放行；`_refused()` 按 4 种 reason 返回不同拒答文案。
- `qa.py`：`GET /api/qa/source/{chunk_id}` 返回切片全文与出处；`retrieval.py` 的 `_row_brief()` 与 PG/SQLite 查询补 `doc_id`。
- `app.js`：`qaCitationsHtml()` 渲染 `<details data-chunk-id>`，`bindQaCitationButtons()` 在展开时拉取来源全文并渲染资料 / 章节 / 页码 / 来源编号 / 引用要求 / 外链 / 原文；`base.css` 增加 `.qa-source-full*` 样式。库外问题只显示「暂不回答」+ 原因，**不附带任何引用**。

### 15.7 云端资产语义同步

`cloud.html` / `cloud.js` 的「检查记录 / 报告文件 / 表述建议」改为「交接单记录 / 交接单文件 / 交接要点整理」；`reportObject()` 只带告知单字段；上传文件名改 `patient-handoff-sheet.json`、metadata `purpose: patient-handoff-sheet`；LLM system 提示改为「交接记录助手」，不评判表达是否准确得体、不做文化澄清、不翻译、不诊断。`cloud.html` 脚注接入点由 `quality.html?tab=patient-check` 改为 `check.html`。

### 15.8 静态资源版本

`app.js?v=17`（全站统一）、`base.css?v=12`、`home-v4.css?v=12`、`patient-check.css?v=12` / `patient-check.js?v=17`、`check.html` 新建、`quality.js?v=15`、`translate.js?v=12`、`cloud.js?v=14`、`culture.css|js?v=11`、`home-v4.js?v=11`。

**发布状态**：用户已明确确认「立即发布」，本轮改动已重新部署，`verified=true`、`deployedAs=http-service`，sandboxId 不变 `b97659826c614869b352249be2047ed1`，**链接不变**：`https://er-lang-service-desk.app.workbuddy.host/?sharecode=F3VK3EZYS2`。线上冒烟与 Playwright 端到端均通过：首页玫红入口 → `check.html` → 圈选提交 → 交接单（无译文 / 无检查结论、原话照录、sharecode 透传）；`quality.html?tab=culture` 紫色子功能 738 条；问答库内 5 条引用可点开全文、库外明确拒答；旧 `quality.html?tab=patient-check` 平滑跳 `check.html`；各公共页 0 errors / 0 warnings。

> 发布同意规则仍然有效：仅「继续 / 优化 / 新增功能」不构成自动部署授权，下一次改动后需用户重新明确说「发布 / 上线 / 同步到线上」才会 redeploy。

## 16. 问答故障修复 · 严格库内闸门 · 注册前置门禁 · 全站中英双语（历史；16.4 门禁语义与 v=24 版本号已被第 17 节取代）

> 本节大部分内容（问答 CSRF 修复、严格库内闸门、全站 i18n 体系、云服务端点）仍有效；仅 **16.4 的「注册前置全站门禁」** 与 **`?v=24` 静态资源版本号** 被第 17 节取代。对应任务 #37–#41。

### 16.1 本轮需求

1. **debug 并修复问答机器人现有故障**：截图中的 `CSRF 校验失败`；
2. **严格限定既有库范围**：超出知识库覆盖或证据不足的问题统一拒绝 / 安全兜底，不出现库外问题或越界回复；
3. **注册前置门禁**：用户完成注册前不开放问答机器人及网站整体功能，未注册用户仅可访问注册入口，所有功能入口受注册状态限制；
4. **全站中英双语**：页面、导航、按钮、表单提示、错误信息与问答界面均支持中英切换，两种语言内容完整一致。

### 16.2 问答 CSRF 故障修复

- 根因：`app.js currentCsrf()` 旧实现优先读取 `localStorage["csrf_token"]`，而服务端按 Cookie 中的 `csrf_token` 做双提交校验；会话轮换 / 匿名 CSRF Cookie 覆盖后出现「localStorage 旧 token ≠ Cookie 当前 token」→ 403。
- 修复：**Cookie 是唯一真源**，`currentCsrf()` 优先读 Cookie，新增 `syncCsrfFromCookie()`；`api()` 收到 403 且文案含 `CSRF` 时，用当前 Cookie 覆盖 localStorage 并**自动重试一次**（`_csrfRetried` 防死循环）。`patient-check.js` 的 `localApi()` 同样按 Cookie 取值。
- 附带修复：`api()` 每次请求带 `X-Lang`；问答悬浮球此前会误跳登录页，现仅在 `state.user` 存在时注入。

### 16.3 问答：严格库内闸门

- `app/routers/qa.py` 整体重写为严格模式：`_refusal()` 统一安全兜底（异常 / 无证据 / 引用失效一律拒答，绝不越界作答）；新增 `_citations_exist()`，用 `SessionLocal()` 逐条核对 `citations[].chunk_id` 是否对应 `chunks` 表中真实 `Chunk.id`。
- 非拒答回答必须同时满足：有答案文本、有引用、引用全部真实存在；否则返回 `refused: true` + `insufficient_evidence`。所有回答带 `scope: "knowledge_base_only"`、`kb_guard: "strict"`、`request_id`。
- `rag.py` 保留 `content_overlap()` / `keyword_evidence()` 强证据门槛与 `should_refuse()` 库外闸门，并新增 `REFUSAL_TEXT` 中英拒答表；`safety.py` 的 `check(text, lang)` 让安全拒答也双语。
- 示例问题 `EXAMPLES` 增加 `question_zh/en` 与 `note_zh/en`，界面按语言展示，但提交给后端的一律是规范中文问题；`GET /api/qa/source/{chunk_id}` 的 404 文案本地化。
- 库外问题只显示「暂不回答」+ 原因，**0 条引用**；库内回答的 `[n]` 仍可点开看切片全文、章节、页码、来源编号、许可与外链。

### 16.4 注册前置全站门禁

- `app/shield.py` 整体重写：`GUEST_API_PREFIXES` 仅含 `/api/auth/register`、`/api/auth/login`、`/api/auth/logout`、`/api/auth/me`、`/api/health`；`GUEST_PAGES = {"/register.html", "/login.html"}`；静态资源按前缀 / 后缀白名单放行。
- `is_registered()` 校验有效 JWT、用户存在且 `is_active`、jti 未吊销。非 guest 的 `/api/*` 未登录 → 401 + `need_register: true`；非 guest 页面未登录 → 302 到 `register.html`（保留 query，含 `sharecode`）。
- `CSRF_EXEMPT` 收敛为 auth 三件套；`/api/patient-check` 不再免 CSRF。匿名 CSRF Cookie（`ensure_anon_csrf()`）保留，保证注册表单可提交。
- 前端：`app.js` 的 `PRIVATE_PAGES` 改为 `GUEST_PAGES = { register: true, login: true }`；`boot()` 对非 guest 页要求 `state.user`，否则 `redirectToRegister()`（带 `next` 与 `sharecode`，注册成功原路返回）；`api()` 的 401 除 auth 探测端点外统一回注册入口；问答悬浮球、`openQa()`、`submitQa()` 均只对已登录用户开放。
- 文案一致性收尾：全站清除「免登录 / 公共功能免登录」历史措辞，改为「注册登录后可用」；`patient-check.js` 去掉 `authOptional`，401 不再被静默吞掉；`auth.py` / `translate.py` 注释同步为注册门禁语义。

### 16.5 全站中英双语

- 方案：**以中文原文为字典键**，天然保证中英一一对应；中文模式直接渲染源码中文，英文模式按「整串精确 → 折叠空白整串 → 模板变量 → 长键短语子串」四级替换。
- 服务端 `app/i18n.py`（`lang_of()` / `tr()` / `tr_detail()` / `apply_vars()`）+ 自动生成 `app/i18n_data.py`；`app/main.py` 注册 `HTTPException` 与 `RequestValidationError` 本地化处理器。
- 前端 `static/js/i18n.js`（语言偏好 `localStorage["wb_lang"]`、`MutationObserver` 动态节点、属性翻译、`SKIP_TAGS` / `SKIP_CLASS` 保护知识库数据容器、语言切换器）+ 自动生成 `static/js/i18n-dict.js`。所有 `static/*.html` 注入两份脚本并统一 bump 到 `?v=24`。
- 字典生成器 `scripts/build_i18n.py` 读取 `i18n_strings.txt`（982 条）/ `i18n_en.txt` / `i18n_extra.txt`（128 条），产出 949 个词条、814 个短语键、53 个模板、`i18n_coverage.json`。
- 语言切换 = 保存偏好 + `location.reload()`（保留 query 与 `sharecode`）；`document.documentElement.lang` 同步 `zh-CN` / `en`；每次 API 请求带 `X-Lang`，错误文案、问答拒答、示例问题、告知单标签与免责声明均按语言返回。
- **边界**：知识库语料、术语、领域分类名、资讯标题、引用原文、患者原话属于数据内容，保持原语种、不参与界面翻译（英文模式下这些仍是中文，是刻意设计，不是漏译）。`i18n_inventory.json` 是文案盘点时的历史快照，已不代表当前源码措辞，以 `i18n_strings.txt` 为准。
- **本轮补齐的三处 i18n 细节**：① 补 8 条无障碍属性词条（`主导航` / `关闭问答窗口` / `功能色对照表` / `打开可溯源问答` / `正在检索` / 品牌 aria-label / QA 输入框 placeholder / `查看引用`），语言切换器 `aria-label` 按当前语言单语化；② `TEXTAREA` 从整体跳过改为「只跳过文本内容、属性照常翻译」，修复译文框 / 患者原话框 / QA 输入框的 placeholder 与 aria-label 在英文模式下不翻译；③ `quality.js` 动态拼接的 `搜索{tab}…` 与 `{tab}{scope}` 改走 `tr()` + 模板，消除 `Search术语…` 这类半译混合串。

### 16.6 验证与状态

- `python -m compileall`：通过；全部 `static/js/*.js` 与 `static/vendor/*.js` 的 `node --check`：通过；`scripts/build_i18n.py`：重建成功（982 源串 / 128 附加标签 / 949 词条 / 814 短语 / 53 模板）。静态资源统一 bump 到 `?v=24`。
- 本地 8100：匿名访问功能页 302 到 `register.html`、匿名 `/api/*` 401 且带 `need_register`、注册页 / 登录页 / 静态资源 200、匿名 CSRF Cookie 下发；注册登录后翻译、语言质量、告知单、问答、云端资产均可用。
- 问答：库内问题带真实 `chunk_id` 引用且 `[n]` 可展开；库外 / 证据不足 / 引用失效统一 `refused: true`；`X-Lang: en` 返回英文拒答与英文示例；`X-Lang: zh` 返回中文。
- 双语：本地 8100 冒烟 **50/50 全通过**（门禁 302/401、匿名 CSRF Cookie、v=24 静态资源、注册登录、库内问答 5 条真实引用可点开、中英库外拒答、告知单无译文/无质量字段、翻译不再 403、英文 401/422 文案无中文）；Playwright DOM 扫描：首页 / 翻译 / 告知单 / 资讯 / 我的资产 / 云端资产英文模式**界面中文残留 0**，语言质量页仅 15 个领域分类名属数据内容；`#ql-search` 英文 `Search Terms…` / 中文 `搜索术语…`；问答面板英文标题 `Traceable Q&A`、英文 placeholder、按钮 `Send`；语言切换保留 `sharecode=TESTKEEP`，`document.documentElement.lang` 同步 `en` / `zh-CN`。
- **发布状态**：用户通过确认选项选择「立即发布（推荐）」，本轮 v=24 已重新部署：`verified=true`、`deployedAs=http-service`、sandboxId 不变 `b97659826c614869b352249be2047ed1`，**链接不变**：`https://er-lang-service-desk.app.workbuddy.host/?sharecode=F3VK3EZYS2`。线上冒烟（直连 + sharecode 会话）**40 项全部通过**：匿名根路径 302 到注册页、7 个功能页匿名 302、`/api/*` 401 + `need_register`、注册页 / 登录页 200、6 个 v=24 静态资源 200、字典含 `Search {tab}…` 与「注册登录后可用」、注册登录、库内问答 5 条真实引用可点开、中英库外统一拒答、告知单无译文 / 无质量字段、翻译不再 403；线上数据完整（terms 4154 / corpus 8308 / chunks 124 / culture 738 / variants 150 / news 62）。另有 1 项为冒烟脚本断言层级笔误（health 计数在 `counts` 嵌套内，站点返回正确），站点侧无故障。云服务端点与 Origin 不变，云登录不受影响。管理入口：设置—数据管理—应用。

## 17. 首页免登录 · 英文 UI 排版 · 语言质量英文优先（线上当前 v=25）

> 本节为**当前有效状态**，取代第 16.4 节的「注册前置全站门禁」语义与 `?v=24` 版本号；第 16 节其余内容（问答强拒答、CSRF 修复、i18n 体系、云服务端点）继续有效。对应任务 #42–#45。

### 17.1 本轮需求（用户截图反馈）

1. 「英文的 UI 太急了，调整一下，确保美观可视」——英文文案被短语拼接挤成一团（接缝粘连、全大写眉题字距过密、页头导航 / 印章拥挤）；
2. 「语言质量里面，在切换语言后，以英文为优先显示」——术语 / 语料列表与详情应英文作主行、中文作副行；
3. 「首页不需要登录可以查看，往后的功能则需要登录」——首页重新免登录，其余功能页维持注册门禁。

### 17.2 首页免登录（门禁语义调整）

- `app/shield.py`：`GUEST_PAGES` 增加 `"/"` 与 `"/index.html"`；`GUEST_API_PREFIXES` 增加 `/api/public/overview`（首页统计与资讯 teaser 的唯一数据源），保证匿名首页数字不为空。其余功能页仍 302、功能 API 仍 401。
- 302 重定向补齐 `next`：由 `register.html?sharecode=…` 改为 `register.html?next=<URL 编码的原始页面+query>&sharecode=…`，注册登录成功后前端 `safeNext()` 解码并原路返回刚点的功能页（此前只回首页）。
- `static/js/app.js`：`GUEST_PAGES` 加入 `index` / `home`；`api()` 的 401 改用 `GUEST_PAGES[state.page]` 判断，首页匿名请求不再误跳注册页；`openQa()` 匿名点击改为引导到注册入口（问答仍不开放）；问答悬浮球仍只对已登录用户注入。
- 前端与服务端白名单保持同一份语义；`home-v4.js` 的 `/api/public/overview` 无需改动即可匿名 200。

### 17.3 英文 UI 排版（消除接缝 + 页头收敛）

- **根因**：`static/check.html` 的 `.pc-intro__desc` / `.pc-intro__notice` 中文长句被 `<strong>` 切成多个文本节点，英文模式逐节点做 `phrases` 子串替换，接缝处丢空格，出现 `typedAffected`、`details(e.g.`、`conventions,Relayed`、`relays:No`；`pc-eyebrow` 全大写 + `.14em` 字距过密；英文导航标签（"Patient Handoff Sheet"）比中文长，把页头与功能印章挤窄。
- **整段英文机制**：`static/js/i18n.js` 新增 `data-i18n-en` 支持——英文模式下 `onReady()` 先执行 `swapEnBlocks()`，把带该属性的元素一次性写入成稿英文（`[[...]]` 还原成 `<strong>`，与中文版强调位置一致），并打 `data-i18n-skip` 阻止运行时与 MutationObserver 二次翻译；中文模式完全不执行、零改动。
- 落地 7 处：`check.html` 的 eyebrow / desc / notice / actions note，`index.html` 的 hero-lead / pc-entry eyebrow / pc-entry desc。字典与 `scripts/build_i18n.py` 不变（长段落属富文本，不走短语表）。
- **短功能印章**：`app.js` 新增 `FUNC_STAMP_EN`（`TRANSLATE · BLUE` / `HANDOFF · ROSE` / `QUALITY · PURPLE` …），`renderHeader()` 按 `I18N.lang()` 选择，避免中文印章直译成长串挤占页头。
- **CSS**：`static/css/base.css` 追加 `html[lang="en"]` 排版块——收敛页头 gap / 导航 padding / 字距，皮肤层 mono 导航英文模式取消强制全大写，功能印章允许换行；告知单页眉题取消全大写、降低字距、放开行高；长段落 `overflow-wrap: break-word`。颜色与「颜色 = 功能」映射完全不变。

### 17.4 语言质量英文优先显示

- `static/js/quality.js` 新增 `isEn()` / `displayPair()` / `relPairHtml()` / `detailHeadingHtml()`，**只调整展示主副行顺序，不改数据库内容**：英文模式下术语 / 语料列表主行为英文、副行为中文（`12308 hotline` / `12308热线`），详情 `h2` 为英文、副标题为中文，例句与关联语料 / 术语同样英文优先；东盟本地语原文仍作主行（数据内容），仅把英文释义提到中文之前。
- 中文模式保持原有的「中文主行 + 英文副行」，切换语言（`location.reload()`）后两套顺序各自生效；中文字号沿用此前已放大的主行 20px / 副行 17px，英文作主行时同样清晰。
- 知识库语料、领域分类名、资讯标题、引用原文、患者原话仍按第 16.5 节边界保持原语种（英文界面里这些中文是刻意设计，不是漏译）。

### 17.5 版本号与验证

- 全部 `static/*.html` 静态资源引用 `?v=24` → **`?v=25`**（14 个 HTML，含 i18n.js / app.js / quality.js / base.css / patient-check.css / retro-skin.css 等本轮改动文件）。`scripts/build_i18n.py` 与字典未改动，无需重建。
- 语法：`python -m compileall` 通过；`node --check` 对 `app.js` / `i18n.js` / `quality.js` / `patient-check.js` / `home-v4.js` 全部通过。
- 本地 8100 服务端冒烟：匿名 `/`、`/index.html`、`/api/public/overview`、`/register.html`、`/login.html` → 200；匿名 `/translate.html` / `/quality.html` / `/check.html` → 302；匿名 `/api/terms` / `/api/qa/examples` → 401；302 `Location` 带 `next=translate.html%3Fsharecode%3D…&sharecode=…`；注册 201 / 登录 200 后 6 个功能页与 3 个 API 全 200；`POST /api/patient-check` 200 且 `no_translation=true`、`no_quality_judgement=true`；overview 计数 terms 4154 / corpus 8308 / local_terms 1040。
- Playwright DOM 验证（英文模式）：`check.html` 的 desc / notice 为连贯整段英文、`<strong>` 强调保留、`typedAffected` / `relays:No` / `details(e.g.` / `conventions,Relayed` 四类接缝 **全部消失**；eyebrow、actions note 为短英文；印章 `HANDOFF · ROSE`；导航全英文；`quality.html` 术语主行 `12308 hotline` / 副行 `12308热线`，详情 h2 同为英文，关联语料亦英文优先；切回中文后主行恢复 `12308热线` / 副行 `12308 hotline`；首页英文版 hero-lead / pc-entry 长段落为整段英文。
- 首页匿名（登出后）：URL 保持 `/` 不跳转，统计 4,154 / 8,308 / 1,040 正常渲染，账户区显示「登录注册」，问答悬浮球未注入。
- 控制台错误 **0**（error / warning 均 0）。
- **发布状态**：用户通过确认选项选择「立即发布（推荐）」。首次 `workbuddy_sites_deploy` 返回 `SITES_SANDBOX_UNAVAILABLE`（ECONNRESET，`retryable=true`），工具指引不得自动重试；转达提示后用户确认「立即重试一次」，第二次部署成功：`verified=true`、`deployedAs=http-service`、sandboxId 不变 `b97659826c614869b352249be2047ed1`，**链接不变** `https://er-lang-service-desk.app.workbuddy.host/?sharecode=F3VK3EZYS2`。首次失败曾让线上短暂处于「新 JS + 旧 HTML / 旧门禁」混合状态，第二次成功后已恢复一致。
- 线上冒烟 **34 项通过 + 6 项断言过严（非站点故障）**：匿名首页 / `/index.html` / `/api/public/overview` / 注册登录页 200，overview 计数 4154 / 8308 / 1040；匿名 6 个功能页 302（带 `next=`）、3 个功能 API 401；5 个 `?v=25` 静态资源 200 且内容含 `swapEnBlocks` / `FUNC_STAMP_EN` / `displayPair` / `html[lang="en"]`；`check.html` 4 处 `data-i18n-en`；注册 201 / 登录 200 后 6 个功能页与 3 个 API 全 200；库内问答 5 条真实引用、库外拒答 0 引用、英文拒答无中文；告知单 `no_translation` / `no_quality_judgement`；health 数据完整（4154 / 8308 / 124 / 62 / 738 / 150）。6 项 FAIL 是断言假设后端能看到 `sharecode`：发布平台会剥离该参数（自己消费），但访问会话靠 `__wb_rsc` cookie 维持，补测证明不带 sharecode 的 URL 访问首页 / 接口 / 静态资源仍全部 200，注册回跳链路完整。
- 线上 Playwright DOM（英文模式）：`check.html` 整段英文连贯、2 处 `<strong>` 保留、三类接缝全部消失、印章 `HANDOFF · ROSE`；`quality.html` 术语主行 `12308 hotline` / 副行 `12308热线`、印章 `QUALITY · PURPLE`；控制台 error / warning **0 / 0**。

---

## 18. 英文优先全站复核 · 手机端适配 · 问答预设清理（本地 v=26，待发布）

> 本节对应任务 #51–#54。**线上仍是第 17 节的 v=25**；本节改动全部在本地工作树完成并通过验证，尚未 redeploy，等待用户明确发布授权。

### 18.1 本轮需求

1. 「英文版本重新过一遍，确保所有内容都以英文为优先级」；
2. 「做好手机端适配，不要出现横屏拉动的情况」；
3. 「智能问答机器人把与医疗无关的预设问题删掉」。

### 18.2 英文优先：从「界面文案」扩展到「数据展示 + 动态文案」

**生成式枚举标签表（新增）**

- `scripts/build_en_labels.py` 扫描 `data/app.db` 的领域 / 子领域 / 场景 / 文化子类 / 国家 / 语种 / 审核状态 / 来源 / 状态等字段，产出 `i18n_labels.json` 与 `static/js/i18n-labels.js`。实测 `labels=727, missing=0`。
- **数据库中文值不变、`<option value>` 保持中文原值**，只在展示层用 `I18N.label()` 映射，避免后端筛选失效。生成的 `i18n-labels.js` 已注入全部 14 个 HTML。

**i18n 运行时加固**（`static/js/i18n.js`）

- 新增 `LABELS`（生成表优先、`DATA_EN` 补齐）、`label()` / `dataMapped()` / `pair()`，并暴露到 `window.I18N`。
- 修正 `t()` 匹配顺序：先查 `DICT` / `TEMPLATES` 再判断 `RE_CJK`，否则 `"{name}（{code}）"` 这类「ASCII + 全角标点」模板会被提前返回，留下 `Chinese（zh）`。
- `schedule()` 从 `requestAnimationFrame` 改为 `setTimeout(…, 0)`：后台标签页 / headless 下 RAF 可能永不触发，导致动态插入的中文 UI 不翻译。
- 扩展 `SKIP_CLASS`（`cx-item__recsub`、`tr-history__item-text`、`cx-quote`、`cx-warn` 等），把「中文原始数据」与「界面文案」分开，避免把知识库原文误判成漏译。
- 全站字典重建：`source_strings=982`、`dict_entries=949`、`phrases=814`、`templates=54`；`scripts/build_i18n.py` 补入「文化表达 {n} 条 · 英语变体 {v} 条 · 覆盖 {c} 个国家与地区」模板。

**服务端英文优先**

- `app/routers/news.py`：接入 `lang_of(request)`；新增 `SOURCE_LABELS_EN` / `METHOD_EN` / `_brief(item, lang)`，英文模式 `title` / `summary` 取 `title_en` / `summary_en`，来源与翻译方式标签全英文；`translated_by_zh` 保留为稳定机器值供前端样式判断。
- `app/routers/public.py`：首页匿名概览的 `latest` 同时返回 `title_zh` / `title_en`，保留 `title` 兼容旧前端。
- `app/routers/qa.py`：`/api/qa/examples` 按 `X-Lang` 返回英文题目与英文说明。

**前端英文优先**

- `app.js`：新增 `isEn()` / `enLabel()` / `enPair()` / `enText()`；资讯列表与详情、QA 悬浮面板的引用 / 拒答 / 加载 / 错误提示、页脚两行说明改为一次成稿英文（消除中英标点混排）；QA 兜底预设改为中英双版本 3 条医疗题。
- `home-v4.js`：资讯英文模式 `title_en` 主行、中文标题降为 `.news-sub` 副行；`sourceLabel("un_zh")` 改 `UN NEWS (ZH)`；知识图图例走 `t()`；`reduceMotion()` 恒 `false`，落实「常驻动画」要求。
- `quality.js` / `culture.js`：筛选 `<option>` 英文显示 + 中文 value；列表 / 详情的中文元数据标签走 `I18N.label()`；英文模式 `rec_en` / `definition_en` 主行、中文降副行；详情中文原始注记归入 `Original Chinese notes · source data` 分组并打 `data-i18n-skip`。
- `translate.js`（本轮收尾）：注入 `isEnMode()` / `enText()` 并接入**全部动态文案**——provider 标签表 `PROVIDER_LABEL_EN`、`MT：` / `provider：` / `（降级）`、字数上限与来源标签、恢复草稿、编辑按钮、空句占位、popover、提交错误、历史抽屉、复制 / 交换 / 重译 / 草稿 toast、`ApiError` 与 `messageOf` 兜底。术语 `domain` 走 `I18N.label()`，括号随语言切换半角 / 全角。
- `translate.html`：草稿提示 `已恢复本地草稿（<span …>）` 改用三枚 `data-i18n-en` span，消除英文模式下残留的孤立全角右括号 `）`。
- **边界**：知识库原文、引用全文、患者原话、东盟本地语原文保持原语种；中文模式所有顺序与文案零改动。

### 18.3 手机端适配：消除横向拉动

- `static/css/base.css`：`html` / `body` 使用 `overflow-x: clip`（不用 `hidden`，避免把 `body` 变成滚动容器）；`prefers-reduced-motion` 只收敛 `scroll-behavior`，**不再一刀切关闭动画**。
- 新增窄屏块：页头 flex 不换行 + 品牌省略号、隐藏长英文功能印章、页脚 / 功能色图例 / 长英文段落 `overflow-wrap: anywhere`、Tab 栏标签允许换行、平板宽度导航收敛。
- `quality.css` / `culture.css` / `patient-check.css` / `home-v4.css`：长计数串、详情字段、能力卡与知识球补充 `overflow-wrap: anywhere` 与窄屏内边距。
- `translate.css`：历史抽屉关闭态改 `display:none`，避免 `transform: translateX(105%)` 的元素仍计入 `scrollWidth`。
- **验证方式**：Playwright 对 14 个页面 × 中英 2 语种 × 375 / 768 / 1280 三档视口共 **84 个组合**，实测 `document.documentElement.scrollWidth - clientWidth`、并执行 `window.scrollTo(2000, 0)` 后读 `window.scrollX`（真实横向拖动）。结果 `overflowCount=0`、拖动值全为 0。

### 18.4 问答预设清理与英文库外闸门

- `app/routers/qa.py`：`EXAMPLES` 由 6 条改为 **4 条**医疗 / 急诊 / 语言服务相关库内题，删除「请推荐北京最好吃的火锅店。」与「今天美元兑人民币汇率是多少？」两条非医疗演示题。库外拒答能力改由闸门保证，不依赖演示题。
- `app/services/rag.py`：中文 bigram 对英文问题会「虚高假重合」，导致火锅店 / 汇率 / 世界杯等英文库外问题误摘录片段。新增 `EN_STOPWORDS` / `EN_DOMAIN_ANCHORS` / `english_terms()` / `english_chunk_hits()` / `english_in_scope()`，`keyword_evidence()` 支持英文整词 LIKE，`answer()` 先判英文问题是否落在知识库主题域且具备整词证据。
- `qa.py` 新增 `_canonical_question()`：英文界面照抄预设题时映射回规范中文问题再检索，避免英文预设题被误拒。
- `docs/selftest_ai.py` 同步改为「4 条全部库内医疗题」，新增英文库外统一拒答、英文预设题不误拒检查，并修正 5 条过时断言（`mymemory` provider、zh→vi 演示译文、hybrid 阈值、`EXCERPT_PREFIX`）。

### 18.5 版本号与验证结果

- 全部 `static/*.html` 静态资源 `?v=25` → **`?v=26`**（14 个 HTML、84 处引用），并全部注入 `i18n-labels.js`。线上 v=25 使用不同 URL，发布后浏览器自然取新文件，无缓存串版风险。
- `python -m compileall`（`.venv/Scripts/python.exe`）：通过；`node --check` 对 `static/js/*.js` 全部通过。
- `docs/selftest_ai.py`：**36/36 通过**。
- 本地 8100 API 冒烟（注册 → 登录会话）：**14/14 通过**——匿名 health / overview / auth-me 200、功能 API 401、功能页 302；预设题 4 条且全为库内医疗题、中英题目按语言切换；资讯英文优先且来源标签无中文；英文库外问题拒答 0 引用、英文预设题作答 5 条真实引用；文化 / 变体 / 翻译接口 200。
- Playwright 双语 × 移动端 **84 组合**：`overflowCount=0`、英文界面中文残留 `cjkPages=0`、英文界面全角标点残留 `fwPages=0`、`qa.html` 三个视口预设题均 4 条、控制台 `pageErrors=0`。
- 过程中发现并修复：`translate.js` 已注入 helper 但未接入实际字符串；静态 `translate.html` 草稿提示残留孤立全角 `）`；本地浏览器缓存旧 `?v=26` 脚本造成假阳性，改用全新浏览器上下文复测。

### 18.6 发布状态：本地完成，平台侧发布失败，线上仍为 v=25

- 用户通过确认选项选择「立即发布（推荐）」，先后共 **2 次** `workbuddy_sites_deploy` 均返回 `SITES_APP_LOOKUP_FAILED`（`retryable=true`）：平台无法确认应用 `wbapp_xp3kbiaDkp2BQ4HnqFvZbl` 的发布域名，底层为 `ECONNREFUSED 127.0.0.1:10793`（本地发布桥接服务不可达），与站点代码无关。第二次为按平台指引、经用户确认的**唯一一次重试**，参数完全不变；仍未成功，按指引停止重试，不改参数、不另建应用、不发布到别处。
- **未发生覆盖**：平台提示「为避免覆盖原来的分享链接，本次没有发布」。实测线上首页 200（12,757 字节）、`/api/health` 200、首页静态资源仍为 `?v=25`，链接不变 `https://er-lang-service-desk.app.workbuddy.host/?sharecode=F3VK3EZYS2`（sandboxId `b97659826c614869b352249be2047ed1`）。
- 本地 v=26 全部就绪；待平台服务恢复后，需用户再次明确「发布 / 上线」再执行 redeploy，并补做线上冒烟与线上 Playwright 双语 / 移动端复核。

## 19. v=27：语音输入（翻译 + 患者情况告知单）与首页跑马灯清理

### 19.1 设计定位：语音是「输入旁路适配层」

语音不改变任何既有业务行为，终点只是「一段可编辑文字」或「既有采集表的结构化字段」：

- 翻译页：麦克风 → `/api/speech/recognize` → 可编辑识别文本 → 人工确认 → 写入 `#tr-source`
  → 点既有 `#tr-submit`（复用 `translate.js` 的 `submit()`）→ 既有 `POST /api/translate` / `renderResult()`。
- 告知单页：同一语音内核 → 受控词表抽取 → 自动填入既有圈选项 + 生成**独立预览**
  → 一次人工确认 → `form.requestSubmit()` 复用 `patient-check.js` 的 `submit()` / `render()`。
- **零改动承诺**：`translate.js` 的 `submit()` / `renderResult()`、`patient-check.js` 的
  `OPTIONS` / `collect()` / `submit()` / `render()` / `hasContent()` / 留档逻辑、
  `app/routers/translate.py`、`app/routers/patient_check.py`、`/api/translate` 与
  `/api/patient-check` 的请求响应契约，全部未修改。
- 默认**不自动翻译、不自动提交、不自动生成告知单、不自动留档**；
  C 层「自动提交 / 自动留档」不开启。

### 19.2 后端：ASR 服务层与识别接口

- `app/config.py` + `.env.example`：新增 `ASR_PROVIDER`（默认 `mock`）、`ASR_HTTP_URL` / `ASR_HTTP_KEY` / `ASR_HTTP_TIMEOUT`、
  `ASR_MAX_AUDIO_BYTES`（8 MiB）、`ASR_MAX_DURATION_MS`（60 s）、`ASR_RATE_LIMIT`（10 次/分/IP）、`ASR_DEMO_TEXT(_EN)`。
- `app/services/asr.py`（新建）：只做「音频 → 文本」，不翻译、不做医学抽取、不写库、不落盘；
  `mock` = 课程演示（不联网、返回 `demo=True`），`http` = 服务端中转第三方 ASR；
  日志只记长度 / MIME / 耗时 / provider，不记音频内容或患者原话。
- `app/routers/speech.py`（新建）：
  - `GET /api/speech/status`：能力探测，不暴露 URL / 密钥；
  - `POST /api/speech/recognize`：multipart 上传、MIME 白名单、时长 / 大小上限（只读 `上限+1` 字节）、
    独立滑动窗口限流、`X-Lang` 双语错误 + 稳定 `code`、返回
    `{text, lang, confidence, duration_ms, provider, demo, request_id}`；
  - 口述语种取表单 `lang`（`zh` / `en`），界面语种取 `X-Lang`，两者可不同；
  - `demo_text` 仅 `mock` 生效，`http` 模式一律忽略，防止伪造识别结果。
- `app/main.py`：挂载 `speech.router`。
- `app/shield.py`：`Permissions-Policy` 由 `microphone=()` 最小放开为 `microphone=(self)`
  （定位 / 摄像头仍禁用）；CSP 增加 `media-src 'self' blob:` 供本地回听。

### 19.3 前端：一个内核 + 两个页面适配器

- `static/js/voice-core.js`（新建）：能力探测、`MediaRecorder`、FormData 上传、CSRF / `X-Lang`、
  状态机、计时与自动停录、回听与 `revokeObjectURL`、可编辑识别文本、确认 / 撤销按钮。
  - `getUserMedia` 加 **4 秒超时保护**；无头浏览器 / 被静默搁置的权限请求不再让「开始录音」点了没反应；
    权限晚到时立即 `track.stop()`，绝不留着用户以为已关闭的麦克风。
  - `mock` 演示模式下麦克风不可用则降级为「模拟录音」，并展示「演示口述内容」输入框，
    使课程演示与自动化验收可离线完整走通；界面显式标注「演示识别」。
- `static/js/voice-translate.js`（新建）：识别文本规范化（只做排版整理，不改写原话）、
  追加写入 `#tr-source` 并派发 `input` 事件（字数 / 上限 / 草稿照旧生效）；
  提供「仅写入原文」与「确认并翻译」两个动作，后者点击既有 `#tr-submit`。
- `static/js/voice-check.js`（新建）：**确定性受控词表抽取**，零出网、可解释：
  - 只把说得明确的内容映射到与 `OPTIONS` / 后端 `DETAIL_GROUP` 逐字一致的既有圈选项；
  - 否定词抑制（「没有发烧」不圈发热）、不确定表述抑制（「好像 / maybe」）、
    歧义抑制（「肚子 / 腹部」根本不进词表，绝不猜上腹还是下腹）；
  - **按类别消费字符跨度**：长别名命中或否定后标记该段字符，短别名不得从长短语内部二次匹配
    （修复「没有疼痛」被单字「痛」绕过否定检测而误圈「疼痛」）；类别独立消费，
    保证「伴呼吸困难」同时命中伴随症状与呼吸困难；
  - 一切未匹配内容不猜标签，完整照录进「患者原话」；
  - 预览面板独立渲染，**不调用 `render()`**：确认前不写 `sessionStorage`、
    不出现「保存到云端」入口、不调用 `/api/patient-check`；撤销可完整还原确认前圈选状态。
  - `window.VoiceCheckExtract` 暴露纯函数，便于本地自检。
- `static/css/voice.css` + `translate.html` / `check.html` 中的语音控件：
  沿用复古印刷 / 纸感 / 硬阴影，翻译页蓝、告知单页玫红，遵循「颜色 = 功能」唯一映射；
  移动端控件可换行，不产生文档级横向滚动。

### 19.4 双语、版本与其他改动

- `i18n_extra.txt` / `i18n_en.txt` 新增 `E128`–`E192` 共 **65 条**语音文案（含服务端错误文案），
  重建 `static/js/i18n-dict.js` 与 `app/i18n_data.py`；动态状态文案用 `VoiceCore.t(zh, en)`
  成稿英文兜底，避免字典短语子串替换产出中英混排的半截英文。
- 英文模式装饰印章由「语」改为 `V`；实测语音框中文残留 `0`。
- 全部 14 个 `static/*.html` 静态资源 `?v=26` → **`?v=27`**（90 处引用）。
- **首页跑马灯删除「DEEPSEEK 生成」**（`static/index.html`），并把字典 `0130` 标记为已移除；
  `home-v4.js` 只是把 `ticker-track` 的 `innerHTML` 复制一遍，删源即可两处副本同时生效。
- 英文页头修复（v=27 前段完成）本轮复核：短导航标签 `Home / Translate / Handoff / Quality / News / Assets`，
  `multiLine=[]`、`navOverflow=0`、文档 `overflow=0`。

### 19.5 验证结果

| 项目 | 结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m compileall app scripts docs run_server.py` | 通过 |
| `node --check static/js/*.js` | 全部通过 |
| `scripts/build_i18n.py` | `source_strings=982, entries=1013, phrases=877, templates=54` |
| `docs/selftest_ai.py` | **36/36 通过**（既有翻译 / RAG / 限流 / 降级无回归） |
| 语音 + 回归 API 冒烟 | **18/18 通过**（匿名 401、登录 200、status 不泄密、识别字段完整、口述语种可分离、非法 MIME 415、英文错误英文、空音频 400、超时长 413、缺 CSRF 403、既有翻译 / 告知单 / 问答 / 门禁 / 首页均正常） |
| Playwright 中文全流程 | 模拟录音 → 识别 → 「仅写入原文」**0 次** `/api/translate` → 「确认并翻译」**1 次**且逐句对照正常；告知单预览正确抽取 + 否定抑制、`pc-result` 隐藏、`sessionStorage` 未写、云端入口 0、`/api/patient-check` 0 次；撤销完全还原；确认后生成告知单 1 次调用且不产出译文 |
| Playwright 英文模式 | 语音框中文残留 0、预览中文残留 0、页面标题 / 眉题 / 说明 / 按钮 / 状态 / 标签全英文；英文优先标签如 `Upper abdomen / Pain / Nausea / vomiting / Intermittent / Colicky pain` |
| 移动端 375 / 414 × 中英 × 3 页（12 组合） | 文档 `overflow=0`、`scrollX=0`，翻译页与告知单页无越界元素 |
| 控制台 | `pageErrors=0`、console error 0 |

- 截图：`docs/screenshots/v27-voice-translate-zh.png`、`v27-voice-check-en.png`、`v27-check-en-full.png`。
- 已知边界：真实语音识别需配置 `ASR_PROVIDER=http` 与自有 ASR 端点；若站点被嵌入跨域 iframe，
  除 `microphone=(self)` 外还需 iframe 的 `allow="microphone"`；当前 `mock` 为课程演示模式。

### 19.6 发布状态：本地 v=27 完成，**未发布**

- 线上仍是 **v=25**：`https://er-lang-service-desk.app.workbuddy.host/?sharecode=F3VK3EZYS2`。
- v=26 的发布仍阻塞在平台侧 `SITES_APP_LOOKUP_FAILED`（见 18.6），本轮未再重试。
- 本轮用户消息为「按方案执行 / 修复英文 UI / 删除跑马灯文案」，**不含「发布 / 上线 / 同步到线上」授权**，
  按发布同意规则未执行 `workbuddy_sites_deploy`。待用户明确发布且平台服务恢复后，
  直接以当前 v=27 工作树 redeploy（无需再单独发 v=26）。

---

## 20. v=29：识别文本必须真正来自语音 + 全量回归 + zip 交付

> 用户反馈：「识别的文本并没有对应上语音内容，这部分要修改，改好后整体测试一遍，然后包装成 zip 文件给我」。
> 这是对 v=27 默认 `mock` 演示模式的**行为纠正**：不能把固定示例句或输入框内容冒充识别结果。

### 20.1 核心修正：默认「真实语音识别」

`static/js/voice-core.js` 重写状态机，三条通道职责严格分离：

| 模式 | 触发条件 | 识别文本来源 | 标记 |
| --- | --- | --- | --- |
| `browser`（默认） | 浏览器提供 `SpeechRecognition` / `webkitSpeechRecognition` | **麦克风语音事件** `onresult` 的 `transcript`，`interimResults` 实时上屏 | `provider=browser, demo=false` |
| `server` | 浏览器无语音识别，但服务端 `ASR_PROVIDER=http` | `MediaRecorder` 录音上传 `/api/speech/recognize`，由真实 ASR 返回 | `provider=http, demo=false` |
| `demo` | **用户手动切换单选** | 用户自己填写的「模拟口述内容」 | `demo=true`，明确标注「不解析麦克风声音」 |

关键约束：

- 真实模式**绝不携带** `demo_text`；服务端若仍返回 `demo=True`（`ASR_PROVIDER=mock`），
  前端直接报错并引导切浏览器识别 / 配置 `ASR_PROVIDER=http` / 手动切演示，**绝不把示例文本当作识别结果**。
- 两条真实通道都不可用时明确报错，不再静默回退示例句；`voice-apply` 保持禁用，原文框保持为空。
- 页面新增「识别方式」单选与可见的**识别来源说明**（`voice-mode-note`），用户随时知道文字从哪来。
- 浏览器连续识别会在静音后自行 `onend`，或遇 `not-allowed` / `audio-capture` 抛错；
  v=29 增加「自动续接 + 致命错误收束 + 角标刷新」，避免界面卡在「录音中…」或仍显示 `LIVE · BROWSER`。

### 20.2 边界不变

- 语音仍是**输入旁路适配层**：默认不自动翻译、不自动写入、不自动留档，必须人工确认。
- 翻译页 `submit()` / `renderResult()`、`/api/translate` 契约零改动；「确认并翻译」只点既有 `#tr-submit`。
- 告知单 `OPTIONS` / `collect()` / `submit()` / `render()` 零改动；语音预览独立渲染，
  不写 `sessionStorage`、不触发云端入口、确认前 0 次 `/api/patient-check`。
- 告知单不翻译、不诊断、不评估表达质量、不澄清文化或信息问题。
- `app/routers/patient_check.py`、`app/services/translate_service.py` 未改动。

### 20.3 双语与版本

- 新增 `E193`–`E197` 共 5 条词条（识别方式 / 真实语音识别 / 演示模拟 / 口述语言 / 丢弃这段），
  其中 `E196`–`E197` 修复了英文模式语音框的两处中文残留。
- 重建字典：`entries=1018, phrases=882, templates=54`（`source_strings=982` 断言保持）。
- 全部 14 个 `static/*.html` 静态资源 `?v=28` → **`?v=29`**（90 处）。
  因 `voice-core.js` 与 `i18n-dict.js` 均已修改，必须换缓存键，避免本地旧缓存盖住新逻辑。
- `app/shield.py` 保持 `microphone=(self)` 与 `media-src 'self' blob:` 的最小放行。

### 20.4 全量回归结果（v=29）

| 项目 | 结果 |
| --- | --- |
| `compileall app scripts docs run_server.py` | 通过 |
| `node --check static/js/*.js` | 15/15 通过 |
| `scripts/build_i18n.py` | `entries=1018, phrases=882, templates=54` |
| `docs/selftest_ai.py` | **36/36**（翻译 / RAG / 限流 / 降级 / 库外拒答无回归） |
| API 冒烟 | **32/32**（门禁 302/401、注册登录、能力接口不泄密、中英口述逐字一致、空音频 400、非法 MIME 415、英文错误英文、超时长 413、缺 CSRF 403、前端契约 7 项、既有翻译/告知单/问答/预设题回归） |
| Playwright 翻译页中文 | **11/11**：注入模拟语音引擎，说出唯一句子 → 识别文本逐字一致且不含任何预置示例；临时结果实时上屏；默认 0 次 `/api/translate`；「仅写入原文」写入人工修正文本仍 0 次；「确认并翻译」恰好 1 次；演示模拟返回自填内容且显式标注 |
| Playwright 告知单中文 | **12/12 有效项**：识别文本 = 患者口述；独立预览正确抽取 `上腹 / 疼痛 / 恶心呕吐 / 间歇性 / 剧痛 / 绞痛 / 进食相关 / 伴呕吐 / 伴出汗`；否定项 `发热 / 咳嗽` 正确进入 `suppressed` 且不进任何圈选项；患者原话照录；`pc-result` 隐藏、`sessionStorage` 未写、确认前 0 次生成；撤销完全还原；确认后恰好 1 次生成且无译文 |
| Playwright 英文 | 语音框 / 预览**零中文残留**，标签英文优先（`Upper abdomen / Pain / Nausea / vomiting / Intermittent / Colicky pain`），英文口述逐字一致 |
| 手机端 | 中英 × 375/414 × 3 页 = **12 组合，`overflow=0, scrollX=0`** |
| 控制台 | `pageErrors=0`、console error 0 |

- 截图：`docs/screenshots/v29-voice-translate-zh.png`、`v29-voice-check-en.png`。
- **解包副本独立运行校验 13/13**：全新解压 → 按 `.env.example` 生成 `.env` → 独立端口启动 →
  DB 数据完整（4,154 / 8,308 / 124 / 738 / 150，账号仅剩 2 个）→ 首页 `?v=29`、语音内核可加载、
  门禁 401、注册登录、语音能力接口、翻译、库外拒答全部通过。即 zip 可脱离原工作树直接运行。

### 20.5 使用与部署提示

- 真实识别默认走 Chrome / Edge 原生语音识别，**需要浏览器可访问其语音服务**；
  若该服务被网络限制，可在 `.env` 配置 `ASR_PROVIDER=http` + `ASR_HTTP_URL` + `ASR_HTTP_KEY`
  走服务端中转，或手动切到「演示模拟」做离线教学演示。
- `ASR_PROVIDER=mock` 仅用于「演示模拟」与接口联调，**不会被真实识别通道当成结果**。
- 本地验收地址：`http://127.0.0.1:8100/`（服务由 `run_server.py` 读取 `PORT` 启动）。

### 20.6 发布状态：本地 v=29 完成，**未发布**

- 线上仍是 **v=25**：`https://er-lang-service-desk.app.workbuddy.host/?sharecode=F3VK3EZYS2`。
- v=26 的平台侧 `SITES_APP_LOOKUP_FAILED` 仍未恢复；本轮用户消息为「修改 + 整体测试 + 打包 zip」，
  **不含「发布 / 上线 / 同步到线上」授权**，按发布同意规则未执行 `workbuddy_sites_deploy`。
- 待用户明确发布且平台服务恢复后，直接以当前 v=29 工作树 redeploy。
- 交付物：`涉外急诊语言服务台_v29.zip`（源码 + 数据 + 文档，排除 `.venv` / `.env` / 缓存）。

### 20.7 zip 包内容与启动方式

包内目录 `涉外急诊语言服务台_v29/`：

```
├── app/             FastAPI 后端（routers / services / shield / i18n_data）
├── static/          14 个页面 + css + js（无构建步骤）
├── data/            app.db（已预置 4,154 术语 / 8,308 语料 / 124 切片 / 738 文化表达 / 150 英语变体）+ 8 份 JSONL 源数据
├── vector_db/       V1.3 独立向量库（14,400 × 1024 维）与评测 / 集成脚本
├── scripts/         数据转换、播种、切片、向量化、字典生成脚本
├── docs/            架构 / 验收 / 自检脚本 / v29 截图
├── tests/           接口测试
├── deploy/          nginx 配置
├── requirements.txt / .env.example / run_server.py
├── start.ps1 / start.sh / Dockerfile / docker-compose.yml
├── i18n_*.txt / i18n_labels.json / i18n_coverage.json
└── README.md       本文件（第 20 节为 v=29 说明）
```

**最快启动（Windows）**：

```bash
cd 涉外急诊语言服务台_v29
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env          # 务必把 SECRET_KEY 改成随机字符串
.\.venv\Scripts\python.exe run_server.py     # 默认 3000 端口；可用 set PORT=8100 改端口
```

浏览器打开 `http://127.0.0.1:3000/`。数据已预置在 `data/app.db`，**无需重跑 seed 脚本**；
需要重建时才按第 3 节顺序执行 `scripts/` 下脚本。

> `.env` 与 `.venv` 不随包分发（含密钥 / 平台相关二进制）；`data/` 中的账号仅保留
> `demo` 与使用者自有账号，测试账号已清理。麦克风与浏览器语音识别需 `localhost` 或 HTTPS 环境。

---

## 21. 公网部署：Render（Docker 容器）与 Cloudflare 的边界

### 21.1 为什么 Cloudflare Workers / Pages 部署不了这个站

Cloudflare Workers 构建默认执行 `npx wrangler deploy`，只认**静态资源目录**或 **Worker 脚本**，
仓库里没有 `wrangler.toml` 也没有 `assets.directory`，于是报：

```
✘ [ERROR] Could not detect a directory containing static files (e.g. html, css and js) for the project
```

但即使补上配置消掉这个错，站点依然跑不起来——本站是 **FastAPI + SQLAlchemy + 本地 SQLite 文件 + uvicorn**
的常驻 Python 服务：

| 站点依赖 | Cloudflare Pages / Workers |
| --- | --- |
| 常驻 Python 进程（FastAPI / uvicorn） | ❌ 不提供 |
| 可写文件系统（`data/app.db` 注册 / 留档写库） | ❌ 只有 D1 / Durable Object |
| SQLAlchemy ORM | ❌ Pyodide 装不了 |
| JWT Cookie 登录（依赖上面 DB） | ❌ 随之不可用 |

Cloudflare 上最多把 `static/` 静态壳挂出去，页面能打开但**翻译 / 问答 / 登录 / 告知单全部 404**。

### 21.2 改造点（本仓库已完成）

| 文件 | 改动 |
| --- | --- |
| `Dockerfile` | ① 启动命令改为 `python run_server.py`：读取平台注入的 `PORT`（Render 默认 10000），绑定 `0.0.0.0` + `--proxy-headers`；② 仓库未提交 `data/app.db` 时**构建期自动播种**（`seed_public` → `build_slices` → `embed_chunks --force` → `embed_corpus`）；③ pip 源改为 `ARG PIP_INDEX_URL`（海外默认官方 PyPI，国内构建可加 build-arg 换清华源） |
| `render.yaml`（新增） | Render Blueprint：`runtime: docker`、`plan: free`、`region: singapore`、健康检查 `/api/health`、`SECRET_KEY` 用 `generateValue` 自动生成、`COOKIE_SECURE=true` |

构建期播种链路已实测：全新目录无 `app.db` → 四步脚本全部成功 → 起服务后
`terms=4154 corpus=8308 chunks=124 culture=738 variants=150`，首页与静态资源 200。

### 21.3 Render 部署步骤

1. 把本仓库推到 GitHub（或更新已有仓库），确认包含：`Dockerfile`、`render.yaml`、
   `app/ static/ scripts/ data/*.jsonl`、`requirements.txt`、`run_server.py`。
   想连资讯一起带上就强制提交现成数据库：`git add -f data/app.db`（约 43MB，低于 GitHub 50MB 警告线）。
2. Render 控制台 → **New + → Blueprint** → 选择该仓库 → Render 读取 `render.yaml` 自动创建服务。
3. 等待构建 + 部署（首播镜像构建约 3–6 分钟），健康检查通过后得到
   `https://emergency-lang-desk.onrender.com`。
4. 冒烟：`/api/health` 应返回 `status=ok` 与数据计数；注册一个新账号验证登录闭环。

### 21.4 免费档限制与应对

| 限制 | 表现 | 应对 |
| --- | --- | --- |
| 15 分钟无访问休眠 | 下次访问冷启动 30–60 秒 | 课程演示可接受；需要常驻换 paid plan |
| 无持久磁盘 | 注册账号 / 告知单留档在**重新部署或重启后清空**（代码与种子数据不受影响） | 需要持久化：挂 paid disk，或改接 PostgreSQL（`DATABASE_URL` 已支持，见第 3 节） |
| 新闻数据 | 只存在于现成 `app.db`；构建期播种产物 `news=0` | 提交 `data/app.db`，或部署后跑一次 `scripts/crawl.py` |
| MyMemory 免费翻译额度 | 有每日上限 | 可在 `.env`/环境变量配 `GENERIC_MT_*` 或 DeepSeek 提升质量 |

### 21.5 其他容器平台的等价配置

- **Fly.io**：`fly launch`（识别 Dockerfile）→ `fly secrets set SECRET_KEY=... COOKIE_SECURE=true` →
  `fly deploy`；同样因为 `run_server.py` 会读 `PORT`，无需改代码。
- **Railway**：New Project → Deploy from repo → 识别 Dockerfile；在 Variables 里加 `SECRET_KEY` 等。
- **腾讯云 / 阿里云轻量服务器**：`docker compose up -d --build`（见 `docker-compose.yml`，
  生产建议把 `DATABASE_URL` 切到 PostgreSQL 容器并启用 `deploy/nginx.conf`）。
