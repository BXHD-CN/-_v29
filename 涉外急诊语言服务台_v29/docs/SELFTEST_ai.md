# AI 层自测报告（ai-core / task-7）

> 后续变更：MT_PROVIDER 已改为 `mymemory`（Lead 配置），hybrid 词面阈值由 Lead 调为 0.15；本文件为 task-7 时的运行快照，翻译/多语种最新自测见 `docs/SELFTEST_mt.md`。`docs/selftest_ai.py` 已做兼容，仍可复跑（34/34）。

- 项目：`work/site`（FastAPI + SQLAlchemy 2.0 同步 Session，SQLite；生产 PostgreSQL + pgvector）
- 环境：Windows + `.venv/Scripts/python.exe`（Python 3.12.14）
- 自测时间：2026-11-03（含 Lead 两轮联调反馈：mock MT degraded=true、local 向量 hybrid 拒答）
- 自测方式：**真实运行应用**。方式一 `fastapi.testclient.TestClient`（34 项断言，走完整中间件 / CSRF / 依赖注入）；方式二 `uvicorn` 起真实 HTTP 服务 + `curl`（注册登录 → 翻译 → 问答 → 403）。
- 数据状态：`chunks=120（已向量化 120）`、术语 4154、语料 8308、资讯 42（由 data-pipeline 灌入，本层只读）。
- 结论：**34/34 通过**；mock 模式全链路可用，无 Key 时 provider 均为 mock/local，模型侧故障一律降级为 200，无 500 抛栈；库内问题返回 2–5 条 citation，库外问题稳定拒答。

## 1. 交付文件

| 文件 | 说明 |
| --- | --- |
| `app/services/embedding.py` | local 哈希向量（字符 1–3 gram + 英文词，md5 分桶 1024，sublinear TF，L2 归一化）/ bigmodel `/embeddings`（embedding-3，批量≤32，20s，重试 1 次）；`EmbeddingUnavailable` |
| `app/services/llm.py` | mock / deepseek / generic 兼容 chat；25s；`LLMUnavailable`；可选 `force_provider` 供 MT 复用 |
| `app/services/retrieval.py` | `search_chunks`（SQLite 余弦 + 向量缓存 / PostgreSQL pgvector `<=>`）、`search_terms`、`search_corpus` |
| `app/services/translate_service.py` | 术语最长匹配锁定 + 3 条平行语料 + MT + 译后校验强替 + 4000 字截断；mock 标 degraded=true |
| `app/services/rag.py` | 检索候选池 → hybrid（0.6·cos + 0.4·lex）重排 → 双低拒答 → 强制 [n] → 引用校验重试 1 次 → 摘录兜底 |
| `app/routers/translate.py` | POST /api/translate（10 次/分钟/用户，429）、GET /api/translate/languages |
| `app/routers/qa.py` | POST /api/qa（20 次/分钟/用户，429）、GET /api/qa/examples（6 条，含 2 条库外） |
| `docs/selftest_ai.py` | 方式一自测脚本（可重复执行，结束自动清理测试账号与临时切片） |
| `app/config.py` | **仅新增** `refuse_threshold_local: float = 0.15`（Lead 授权“未加则你加”），未改任何已有字段 |

未改 Lead 定稿的 models/db/security/deps/shield/audit/main、auth/health/terms/corpus/me/admin 路由、tests/、前端；未新增 pip 包。

## 2. 拒答策略（Lead 联调后的最终口径）

local 哈希向量没有语义能力，库内/库外问题的纯余弦分布重叠（实测 top1 都在 0.15–0.30），因此：

```text
lex    = |bigrams(q) ∩ bigrams(chunk.text ∪ chunk.title)| / max(1, |bigrams(q)|)
hybrid = 0.6 * cosine + 0.4 * lex
候选池 = 检索 top_k*3（15 条）→ 按 hybrid 降序 → 取前 5 条作 citations（保留 cosine 分，字段名 score）
拒答（local）：cos_top < 0.15（极低相似兜底）  或  (hybrid_top < 0.22 且 lex_top < 0.12)
拒答（bigmodel 等语义向量）：维持契约的 cos_top < config.refuse_threshold(0.35)
```

Lead 指定的 4 句回归（TestClient 实测，全部通过）：

| # | 问题 | 结果 | 引用数 |
| --- | --- | --- | --- |
| ① | 传染病防治法规定了什么？ | 有引用 | 5（top cos=0.258） |
| ② | 预检分诊是什么？ | 有引用 | 5 |
| ③ | 今天美元汇率多少？ | **refused** | 0 |
| ④ | 明天天气怎么样？ | **refused** | 0 |

另实测（同一批数据）：`/api/qa/examples` 的 4 条库内问题全部有引用、2 条库外问题全部拒答，脚本逐条核对 in_scope 一致（输出见下）。

## 3. 方式一：TestClient 全链路自测（34/34）

命令（在 `work/site` 下）：

```bash
./.venv/Scripts/python.exe docs/selftest_ai.py
```

实际输出（完整）：

```text
[PASS] GET /api/health | {"terms": 4154, "corpus": 8308, "chunks": 120, "news": 42}
[PASS] 无 Key 时 providers 为 mock/local | {"embedding": "local", "llm": "mock", "mt": "mock"}
[PASS] GET /api/translate/languages | {"mt": "mock", "embedding": "local", "llm": "mock"}
[PASS] POST /api/translate 200 | status=200
[PASS] 术语锁定命中中文术语 | locked=['分诊台', '分诊护士', '分诊标准', '预检分诊']
[PASS] 译文含锁定术语译法 | translation=triage：请先在triage desk登记，triage nurse会按triage criteria安排就诊。
[PASS] translate provider=mock 且按联调口径标记 degraded=true | provider=mock degraded=True notes=['演示降级：未配置 MT 服务（术语替换+句对拼接，非真实翻译）']
[PASS] 英文术语锁定（triage desk / triage nurse） | matched=['triage desk', 'triage nurse']
[PASS] en->zh 译文含中文术语 | Please wait at the 分诊台; the 分诊护士 will call you.
[PASS] zh->vi 演示模式返回 200 | [VI 演示] triage
[PASS] 同语种方向 400
[PASS] 不支持语种 400
[PASS] 缺 CSRF 403
[PASS] MT 无 Key 时降级不 500 | status=200 notes=['mt_degraded:deepseek->mock(llm_unavailable)']
[PASS] bigmodel 无 Key 抛 EmbeddingUnavailable | EmbeddingUnavailable
[PASS] POST /api/qa 返回结构合法（库内已有 120 切片） | refused=False reason= mode=excerpt n=5
[PASS] 库内问题不拒答且有 2–5 条 citation | refused=False n=5 top=0.257973
[PASS] 短句库内问题也不拒答 | refused=False n=5
[PASS] 回归：传染病防治法规定了什么？ -> 有引用 | refused=False n=5
[PASS] 回归：预检分诊是什么？ -> 有引用 | refused=False n=5
[PASS] 回归：今天美元汇率多少？ -> 拒答 | refused=True n=0
[PASS] 回归：明天天气怎么样？ -> 拒答 | refused=True n=0
[PASS] hybrid 参数符合约定（0.6/0.4，0.22/0.12） | 0.6/0.4 0.22/0.12
[PASS] 6 条示例问题拒答/回答与 in_scope 一致 | 1:OK 2:OK 3:OK 4:OK 5:OK 6:OK
[PASS] GET /api/qa/examples 6 条含 2 条库外
[PASS] 有切片时 QA 不拒答 | refused=False reason=
[PASS] citations 结构完整（index/chunk_id/snippet<=120） | n=5 top=0.448366
[PASS] 无生成模型走摘录模式且带前缀 | （未配置生成模型）
[1] 预检分诊是急诊接诊的第一环节。分诊护士依据分诊标准，
[PASS] LLM provider 不可用时降级摘录不 500 | status=200 mode=excerpt
[PASS] 引用校验失败重试 1 次后降级摘录 | chat_calls=2 mode=excerpt
[PASS] 引用合法时直接采用 LLM 答案 | chat_calls=1 mode=llm
[PASS] 越界引用 [9] 视为无效 -> 摘录 | mode=excerpt answer=（引用校验未通过，以下为检索片段摘录）
[1] 预检分诊是急
[PASS] translate 限流 10 次/分钟后 429 | statuses=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429]
[PASS] qa 限流 20 次/分钟后 429 | tail=[200, 200, 429]
cleaned test users: [13, 14]

==== 结果：34/34 通过 ====
```

复测提示：脚本会打印 `生成模型不可用，降级为摘录模式：未配置 deepseek 的 API Key`（logging，非报错），属“LLM 不可用降级”用例的预期输出。脚本结束会删除自建测试账号与临时切片，数据库只保留 Lead 的 `demo` 账号。

## 4. 方式二：uvicorn + curl 真实 HTTP

命令（在 `work/site` 下；请求体用 python 以 UTF-8 写文件，避免 shell 参数编码问题）：

```bash
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8077 --log-level warning &
./.venv/Scripts/python.exe -c "
import json,pathlib
p=pathlib.Path('.tmp_ai'); p.mkdir(exist_ok=True)
write=lambda n,o:(p/n).write_text(json.dumps(o,ensure_ascii=False),encoding='utf-8')
write('register.json',{'email':'ai_curl@example.com','username':'ai_curl','password':'CurlTest#2026','display_name':'curl 自测'})
write('login.json',{'account':'ai_curl','password':'CurlTest#2026'})
write('translate.json',{'text':'预检分诊：请先在分诊台登记，分诊护士会按分诊标准安排就诊。','src':'zh','tgt':'en'})
write('qa_in.json',{'question':'预检分诊的英文术语是什么？'})
write('qa_out.json',{'question':'请推荐北京最好吃的火锅店。'})
"
curl -s http://127.0.0.1:8077/api/health
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8077/api/auth/register -H 'Content-Type: application/json' -d @.tmp_ai/register.json
curl -s -c .tmp_ai/cookies.txt -X POST http://127.0.0.1:8077/api/auth/login -H 'Content-Type: application/json' -d @.tmp_ai/login.json
# 从登录响应体取 csrf_token，后续写请求带 -b cookies -H "X-CSRF-Token: <csrf>"
curl -s -b .tmp_ai/cookies.txt -H "X-CSRF-Token: <csrf>" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8077/api/translate -d @.tmp_ai/translate.json
curl -s -b .tmp_ai/cookies.txt -H "X-CSRF-Token: <csrf>" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8077/api/qa -d @.tmp_ai/qa_in.json
curl -s -b .tmp_ai/cookies.txt -H "X-CSRF-Token: <csrf>" -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8077/api/qa -d @.tmp_ai/qa_out.json
kill %1
```

实际输出（节选，均已实跑）：

```text
=== 1) GET /api/health ===
{"status":"ok","app":"涉外急诊语言服务台","counts":{"terms":4154,"corpus":8308,"chunks":120,"news":42},"embedded_chunks":120,"providers":{"embedding":"local","llm":"mock","mt":"mock"}}

=== 2) 注册 + 登录（cookie jar + csrf） ===
register status=201
login ok, csrf_token 长度=32

=== 3) GET /api/translate/languages ===
{"languages":[{"code":"zh","name":"中文"},{"code":"en","name":"英语"},{"code":"vi","name":"越南语"},{"code":"th","name":"泰语"},{"code":"id","name":"印尼语"},{"code":"ms","name":"马来语"}],"providers":{"mt":"mock","embedding":"local","llm":"mock"}}

=== 4) POST /api/translate（术语锁定） ===
translation: triage：请先在triage desk登记，triage nurse会按triage criteria安排就诊。
provider: mock | degraded: True | request_id: 8942c7255fa34cef
locked_terms: [('预检分诊', 'triage', '预检分诊'), ('分诊台', 'triage desk', '分诊台'), ('分诊护士', 'triage nurse', '分诊护士'), ('分诊标准', 'triage criteria', '分诊标准')]
context_pairs: 3 | notes: ['演示降级：未配置 MT 服务（术语替换+句对拼接，非真实翻译）']

=== 5) POST /api/qa（库内/库外问题） ===
qa_in.json -> refused: False | reason:  | mode: excerpt | n_citations: 5 | elapsed_ms: 19
qa_out.json -> refused: True | reason: no_relevant_chunk | mode: None | n_citations: 0 | elapsed_ms: 5

=== 6) 未带 CSRF 的 POST 应为 403 ===
no-csrf status=403

=== 7) GET /api/qa/examples ===
条数: 6
 - 急诊分诊台如何用英语向患者说明候诊顺序？ | in_scope= True
 - “预检分诊”的标准英文术语是什么？ | in_scope= True
 - 灾害现场医疗点如何进行检伤分类？ | in_scope= True
 - 手术知情同意需要向患者说明哪些内容？ | in_scope= True
 - 请推荐北京最好吃的火锅店。 | in_scope= False
 - 今天美元兑人民币汇率是多少？ | in_scope= False
```

## 5. 覆盖矩阵（对照 CONTRACT `4.1）

| 契约要求 | 实现/验证 |
| --- | --- |
| embed_texts 1024 维、L2 归一化、local/bigmodel 双 provider | 方式一 #1–#3、#15；local 确定性（同文本两次逐元素相等，norm=1.0），已与 data-pipeline 灌库向量一致性校验（cosine(stored, mine)=1.0） |
| bigmodel 批量≤32、20s、重试 1 次、`EmbeddingUnavailable` | 代码；#15 验证无 Key 时抛类型化异常且不联网 |
| embedding_dim() / cosine() | 已提供并在检索中使用 |
| llm chat mock/deepseek/generic、25s、`LLMUnavailable` | 代码；#29–#32（伪造 chat 验证降级、引用重试、生成） |
| search_chunks SQLite 余弦 + PG pgvector `<=>` | SQLite 路径 #15–#27；PG 分支按 `database_url` 前缀切换（本机 SQLite，PG 分支未实跑） |
| search_terms 中/英命中 + 最长匹配 | #5–#8（中文 4 术语、英文 triage desk/nurse） |
| search_corpus 取 3 条平行语料 | #7 context_pairs=3 |
| translate 返回 translation/provider/degraded/locked_terms/context_pairs/notes | #4、#7（字段稳定，`matched` 供前端高亮） |
| 译后校验强替 + `term_fixed:` notes | 代码路径（mock 已替换时不触发；tgt=zh 反向/vi 演示方向可触发） |
| 5 语 + 中文，不支持方向 400 | #10–#12 |
| rag top_k=5、拒答、[n] 校验重试、摘录兜底 | #15–#27、#28–#32 |
| translate 10/min、qa 20/min → 429 | #33–#34 |
| 不 500、不抛栈 | #14（MT 无 Key）、#15、#29 全部 200 降级 |

## 6. 与契约的偏差 / 需要 Lead 决策

1. **mock MT 的 degraded**：CONTRACT `4.1 原文“mock…标 degraded=false”，按 Lead 联调反馈改为 `degraded=true` + notes“演示降级：未配置 MT 服务（术语替换+句对拼接，非真实翻译）”。建议 Lead 同步更新 CONTRACT 措辞。
2. **local 向量拒答改用 hybrid**：Lead 指定公式（0.6·cos + 0.4·lex，双低才拒），替代契约的纯余弦阈值；仅对 `EMBEDDING_PROVIDER=local` 生效，bigmodel 仍用 `refuse_threshold=0.35`。已在 `config.py` 新增 `refuse_threshold_local=0.15` 作兜底。**这是对 CONTRACT `4.1 拒答条件的明确扩展，请 Lead 知悉并在 CONTRACT 里补一句。**
3. **local 向量特征**：本卡派单口径为“字符 1–3 gram + 英文词”，CONTRACT 写作“2–3 gram”，实现按派单口径（已提醒 data-pipeline 用本实现重跑 `--force`）。
4. **numpy 未安装**：`.venv` pip list 无 numpy（与契约前提不符）。`retrieval.py` 采用“有 numpy 矩阵余弦、无 numpy 纯 Python”兜底，未安装新包；装 numpy 后自动走矩阵路径。
5. **新增/附加字段（均为增量）**：`/api/translate` 增 `src`/`tgt`；`/api/qa` 增 `mode`（`llm`/`excerpt`）；citations 增 `hybrid`（排序分，`score` 仍是 cosine）；`llm.chat` 增可选 `force_provider`。
6. **限流为进程内内存态**：多 worker 各自计数、重启清零（契约要求“简单内存限流”，生产由 Nginx limit_req 兜底）。
7. **PG/pgvector 分支未实跑**：本机无 PostgreSQL，按 `database_url` 前缀实现，留待生产验证。
8. **残余风险**：个别库外中文问题若与切片存在偶然 bigram 重合（如“2026 年世界杯的冠军是哪支球队？”lex≈0.19）仍可能越过 hybrid 门槛；根治需换语义向量（bigmodel embedding-3）或再加领域术语锚点。建议生产用 bigmodel，本地演示用现口径。
