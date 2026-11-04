# 向量检索服务 · 接入说明（V1.0）

> 服务：`work/vector_db/api_server.py`（纯标准库，无 fastapi/flask）
> 索引：`work/vector_db/index/`（vectors.npy 14400×1024 float16 L2 归一化、idf.npy、meta.jsonl、index_meta.json）
> 检索内核：`work/vector_db/search.py`（**未修改**，API 只做进程内复用）
> 配套文件：`integration/function_schema.json`、`integration/rag_prompt.md`、`integration/mt_prompt.md`

## 1. 文件清单

| 文件 | 作用 | 谁用 |
|---|---|---|
| `api_server.py` | HTTP API 服务（5 个接口 + 软超时 + CORS + 统一错误） | 平台后端、采集脚本 |
| `integration/function_schema.json` | 3 个工具的 JSON Schema（search_terms / search_corpus / compare_translations） | 大模型 function calling |
| `integration/rag_prompt.md` | RAG 问答系统提示词 + context 模板 + 3 个完整示例 | 问答机器人 |
| `integration/mt_prompt.md` | MT 术语约束提示词 + 中英各 2 例 | 翻译管线 |
| `integration/README.md` | 本文件 | 所有人 |

## 2. 启动

### 2.1 最简启动

```bash
python work/vector_db/api_server.py --port 8848
# 输出：vector-db API 已启动：http://0.0.0.0:8848  (docs=14400, dim=1024)
```

### 2.2 常用参数

| 参数 | 默认 | 环境变量 | 说明 |
|---|---|---|---|
| `--host` | 0.0.0.0 | `VDB_HOST` | 监听地址；只给本机用可设 127.0.0.1 |
| `--port` | 8848 | `VDB_PORT` | 监听端口 |
| `--index-dir` | `work/vector_db/index` | `VDB_INDEX_DIR` | 索引目录（须含 4 个索引文件） |
| `--timeout` | 20 | `VDB_TIMEOUT` | 单请求软超时（秒），超时返回 504 |
| `--max-k` | 50 | `VDB_MAX_K` | 单次返回条数上限 |
| `--max-batch` | 50 | `VDB_MAX_BATCH` | 批量检索 queries 上限 |
| `--quiet` | 关 | — | 关闭访问日志（错误仍会打印） |
| `--selftest` | — | — | 起临时端口自测全部接口后退出 |
| `--version` | — | — | 打印版本 |

启动耗时：索引加载约 0.4 秒；常驻内存约 150–200 MB（vectors 以 float32 载入 + meta 全文）。

### 2.3 自测（推荐先跑）

```bash
python work/vector_db/api_server.py --selftest
# 末尾应输出：selftest: 8/8 成功
```

## 3. 接口一览

| 方法 | 路径 | 参数 | 返回 |
|---|---|---|---|
| GET | `/health` | — | `{status, docs, dim, sources, version, uptime_s, requests}` |
| GET | `/search` | `q`（必填）、`k`（默认 8，≤50）、`source`（term/corpus/culture/local/real，可空=全库） | `{query,k,source,count,results[]}` |
| GET | `/term/<doc_id>` | doc_id 路径参数 | 单条完整字段（含 `text`、`i`） |
| GET | `/compare` | `q`（必填）、`k`（默认 5） | `{query,k,groups{term|corpus|culture|local|real},total}` |
| POST | `/batch` | JSON：`{"queries":[...],"k":8,"source":null}` | `{count,k,source,elapsed_ms,results:[{query,hits[]}]}` |
| GET | `/` | — | 路由提示（自描述 JSON） |
| OPTIONS | 任意 | — | 204，返回 CORS 头 |

每条结果字段：`score, source, doc_id, zh, en, domain, scene, country, parent`（`/term` 额外给 `text`、`i`）。

**score 语义**：混合打分（向量 0.45 + 词法 0.55）加精确匹配加成，范围约 0–1.4，**只用于相对排序，不是概率**；同题不同查询之间不可直接比大小。

## 4. 接口示例

### 4.1 curl

```bash
# 健康检查
curl -s http://127.0.0.1:8848/health

# 术语检索（中文需 URL 编码）
curl -s "http://127.0.0.1:8848/search?q=%E9%A2%84%E6%A3%80%E5%88%86%E8%AF%8A&k=8&source=term"

# 英文检索，全库
curl -s "http://127.0.0.1:8848/search?q=triage&k=5"

# 单条详情
curl -s "http://127.0.0.1:8848/term/term-T-0001"

# 译法对比（五类来源分组）
curl -s "http://127.0.0.1:8848/compare?q=%E9%A2%84%E6%A3%80%E5%88%86%E8%AF%8A&k=5"

# 批量检索
curl -s -X POST http://127.0.0.1:8848/batch \
  -H "Content-Type: application/json" \
  -d '{"queries":["预检分诊","triage"],"k":3}'
```

### 4.2 Python（requests）

```python
import requests

BASE = "http://127.0.0.1:8848"

r = requests.get(f"{BASE}/search", params={"q": "预检分诊", "k": 8, "source": "term"}, timeout=30)
for h in r.json()["results"]:
    print(h["doc_id"], h["zh"], h["en"], h["score"])

r = requests.get(f"{BASE}/compare", params={"q": "知情同意", "k": 5}, timeout=30)
for src, hits in r.json()["groups"].items():
    print(src, [(h["doc_id"], h["zh"], h["en"]) for h in hits[:2]])

r = requests.post(f"{BASE}/batch", json={"queries": ["医疗意外", "非正常死亡"], "k": 5}, timeout=60)
for item in r.json()["results"]:
    print(item["query"], item["hits"][0]["doc_id"])
```

### 4.3 Python（仅标准库 urllib，无第三方依赖）

```python
import json, urllib.parse, urllib.request

base = "http://127.0.0.1:8848"
q = urllib.parse.urlencode({"q": "预检分诊", "k": 5, "source": "term"})
with urllib.request.urlopen(base + "/search?" + q, timeout=30) as resp:
    data = json.load(resp)
print(data["count"], data["results"][0]["doc_id"])
```

## 5. 自测记录（真实执行结果）

### 5.1 内建自测 `--selftest`（2026-11-02 21:00，临时端口）

```text
[PASS] GET /health            200     54ms  {"status": "ok", "docs": 14400, "dim": 1024, "sources": {"term": 4154, "corpus": 8308, "culture": 738, "local": 1040, "real": 160}, ...}
[PASS] GET /search(term)      200    190ms  count 8, top1 term-T-0001 score 1.0436
[PASS] GET /search(all)       200    510ms  count 5, top1 corpus-T-0001-02 score 0.9379
[PASS] GET /term/<doc_id>     200     11ms  term-T-0001, has_text=true
[PASS] GET /compare           200    531ms  5 组来源各 5 条
[PASS] POST /batch            200    995ms  count 2（含中文 预检分诊 与 triage）
[PASS] GET /search(400)       400      2ms  {"error":{"code":"empty_query",...}}
[PASS] GET /term(404)         404     21ms  {"error":{"code":"not_found",...}}
selftest: 8/8 成功
```

### 5.2 真实起服务 + curl（2026-11-02 21:03，端口 8848，pid 1607，LISTENING 已确认）

| # | 请求 | 结果 |
|---|---|---|
| 1 | `GET /health`（-i 看头） | 200；`Server: VDB/1.0.0`；`Access-Control-Allow-Origin: *`；body 183 字节 |
| 2 | `GET /search?q=预检分诊&k=3&source=term` | 200；count 3；top3 = term-T-0001(1.0436) / term-T-0019(0.5242) / term-T-0018(0.5235) |
| 3 | `GET /term/term-T-0001` | 200；doc_id=term-T-0001，source=term，has_text=true |
| 4 | `GET /compare?q=预检分诊&k=2` | 200；groups = term/corpus/culture/local/real 各 2 条，total=10 |
| 5 | `POST /batch`（triage、chest pain，k=2） | 200；count 2；elapsed_ms 136；first_doc=corpus-T-0001-02 |
| 6 | 错误路径 `/search?k=3`、`/nope` | 400（missing q）、404（unknown path），均为统一 JSON |

> 说明：中文查询在 curl 中必须 percent-encode（`%E9%A2%84...`）；POST /batch 的 JSON body 可直接写中文。

## 6. 平台怎么调

1. **直连**：平台后端用 HTTP 调 `/search`、`/compare`；单次 P95 < 700 ms（k≤10）。
2. **反向代理**：生产环境建议前面挂 Nginx（HTTPS、限流、鉴权），服务本身不带鉴权，**不要直接暴露公网**。
3. **并发**：ThreadingHTTPServer + 8 线程工作池；检索本身 CPU 轻量（14400×1024 点积 + 词法打分），单机 4–8 QPS 实测够用；更高并发建议多进程 + 前置 LB。
4. **超时**：服务侧软超时 20s 返回 504；调用方 timeout 建议 30s，批量接口按 queries 数 × 1s 估算。
5. **容器化**：只需 python3 + numpy，把 `api_server.py`、`search.py`、`index/` 三个一起挂载即可；`index/` 约 35 MB。

## 7. LLM 怎么调

### 7.1 Function Calling 流程

```text
用户问题
  → LLM 按 function_schema.json 选择工具（search_terms / search_corpus / compare_translations）
  → 平台执行对应 HTTP 请求（/search?source=term | /search?source=corpus | /compare）
  → 结果精简后作为 tool 消息回填给 LLM
  → LLM 生成带 doc_id 与来源的回答
```

要点：schema 里已写死「何时调用」「何时不要调用」；回填时只保留 `score/source/doc_id/zh/en/domain/scene`，避免 context 过长。

### 7.2 RAG 流程

1. 先按 `rag_prompt.md` 的「问题 → 检索词」四步改写；
2. 调 `/search`（术语优先 term，例句用 corpus）或 `/compare`；
3. 按模板拼 `{context}`（默认 8 条）；
4. 生成回答后，平台正则校验回答里的 doc_id 是否都在 context 内，越界即重试一次。

### 7.3 MT 流程

1. 抽取原文专业词 → 逐个 `/search?source=term` 取 top1 作为术语表；
2. 按 `mt_prompt.md` 注入 `{glossary}`；
3. 译后质检：推荐译法命中率、[未收录] 标注是否齐全。

## 8. 常见问题（FAQ）

**Q1：端口被占用怎么办？**
```bash
python work/vector_db/api_server.py --port 8849
# 或 Windows 查占用： netstat -ano | findstr 8848
```

**Q2：启动报「索引未加载」？**
检查 `--index-dir` 下是否有 `vectors.npy / idf.npy / meta.jsonl / index_meta.json` 四个文件；`/health` 会返回 `degraded` 与具体错误。

**Q3：为什么返回 504？**
查询太长或 k 太大时词法打分耗时会上升；把 k 降到 10 以内、查询控制在 30 字内。软超时可通过 `--timeout 40` 放宽（不建议超过 60）。

**Q4：CORS 已开 `*`，浏览器还是报错？**
OPTIONS 预检已实现（204 + Allow 头）；若前面挂了 Nginx，注意不要覆盖 `Access-Control-Allow-Origin`。

**Q5：中文返回乱码？**
接口本身返回 UTF-8 JSON；Windows 控制台默认 GBK 会显示乱码，用 `curl ... | python -c "import sys,json;print(json.load(sys.stdin))"` 或浏览器/Postman 查看即可。

**Q6：`/batch` 最多多少条？**
默认 50（`--max-batch`），每条耗时约 0.2–0.6s；建议单批 ≤20 条，超时风险低。

**Q7：score 能当置信度用吗？**
不能。它混合了向量相似度、词法命中与精确匹配加成，跨查询不可比，只用于同一查询内的排序。

**Q8：为什么 `/term` 返回的 score 是 null？**
单条详情不参与排序，无评分；需要评分请用 `/search`。

**Q9：服务没有鉴权，安全吗？**
仅限内网/本机使用；上线必须由网关做鉴权、限流与 HTTPS，并限制 `--host 127.0.0.1` 或内网地址。

## 9. 已知限制

1. **软超时不能强杀线程**：超时后响应立即返回 504，但后台线程仍会跑完（Python 线程无法强制终止）；极端情况下会短暂占用工作线程，故并发上限设为 8。
2. **无鉴权、无 TLS**：见 Q9。
3. **单进程内存常驻**：约 150–200 MB；多进程部署时按进程数倍增。
4. **索引只读**：增量更新需重建索引并重启服务（`build_vectors.py`），API 不做热加载。
5. **source 固定五类**：新增来源需同时改 `search.py`（本次未改）与 API 的 SOURCES 常量。

## 10. 变更记录

- v1.0.0（2026-11-02）：首版。5 个接口、CORS、软超时、统一错误、内建 selftest；配套 function schema 与 3 份提示词/说明。
