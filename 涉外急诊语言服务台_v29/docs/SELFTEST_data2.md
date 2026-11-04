# 数据管线自测记录 2（data-pipeline / task-11）

- 日期：2026-11-03（Asia/Shanghai）· 环境：Windows + `work/site/.venv`（Python 3.12）+ SQLite `data/app.db`
- 约束遵守：**未改 `app/services/translate_service.py`**；未新增 pip 包；只动机器数据管线相关文件。
- 交付：新增 `scripts/embed_corpus.py`、`scripts/update_slices.py`；`app/services/retrieval.py` 追加
  `search_corpus_vector`；`app/services/crawler.py` 补 MyMemory `de` 参数；复用 `scripts/translate_news.py`。

## 1. 语料向量化（scripts/embed_corpus.py）

命令：

```bash
./.venv/Scripts/python.exe scripts/embed_corpus.py
```

首次运行（8308 条，260 批 × 32）：

```text
[corpus] public_corpus=8308 条，corpus_vectors 已有 0 条，dim=1024，force=False
[progress] 已处理 320 条（新增 320 / 更新 0 / 跳过 0 / 失败 0）
…
[progress] 已处理 8308 条（新增 8308 / 更新 0 / 跳过 0 / 失败 0）
[corpus] 新增 8308，更新 0，已有跳过 0，失败 0；corpus_vectors 现有 8308 条（期望 8308）
```

存储格式与校验（sqlite 直查）：

```text
corpus_vectors: 8308 条
BLOB 长度：只出现 4096 字节（1024 × float32 小端）
抽样范数：1.0（已 L2 归一化）；dim=1024
孤儿行（corpus_id 不存在的向量）：0
```

幂等与参数：

```text
再跑一次（无 --force）：新增 0，更新 0，已有跳过 8308，失败 0
--force --limit 2：新增 0，更新 2，已有跳过 0（按 public_corpus.id 顺序处理前 2 条重新向量化）
```

实现要点：向量化文本 = `f"{zh} {en}"`（中英同时入向量，中/英查询都能命中）；
按 `corpus_id`（= public_corpus.id，外键）upsert；`struct.pack("<1024f")` 写 float32 BLOB；
单批失败计数不中断。

## 2. 语料向量检索（retrieval.search_corpus_vector）

新增函数（只在 `retrieval.py` **末尾追加**，ai-core 已确认其 task-10 不改该文件；
原有 `search_chunks / search_terms / search_corpus` 未动、签名不变）：

```python
search_corpus_vector(query: str, lang_pair: str = "", limit: int = 5) -> list[dict]
# 返回 [{id, corpus_id, zh, en, lang_pair, source_code, source_url, score}]，score 降序
```

实测（SQLite，numpy 矩阵余弦）：

| 查询 | 耗时 | Top1 |
| --- | --- | --- |
| 患者胸痛怎么分诊？ | 84ms | 0.1913 · T-0026-01「分诊决策需在患者到院五分钟内作出。」 |
| informed consent for surgery | 83ms | 0.6995 · T-1818-01「手术知情同意需由患者本人签署。」 |
| 传染病预防控制措施 | 82ms | 0.1996 · T-3581-02「疾病预防控制机构马上到，先留好资料。」 |

边界：`lang_pair='zh-en'` 过滤生效；空查询返回 `[]`；query 先走 `embed_texts`（与 chunks 同一 provider）。

无 numpy 兜底（把模块内 `_np` 置 None 模拟）：

```text
search_corpus_vector('informed consent for surgery') → T-1818-01 0.699526、T-1818-02 0.652919
（与 numpy 路径得分完全一致，struct 解 BLOB + 纯 Python 余弦）
```

PostgreSQL：保留 `_pg_corpus_search` 接口（`corpus_vectors.embedding <=> CAST(:q AS vector)`，
生产迁移加 `embedding vector(1024)` 列 + HNSW 即可启用；未迁移时告警并返回 `[]`，不阻断调用方）。

环境事实：本机 `.venv` 实际已安装 numpy 2.5.4（ai-core 早前记录为“无 numpy”已过时）；
代码仍保留“有 numpy 走矩阵 / 无 numpy 走 struct 纯 Python”两条路径，两种都实测通过。

## 3. 切片增量更新（scripts/update_slices.py）

规则：按 `(doc_id, chunk_no)` 对齐、用 `doc_fingerprint` 判断是否变更：

- 新增（库内无该键）→ 插入，`version=1`；
- 变更（同键 fingerprint 不同）→ 原地更新字段并 `version+1`（写新版本，避免检索命中重复旧片）；
- 删除（库内有、jsonl 无）→ 删除；
- `--dry-run` 只打印 diff；`--file` 可指定 jsonl。变更后提示重跑 `embed_chunks.py` 补向量。

实跑 1（当前库与 data/chunks.jsonl 一致）：

```text
$ ./.venv/Scripts/python.exe scripts/update_slices.py --dry-run
[diff] jsonl=124 条，DB=124 条；新增 0，变更 0，删除 0，未变 124
[dry-run] 未写库
```

实跑 2（构造 123 条变体：删 2 条、改 1 条正文、加 1 条新 doc，验证三条路径）：

```text
[diff] jsonl=123 条，DB=124 条；新增 1，变更 1，删除 2，未变 121
  新增（1）: + TEST-DOC#0  fingerprint cf2ee599  version 1
  变更（1）: + RCL-F01#0  fingerprint e06c3f42 → 572ce64c  version 4 → 5
  删除（2）: - PT-D04#3 …; - PT-D04#4 …
[apply] 新增 1，变更 1，删除 2；chunks 表现有 123 条（已向量化 122 条）
```

随后 `embed_chunks.py --in <变体>` 只补 1 条新向量；再用正式 jsonl 恢复：

```text
[diff] jsonl=124 条，DB=123 条；新增 2，变更 1，删除 1，未变 121
[apply] 新增 2，变更 1，删除 1；chunks 表现有 124 条（已向量化 122 条）
$ embed_chunks.py → 向量成功 2，失败 0；chunks 表 124 行，已向量化 124 行
$ update_slices.py --dry-run → 新增 0，变更 0，删除 0，未变 124（已恢复一致）
```

最终库内：`chunks=124`、`embedded=124`、无 TEST-DOC 残留（变体临时文件已删除）。

## 4. 补译剩余资讯（scripts/translate_news.py --limit 10）

第 1 次运行：MyMemory 匿名额度按 IP 计、当天已用尽 → 5 条全部 429：

```text
[fail] 38 HTTPStatusError: Client error '429 Too Many Requests' …
…（其余 4 条同样 429）…
[done] published=0 failed=5
（响应体：MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY…）
```

修复：MyMemory 官方支持 `de=<email>` 参数按邮箱计额度，已在
`crawler._translate_with_mymemory` 的请求参数中加入 `de=_MYMEMORY_DE`
（默认项目占位邮箱，可用环境变量 `MYMEMORY_DE` 覆盖）。重跑：

```text
$ ./.venv/Scripts/python.exe scripts/translate_news.py --limit 10 --with-summary
[mode] MyMemory（免费公共端口，逐条限速）
[start] pending=5
[ok] 38 加强南苏丹的粮食系统
[ok] 39 AMDA紧急救援# 2 ：尼泊尔山洪暴发（ 2026年11月2日）
[ok] 40 刚果民主共和国：刚果民主共和国北基伍省：有害的限制性措施阻碍了对性暴力幸存者的护理
[ok] 41 QRCS启动孟加拉国难民庇护项目[EN/AR]
[ok] 42 埃及：截至2026年10月29日来自苏丹的新移民
[done] published=5 failed=0
```

结果统计（目标 `news_zh ≥ 60` 达成）：

```text
news_items：62 条；published 62 / pending 0
title_zh 非空：57 → 62  （≥60 ✓）
summary_zh 非空：20 → 25（新增的 5 条标题+摘要都已中文化）
```

## 5. 回归自查

```text
GET /api/health → counts={terms:4154, corpus:8308, chunks:124, news:62}, embedded_chunks=124
GET /api/news?page_size=3 → total=62，列表含中文标题、status=published
corpus_vectors=8308（全部 4096 字节 BLOB）、chunks=124（全部有向量）
compileall：scripts/embed_corpus.py、scripts/update_slices.py、scripts/translate_news.py、
           app/services/retrieval.py、app/services/crawler.py 全部通过
```

## 6. 复现命令

```bash
cd work/site
./.venv/Scripts/python.exe scripts/embed_corpus.py            # 8308 句对 → corpus_vectors
./.venv/Scripts/python.exe scripts/embed_corpus.py --force    # 全量重算
./.venv/Scripts/python.exe scripts/update_slices.py --dry-run # 查看切片 diff
./.venv/Scripts/python.exe scripts/update_slices.py           # 应用 diff
./.venv/Scripts/python.exe scripts/translate_news.py --limit 10 --with-summary  # 补译资讯
```

## 7. 说明 / 遗留

1. `update_slices` 的“变更”采用**原地更新 + version+1**（保留唯一行，避免向量检索命中同一片的新旧两份）；
   如需保留历史版本需单独建版本表（超出本任务范围）。
2. 切片新增/变更后要重跑 `scripts/embed_chunks.py`，否则新片无向量（脚本已打印提示）。
3. MyMemory `de` 参数用的是演示占位邮箱；正式部署请用 `MYMEMORY_DE` 环境变量配置真实联系邮箱，
   或切 `DEEPSEEK_API_KEY` / 自建 MT（`MT_PROVIDER=generic`）。
4. PostgreSQL 的语料向量检索目前是**接口占位**（需迁移 `corpus_vectors.embedding vector(1024)` + HNSW），
   本机 SQLite 路径已完整实现并实测。
