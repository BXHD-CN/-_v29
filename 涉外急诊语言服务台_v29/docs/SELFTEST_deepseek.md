# DeepSeek 真实翻译 / 生成 联调记录

日期：2026-11-03　环境：本地 uvicorn（127.0.0.1:8000）　配置：`MT_PROVIDER=deepseek`、`LLM_PROVIDER=deepseek`、`EMBEDDING_PROVIDER=local`

## 1. 服务状态

```json
GET /api/health → providers: {"embedding": "local", "llm": "deepseek", "mt": "deepseek"}
```

## 2. 翻译实测（真实调用 DeepSeek）

| 方向 | 原文 | 译文 | provider / degraded | 耗时 |
| --- | --- | --- | --- | --- |
| zh→en | 患者主诉活动后呼吸困难加重三天，既往有高血压病史。 | The patient's chief complaint is worsening dyspnea after activity for three days… | deepseek / false | 1.3 s |
| zh→vi | 预检分诊在哪里？ | Phân loại sàng lọc ở đâu? | deepseek / false | <1 s |
| zh→th | 请出示您的身份证件。 | กรุณาแสดงบัตรประชาชนของท่าน | deepseek / false | 0.9 s |
| zh→id | 患者对青霉素过敏。 | Pasien alergi terhadap penisilin. | deepseek / false | 0.8 s |
| en→zh | The patient has chest pain and shortness of breath. | 患者有胸痛和气短。 | deepseek / false | 1.0 s |

术语锁定命中示例：chief complaint（主诉）、dyspnea（呼吸困难）、blood pressure（血压）；zm→vi 时命中本地语对照（如 预检分诊 → phân loại sàng lọc）。

## 3. RAG 问答实测

```json
POST /api/qa {"question":"预检分诊是什么？"}
→ refused=false, citations=5
→ answer: 预检分诊（triage）是患者到院后由护士进行的一项工作 [1]。资料片段中该词条内容不完整，无法给出更完整的定义。
```

- 回答带 [1] 引用，页面可点开来源（source_url/section）；
- 模型按“资料不足就说明”的系统提示作答，不编造；
- 库外问题（汇率/天气/世界杯）仍走拒答路径。

## 4. 结论

- 任务书要求的“真实机器翻译 + 生成式问答”已在线可用；
- 仍建议：若需完全符合“BigModel Embedding”口径，补智谱 Key 后重嵌 124 个切片与 8,308 条语料（脚本已就绪：`embed_chunks.py --force`、`embed_corpus.py --force`）。

## 5. 复现

```powershell
cd "D:\Deepseek Harness Workplace\work\site"
.\start_demo.ps1 -DeepSeekKey "sk-***"    # Key 只进进程环境变量，不落盘
```
