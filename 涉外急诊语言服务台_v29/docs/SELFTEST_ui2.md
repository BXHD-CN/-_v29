# 前端第二轮自测报告（task-12：来源链接 / 资讯元信息 / 本地语页 / provider 标识）

- 自测时间：2026-11-03
- 自测环境：Windows；Chrome 无头浏览器（CDP 驱动）；项目 .venv 的 Python；Node v24.21.0
- 服务启动（work/site 下）：./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
- 路由：main.py 仍将 static/ 同时挂到 /static 与站点根（StaticFiles(html=True)），本报告按根路径校验。

## 1. 本轮变更（只改 static/ + 本报告）

1) 术语 / 语料详情：来源代号变成 /api/sources/{code} 链接（target=_blank + rel="noopener noreferrer"），并显示来源文件与审核状态徽标；来源代号悬停提示来源名称/机构/等级（懒加载 /api/sources 后补全 title）。
2) 资讯页：新增「已中文化 / 全部」切换（默认只显示 title_zh 且 status=published 的条目），来源下拉筛选（UN News / 联合国新闻中文版 / ReliefWeb / USGS）；每条带「机器翻译 / 中文版源 / 待中文化」标注；详情显示访问日期、许可、原文链接（target=_blank + noopener）、抓取时间与中文化标注。
3) 新增 local.html（东盟本地语对照）：搜索 + 语种筛选（/api/local-terms、/api/local-terms/meta）+ 列表 + 详情抽屉（本地语原文、罗马化、发音提示、语用提示、待母语审校状态、来源代号链接）；已加入顶部导航与底部导航（导航 8 项），所有页面页脚同步加「本地语」。
4) 翻译页：显示 provider 徽标（MT / 向量 / 生成，来自 /api/translate/languages 的 providers），结果区显示本次 provider 与「降级」徽标；降级说明条写明本次引擎、拼接生成与"并非真实机器翻译、请人工复核"。
5) 问答页：新增知识库统计条（/api/kb/stats：docs / chunks / embedded_chunks / news_zh / local_terms），并显示资讯总数与中文化说明。
6) 首页数据条改为 /api/kb/stats：知识文档、知识切片、已向量化、本地语术语、来源清单、中文资讯（6 项），说明行显示向量/生成/资讯中文化 provider。
7) 样式：新增六项数据条（桌面 6 列 / 平板 3 列 / 手机 2 列）、来源代号链接、provider 徽标、知识库统计条、资讯工具栏、本地语列样式；底部导航改为 8 列；修复资讯标题与英文副标题同行粘连。

## 2. 自测命令与结果

### 2.1 JS 语法

~~~bash
cd work/site
node --check static/js/app.js
~~~

结果：PASS（app.js 约 2,800 行 / 119 KB）。

### 2.2 页面 HTTP 200（根路径 + /static）

~~~bash
for p in index.html login.html register.html account.html translate.html terms.html corpus.html local.html qa.html news.html; do
  curl -s -o /dev/null -w "$p %{http_code}\n" "http://127.0.0.1:8000/$p"
done
~~~

结果：10/10 页面 200；/static/css/style.css、/static/js/app.js、/static/favicon.svg、/static/local.html 均 200。

### 2.3 新接口联调（curl）

- /api/kb/stats → 200：{"docs":10,"chunks":124,"embedded_chunks":124,"news_total":62,"news_zh":62,"local_terms":1040,"sources":69,"providers":{"embedding":"local","llm":"mock","mt":"mymemory","news_mt":"mymemory"}}
- /api/sources/T03 → 200：国家卫生健康委诊疗方案…（level=A，term_count=1156，corpus_count=2312）
- /api/local-terms/meta → 200：越南语/泰语/印尼语/马来语各 260，共 1040
- /api/local-terms?page=1&page_size=2 → 200：含 local_id/lang/local_text/romanization/pron_hint/usage_note/source_code/audit_status

### 2.4 浏览器端到端测试（无头 Chrome + CDP，1280 / 800 / 375）

共 81 项检查，全部 PASS。覆盖：

- 导航：所有页面顶部 8 项、底部 8 项，含「本地语」；账号登录流程可用。
- 首页：6 项数据条全部渲染，且数值与 /api/kb/stats 一致（10 / 124 / 124 / 1040 / 69 / 62）；说明行含"知识库实时统计"；最新资讯仍渲染。
- local.html：列表 20 行、语种下拉 5 项、统计"共 1,040 条"；详情抽屉含罗马化、发音提示、语用提示、待母语审校，来源代号 L01 → /api/sources/L01（target=_blank、rel 含 noopener）；搜索「分诊」→ 28 条；语种筛选 vi 生效；重置筛选恢复。
- 术语详情：来源代号链接指向 /api/sources/（示例 N28）、新窗口 + noopener；含来源文件与审核状态徽标；来源名称 title 提示补全。
- 语料详情：来源代号链接、noopener、审核状态徽标。
- 翻译：provider 徽标 3 项（MT MyMemory / 向量 本地向量 / 生成 演示模式）；登录后无登录提示；译文含 mark 高亮；结果区显示 provider + 降级徽标；降级说明含"降级说明""并非真实机器翻译"。
- 问答：知识库统计 5 项（10 文档 / 124 切片 / 124 已向量化 / 62 中文资讯 / 1,040 本地语术语），说明来自 /api/kb/stats；预置问题仍渲染。
- 资讯：默认「已中文化」（62 / 62，无"待中文化"项）；列表含「机器翻译」标注；切换「全部」显示"共 62 条（含未中文化）"；来源筛选 un_zh 后出现「中文版源」；详情含访问日期、许可、原文链接（rel=noopener）、中文化标注。
- 响应式：375px 下 10 个页面均无页面级横向滚动，底部导航 8 项；800px 下首页/翻译/术语/本地语/资讯无横向滚动（平板导航不换行、不溢出）。
- 控制台：全程无 JS 异常 / console.error（无 CSP 报错）。

### 2.5 静态合规检查

- 所有页面只引用外部 js/app.js，无内联 script、无 onclick 等内联事件属性（grep 为 none）。
- 新增的 /api/sources/{code} 链接与资讯原文链接均 target=_blank + rel="noopener noreferrer"。
- 动态文本仍统一 escapeHtml；来源代号、标题、摘要、许可、本地语原文均转义后再插入 DOM。

## 3. 已知限制 / 交接说明

1) /api/local-terms 列表响应未包含 LocalTerm 的 category 与 scene 字段（模型有、路由未输出），因此本地语列表"场景"列回退显示 domain，详情中"分类/场景"行暂缺省；如后端在列表/详情补这两个字段，前端无需改结构即可展示（或新增详情接口时我再接）。
2) 当前数据已全部中文化（news_zh=62/62），因此「已中文化 / 全部」数量相同；前端筛选逻辑按 status=published 且 title_zh 非空执行，后续爬虫新增 pending 条目会自动只显示在「全部」中。
3) 翻译 notes 里会原样展示后端技术标记（如 mt_degraded:mymemory->mock(mt_unavailable)），如需面向终端用户可在后端或前端再映射为中文说明（本轮保留原始信息，便于排障）。
4) 测试脚本与截图为临时文件，已删除；dev 库中留有少量 ui2user* / shotbuser* 测试账号（仅本地开发库）。
5) 本轮只改 static/，另新增本报告 docs/SELFTEST_ui2.md；未改后端。
