# 自测报告：前端 V2 翻译页 + 语言质量维护页（ui4）

日期：2026-11-03　执行人：flow-writer（T3）　环境：Windows 11 + Python 3.12 + SQLite 开发库 `work/site/data/app.db`
被测页面：`static/translate.html`、`static/quality.html`；跳转页：`terms.html / corpus.html / local.html`
依赖：T2 的 `static/js/app.js`（window.App）与 `static/css/base.css` 已就绪，本页只调用 App，未改 T2 文件。

## 1. 自测方式

| 手段 | 说明 |
| --- | --- |
| 静态检查 | `node --check` 通过：`js/translate.js`、`js/quality.js`；HTML/CSS 手检 |
| 接口实测 | `httpx` 脚本直连 API（登录 → 翻译 → 历史 → 术语/语料/本地语 → 增删改 → 导入导出） |
| 端到端 | 无头 Chrome（CDP 协议，原生 WebSocket，无第三方库）：登录 → 翻译 → 悬停 → 浮层 → 历史 → 草稿 → 质量页三 Tab → 增删改 → 导出 → 导入 → 375px |
| 服务 | `uvicorn app.main:app --port 8010`，`MT_PROVIDER=mock`（离线可复现）；下载文件用 openpyxl 验证可打开 |

## 2. 结果总览

**E2E 33 / 33 通过**，控制台错误 0（翻译页、质量页均为 0）。板块色、无横向滚动（1440 / 375）、单列布局、CSRF、401 跳转全部通过。

| 分组 | 通过/总数 | 备注 |
| --- | --- | --- |
| 翻译页：加载 / 配色 / 1440 无横向滚动 | 3/3 | 板块蓝 #2563EB 实测 `rgb(37, 99, 235)` |
| 翻译页：字数计数 / 5000 硬上限 | 2/2 | 粘 5100 字被截断为 5000，红字提示"超出 5000 字上限，已截断" |
| 翻译页：翻译 / segments / provider / 降级 | 3/3 | 后端返回 `segments`（含 terms/pairs）与 `history_id`；mock 模式 `degraded=true` 有黄条 |
| 翻译页：逐句双向高亮 / 点击浮层 | 3/3 | 悬停译文↔原文互高亮；浮层显示 4 条术语、2 条参考语料 |
| 翻译页：草稿 / 历史 / 删除 / 恢复 | 6/6 | 历史载入后出现「恢复草稿」入口；删除一条后 4→3 |
| 质量页：术语 Tab / 详情 / 关联语料 / 配色 | 4/4 | 板块紫 #7C3AED 实测 `rgb(124, 58, 237)`；关联语料 2 条 |
| 质量页：加入我的库 | 1/1 | 我的条目 0→1 |
| 质量页：语料详情 / 关联术语 | 1/1 | 通过 `term_id` 数字部分定位 PK，正确显示「预检分诊 / triage」 |
| 质量页：本地语只读 | 1/1 | 罗马化 / 发音提示 / 语用提示 / 待母语审校 / 来源链接齐全 |
| 质量页：新建 / 编辑 / 删除我的条目 | 2/2 | 新建→列表出现→编辑→删除→列表消失 |
| 质量页：导出 Excel / JSON | 2/2 | 下载 `my_terms.xlsx`（openpyxl 可打开，表头 8 列）与 `my_terms.json` |
| 质量页：导入文件 | 1/1 | 成功 1 条、失败 0 条（后端返回 imported/skipped/errors） |
| 响应式 375px | 3/3 | 两页 scrollWidth=375=viewport；翻译页单列（1 列网格） |
| 登录前置 / 跳转页 | 3/3 | 未登录访问 translate/quality → `login.html?next=…`；terms/corpus/local → `quality.html?tab=…` |

## 3. 后端接口实测（DESIGN §4 契约）

| 接口 | 结果 | 说明 |
| --- | --- | --- |
| POST /api/translate（5000 上限） | 200 | 返回 translation / provider / degraded / locked_terms / context_pairs / **segments** / history_id |
| GET /api/me/translations?limit=20 | 200 | items 含 id/src/tgt/source_text/translation/created_at |
| DELETE /api/me/translations/{id} | 200 / 404 | 删除成功；不存在返回 404（前端 toast 提示） |
| GET /api/me/terms/export.xlsx?format=xlsx | 200 | 真实 xlsx（PK 头，openpyxl 可打开） |
| GET /api/me/terms/export.xlsx?format=json | 200 | JSON 数组，可直接下载 |
| POST /api/me/terms/import（multipart，≤5MB） | 200 | `{ok, imported, skipped, errors}`；前端先校验大小与后缀 |
| GET /api/me/terms / corpus（增删改用 POST/PUT/DELETE） | 200/201 | 私有库按用户隔离，重复创建 409 |
| GET /api/terms、/api/terms/meta、/api/corpus、/api/corpus/meta | 200 | 分页/筛选/详情正常 |
| GET /api/local-terms、/api/local-terms/meta | 200 | 1,040 条，含 romanization/pron_hint/usage_note/audit_status |
| GET /api/terms/{id}/corpus | **404（未实现）** | 按要求复用 `/api/corpus?term_id=`，功能不受影响 |
| POST /api/me/terms/import/{public_id}（加入我的库） | 201 / 409 | 重复加入返回 409，前端提示"已在你的库中" |

## 4. 本轮修复的问题（自测中发现）

1. `renderSegments` 误用 `byId("tr-src")`（实际 id 为 `tr-source`），导致译文渲染后抛异常、结果区报"翻译失败"——已改为正确 id（3 处）。
2. 历史载入后「草稿」恢复入口不出现（草稿与当前输入相同时被跳过备份）——已改为始终快照当前输入到草稿备份。
3. 语料详情的关联术语只按中文句搜索，长句匹配不到——已改为 `T-XXXX` 数字部分直取 `/api/terms/{pk}` 并校验 term_id，再退化为关键词搜索。
4. 导入结果展示补充 skipped 计数（后端按"跳过"返回重复条目）。

## 5. 已知限制 / 需 Lead 关注

| 项 | 说明 | 建议 |
| --- | --- | --- |
| /api/terms/{id}/corpus 未实现 | 契约里已给"或复用 /api/corpus?term_id="，当前按备选实现 | 可不补；若补则前端改一行 |
| 重复并发导入可能 500 | 浏览器一次 change 只发一次请求，UI 有 busy 禁用；脚本并发双发时后端曾抛 UNIQUE IntegrityError | 建议后端 import 捕获 IntegrityError 计为 skipped |
| mock MT 为演示译法 | `MT_PROVIDER=mock` 时译文=术语替换+句对拼接，provider 显示"演示模式（mock）"、degraded=true | 演示前配 DeepSeek/自定义 MT（页面已有降级提示） |
| 本地语 1,040 条待审校 | 全部标"待母语审校"，只读 | 与 DESIGN 一致，勿改成已上线 |
| 无头 Chrome 截图 | 4 张（1440 翻译/浮层/质量术语/我的、375 两页）保存在测试临时目录，未入库 | 需要时重跑脚本生成 |

## 6. 复现命令

```bash
cd work/site
MT_PROVIDER=mock ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8010
# 另开终端：浏览器登录后访问
#   http://127.0.0.1:8010/translate.html
#   http://127.0.0.1:8010/quality.html?tab=terms
# 手工核对：5000 字截断、悬停双向高亮、点击浮层、历史→恢复草稿、三 Tab、增删改、导出 Excel/JSON、导入 JSON、375px 单列
```
