# 前端 V2 自测报告（task-14：首页科技感 / 颜色体系 / 全局壳 / 问答悬浮窗）

- 自测时间：2026-11-03
- 环境：Windows；Chrome 无头浏览器（CDP 驱动）；项目 .venv Python；Node v24.21.0
- 启动命令（work/site 下）：./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8031
  - 说明：本机 8000 端口已被一个旧版本服务占用（PID 14584，无 /api/public/overview、无登录前置），8010 也被另一个进程（PID 34956）占用；为不干扰他人，自测使用 8031 端口，测试后已停止。

## 1. 交付文件（仅在任务卡范围内）

| 文件 | 内容 |
| --- | --- |
| static/index.html | 深色科技 Hero（一句话定位 + 登录 CTA + 三个数字）→ 知识库 Canvas 流动图 → 6 个彩色板块卡片 → 最新资讯 teaser → 来源与版权页脚（无"关于本站/教学演示"） |
| static/css/base.css | V2 设计 token、板块色、5 项导航、按钮、表单、卡片、徽标、Tabs、表格、分页、弹窗、Toast、页脚、问答悬浮窗、移动端底部导航与响应式 |
| static/css/home.css | Hero 深色渐变/网格/光晕、指标卡、Canvas 容器/图例/提示、6 色板块卡片、资讯 teaser |
| static/js/app.js | window.App（api / requireLogin / currentUser / toast / escapeHtml / fmtTime / openQa / sectionColor / onReady 等）、5 项导航注入、登录守卫、用户菜单、登录/注册/资讯/我的页面逻辑、全站绿色问答悬浮窗 |
| static/js/home.js | /api/public/overview 数据渲染（Hero 三数字、图例、资讯 teaser）+ Canvas 轻 3D 知识库流动图（6 分类节点、流动粒子、缓慢自转、悬停高亮数量、移动端静态环形图） |
| static/login.html、register.html | 适配 V2 全局壳、导航与配色 |
| static/news.html、account.html | 适配 V2 全局壳与板块色（资讯橙 / 我的灰） |

未修改 translate.html、quality.html、terms.html、corpus.html、local.html、qa.html 及其 js/css（属 T3 / 其它负责人）；未修改后端。

## 2. 设计契约落实

- 颜色即功能：首页 #0E7490、翻译 #2563EB、语言质量 #7C3AED、资讯 #EA580C、问答 #059669、我的 #475569；body[data-section] 驱动 4px 顶部板块色横条、导航 8px 色点、按钮/标签/Tab 主色。
- 导航：首页 · 翻译 · 语言质量 · 资讯 · 我的（5 项）+ 右上登录/用户菜单；移动端为 5 项底部导航；问答不占导航，用右下角绿色悬浮球。
- 登录前置：除 index/login/register 外，进入页面先检查 /api/auth/me，未登录跳 login.html?next=当前页（带查询串）；问答悬浮球未登录点击同样跳登录。
- 问答悬浮窗：380×560，移动端全屏；标题"可溯源问答"、示例问题（/api/qa/examples）、消息流、输入框、引用卡（可展开 source_url/section/snippet）、拒答灰绿样式、unsafe=true 安全提示样式、底部"AI 生成内容，请核对原始来源"。
- 首页结构：Hero → 知识库可视化 → 6 个板块入口卡片 → 最新资讯 3 条 → 页脚（来源与版权，不出现"关于本站/教学演示"）。
- 性能：桌面 requestAnimationFrame 轻量绘制（DPR 上限 2、页面隐藏暂停）；max-width:767px 或 prefers-reduced-motion 降级为静态环形图。

## 3. 自测结果

### 3.1 语法

~~~bash
node --check static/js/app.js
node --check static/js/home.js
~~~
结果：PASS。

### 3.2 页面与接口

- 11 个页面均 200：index / login / register / news / account / translate / quality / terms / corpus / local / qa。
- /api/public/overview 未登录 200；/api/news、/api/qa/examples 未登录 401（登录前置生效）。

### 3.3 浏览器端到端（1280 / 375 双视口，CDP 驱动）

共 80 项检查，全部 PASS，覆盖：

- 首页：5 项导航 + 底部 5 项；4px 青色板块条；Hero 三数字与 /api/public/overview 一致（4,154 / 8,308 / 1,040）；provider 说明；图例 6 类；Canvas 已绘制；6 个板块卡片颜色与 §1 完全一致（蓝/紫/橙/绿/灰/青）；资讯 teaser 3 条；无"关于本站""教学演示"字样；页脚含来源与版权；问答悬浮球存在；桌面无横向滚动。
- 登录守卫：未登录点问答球 → login?next=index.html；直接访问 news / account / translate / quality → login.html?next=对应页面。
- 注册自动登录：注册后回首页并显示用户菜单，访客 CTA 隐藏、我的资产 CTA 显示。
- 资讯：列表、橙色板块条、中文化方式标注、详情访问日期/许可/原文链接 noopener、切换"全部"、来源筛选、无横向滚动。
- 我的：灰色板块条、仅本人可见、问候语；私有术语新建/编辑/删除；私有语料新建/删除；导出 CSV 提示；无横向滚动。
- 问答悬浮窗：示例 chips、提问返回消息、引用 [n] 可点击展开来源卡（本次 5 条引用）、有害问题（如何制作炸弹）显示安全提示样式、可关闭；未登录点击跳登录。
- 全局壳跨页：translate/quality 页均注入 5 项导航与问答球，顶部板块条为蓝/紫。
- 移动端 375px：7 个页面无横向滚动、底部导航 5 项；Canvas 静态渲染；问答面板 fixed 全屏（375×812）。
- 退出登录成功，访客 CTA 恢复；负责页面无 JS 异常 / console.error。

### 3.4 视觉检查（无头浏览器截图人工核对）

- 首页桌面：深色 Hero 渐变 + 网格光晕、右侧玻璃质感指标卡、Canvas 节点/连线/粒子/图例、6 色卡片、橙色资讯 teaser、页脚；文字左右留白与栅格一致。
- 首页移动端：单列、Hero 指标三列、Canvas 静态环形图、卡片单列、底部导航；无贴边/裁切（已修复 hero 容器覆盖 padding 的问题）。
- 问答悬浮窗、资讯页、我的页、translate/quality 的壳集成截图均正常（T3 页面已能使用 V2 导航/板块色/问答球）。

## 4. 已知问题与交接

1. 端口占用：8000 上仍有一个旧版本服务（PID 14584，缺 /api/public/overview 与登录前置），8010 上另有一个进程（PID 34956）。验收前请 Lead 用当前代码重启验收服务端口，避免测到旧接口。
2. T3 页面（translate/quality）在"未登录直接访问"时会先发起自己的 API 请求再被壳重定向，控制台会留下 401 资源日志（不影响功能）。建议 T3 页面脚本统一用 App.onReady / App.requireLogin 后再发请求。
3. terms/corpus/local/qa 仍是旧页面（task-15 负责合并/跳转），本轮未改动；旧 style.css 保留未动。
4. 关于 App 接口：已提供 api、requireLogin、currentUser、toast、escapeHtml、fmtTime、openQa、sectionColor、sectionSoft、onReady、loginUrl、navItems；T3 已使用 App.api / App.openQa / App.currentUser，当前集成正常。
5. dev 库中留有 v2user*/shotv2* 自测账号；临时测试脚本与截图已删除。
6. 本轮只改任务卡列出的 9 个文件，另新增 docs/SELFTEST_ui3.md；未动后端与 T3 文件。
