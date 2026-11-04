# 前端（static/）自测报告

- 自测时间：2026-11-03
- 自测环境：Windows；Chrome 无头浏览器（CDP 驱动）；项目 .venv 的 Python；Node v24.21.0
- 服务启动命令（在 work/site 下）：
~~~bash
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~
- 路由方式：Lead 已在 app/main.py 把 static/ 同时挂到 /static 与站点根（StaticFiles(html=True)），本报告按根路径 /xxx.html 校验。

## 1. 交付文件清单（只写 static/）

| 文件 | 说明 |
| --- | --- |
| static/index.html | 首页：一句话定位 + 翻译/术语/问答三入口 + 数据条（/api/health）+ 最新资讯 3 条 + 页脚声明 |
| static/login.html | 登录：表单校验、错误提示、next 回跳 |
| static/register.html | 注册：邮箱/用户名/密码校验，成功后自动登录 |
| static/account.html | 个人中心：我的术语/我的语料双标签、搜索、分页、新建/编辑弹窗、删除确认、CSV 导出、"仅本人可见" |
| static/translate.html | 翻译：6 语下拉、2000 字计数、术语 mark 高亮、锁定术语、参考语料折叠、复制/清空、降级提示条 |
| static/terms.html | 术语：搜索 + 语种/领域/状态筛选（/api/terms/meta）+ 列表 + 详情抽屉 + 加入我的库 |
| static/corpus.html | 语料：原文/译文分栏搜索 + 列表 + 详情抽屉 + 加入我的库 |
| static/qa.html | 问答：提问框 + 预置问题（库外问题带"库外"标记）+ 引用 [n] 浮层 + 拒答样式 + 加载态 |
| static/news.html | 资讯：来源徽标/时间 + 详情展开 + 原文链接 target=_blank rel=noopener + 访问日期 |
| static/css/style.css | 全站样式（设计基线、桌面/移动端响应式、表格移动端卡片化） |
| static/js/app.js | 全部页面逻辑（单文件，按 body[data-page] 分发；无框架、无构建） |
| static/favicon.svg | 站点图标（避免 favicon.ico 404） |

设计基线落实：主色 #0E6E6E、强调 #B45309、底色 #FAF8F4、文字 #111827；H1 使用 clamp(28px, 4.4vw, 32px)、正文 16px；卡片 12px 圆角 + 1px 边框；间距为 8 的倍数；顶部导航 7 项（首页/翻译/术语/语料/问答/资讯/我的）+ 登录态；<768px 单列 + 7 项底部导航。

## 2. 自测命令与结果

### 2.1 JS 语法

~~~bash
cd work/site
node --check static/js/app.js
~~~

结果：PASS（无输出即通过；app.js 约 2,600 行 / 102.8 KB）。

### 2.2 9 个页面 HTTP 200（根路径 + /static）

~~~bash
for p in index.html login.html register.html account.html translate.html terms.html corpus.html qa.html news.html; do
  curl -s -o /dev/null -w "$p %{http_code}\n" "http://127.0.0.1:8000/$p"
done
curl -s -o /dev/null -w "root %{http_code}\n" http://127.0.0.1:8000/
curl -s -o /dev/null -w "static css %{http_code}\n" http://127.0.0.1:8000/static/css/style.css
~~~

结果：9/9 页面 200；根路径 / 200；/static/index.html、/static/css/style.css、/static/js/app.js、/static/favicon.svg 均 200。

### 2.3 接口联调（httpx 脚本，浏览器同款 Cookie + CSRF 流程）

共 37 项检查，36 PASS / 1 FAIL：

- PASS：注册/登录/GET /api/auth/me/登出；/api/health counts；/api/terms 列表/详情/meta；/api/corpus 列表/详情/meta；/api/translate/languages（6 语）；/api/translate zh→en（degraded=true、locked_terms 含 must_use/matched、context_pairs 3 条）与 zh→vi；/api/qa/examples（6 条）；/api/me/terms 与 /api/me/corpus 全量增删改查；公共库导入；CSV 导出（text/csv; charset=utf-8）；/api/me/overview、/api/me/audit；/api/news 列表/详情；无 CSRF 写请求 403、未登录访问 /api/me/* 401。
- FAIL（跨组问题，非前端缺陷）：中文问题（如"灾害现场医疗点如何进行检伤分类？"）调用 /api/qa 全部返回 refused=true, reason=no_relevant_chunk。
  - 原因：当前 refuse_threshold=0.35，本地哈希 embedding 下中文问题 top 相似度约 0.12–0.21；英文问题 chest pain triage 的 top 相似度为 0.406，可正常返回 5 条 citations。
  - 建议（ai-core / data-pipeline 决策，前端不改）：把 REFUSE_THRESHOLD 调到约 0.18，或对切片与问题做同义扩展；前端拒答样式已可用，命中时会正常渲染引用。

### 2.4 浏览器端到端测试（无头 Chrome + CDP，1280×900 与 375×812）

共 77 项检查，全部 PASS。覆盖：

- 首页：顶部导航 7 项、底部导航 7 项、未登录登录按钮、数据条（4,154 / 8,308 / 120 / 资讯数）、最新资讯渲染。
- 登录/注册：空表单前端校验提示；注册成功自动登录并跳 account.html；csrf_token 写入 localStorage（长度 32）。
- 个人中心：页头"仅本人可见"；顶部显示用户名；术语新建（弹窗）/编辑（回填原值）/删除（确认弹窗）；语料标签页新建/删除；导出 CSV 触发下载提示；桌面无横向滚动。
- 翻译：6 语下拉；登录后不显示登录提示；2000 字计数；译文 mark 高亮 2 处；降级提示条（degraded=true）；锁定术语 chips；参考语料折叠；复制按钮提示；清空按钮。
- 术语：列表/分页/详情抽屉/加入我的库/抽屉关闭。
- 语料：列表/详情抽屉/加入我的库。
- 问答：预置问题（含 2 条"库外"标记）；回答渲染；引用 [n] 按钮 3 个；点击引用浮层显示章节/相似度/片段，外链带 noopener，Esc 可关闭；引用列表 5 条；拒答样式。
- 资讯：列表/详情展开（含"访问日期"）/原文链接 target=_blank 且 rel 含 noopener。
- 移动端 375px：7 个页面 document 宽度均 ≤ 375（无页面级横向滚动），底部导航 display: grid 正常。
- 退出登录清空 localStorage csrf；重新登录跳转正确；全程无 JS 异常 / console.error（控制台无 CSP 报错）。
- 另用 CDP 实测：桌面与移动端 .table-wrap 横向溢出均为 0（移动端表格已改为卡片式列表，不产生内部横向滚动）。

## 3. 安全与合规自测

- CSP 为 script-src 'self'：所有页面只引用外部 js/app.js，无内联 script、无 onclick 等内联事件属性（grep 验证为 none）。
- 所有动态文本先 escapeHtml 再写入 DOM；译文术语高亮在转义后按区间插入 mark，避免 XSS。
- 外链统一 target="_blank" rel="noopener noreferrer"。
- 非 GET 请求自动带 X-CSRF-Token（localStorage → 读不到时回退 Cookie）；401 跳 login.html?next=当前页；403/429 有统一提示。
- 未登录访问 account 自动跳登录；点"加入我的库"先提示登录再跳转。

## 4. 已知限制 / 交接说明

1. QA 中文问题拒答：见 2.3，属阈值/向量质量，建议 ai-core 调整 refuse_threshold；前端无需改动。
2. 资讯中文标题：当前 llm_provider=mock，爬虫写入的 title_zh 为空，前端显示英文标题 + "待中文化"徽标；配置真实生成模型并重跑 scripts/crawl.py --translate 后自动显示中文。
3. 联调脚本与截图是临时文件，已删除；dev 库中留有少量自测账号（uiuser* / e2euser* / shotuser* / metric*，仅本地开发库，不影响验收）。
4. 前端只改 static/；docs/SELFTEST_ui.md 按本次任务要求新增。
