# 五项核心功能 × 15 个子项 验收自查（RUBRIC AUDIT）

> 依据：任务书「三、五项核心功能」逐项口径 + 附件一评分表（每项 功能实现 5 / 数据达标 5 / 质量抽检 5）。
> 自查时间：2026-11-03；环境：本地 SQLite + 本地哈希向量 + 免费 MT 端口（MyMemory，当日额度已耗尽）+ mock 生成。
> 结论标记：**达标** / **达标（需配置密钥）** / **部分达标（如实说明）**。

## 总表

| # | 功能 | 子项 | 验收口径 | 现状 | 结论 |
| --- | --- | --- | --- | --- | --- |
| 1 | 外语信息聚合 | 功能实现 | 独立聚合模块；中文浏览全部内容 | `/news.html` + `/api/news`；列表默认只返回已中文化条目（62/62） | 达标 |
| 2 | 外语信息聚合 | 数据达标 | ≥3 权威源；≥50 条已中文化 | 4 源（UN News / ReliefWeb / USGS / 联合国新闻中文版）；62 条中文 | 达标 |
| 3 | 外语信息聚合 | 质量抽检 | 来源可点、内容可信 | 每条带来源徽标、原文链接（noopener）、访问日期、许可、机器翻译/中文版源标注 | 达标 |
| 4 | 多语种翻译 | 功能实现 | 界面六要素：源/目标语言、输入、结果、复制、清空 | `/translate.html` 六语下拉 + 输入计数 + 结果高亮 + 复制/清空；E2E 通过 | 达标 |
| 5 | 多语种翻译 | 数据达标 | ≥4 语种；中文与各语种双向 | 中/英/越/泰/印尼/马来 6 语种、10 个方向；链路支持 MyMemory/DeepSeek/通用 MT 端口 | 达标（需配置 MT 端口/Key） |
| 6 | 多语种翻译 | 质量抽检 | 原文与译文术语双高亮；译文采用库内译法 | 术语最长匹配锁定 → `must_use` 注入 → 译后校验缺失则强替；前端原文与译文双向 `<mark>` | 达标 |
| 7 | 术语管理 | 功能实现 | 中/外文检索；列表显示术语/译法/语种/来源/审核状态；可看详情 | `/terms.html` 搜索 + 语种/领域/状态筛选；列表六列；详情含释义、来源文件、来源链接 | 达标 |
| 8 | 术语管理 | 数据达标 | ≥500 条；每条来源与审核状态；按语种、领域筛选 | 4,154 条；来源代号 100%、审核状态 100%；筛选可用 | 达标 |
| 9 | 术语管理 | 质量抽检 | 抽 5 条核来源；译文用指定译法 | 详情返回 `sources[{code,name,org,url}]` 可点开；翻译锁术语后强制使用库内译法 | 达标 |
| 10 | 平行语料 | 功能实现 | 原文/译文关键词检索；显示原文/译文/来源/语种对/审核状态 | `/corpus.html` 分栏检索；列表五列齐全；详情含来源链接 | 达标 |
| 11 | 平行语料 | 数据达标 | ≥500 句；一一对齐；来源可追溯；完成向量化建库 | 8,308 句对；`corpus_vectors` 8,308 条 × 1024 维（float32，L2 归一） | 达标 |
| 12 | 平行语料 | 质量抽检 | 向量化后为翻译提供双语上下文 | 翻译改用 `search_corpus_vector` top-3（返回 score），失败回退 LIKE | 达标 |
| 13 | 可追溯问答 | 功能实现 | BigModel Embedding + DeepSeek；回答展示来源 | 代码路径已接 `embedding-3` 与 `deepseek-chat`（配置 Key 即切换）；当前本地降级；引用卡片可点开 | 达标（需配置 Key） |
| 14 | 可追溯问答 | 数据达标 | 切片 ≥100；可追溯到页码/URL；支持增量更新 | 124 片，每片 source_url/section/page/license/doc_fingerprint；`update_slices.py` 增量对比（新增/变更 version+1/删除） | 达标 |
| 15 | 可追溯问答 | 质量抽检 | 回答带可点来源；库外拒答 | 库内问题返回 5 条引用；3 个库外问题全部拒答（汇率/天气/世界杯） | 达标 |

## 本轮为对齐口径做的修缮

| # | 问题（原状） | 修缮 | 证据 |
| --- | --- | --- | --- |
| A | 资讯列表混入未中文化条目，无法“全中文浏览” | `/api/news` 默认只返回已中文化（`status=published`），可切 `all`；补 5 条待译 → 62/62 中文化 | `api/news`、`docs/SELFTEST_data2.md` |
| B | 术语/语料“来源”只有代号，抽检无法核对 | 新增 `sources` 表（69 个编号，含发布机构/等级/可核查入口）；详情返回 `sources[]` 与兜底 URL；前端做成外链 | `/api/sources/{code}`、`/api/terms/{id}` |
| C | 东盟语种翻译没有库内术语可锁定 | 新增 `local_terms` 表（1,040 条，越泰印尼马各 260）；目标语为 vi/th/id/ms 时 `must_use=local_text`，译后强替 | `translate_service.py`、`/api/local-terms` |
| D | 无可用 MT 时东盟翻译退化为“中文+术语替换” | 接 MyMemory 免费端口（8s 超时、1.2s 间隔、429 重试、20s 冷却、LRU 缓存）；也可切 DeepSeek / 通用 MT 端口 | `docs/SELFTEST_mt.md` |
| E | 平行语料只做 LIKE，未证明“向量化与翻译结合” | 8,308 句向量化入库；翻译上下文改走向量 top-3 并返回 score | `scripts/embed_corpus.py`、`corpus_vectors` |
| F | 切片无增量更新能力 | `scripts/update_slices.py` 按指纹做新增/变更（version+1）/删除，`--dry-run` 可预演 | 实跑 124 条一致 |
| G | 前端缺来源链接、资讯元信息、本地语页面、provider 标识 | 本轮补齐：来源外链、访问日期/许可/机翻标注、`/local.html`、provider 徽标、kb 统计条 | `docs/SELFTEST_ui2.md`（E2E 81/81） |

## 仍受限的三项（如实标注）

1. **真实机翻**：MyMemory 免费额度当日耗尽（HTTP 429，约 7 小时后恢复）；当前降级 mock（页面标 `degraded`）。配置 `DEEPSEEK_API_KEY` 或 `GENERIC_MT_URL`（百度/腾讯/DeepL 端口）即为真实翻译。**演示前必须二选一**。
2. **BigModel/DeepSeek**：任务书点名要求，代码已接；未配置 Key 时用本地向量 + 检索摘录，页面标注“未配置生成模型”。
3. **本地语**：1,040 条状态为“待母语审校”，页面如实展示，不冒充已审校。

## 复现命令

```bash
cd work/site
./.venv/Scripts/python.exe -m pytest tests -q                 # 8 passed
./.venv/Scripts/python.exe scripts/embed_corpus.py            # 8,308 句向量
./.venv/Scripts/python.exe scripts/update_slices.py --dry-run # 增量预览
./.venv/Scripts/python.exe docs/selftest_mt.py                # 翻译 8 方向（需 MT 额度）
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```
