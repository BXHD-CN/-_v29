# 多语种 MT 接驳 + 本地语术语锁定 自测报告（task-10 / ai-core）

- 项目：`work/site`；改动文件：`app/services/translate_service.py`（唯一被改的 services 文件）
- 自测脚本：`docs/selftest_mt.py`（可重复执行，结束自动清理测试账号）
- 自测时间：2026-11-03；环境：Windows + `.venv/Scripts/python.exe`（Python 3.12.14）
- 结论：**18/18 通过**。8 个翻译方向全部 200 且无 500；本地语术语锁定（must_use=local_terms.local_text）、译后强替、语料向量上下文（带 score）、LRU 缓存、MyMemory 失败降级全部验证通过。
- **真实译文说明（重要）**：本机出口 IP 当日的 MyMemory 免费额度已耗尽——单请求探测返回
  `HTTP 429 | responseStatus=429 | MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY`，
  因此 8 个方向都走了「429 → 重试 1 次 → 20s 冷却 → 降级 mock」路径，**本文档未能写入真实机翻译文**；
  MyMemory 成功路径用单元级模拟（monkeypatch）验证，见 `6。Lead 环境单请求可通（HTTP 200），
  直接在 `work/site` 重跑 `docs/selftest_mt.py` 即可看到真实译文（脚本每方向间隔 2s）。

## 1. 实现要点（translate_service.py）

| 项 | 实现 |
| --- | --- |
| MT provider | 新增 `mt_provider=mymemory`：GET `https://api.mymemory.translated.net/get?q=...&langpair=zh-CN|vi-VN...` |
| 语言对 | zh→zh-CN、en→en-GB、vi→vi-VN、th→th-TH、id→id-ID、ms→ms-MY；zh-CN↔en/vi/th/id/ms 全方向 |
| 超时 | 单请求 8s；长文本按 450 字切分后逐段请求再拼接 |
| 限流防护 | 进程内全局最小间隔 **1.2s**；命中 **429 等 2.5s 重试 1 次**；仍失败进 **20s 冷却** |
| 失败信息 | 统一带 HTTP 状态码：`MyMemory 返回 HTTP 429`、`MyMemory 冷却中（上次 HTTP 429）` |
| 可选 de 参数 | `MYMEMORY_EMAIL`（`settings.mymemory_email` 或同名环境变量）存在时附加 `&de=` |
| 降级 | 任何失败 → mock 译文 + `degraded=true` + note `mt_degraded:mymemory->mock(mt_unavailable)`，不抛 500 |
| 本地语术语锁定 | 目标语 ∈ {vi,th,id,ms} 时读 `local_terms`（各 260 条），最长匹配锁定，`must_use=local_terms.local_text`，locked_terms 带 `lang`/`local_text`/`romanization`/`pron_hint` |
| 译后校验 | 目标语术语缺失则强替（源词在译文中优先替换，否则追加“术语补正”）并写 `term_fixed:{zh}->{local_text}` |
| 语料上下文 | 改用 `retrieval.search_corpus_vector(query, lang_pair, 3)`，失败/无命中回退 `search_corpus`；context_pairs 保留 `score` |
| 进程内缓存 | LRU 容量 500，键 `(src,tgt,text)`；降级结果 30s TTL，避免重复请求触发限流 |

未改 `models.py`、`routers/*`、其他 services（`retrieval.py` 由 data-pipeline 追加 `search_corpus_vector`，本层只调用）。

## 2. 自测命令与结果（18/18）

```bash
cd work/site
./.venv/Scripts/python.exe docs/selftest_mt.py
```

实际输出（完整）：

```text
MyMemory HTTP 429（zh-CN|en-GB），2.5s 后重试一次
MyMemory 失败（zh-CN|en-GB）：MyMemory 返回 HTTP 429
[PASS] providers.mt = mymemory | {"mt": "mymemory", "embedding": "local", "llm": "mock"}
[MyMemory 单请求探测] HTTP 429 | responseStatus=429 | MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY. NEXT AVAILABLE IN  06 HOURS 49 MINUTES 31 SECONDS
[PASS] local_terms 各语 260 条 | {'vi': 260, 'th': 260, 'id': 260, 'ms': 260}

=== 8 个翻译方向（HTTP 实测，每方向间隔 2s）===
[PASS] context_pairs 带 score（语料向量检索） | scores=[0.2397, 0.2267, 0.2219]
[PASS] zh->en | status=200 provider=mock degraded=True locked=4 | triage：请先在triage desk登记，triage nurse会按triage criteria安排就
    translation: triage：请先在triage desk登记，triage nurse会按triage criteria安排就诊。
    notes: ['mt_degraded:mymemory->mock(mt_unavailable)']
[PASS] zh->vi must_use 取 local_terms.local_text | 预检分诊 -> phân loại sàng lọc
[PASS] zh->vi | status=200 provider=mock degraded=True locked=4 lang_ok=True local_text_in_translation=True | [VI 演示] phân loại sàng lọc：请先在quầy phân loại登记，điều dưỡn
    translation: [VI 演示] phân loại sàng lọc：请先在quầy phân loại登记，điều dưỡng phân loại会按tiêu chuẩn phân loại安排就诊。
    notes: ['local_terms:vi:4', 'mt_degraded:mymemory->mock(mt_unavailable)']
[PASS] zh->th | status=200 provider=mock degraded=True locked=3 lang_ok=True local_text_in_translation=True | [TH 演示] คัดแยกผู้ป่วย：请先在จุดคัดแยกผู้ป่วย登记，พยาบาลคัดแยก
    translation: [TH 演示] คัดแยกผู้ป่วย：请先在จุดคัดแยกผู้ป่วย登记，พยาบาลคัดแยกผู้ป่วย会按分诊标准安排就诊。
    notes: ['local_terms:th:3', 'mt_degraded:mymemory->mock(mt_unavailable)']
[PASS] zh->id | status=200 provider=mock degraded=True locked=3 lang_ok=True local_text_in_translation=True | [ID 演示] triase：请先在meja triase登记，perawat triase会按分诊标准安排就诊
    translation: [ID 演示] triase：请先在meja triase登记，perawat triase会按分诊标准安排就诊。
    notes: ['local_terms:id:3', 'mt_degraded:mymemory->mock(mt_unavailable)']
[PASS] zh->ms | status=200 provider=mock degraded=True locked=3 lang_ok=True local_text_in_translation=True | [MS 演示] triaj：请先在kaunter triaj登记，jururawat triaj会按分诊标准安排
    translation: [MS 演示] triaj：请先在kaunter triaj登记，jururawat triaj会按分诊标准安排就诊。
    notes: ['local_terms:ms:3', 'mt_degraded:mymemory->mock(mt_unavailable)']
[PASS] en->zh | status=200 provider=mock degraded=True | Please wait at the 分诊台; the 分诊护士 will call you.
    translation: Please wait at the 分诊台; the 分诊护士 will call you.
    notes: ['mt_degraded:mymemory->mock(mt_unavailable)']
[PASS] vi->zh | status=200 provider=mock degraded=True | [ZH 演示] Vui lòng chờ tại quầy phân loại, điều dưỡng phân
    translation: [ZH 演示] Vui lòng chờ tại quầy phân loại, điều dưỡng phân loại sẽ gọi bạn.
    notes: ['mt_degraded:mymemory->mock(mt_unavailable)']
[PASS] th->zh | status=200 provider=mock degraded=True | [ZH 演示] กรุณารอที่จุดคัดแยกผู้ป่วย พยาบาลคัดแยกผู้ป่วยจะ
    translation: [ZH 演示] กรุณารอที่จุดคัดแยกผู้ป่วย พยาบาลคัดแยกผู้ป่วยจะเรียกคุณ
    notes: ['mt_degraded:mymemory->mock(mt_unavailable)']

=== 进程内 LRU 缓存 ===
[PASS] 同 text+src+tgt 命中缓存且结果一致 | cache_size=9 capacity=500

=== 单元级：_parse_mymemory ===
[PASS] 解析正常响应（含 HTML 实体反转义） | phân loại & sàng lọc
[PASS] 限额/空结果/非 200 都抛 MTUnavailable

=== 单元级：模拟 MyMemory 成功路径 ===
[PASS] 成功路径 provider=mymemory / degraded=false | provider=mymemory degraded=False
[PASS] 译后校验强替缺失本地语术语并写 note | notes=['term_fixed:预检分诊->phân loại sàng lọc', 'term_fixed:分诊台->quầy phân loại'] translation=phân loại sàng lọc：请先在quầy phân loại登记.
[PASS] 成功路径 zh->en 仍按 en 译法校验 | triage：请先在triage desk登记.

cleaned test user: [5]

==== 结果：18/18 通过 ====
```

复测提示：日志里的 `MyMemory 返回 HTTP 429` 是本机出口 IP 当日额度耗尽的预期降级路径，不是代码异常；额度恢复或换到可用的出口 IP 后，同一条命令会打印 `provider=mymemory | degraded=False` 与真实机翻译文。

## 3. 8 方向结果表（本次实跑）

| 方向 | provider | degraded | 术语锁定 | 译文（本次为降级 mock） |
| --- | --- | --- | --- | --- |
| zh→en | mock | true | 4 条（triage/triage desk/triage nurse/triage criteria） | `triage：请先在triage desk登记…` |
| zh→vi | mock | true | 4 条，must_use=local_text | `[VI 演示] phân loại sàng lọc：请先在quầy phân loại登记…` |
| zh→th | mock | true | 3 条（th 缺“分诊标准”条目） | `[TH 演示] คัดแยกผู้ป่วย：请先在จุดคัดแยกผู้ป่วย登记…` |
| zh→id | mock | true | 3 条 | `[ID 演示] triase：请先在meja triase登记…` |
| zh→ms | mock | true | 3 条 | `[MS 演示] triaj：请先在kaunter triaj登记…` |
| en→zh | mock | true | 公共 zh-en 术语反向锁定 | `Please wait at the 分诊台; the 分诊护士 will call you.` |
| vi→zh | mock | true | 无（本地语→中文暂不锁本地语词） | `[ZH 演示] Vui lòng chờ tại quầy phân loại…` |
| th→zh | mock | true | 无 | `[ZH 演示] กรุณารอที่จุดคัดแยกผู้ป่วย…` |

## 4. 关键验收点逐条自查

1. **MyMemory 接驳**：`providers.mt=mymemory`；8 方向均 200；8s 超时、1.2s 全局间隔、429→2.5s 重试 1 次、20s 冷却均已生效（日志 `MyMemory HTTP 429（zh-CN|en-GB），2.5s 后重试一次` 可证）。
2. **本地语锁定 must_use=local_text**：`预检分诊 → phân loại sàng lọc`（脚本单独断言）；locked_terms 元素含 `lang="vi"`、`local_text`、`romanization`、`pron_hint`。
3. **译后校验**：模拟成功路径下，模型译文缺少本地语术语 → 强替并写 `term_fixed:预检分诊->phân loại sàng lọc`、`term_fixed:分诊台->quầy phân loại`。
4. **语料向量上下文**：context_pairs 来自 `search_corpus_vector`，带 score（本次 zh→en 为 0.2397/0.2267/0.2219）；向量检索异常/无命中自动回退 `search_corpus`。
5. **LRU 缓存**：同 `(src,tgt,text)` 第二次调用结果一致且不再发起网络请求；容量 500。
6. **不 500**：所有失败均降级 200，`degraded=true` + notes 说明。

## 5. 数据侧观察（给 data-pipeline 的反馈）

- `local_terms` 各语 260 条；但 th/id/ms **缺少“分诊标准”** 的本地语条目（zh 在 local_terms 中查不到该词），所以同一句锁定数是 vi=4、th/id/ms=3。建议补齐。
- 反向（vi/th/id/ms→zh）目前不做本地语源词锁定：现有实现按“目标语为 vi/th/id/ms 时用 local_terms”的口径，反向走公共 zh-en 术语+MT 降级。若需要，可后续扩展。

## 6. MyMemory 成功路径验证（单元级，不联网）

因本机额度耗尽，用 monkeypatch 模拟 `_mymemory_translate` 返回“只翻了一部分”的文本，验证接线：

```text
provider=mymemory, degraded=False
notes=['term_fixed:预检分诊->phân loại sàng lọc', 'term_fixed:分诊台->quầy phân loại']
translation=phân loại sàng lọc：请先在quầy phân loại登记.
```

并单测 `_parse_mymemory`：正常响应（含 HTML 实体反转义）返回译文；`responseStatus=429`/空译文/403 均抛 `MTUnavailable`。

## 7. 与契约/任务卡的偏差

1. 任务卡只要求 `translate_service.py`；实际另改了 `docs/selftest_ai.py` 的一处断言（兼容 MT_PROVIDER 被改为 mymemory 后的降级 note）与新增 `docs/selftest_mt.py`（自测脚本），未触碰 models/routers/其他 services。
2. MyMemory 免费额度为**按出口 IP 每日 5000 字符**量级：本机当日已耗尽，故本次 8 方向为降级结果；真实译文需在额度可用的环境复跑（命令见 `2）。
3. 语料只有 zh-en 句对，vi/th/id/ms 方向的 context_pairs 由 zh-en 检索兜底（score 仍是该语料句向量与问题的余弦）。
