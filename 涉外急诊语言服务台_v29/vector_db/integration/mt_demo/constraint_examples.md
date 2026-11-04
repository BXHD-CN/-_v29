# 术语约束机器翻译演示 · 对照与接入说明

> 配套代码：`mt_demo.py`（译前检索约束术语）、`term_check.py`（译后一致性校验）
> 数据来源：总库 V1.3 向量索引 `work/vector_db/index`（14400 条；术语表 4154 条）
> 运行环境：`python work/vector_db/integration/mt_demo/mt_demo.py --write`

## 1. 演示设置

| 项 | 值 |
|---|---|
| 句子数 | 30（分诊 6 / 急救 6 / 用药 6 / 知情同意 6 / 文化禁忌 6） |
| 检索方式 | `SearchIndex().search(句子, k=8, source="term")`（真实运行，非模拟） |
| 约束阈值 | score ≥ **0.45**（经验标定：至少命中 1 条、平均 3–4 条） |
| 单句上限 | 5 条术语（防止 glossary 过长干扰译引擎） |
| 命中情况 | 30/30 句有约束；共 **112** 条约束术语；**平均每句 3.73 条** |
| 分类平均 | 分诊 4.00、急救 4.67、用药 3.83、知情同意 3.83、文化禁忌 2.33 |

阈值 0.45 的取值逻辑：调高则约束更少更准，但会漏掉必要术语；调低则会把同域近邻词
（如「分诊记录」之于「分诊护士」）塞进 glossary，反而干扰译引擎。上线应按科室分别标定并记录版本号。

## 2. 十条对照：约束术语 vs 无约束错译

| # | 原句（中文） | 检索到的约束术语（doc_id / 分数） | 无约束时常见错译 | 术语约束后的正确译法 | 差异说明 |
|---|---|---|---|---|---|
| 1 | 高热患者到急诊先做预检分诊，护士按病情紧急程度安排就诊顺序 | 预检分诊 → triage（term-T-0001 / 0.991）；分诊准确性 → triage accuracy（term-T-0014 / 0.620）；分诊标准 → triage criteria（term-T-0004 / 0.580） | 把「预检分诊」译成 **pre-examination classification** 或 **injury classification**（后者是「检伤分类」，属另一概念） | A febrile patient is **triaged** on arrival, and the nurse sets the order of consultation according to acuity. | `triage` 是国际通行术语；`classification` 会被读成「分类登记」，`injury classification` 更会被读成检伤分级，导致流程理解错误。 |
| 2 | 胸痛患者走绿色通道，优先接诊并直接送抢救室 | 绿色通道 → fast-track pathway（term-T-0182 / 1.034）；优先接诊 → priority reception（term-T-0189 / 0.967） | **green channel**（字面直译；英语母语医护无法理解，且 `channel` 常指通信频道） | Chest pain patients go through the **fast-track pathway**, receive **priority reception** and are sent straight to the resuscitation room. | `green channel` 是典型中式英语；`fast-track` 才是英联邦/WHO 材料里的固定说法。 |
| 3 | 室颤患者需要电除颤，能量按双相波设定 | 电除颤 → defibrillation（term-T-1153 / 0.724）；双相波除颤 → biphasic defibrillation（term-T-1160 / 0.598） | 把「电除颤」译成 **electric shock** / **electrical shock**（这是「电击伤」） | A patient in ventricular fibrillation requires **defibrillation**, with energy set for a **biphasic** waveform. | `electric shock` 是创伤/触电概念，与治疗性除颤完全相反；能量参数与波形也须一并译出。 |
| 4 | 气道梗阻时用仰头抬颏法开放气道，必要时置入口咽通气管 | 口咽通气管 → oropharyngeal airway（term-T-1183 / 0.998）；仰头抬颏法 → head tilt-chin lift（term-T-1180 / 0.939）；气道梗阻 → airway obstruction（term-T-1200 / 0.770） | 译成 **head lifting method** / **chin lifting technique**（拆字直译，国际指南无此说法） | In **airway obstruction**, open the airway with the **head tilt-chin lift** manoeuvre and insert an **oropharyngeal airway** if needed. | 手法名是国际指南固定词组，拆字直译会让接收方无法对应到培训动作，现场易做错。 |
| 5 | 缓释片必须整片吞服，不能掰开或嚼碎 | 整片吞服 → swallow the tablet whole（term-T-2884 / 1.021）；缓释片 → extended-release tablet（term-T-2845 / 0.768） | 译成 **slow-release tablet**（非规范剂型名），或把「整片吞服」译成 take it whole 而漏掉吞服方式 | The **extended-release tablet** must be **swallowed whole** and must not be split or chewed. | `slow-release` 不是药典剂型名，且会掩盖「掰开会剂量突释」的风险；`extended-release` 与 `delayed-release`（肠溶） 必须区分。 |
| 6 | 配伍禁忌的药物不能加在同一瓶液体里 | 配伍禁忌 → drug incompatibility（term-T-1392 / 0.999） | 译成 **contraindication**（这是「禁忌证」，指该患者不能用此药，与两药混合不相容是两回事） | Drugs with **drug incompatibility** must not be added to the same bottle of fluid. | 概念偷换最危险：护士看到 `contraindication` 会以为只要患者不过敏就能同瓶配伍，直接造成配液事故。 |
| 7 | 手术前要向患者说明手术风险、替代方案并签署手术知情同意书 | 知情同意 → informed consent（term-T-3478 / 1.062）；手术知情同意书 → surgical informed consent form（term-T-3479 / 1.031）；手术风险 → surgical risk（term-T-3462 / 0.741） | 译成 **consent agreement** / **notification consent**（只表示「同意」，丢失 informed = 充分告知后理解） | Before surgery, explain the **surgical risk** and alternatives, and obtain a signed **surgical informed consent form**. | `consent` 只有「同意」义；`informed consent` 才是法律要件（告知—理解—自愿），直接决定签字效力。 |
| 8 | 家属要求不要告诉患者癌症诊断，需要沟通告知策略 | 告知策略 → disclosure strategy（term-T-2609 / 0.933）；癌症诊断 → cancer diagnosis（term-T-2592 / 0.895）；坏消息告知 → breaking bad news（term-T-2585 / 0.524） | 译成 **bad news notification**（notification 是「通知」，缺告知技巧与渐进披露义） | The family asks that the **cancer diagnosis** not be disclosed, so a **disclosure strategy** for **breaking bad news** must be agreed. | `notification` 暗示单向通知，`breaking bad news` 是国际沟通培训的固定概念（含 SPIKES 等流程）。 |
| 9 | 医护人员需要了解宗教禁忌，查体前先说明避免冒犯患者 | 宗教禁忌 → religious taboo（term-T-2695 / 0.973）；文化能力 → cultural competence（term-T-2833 / 0.498） | 译成 **religious contraindication**（把 taboo 当成医学 contraindication） | Staff need to know the **religious taboos** and explain the examination beforehand so as not to offend the patient. | `contraindication` 在医疗语境专指用药/操作禁忌，用来说宗教禁忌会让读者以为是宗教禁止某项医疗操作，语义完全漂移。 |
| 10 | 家属希望遗体尽快火化，需要开具死亡证明并联系殡仪馆 | 死亡证明 → death certificate（term-T-4026 / 0.924）；殡仪馆 → funeral home（term-T-4039 / 0.754）；火化 → cremation（term-T-4040 / 0.693） | 译成 **burning of the body** / **incineration of the body**（粗俗且像废弃物处理） | The family wants the **remains cremated** as soon as possible, so a **death certificate** must be issued and a **funeral home** contacted. | `cremation` 是殡葬标准词；`incineration` 用于垃圾焚烧，用在遗体上属严重失礼，涉及家属情绪与宗教敏感。 |

### 错译类型归纳

1. **概念偷换**（最危险）：配伍禁忌→contraindication、宗教禁忌→religious contraindication——把「禁忌」一律译成医学 contraindication。
2. **字面直译**：绿色通道→green channel、仰头抬颏法→head lifting method——中文能拼出来，英文没有这个搭配。
3. **近义误配**：电除颤→electric shock（电击伤）、缓释片→slow-release（非药典剂型）。
4. **法律要件丢失**：知情同意→consent、坏消息告知→bad news notification——丢掉 informed / breaking 的流程含义。
5. **语域失礼**：火化→burning of the body——用词粗俗，触碰丧葬敏感。

## 3. 如何接入平台翻译流水线

### 3.1 译前：术语注锚（pre-translation term anchoring）

```python
from mt_demo import build_constraints   # 或复制其逻辑进平台 SDK
from search import SearchIndex

idx = SearchIndex()
cons = build_constraints(idx, zh_sentence)      # [{zh, en, doc_id, score}, ...]
# 把 cons 作为 glossary 传给翻译引擎（三种接法见 mt_demo.py 文件头）：
#   DeepL   -> glossary_id（CSV: zh,en）
#   Google  -> glossary_config
#   本地模型 -> 提示词 / force_words_ids 受限解码
en = translate_with_glossary(zh_sentence, cons)
```

要点：
- glossary 只在**该句命中的术语**上注入，不要整库灌入（会稀释约束、拖慢引擎）。
- 同一句最多 5 条，按 score 降序截断；doc_id 一并落库，便于审计「这句依据哪条术语」。
- 阈值 0.45 是起点，按科室/语种分别标定，并把阈值版本写进请求元数据。

### 3.2 译后：一致性校验（post-translation verification）

```python
from term_check import check
rep = check(idx, zh_sentence, en_translation)
if rep["banned"]:          # ❌ 命中禁用译法 → 阻断发布
    en = retranslate(zh_sentence, constraints=rep["constraints"], hints=rep["banned"])
elif rep["missing"]:       # ⚠️ 未用推荐译法 → 人工抽检 / 二次回译
    enqueue_human_review(rep)
```

- **❌ 命中禁用译法**：直接拦截并带着修正建议重译一次；重译仍失败则转人工。
- **⚠️ 未使用推荐译法**：进人工抽检队列，按科室统计 top 错译术语，反哺术语表与提示词。
- 与译前共用同一个 `SearchIndex`、同一个 `K/THRESHOLD`，保证「译前注入的术语」和「译后检查的术语」同源，避免自相矛盾。

### 3.3 建议的落库字段（每次翻译任务）

```json
{
  "request_id": "...",
  "zh": "胸痛患者走绿色通道……",
  "en": "Chest pain patients go through the fast-track pathway ...",
  "constraints": [{"zh": "绿色通道", "en": "fast-track pathway", "doc_id": "term-T-0182", "score": 1.034}],
  "engine": "deepl|google|local",
  "threshold_version": "0.45/2026-11",
  "check": {"pass": false, "banned": [...], "missing": [...]}
}
```

### 3.4 指标与验收

| 指标 | 定义 | 建议目标 |
|---|---|---|
| 术语命中率 | 约束术语表非空句占比 | ≥ 95%（本次 30/30 = 100%） |
| 术语使用率 | term_check 判为 OK 的约束术语占比 | ≥ 90% |
| 禁用译法命中率 | 命中 BANNED 的句占比 | ≤ 2%，且全部被拦截 |
| 平均约束数 | 每句注入术语数 | 3–4 条（本次 3.73） |
| 人工抽检率 | ⚠️ 进入人工的句占比 | 首月 100%，稳定后降至 10% |

## 4. 复现

```bash
python work/vector_db/integration/mt_demo/mt_demo.py --write    # 30 句检索 + 约束表 + 汇总 + JSON
python work/vector_db/integration/mt_demo/mt_demo.py --json     # 机器可读
python work/vector_db/integration/mt_demo/term_check.py --demo   # 3 个译后校验示例
python work/vector_db/integration/mt_demo/term_check.py "胸痛患者走绿色通道" "Chest pain patients go through the green channel."
```

## 5. 局限与后续

1. **检索会带近邻词（已做精度过滤）**：如第 2 句会同时召回「优先检查 / 优先权 / 转诊绿色通道」。`term_check.py` 默认启用 **attestation 过滤**——只强制检查「原句字面出现该中文术语」或分数 ≥ 0.85 的强匹配，近邻词直接忽略；需要看全量检索结果时用 `--no-attested` 关闭过滤。
2. **多术语冲突**：同一句里「知情同意」与「知情同意书」同时命中时，应优先长词（最长匹配），当前按分数排序近似实现，需显式规则化。
3. **文化禁忌类召回偏低**（平均 2.00 条）：文化类术语在 term 表只有约 200 条，句子改写后向量召回不足；建议把 culture 表也纳入约束源（`source="culture"`），并在译前提示词中补充文化提示。
4. **翻译引擎未真跑**：本演示用 `translate_stub` 占位，接口与 glossary 注入方式已在 `mt_demo.py` 文件头给出，接 key 即可替换。
5. **阈值需分场景标定**：急诊抢救、门诊咨询、知情同意三类文本的术语密度不同，建议分别取 0.45 / 0.40 / 0.50 并做 A/B。
