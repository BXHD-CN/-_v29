# 机器翻译 · 术语约束提示词模板

> 配套：`work/vector_db/api_server.py`（`/search?source=term`、`/compare`）
> 用途：在 MT 前后注入术语约束，保证译文与库内推荐译法一致；库未覆盖时**显式标注**，而不是让模型自由发挥。

## 一、系统提示词

```text
你是涉外急诊领域的专业译者，负责中英互译。你的译文必须遵守给定的【术语约束表】。

【硬约束】
1. 凡术语表中出现的词，译文必须使用表中的推荐译法，不得改写、不得同义替换、不得省略。
2. 术语表与你的习惯译法冲突时，一律以术语表为准；即使你认为表中的译法不常用。
3. 一条中文对应多条英文（或反之）时，按术语表给出的语境（domain/scene）选择；无法判断时优先选 score 最高的条目，并在译文后标注 [多译法待确认]。
4. 术语表未覆盖、但属于专业概念的表达，译文照常给出，并在句末标注 [未收录: 原词]。
5. 不得自造专业术语；不确定的直译要在译后说明，不得硬造"看起来专业"的词。
6. 人名、机构名、法律条文名称保留原文或按官方译名，不要意译。

【输出格式】
- 只输出译文；若有标注，标注紧跟在相关句之后，用方括号。
- 不要输出术语表本身，不要输出解释段落（除非用户要求）。
- 数字、单位、剂量、日期必须原样保留，不得换算或四舍五入。

【术语表格式】
每条为：原词 → 推荐译法 | doc_id | source | domain/scene
例：预检分诊 → triage | term-T-0001 | term | 分诊与接诊/分诊台
```

## 二、组装模板

```text
【术语约束表 {glossary}】
{glossary_items}

【待译文本】
{source_text}

【方向】
{zh→en 或 en→zh}

请按系统提示词约束输出译文。
```

术语表怎么来（二选一）：
- 抽取式：先把原文里的专业词抽出来，逐个调 `GET /search?q=<词>&source=term&k=3`，取 top1 作为约束；
- 对比式：调用 `GET /compare?q=<词>&k=3`，同时拿到五类来源说法，冲突时按 term 源优先。

## 三、示例（中译英 ×2）

### 示例 1：中文 → 英文（急诊流程）

**术语表**：
```text
预检分诊 → triage | term-T-0001 | term | 分诊与接诊/分诊台
分诊分级 → acuity level | term-T-0002 | term | 分诊与接诊/分诊台
```

**待译**：患者到院后先做预检分诊，护士按分诊分级把他安排到红区。

**输出**：
The patient was triaged on arrival, and the nurse assigned him to the red zone according to his acuity level. [未收录: 红区]

**要点**：triage 用了术语表动词化用法（triaged）；"分诊分级"用 acuity level 而非 triage level；"红区"库中未收录，按要求标注而非硬造 red area。

### 示例 2：中文 → 英文（法律口径，最易错）

**术语表**：
```text
医疗意外 → medical mishap | E7-0005 | term | 医疗损害与事故/医务处
医疗事故 → medical malpractice | E7-0003 | term | 医疗损害与事故/医务处
非正常死亡 → unnatural death | E7-0083 | term | 死亡证明/医务处
```

**待译**：本例属医疗意外，已向家属说明并记录；若是非正常死亡，须报公安。

**输出**：
This case is a medical mishap, which has been explained to the family and documented; if it were an unnatural death, it must be reported to the police.

**要点**：医疗意外**不得**译成 medical accident / malpractice（库中 term 源明确区分）；"报公安"用 reported to the police，不用 reported to police station；法律口径类术语一旦译错会改变责任性质，宁可标注也不改写。

## 四、示例（英译中 ×2）

### 示例 3：英文 → 中文（入院表述）

**术语表**：
```text
admitted → 收治住院 | E7-0075 | term | 护照与旅行证件/分诊台
medical certificate of death → 死亡医学证明 | E7-0078 | term | 死亡证明/医务处
```

**待译**：He was admitted yesterday, and the medical certificate of death was issued after the family arrived.

**输出**：他昨天收治住院，家属到场后签发了死亡医学证明。

**要点**：admitted 在菲律宾英语语境里是"住院"，库中 term 源给"收治住院"，不要译成"被承认/被接纳"；issued 的主语是医院，中文宜调整为"（医院）签发"。

### 示例 4：英文 → 中文（知情同意主体）

**术语表**：
```text
legal representative → 法定代理人 | E7-0175 | term | 未成年人保护/病房
informed consent → 知情同意 | D8-0001 | term | 知情同意/谈话室
letter of authorization → 授权委托书 | D8-0003 | term | 知情同意/谈话室
```

**待译**：Informed consent for the procedure was obtained from the legal representative, not from a proxy under a letter of authorization.

**输出**：该操作的知情同意由法定代理人取得，而非依授权委托书由代理人签署。

**要点**：informed consent（同意本身）、legal representative（法定代理人）、letter of authorization（授权委托书）三个概念在库中分列，译文不得合并成"家属同意"；否定结构 not from 要译出，否则会丢掉授权瑕疵这一关键信息。

## 五、译后质检清单

| 检查项 | 判据 | 不合格处理 |
|---|---|---|
| 术语覆盖率 | 原文专业词是否都在术语表中 | 缺的补检索，仍缺则标注 [未收录] |
| 推荐译法命中 | 译文是否逐条使用表中译法 | 有偏离即重译 |
| 多译法处理 | 是否按 domain/scene 选择并标注 | 无法判断时标 [多译法待确认] |
| 数字与单位 | 剂量、日期、编号是否原样 | 有改动即判错 |
| 法律口径 | 医疗意外/事故、非正常死亡等是否区分 | 混用即判错 |
| 标注完整性 | [未收录] / [多译法待确认] 是否齐全 | 缺标即退回 |
