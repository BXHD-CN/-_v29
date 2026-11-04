# 数据管线自测记录（data-pipeline / task-8）

- 日期：2026-11-03（Asia/Shanghai）
- 环境：Windows · `work/site/.venv`（Python 3.12）· SQLite `data/app.db`
- 配置：`embedding_provider=local`（复用 ai-core 的 `app/services/embedding.py`），`llm_provider=mock`（无 Key）
- 交付文件：`app/services/crawler.py`、`scripts/crawl.py`、`scripts/build_slices.py`、
  `scripts/embed_chunks.py`、`app/routers/news.py`、`app/routers/admin.py`、`data/chunks.jsonl`（生成物）

## 1. 切片构建（build_slices）

命令：

```bash
cd work/site
./.venv/Scripts/python.exe scripts/build_slices.py --out data/chunks.jsonl
```

实际输出：

```text
真实语料切片：40 片（160 条 / 每 4 条一片）
术语切片：80 片（每 15 条术语一片）
合计 120 片，doc 10 个；text 长度 302–500 字，300–500 字合规 120/120
输出：D:\Deepseek Harness Workplace\work\site\data\chunks.jsonl
```

校验结果：

- 120 片 = 真实语料 40 片 + 公共术语 80 片；doc 10 个（6 个真实语料来源文件 + 4 个术语领域）
- 每片字段齐全：`doc_id / chunk_no / title / text / source_url / section / page / lang / license / fetched_at / doc_fingerprint`
- `doc_fingerprint = sha256(text)[:16]`；同 doc 内 `chunk_no` 从 0 递增；`text` 全部落在 300–500 字
- 真实语料：按（来源文件, 类别）排序后每 4 条一片，`section=category`、`license` 原样、`fetched_at=access_date`；
  不足 300 字时补英文摘要（40 片中有 34 片需要补英文）
- 公共术语：按领域分组、每 15 条一片，`section=领域`、`license="来源见 source_code"`、`source_url` 可空

## 2. 向量化（embed_chunks）

命令：

```bash
./.venv/Scripts/python.exe scripts/embed_chunks.py
```

实际输出（全量首次运行）：

```text
[embed] 待处理切片 120 条（force=False, from_db=False）
[embed] 使用 app.services.embedding（dim=1024）
[embed] 第 1 批：成功 32/32
[embed] 第 2 批：成功 32/32
[embed] 第 3 批：成功 32/32
[embed] 第 4 批：成功 24/24
[embed] 写入 120，更新 0，已有向量跳过 0；向量成功 120，失败 0
[embed] chunks 表：120 行，已向量化 120 行
```

再跑一次（幂等，按 `doc_id+chunk_no` 去重、已有向量跳过）：

```text
[embed] 写入 0，更新 120，已有向量跳过 120；向量成功 0，失败 0
[embed] chunks 表：120 行，已向量化 120 行
```

`--limit` / `--force` / `--from-db` 均验证通过：

```bash
./.venv/Scripts/python.exe scripts/embed_chunks.py --limit 3 --force        # 只重算前 3 条
./.venv/Scripts/python.exe scripts/embed_chunks.py --from-db --limit 2 --force  # 从库里读再重算
```

数据库校验（sqlite 直查）：

```text
chunks: 120  embedded: 120
dim = 1024（全部一致）；embedding JSON 全部可解析；L2 范数 0.999996–1.000005
(doc_id, chunk_no) 唯一 120 组；text 长度 302–500
```

## 3. 爬虫（crawler / crawl.py）

命令与结果：

```bash
./.venv/Scripts/python.exe scripts/crawl.py --source usgs --limit 20
# [usgs/USGS 地震] 抓到 1 条：写入 1，更新 0，跳过 0，中文化 0，翻译失败 0
# 合计：写入 1，更新 0，跳过 0，中文化 0，翻译失败 0；news_items 现有 1 条

./.venv/Scripts/python.exe scripts/crawl.py --source all --limit 20
# [un/联合国新闻] 抓到 20 条：写入 20，更新 0，跳过 0 …备注：主源失败（HTTPStatusError），已改用后备源 https://news.un.org/feed/subscribe/en/news/all/rss.xml
# [reliefweb/ReliefWeb] 抓到 20 条：写入 20，更新 0 …备注：主源失败（HTTPStatusError），已改用后备源 https://reliefweb.int/updates/rss.xml
# [usgs/USGS 地震] 抓到 1 条：写入 0，更新 1 …
# 合计：写入 40，更新 1，跳过 0 …；news_items 现有 41 条
```

最终库内：`news_items` 42 条（un 20 / reliefweb 21 / usgs 1），全部 `status=pending`、`title_zh=""`
（未配置 LLM，按契约不做中文化）。

`--translate`（无 Key）行为：

```text
[提示] 未配置生成模型（llm_provider=mock 或缺少 Key），本次跳过中文化，状态记 pending
```

### 3.1 三源实测状态（重要）

| 来源 | 契约 URL | 实测 | 处理 |
| --- | --- | --- | --- |
| UN News | `https://news.un.org/en/rss` | 302 到 RSS 索引页，机器人 UA → 403 / 浏览器 UA → 406 | 自动改用官方订阅源 `https://news.un.org/feed/subscribe/en/news/all/rss.xml`（200，RSS，xml.etree 解析） |
| ReliefWeb | `https://api.reliefweb.int/v1/reports?appname=ait-course&limit=20` | 410 Gone：API v1 已下线；v2 需已申请 appname（403） | 自动改用官方 RSS `https://reliefweb.int/updates/rss.xml`（200） |
| USGS | `https://earthquake.usgs.gov/.../significant_week.geojson` | 200（本周 1 条显著地震） | 正常，json 解析 |

实现要点：httpx 超时 15s、UA `AIT-CourseBot/1.0`、单源失败只记日志/计数、不抛栈；主源失败自动切后备源并把原因写进统计 `note`，主备都失败写 `error` 并跳过。
落库按 `url` 去重：已存在则更新英文事实字段，不覆盖已有中文译文。

### 3.2 踩坑记录：UA 含中文导致 UnicodeEncodeError

首次跑 USGS 报 `UnicodeEncodeError: 'ascii' codec can't encode ...`：HTTP 头值只允许 ASCII，
而契约 UA 为 `AIT-CourseBot/1.0 (+教学演示)`。现改为 UTF-8 百分号编码
`AIT-CourseBot/1.0 (+%E6%95%99%E5%AD%A6%E6%BC%94%E7%A4%BA)`（解码后与契约一致），问题解决。

## 4. 路由自测（news / admin）

用 FastAPI TestClient 实测（`require_admin` 通过 `dependency_overrides` 注入模拟 admin，未新建正式管理员）：

| 接口 | 结果 |
| --- | --- |
| `GET /api/news?page_size=3` | 200，total=42，items 字段 id/source/title_zh/title_en/url/published_at/status |
| `GET /api/news?source=usgs` | 200，total=1（来源过滤生效） |
| `GET /api/news/{id}` | 200，含 summary_zh / summary_en / license / fetched_at；不存在 → 404 |
| `GET /api/news` 日期 | 历史 RFC 822 日期已统一为 ISO 8601（如 `2026-11-02T13:35:39Z`） |
| `GET /api/admin/stats` 未登录 | 401（前端应跳登录） |
| `GET /api/admin/stats`（admin） | 200：users/active_users/user_terms/user_corpus/chunks/embedded_chunks/news/logins_7d/new_users_7d |
| `GET /api/admin/users`（admin） | 200，分页 + 每用户私有术语/语料条数，响应不含 password_hash |
| `PATCH /api/admin/users/{id}`（admin + CSRF） | 200，改 role / is_active 生效并写审计日志 |
| PATCH 未带 CSRF | 403（全局双提交校验，符合契约） |
| PATCH 用户不存在 | 404；非法 role → 422；空 body → 400 |
| `GET /api/admin/audit?limit=3`（admin） | 200，含 action/object_type/object_id/ip/at/username |

`GET /api/health` 复核：`counts={terms:4154, corpus:8308, chunks:120, news:42}`，`embedded_chunks=120`。

## 5. 需要 Lead 决策 / 已知取舍

1. **40 片 vs 禁止切片跨文档**：160 条 / 每 4 条 = 40 片。6 个来源文件条数 30/30/28/30/26/16 均非 4 的倍数，
   若严格要求「切片不跨来源文件」且每片 ≤4 条，最少需要 42 片。为满足 40 片，按（来源文件, 类别）排序后每 4 条切，
   会有 **2 片跨越相邻白皮书边界**（doc 归属首条记录；页面/溯源仍指向首条记录的 source_url）。
   如验收更看重「不跨文档」，可改为 42 片（术语 80 片 → 合计 122 片），我随时可调。
2. **术语片长度**：15 条术语 + 完整释义实测约 719 字，超出 CONTRACT §4.2 的 `text(300–500 字)`。
   现按契约把释义截断（保留「术语（英文）：释义前若干字」），整片 446–500 字；如需完整释义，
   可放宽长度或改为每片 10 条术语。
3. **契约源 URL 失效**：UN/ReliefWeb 主源已不可用（见 3.1），已用官方 RSS 后备源，解析与落库结构一致；
   主源仍按契约保留，失败原因进统计。
4. **中文化**：当前无 LLM Key，全部 `pending`；配置 Key 后 `--translate` 会走 `services.llm.chat`，成功记 `published`。
5. 未改任何 Lead / ai-core / frontend 文件；`data/app.db` 内新增 120 切片、42 条资讯均由上述脚本写入。

## 6. 复现命令汇总

```bash
cd work/site
./.venv/Scripts/python.exe scripts/build_slices.py --out data/chunks.jsonl
./.venv/Scripts/python.exe scripts/embed_chunks.py
./.venv/Scripts/python.exe scripts/crawl.py --source usgs --limit 20
./.venv/Scripts/python.exe scripts/crawl.py --source all --limit 20
```
