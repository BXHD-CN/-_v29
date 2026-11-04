# 界面改版 V2 设计契约（本轮所有前端改动必读）

> 目标：颜色即功能（看颜色知道板块）、首页科技感与专业度、知识库动态可视化、翻译像 DeepL、问答悬浮窗、登录前置。
> 文件归属见 §5；只改自己名下文件。

## 1. 板块色（颜色即功能）

| 板块 | 页面 | 主色 | 用法 |
| --- | --- | --- | --- |
| 首页 | index.html | #0E7490（青） | 深色 Hero（#0B1220 → #0E7490 渐变）+ 青色强调 |
| 翻译 | translate.html | #2563EB（蓝） | 顶部色条、按钮、选区、历史项激活态 |
| 语言质量维护 | quality.html | #7C3AED（紫） | 三个 Tab、术语/语料对照卡、导入导出按钮 |
| 资讯 | news.html | #EA580C（橙） | 来源徽标、时间、外链按钮 |
| 问答 | 全局悬浮窗 | #059669（绿） | 悬浮球、气泡、引用卡 |
| 我的 | account.html | #475569（石板灰） | 表头、徽标 |

- 每个功能页面左侧或顶部有一条 4px 板块色竖/横条；导航项前面有 8px 板块色圆点；按钮/标签用对应板块色。
- 中性色：页面底 #F7F8FA，卡片 #FFFFFF，文字 #0F172A / #475569，边框 #E2E8F0。
- 字号：H1 28–32、H2 20–22、正文 15–16、辅助 13；圆角 12px；间距 8 的倍数；阴影极轻（0 1px 2px rgba(15,23,42,.06)）。

## 2. 页面与信息架构

导航：**首页 · 翻译 · 语言质量 · 资讯 · 我的**（5 项）+ 右上角登录/用户菜单；问答不占导航，用右下角悬浮球（全站可见）。
旧页面 terms.html / corpus.html / local.html 一律 301/跳转到 quality.html 的对应 Tab。

## 3. 登录前置（已由后端中间件强制）

- 除 `/api/auth/*`、`/api/public/overview`、静态页外，所有 `/api/*` 未登录返回 401；
- 前端：`App.requireLogin()` 检查 `/api/auth/me`，401 跳 `login.html?next=当前页`；
- 首页/登录/注册公开；其余页面进入前必须已登录；
- 翻译、问答必须登录（后端已强制 + 前端拦截）。

## 4. 本轮新增/变更接口（后端同步实现）

| 接口 | 说明 |
| --- | --- |
| GET /api/public/overview | 公开概览：counts/domains/langs/latest/providers（首页可视化用，不含正文） |
| POST /api/translate | 入参上限 **5000 字**；返回新增 `segments:[{src,tgt,terms[],pairs[]}]` 供逐句对照 |
| GET /api/me/translations?limit=20 | 翻译历史列表 |
| DELETE /api/me/translations/{id} | 删除一条历史 |
| GET /api/me/terms/export.xlsx?format=xlsx\|json | 私有术语导出（Excel/JSON） |
| POST /api/me/terms/import | 上传 .xlsx/.json 导入私有术语（multipart，字段 zh,en,lang_pair,domain,definition,note,source_code,source_url） |
| GET/POST | 语料同上：/api/me/corpus/export.xlsx、/api/me/corpus/import |
| GET /api/terms/{id}/corpus | 术语关联语料（或复用 /api/corpus?term_id=） |

所有非 GET 的 /api/* 仍需 `X-CSRF-Token`。

## 5. 文件归属（严禁越界）

| 文件 | 归属 |
| --- | --- |
| static/index.html、static/css/base.css、static/css/home.css、static/js/app.js、static/js/home.js | T2（首页与全局壳） |
| static/translate.html、static/js/translate.js、static/css/translate.css | T3 |
| static/quality.html、static/js/quality.js、static/css/quality.css | T3 |
| static/news.html、account.html、login.html、register.html（仅适配新导航与颜色） | T2 |
| static/terms.html、corpus.html、local.html（改为跳转 quality.html） | T3 |
| app/routers/translate.py、history.py、transfer.py、services/sentence_align.py | T1（后端） |
| app/main.py / config.py / models.py / shield.py / qa.py / safety.py / public.py | Lead |

T2 在 `window.App` 上暴露：`api(path,opts)`、`requireLogin()`、`currentUser`、`toast(msg,type)`、`escapeHtml(s)`、`fmtTime(s)`、`openQa(question?)`、`sectionColor`。
T3 只调用这些，不重写它们；页面脚本用独立文件，`<script src="/static/js/app.js"></script>` 之后再引入自己的 js。

## 6. 首页知识库可视化（T2）

- Canvas 2D 实现“轻 3D”：中心核心球（知识库）+ 6 个环绕分类节点（术语/语料/本地语/资讯/来源/切片），节点之间流动粒子连线；整体缓慢自转，鼠标悬停高亮该分类并显示数量；不闪烁、不刺眼，移动端降级为静态环形图。
- 数据来自 /api/public/overview（domains/langs/counts）。
- 首页结构：Hero（一句话定位 + 登录 CTA + 三个数字）→ 知识库可视化 → 板块入口卡片（6 个彩色卡片，颜色对应 §1）→ 最新资讯 3 条（teaser）→ 页脚（来源与版权，不写“关于本站/教学演示”字样）。

## 7. 翻译页（T3，DeepL 风格）

- 左右两栏：左输入（5000 字上限，实时计数，超额禁止提交并提示）、右译文；顶部源/目标语言下拉 + 交换按钮；底部复制/清空/重新翻译。
- 历史记录：右侧可折叠侧栏（GET /api/me/translations），点击载入；**当前输入自动存 localStorage 草稿，不被历史顶掉**；历史可删除。
- 逐句对照：使用返回的 `segments`；鼠标移到译文某句 → 对应原文句高亮；移到原文句 → 对应译文句高亮；点击句段弹窗显示该句命中的术语（zh→译法）与参考语料。
- provider 徽标 + 降级提示；错误用 toast。

## 8. 语言质量维护页（T3）

- 顶部三个 Tab：术语 / 平行语料 / 东盟本地语（各自板块紫色系）。
- 布局：左侧检索+筛选+列表（分页），右侧详情面板；**术语选中时右侧下半部分显示该术语的关联语料（/api/corpus?term_id=）**；语料选中时显示关联术语卡。
- 读写：登录用户可新建/编辑/删除“我的条目”（POST/PUT/DELETE /api/me/terms|corpus）；公共条目只读并提供“加入我的库”。
- 导入导出：工具条按钮“导入 Excel/JSON”“导出 Excel/JSON”（/api/me/*/export.xlsx、/api/me/*/import），导入结果显示成功/失败条数。
- 本地语 Tab：只读（/api/local-terms），含罗马化、发音提示、语用提示、待母语审校标注、来源链接。

## 9. 问答悬浮窗（T2）

- 右下角悬浮球（绿色 #059669），未登录点击 → 跳登录；登录后展开面板（380×560，移动端全屏）。
- 面板：标题“可溯源问答”、示例问题 chips（/api/qa/examples）、消息流、输入框；答案带引用卡片（点击展开 source_url/section），拒答用灰绿色提示；底部固定“AI 生成内容，请核对原始来源”。
- 安全：后端已拦截有害问题；前端对返回 `unsafe=true` 显示安全提示样式，不渲染任何危险内容。
- 全站可用：由 app.js 注入，不依赖单独页面。

## 10. 验收

- 未登录访问 /translate /quality /check /news /account → 由 shield.py 302 到 register.html；注册并登录后可正常使用。
- 首页可视化 60fps 左右、移动端不卡；10 个页面 200；375px 无横向滚动。
- 翻译 5000 字拦截（前端计数 + 后端 422/400）；逐句 hover 高亮与弹窗可用；历史不丢草稿。
- 质量维护页可导入导出 Excel/JSON（下载文件可被 openpyxl 打开）。
- 问答悬浮窗在任意页面可开；有害问题返回安全提示；正常问题带引用。
