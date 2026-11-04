# 涉外急诊医学术语语料库 · 向量检索与 AI 接入层（V1.3 索引）

把总库 V1.3 的 **14,400 条**内容（术语 4,154、术语语料 8,308、东盟文化表达 738、东盟本地语 1,040、真实语料 160）统一向量化，提供检索、译法对比、机器翻译术语约束与问答机器人检索底座。

## 一、索引是怎么做的

| 项 | 说明 |
|---|---|
| 文档粒度 | 一条术语 / 一条语料 / 一条文化表达 / 一条本地语 / 一条真实语料各算一个文档 |
| 文本拼接 | 术语=中文+英文+释义+子领域+场景+备注；语料=中英句对；文化=原词+推荐译法+直译风险+提示+例句；本地语=中英+本地语写法+罗马化+发音提示 |
| 切词 | 中文 2–3 字 n-gram（单字单独处理）、英文词与双词、泰文 2–3 字 n-gram |
| 向量化 | 特征哈希（md5 到 1024 维）+ 次线性 TF-IDF + L2 归一化，存 float16 |
| 检索打分 | 0.45 × 向量余弦 + 0.55 × 词面重合（仅对向量粗排前 300 条计算），再叠加"查询命中术语/英文"加成 |
| 口语扩展 | index/aliases.json 收录 60+ 组患者口语映射（"喘不上气"→呼吸困难、"心跳停了"→心搏骤停），检索前自动扩展；精确术语查询不扩展 |
| 规模 | 14,400 × 1,024，索引 28.1 MB，单次查询约 20–60 ms（冷启动加载约 0.5 s） |

**为什么没用预训练模型**：本机没有 GPU、没有 sentence-transformers，也下载不了模型。所以先用无需训练的词面向量把链路跑通；接口按"可替换"设计（见第六节），换成 BGE-m3 等模型只需重算 vectors.npy，检索与接入代码不动。

## 二、实测指标（两套评测，数字均由脚本跑出）

**基线评测（180 条，eval/baseline_metrics.json）**

| 场景 | Top-1 | Top-5 |
|---|---|---|
| 中文精确术语 | 97.3% | 100% |
| 英文精确术语 | 98.7% | 100% |
| 自然语言问句（含口语别名扩展） | 53.3% | 83.3% |

**独立评测（120 条，另建查询集，eval/independent_report.md）**

| 口径 | Top-1 | Top-5 | 说明 |
|---|---|---|---|
| 全库（14,400 条） | 66.7% | 80.0% | 综合口径 |
| 仅术语表 | 56.7% | 69.2% | 精确中英 100%，本地语弱 |
| 中文/英文精确 | 100% | 100% | 强项 |
| 自然语言问句 | 23.3%（全库 33.3%） | 50.0%（全库 53.3%） | 弱项，依赖问题改写 |
| 跨语言（英文问→中文术语） | 40% | 65% | 中等 |
| 本地语问句 | — | — | 命中 local 表本身（86.7%），未做跨语言语义对齐 |
| 缩写（CPR/ACS/GCS） | 100% | 100% | 已用术语表缩写字段建别名 |

**结论**：已做两轮优化——补全缩写/别名表（缩写 top1 从 14.3% 提到 100%）、词面打分加 token 级 IDF 并做文档长度归一。精确查词已经是生产可用水平；自然语言问句必须配"大模型改写为检索词"再检索（模板见 integration/rag_prompt.md），否则命中率只有三到五成。这一条写在接入要求里，不要跳过。

## 三、文件结构

~~~
work/vector_db/
├── build_vectors.py        从总库 V1.3 重建索引（改数据后跑一次）
├── search.py               SearchIndex：search / compare / get，含 CLI
├── index/
│   ├── vectors.npy         14,400 × 1024 float16
│   ├── idf.npy             每维 IDF
│   ├── meta.jsonl          每行一条：i/source/doc_id/zh/en/domain/scene/country/parent/text
│   ├── index_meta.json     索引元信息（维度、文档数、方法）
│   └── aliases.json        口语/别名扩展表
├── eval/
│   ├── baseline_eval.py    基线评测（精确中英 + 自然语言）
│   ├── baseline_metrics.json
│   └── tune.py             权重与改写实验
└── integration/
    ├── api_server.py       HTTP API（纯标准库，无第三方依赖）
    ├── function_schema.json 大模型 function calling 工具定义
    ├── rag_prompt.md       问答机器人提示词模板
    ├── mt_prompt.md        机器翻译术语约束提示词
    ├── mt_demo/            术语约束翻译演示（30 句真实检索）
    └── README.md           接入说明
~~~

## 四、怎么用

### 1. Python

~~~python
from search import SearchIndex
idx = SearchIndex()
idx.search("预检分诊", k=5, source="term")          # 术语检索
idx.search("病人喘不上气血氧低", k=5)                # 自然语言（自动口语扩展）
idx.search("triage", k=5, source="corpus")          # 例句检索
idx.compare("绿色通道")                              # 五张表的译法对比
~~~

返回每条含 score / source / doc_id / zh / en / domain / scene，可直接回链总库 Excel 的行。

### 2. 命令行

~~~bash
python search.py "预检分诊" --k 5
python search.py "triage" --source term --k 5
python search.py "绿色通道" --compare
python search.py "分诊" --json
~~~

### 3. HTTP 服务（供平台调用）

~~~bash
python integration/api_server.py --port 8848
curl "http://127.0.0.1:8848/search?q=预检分诊&k=5&source=term"
curl "http://127.0.0.1:8848/compare?q=绿色通道"
~~~

## 五、给 AI 与机器翻译用

1. **问答机器人**：先检索（term/corpus/culture 三路），把命中条目作为 context 注入大模型，要求回答必须带 doc_id 与来源；提示词模板见 integration/rag_prompt.md。
2. **机器翻译**：译前用 mt_demo/mt_demo.py 抽取约束术语，走 DeepL Glossary / Google v3 glossaryConfig / 本地模型强制解码注入；译后用 term_check.py 做术语一致性校验。演示与错译对照见 integration/mt_demo/constraint_examples.md。
3. **译法对比**：compare() 一次返回术语表、语料、文化表、本地语、真实语料五个来源的说法，用于审校与一致性核查。

## 六、升级路径（换成神经向量）

接口约定：只要保持 vectors.npy（L2 归一化）+ meta.jsonl 不变，检索层无需改。步骤：
1. 安装 sentence-transformers，选 BGE-m3 / m3e-base 等中文医疗适配模型；
2. 修改 build_vectors.py 的编码函数：对每条 meta.text 编码、归一化、覆盖 vectors.npy；
3. search.py 中 encode() 改为调用同一模型；
4. 重跑 eval/baseline_eval.py，自然语言 top5 预期从 83% 提升到 95% 以上。

## 七、已知局限

1. 词面向量对**同义改写**不敏感，依赖别名表与大模型改写；长句语义不如神经嵌入。
2. 本地语与真实语料目前只是"能被检索到"，**没有做跨语言语义对齐**（越南语问句检索中文术语仍靠词形重合）。
3. 索引是静态快照，**总库更新后必须重跑 build_vectors.py**；没有增量更新机制。
4. 文化禁忌类在术语表里条目偏少（约 200 条），术语约束召回偏低（2.3 条/句），建议约束源同时纳入 culture 表。
5. 实测指标基于 180 条自建查询，**不是公开基准**，仅供参考。
