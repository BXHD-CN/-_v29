# 站点当前状态（交付时快照）

日期：2026-11-03　环境：Windows + Python 3.12 + SQLite（本地开发库 `data/app.db`）

## 1. 数据量

| 数据 | 数量 | 说明 |
| --- | --- | --- |
| 公共术语 | 4,154 | 来源代号 100%、审核状态 100%、可按语种/领域筛选 |
| 公共语料 | 8,308 | 中英句对；语种对/审核状态/来源齐全 |
| 语料向量 | 8,308 | float32 × 1024 维（`corpus_vectors`），翻译时 top-3 上下文 |
| 知识库切片 | 124 | 真实语料 44 片（不跨文档）+ 术语组 80 片，全部向量化 |
| 东盟本地语对照 | 1,040 | 越/泰/印尼/马来各 260；状态“待母语审校”如实标注 |
| 来源清单 | 69 | 含发布机构、等级、可核查入口 URL |
| 资讯 | 62 | 全部已中文化（20 条中文版源 + 42 条机器翻译），待译 0 |
| 用户 | 1 | demo 演示账号（私有库为空） |

## 2. 功能自查（全部实跑）

| 项 | 结果 |
| --- | --- |
| 注册 / 登录 / 登出 / 当前用户 | 通过（bcrypt + JWT HttpOnly Cookie） |
| CSRF 双提交 | 无 token 写请求 403；带 token 201 |
| 私有术语/语料 CRUD | 通过；跨用户 404（pytest 覆盖） |
| 从公共库复制 / 导出 CSV | 通过（重复导入 409） |
| 翻译 | 6 语种 10 方向；术语锁定（zy→en 用英文术语，→vi/th/id/ms 用本地语）+ 语料向量上下文 + 译后校验；无 MT 额度时降级并标注 |
| 问答 | 库内 5 条引用（可点开 source_url/section）；库外拒答（汇率/天气/世界杯均拒） |
| 资讯 | 默认只显示已中文化；详情含访问日期/许可/原文链接/机翻标注 |
| 术语/语料详情 | 来源代号→`/api/sources/{code}` 外链；来源文件、审核状态 |
| 本地语对照 | `/local.html`：搜索/语种筛选/罗马化/发音提示/语用提示 |
| 管理接口 | 401 / 403 / admin 改角色、停用、审计 |
| 页面 | 10 页 + CSS/JS 全 200；375px 无横向滚动（无头 Chrome E2E 81/81） |
| 增量更新 | `update_slices.py --dry-run`：124 条一致（新增/变更/删除三种 diff 已演练） |

## 3. 问答回归（本地哈希向量 + hybrid 拒答）

| 问题 | 结果 |
| --- | --- |
| 传染病防治法规定了什么？ | 5 条引用 |
| 预检分诊是什么？ | 5 条引用 |
| 外籍患者签知情同意要注意什么？ | 5 条引用 |
| 患者胸痛怎么分诊？ | 5 条引用 |
| 今天美元汇率多少？ | 拒答 |
| 明天天气怎么样？ | 拒答 |
| 2026 年世界杯冠军是谁？ | 拒答 |

## 4. 当前限制

- **真实机翻**：默认走 MyMemory 免费端口，当日额度用尽时自动降级 mock（页面标 degraded）。演示前请配置 `DEEPSEEK_API_KEY` 或 `GENERIC_MT_URL`（百度/腾讯/DeepL 等端口），否则东盟语种只能是“术语替换 + 句对拼接”的演示效果。
- **BigModel/DeepSeek**：任务书点名要求，代码已接；未配置 Key 时为本地向量 + 检索摘录模式。
- **本地语**：1,040 条“待母语审校”，页面如实展示。
- **PostgreSQL/pgvector**：代码分支已写（`chunk_vectors` HNSW），本机无 PG 未实跑。

## 5. 复现命令

```bash
cd work/site
./.venv/Scripts/python.exe -m pytest tests -q          # 8 passed
./.venv/Scripts/python.exe scripts/seed_public.py      # 幂等（术语/语料/来源/本地语）
./.venv/Scripts/python.exe scripts/build_slices.py
./.venv/Scripts/python.exe scripts/embed_chunks.py --force
./.venv/Scripts/python.exe scripts/embed_corpus.py
./.venv/Scripts/python.exe scripts/crawl.py --source all --limit 30 --translate
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

## 6. 上生产前必做

1. `.env` 换 `SECRET_KEY`、开 `COOKIE_SECURE=true`；
2. 配 `BIGMODEL_API_KEY` / `DEEPSEEK_API_KEY`，或 `MT_PROVIDER=generic` 填已有 MT 端口；
3. 切 PostgreSQL + pgvector，重跑 seed/slices/embed；
4. 套 `deploy/nginx.conf`（TLS、安全头、限流、/api/admin IP 白名单）；
5. `scripts/create_admin.py` 建管理员，删 demo 或改密码。

## 7. V2 改版快照（2026-11-03）

- 页面：11 个（首页/翻译/语言质量/资讯/登录/注册/我的 + 3 个旧页跳转 + qa 兼容页）；板块色：青/蓝/紫/橙/绿/灰。
- 登录前置：中间件强制，匿名 `/api/terms`、`/api/corpus`、`/api/translate`、`/api/qa` 全部 401。
- 翻译：真实 DeepSeek，逐句 `segments` + 历史记录 + 5000 字上限（422）+ 逐句悬停对照。
- 语言质量维护：术语/语料/本地语合并，术语↔语料对照，私有库 CRUD，Excel/JSON 导入导出。
- 问答：右下角全站悬浮窗，安全过滤（武器/自伤/暴力/毒品/黑客/仇恨/未成年人/提示注入），自伤类返回危机干预提示。
- 测试：pytest 20 项；无头 Chrome E2E 80 + 33 项。
