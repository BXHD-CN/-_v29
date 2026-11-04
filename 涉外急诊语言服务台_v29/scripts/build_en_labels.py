# -*- coding: utf-8 -*-
"""生成「知识库中文元数据枚举 → 英文展示标签」映射（v=26 英文优先）。

背景：V1.3 总库里 domain / subdomain / scene / subcategory / ctype / country /
taboo_level / register / audit_status / lang / category 等字段只有中文值，且这些
中文值同时是后端筛选参数。英文模式要求「所有内容都以英文为优先级」，但直接改库
会破坏后端 WHERE 条件，因此：

- 后端 / 数据库保持中文原值不变（<option value> 也保持中文原值）；
- 前端展示层通过 I18N.label() 把中文枚举换成英文标签；
- 本脚本扫描 data/app.db 的所有枚举值，产出 100% 覆盖的 zh→en 映射，
  写入 i18n_labels.json 与 static/js/i18n-labels.js。

翻译策略：
1. EXACT：高频 / 非组合型值的人工精确译法；
2. TOKENS：中文词素词典，对长尾短语做最长匹配组合翻译；
3. 任何仍含汉字的译文都会被报告为 missing，脚本以非零码退出， CI 可拦截。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "app.db"
OUT_JSON = ROOT / "i18n_labels.json"
_OUT_JS = ROOT / "static" / "js" / "i18n-labels.js"

FIELDS = {
    "public_terms": ["domain", "subdomain", "lang_pair", "audit_status"],
    "public_corpus": ["register", "domain", "lang_pair", "audit_status"],
    "local_terms": ["lang", "lang_code", "category", "domain", "scene", "audit_status"],
    "culture_exprs": ["ctype", "subcategory", "country", "original_lang", "scene", "taboo_level"],
    "english_variants": ["variant", "country"],
    "news_items": ["source", "status"],
}

CJK = re.compile(r"[\u3400-\u9fff]")

# ---------------------------------------------------------------------------
# 1. 精确译法：界面筛选器、标签、高风险枚举、非组合型值
# ---------------------------------------------------------------------------
EXACT: dict[str, str] = {
    # 语种对 / 审核 / 语体 / 分类 / 状态 / 来源
    "zh-en": "Chinese–English",
    "来源核验": "Source verified",
    "待母语审校": "Pending native-speaker review",
    "书面": "Written",
    "口语": "Spoken",
    "术语": "Term",
    "文化表达": "Cultural expression",
    "published": "Published",
    "un": "UN News",
    "un_zh": "UN News (Chinese)",
    "reliefweb": "ReliefWeb",
    "usgs": "USGS Earthquakes",
    "id": "Indonesian",
    "ms": "Malay",
    "th": "Thai",
    "vi": "Vietnamese",
    "ICU": "ICU",
    "ASA 分级": "ASA classification",
    "MRI与超声": "MRI & ultrasound",
    "X线与CT": "X-ray & CT",

    # 15 个一级领域
    "传染病与公共卫生应急": "Infectious disease & public-health emergency",
    "内科急症与中毒": "Medical emergencies & poisoning",
    "分诊与接诊": "Triage & intake",
    "创伤与外科急症": "Trauma & surgical emergencies",
    "医疗文书与证明": "Medical documents & certificates",
    "医疗法律与领事事务": "Medical law & consular affairs",
    "妇儿与精神心理": "Women, children & mental health",
    "急救复苏与气道": "Resuscitation & airway",
    "手术与麻醉知情同意": "Surgery & anaesthesia consent",
    "检验与影像报告": "Laboratory & imaging reports",
    "沟通与合规": "Communication & compliance",
    "生命体征与危重症": "Vital signs & critical care",
    "病史采集与查体": "History taking & examination",
    "精神卫生与非自愿医疗": "Mental health & involuntary care",
    "药品与用药交代": "Medication & counselling",
    "东盟文化": "ASEAN cultures",

    # 国家 / 地区 / 语言
    "东盟通用": "ASEAN-wide",
    "印尼": "Indonesia",
    "文莱": "Brunei",
    "新加坡": "Singapore",
    "柬埔寨": "Cambodia",
    "泰国": "Thailand",
    "缅甸": "Myanmar",
    "老挝": "Laos",
    "菲律宾": "Philippines",
    "越南": "Vietnam",
    "马来西亚": "Malaysia",
    "印尼语": "Indonesian",
    "泰语": "Thai",
    "越南语": "Vietnamese",
    "马来语": "Malay",
    "缅甸语": "Burmese",
    "老挝语": "Lao",
    "菲律宾语": "Filipino",
    "高棉语": "Khmer",
    "阿拉伯语": "Arabic",
    "英语变体": "English variety",

    # 文化表达类型 / 风险等级
    "宗教禁忌": "Religious taboo",
    "文化负载词": "Culture-loaded term",
    "礼仪称谓": "Honorific address",
    "红": "High risk",
    "橙": "Medium risk",
    "黄": "Low risk",
    "无": "None",
    "Filipino English": "Filipino English",
    "Indonesian English": "Indonesian English",
    "Manglish": "Manglish",
    "Singlish": "Singlish",
    "Thai English": "Thai English",

    # 组合翻译不易自然表达的长尾值
    "应急准备": "Emergency preparedness",
    "手术知情沟通": "Surgical consent communication",
    "术前准备与禁食": "Preoperative preparation & fasting",
    "机构名称": "Institution names",
    "破伤风预防": "Tetanus prophylaxis",
    "礼拜安排": "Worship arrangements",
    "过敏史": "Allergy history",
    "递物接触": "Contact when handing over objects",
    "造影与对比剂": "Contrast imaging & contrast media",
    "领事保护与协助": "Consular protection & assistance",
    "领事协助与通知": "Consular assistance & notification",
    "领事通知与探视": "Consular notification & visits",
}

# ---------------------------------------------------------------------------
# 2. 词素词典：长尾 subdomain / scene / subcategory 的组合翻译
#    键按长度倒序匹配；& 用于连接并列成分。
# ---------------------------------------------------------------------------
TOKENS: dict[str, str] = {
    # 连接 / 结构
    "与": "&", "及": "&", "和": "&", "或": "/", "的": "", "／": "/",

    # 医疗大类
    "公共卫生": "Public health", "传染病": "Infectious disease", "法定传染病分类": "Statutory notifiable diseases",
    "重点传染病": "Priority infectious diseases", "疫情发布": "Outbreak reporting", "风险沟通": "Risk communication",
    "流行病学调查": "Field epidemiology", "密切接触者": "Close contacts", "口岸检疫": "Border quarantine",
    "健康申报": "Health declaration", "隔离": "Isolation", "医学观察": "Medical observation",
    "院感防控": "Infection prevention & control", "院感防护": "Infection control precautions",
    "消毒": "Disinfection", "灭菌": "Sterilisation", "个人防护": "Personal protective equipment",
    "职业暴露": "Occupational exposure", "疫苗接种": "Vaccination", "接种": "Vaccination",
    "疫苗不良反应": "Adverse vaccine reactions", "疫苗": "Vaccine", "免疫与血清学": "Immunology & serology",
    "微生物": "Microbiology", "感染标志物": "Infection markers", "感染与脓毒症": "Infection & sepsis",
    "抗菌药物": "Antimicrobials", "重点": "Priority",

    "内科急症": "Medical emergencies", "急性中毒": "Acute poisoning", "中毒": "Poisoning",
    "解毒": "Antidote", "过量": "Overdose", "过敏反应": "Allergic reaction", "过敏性休克": "Anaphylaxis",
    "胸痛": "Chest pain", "急性冠脉综合征": "Acute coronary syndrome", "心律失常": "Arrhythmia",
    "心搏骤停": "Cardiac arrest", "心肺复苏": "CPR", "心肌标志物": "Cardiac markers",
    "心电监护": "ECG monitoring", "脑卒中": "Stroke", "晕厥": "Syncope",
    "消化道出血": "Gastrointestinal bleeding", "腹痛": "Abdominal pain", "急腹症": "Acute abdomen",
    "呼吸困难": "Dyspnoea", "哮喘": "Asthma", "内分泌急症": "Endocrine emergencies",
    "电解质紊乱": "Electrolyte imbalance", "物质依赖": "Substance dependence", "戒断": "Withdrawal",
    "中暑": "Heat illness", "冻伤": "Frostbite", "动物咬伤": "Animal bites",
    "发热待查": "Fever of unknown origin", "儿童发热": "Paediatric fever",
    "儿童脱水": "Paediatric dehydration", "补液": "Rehydration", "新生儿复苏": "Neonatal resuscitation",
    "休克识别": "Shock recognition", "液体复苏": "Fluid resuscitation", "容量评估": "Volume assessment",
    "危急值": "Critical values", "参考区间": "Reference ranges", "影像结论": "Imaging findings",
    "报告术语": "Report terminology", "报告与时限": "Reporting & time limits",
    "报告": "Report", "检验": "Laboratory", "影像": "Imaging", "生化": "Biochemistry",
    "血常规": "Complete blood count", "血气": "Blood gas", "凝血": "Coagulation",
    "尿液与粪便": "Urine & stool", "尿量监测": "Urine output monitoring", "标本采集": "Specimen collection",
    "血氧饱和度": "Oxygen saturation", "血压": "Blood pressure", "脉搏": "Pulse", "体温": "Temperature",
    "呼吸": "Respiration", "氧疗": "Oxygen therapy", "呼吸支持参数": "Respiratory support settings",
    "吸氧": "Oxygen therapy", "氧流量": "Oxygen flow", "球囊面罩通气": "Bag-mask ventilation",
    "气管插管": "Endotracheal intubation", "声门上气道": "Supraglottic airway",
    "外科气道": "Surgical airway", "气道开放手法": "Airway manoeuvres", "气道评估": "Airway assessment",
    "儿童气道": "Paediatric airway", "儿童急诊评估": "Paediatric emergency assessment",
    "意识": "Consciousness", "格拉斯哥评分": "Glasgow Coma Scale", "危重症评分": "Severity scores",
    "生命体征": "Vital signs", "危重症": "Critical care", "复苏后处理": "Post-resuscitation care",
    "复苏团队分工": "Resuscitation team roles", "电除颤": "Defibrillation",
    "静脉通路": "Intravenous access", "骨内通路": "Intraosseous access",
    "输液": "Infusion", "配伍": "Compatibility", "输血": "Blood transfusion", "备血": "Cross-matching",
    "给药途径": "Route of administration", "剂量": "Dose", "频次": "Frequency",
    "剂型": "Dosage form", "规格": "Strength", "储存": "Storage", "稳定性": "Stability",
    "高警示药品": "High-alert medicines", "急救药品": "Emergency drugs", "急救药物": "Emergency drugs",
    "抢救用药": "Resuscitation drugs", "药物相互作用": "Drug interactions",
    "药品辅料": "Pharmaceutical excipients", "用法": "Administration", "服用时间": "Timing",
    "用药交代": "Medication counselling", "用药史": "Medication history", "用药禁忌": "Medication taboos",
    "用药": "Medication", "禁忌与慎用": "Contraindications & cautions", "不良反应": "Adverse reactions",

    "分诊": "Triage", "预检分诊": "Pre-examination triage", "分诊分级": "Triage levels",
    "候诊管理": "Waiting-room management", "候诊区": "Waiting area", "候诊沟通": "Waiting-room communication",
    "绿色通道": "Fast-track pathway", "急诊挂号": "Emergency registration",
    "就诊流程": "Care pathway", "就医流程": "Care pathway", "就医行为": "Help-seeking behaviour",
    "基层就医": "Primary care access", "导医": "Wayfinding", "投诉": "Complaints",
    "医保": "Health insurance", "支付": "Payment", "费用": "Costs", "保险": "Insurance",
    "赔偿": "Compensation", "调解": "Mediation", "诉讼": "Litigation",

    "创伤": "Trauma", "初级评估": "Primary survey", "次级评估": "Secondary survey",
    "脊柱制动": "Spinal immobilisation", "骨折固定": "Fracture splinting", "脱位复位": "Joint reduction",
    "加压包扎": "Pressure dressing", "止血": "Haemostasis", "清创缝合": "Debridement & suturing",
    "烧伤评估": "Burn assessment", "烧伤处置": "Burn management", "烧伤病房": "Burn ward",
    "颅脑损伤": "Traumatic brain injury", "胸部创伤": "Chest trauma", "腹部创伤": "Abdominal trauma",
    "胸部查体": "Chest examination", "腹部查体": "Abdominal examination",
    "神经系统查体": "Neurological examination", "皮肤检查": "Skin examination",
    "一般查体": "General examination", "体格检查": "Physical examination", "查体": "Examination",
    "体征描述": "Sign description", "主诉": "Chief complaint", "现病史": "History of present illness",
    "既往史": "Past medical history", "个人史": "Personal history", "社会史": "Social history",
    "家族史": "Family history", "婚育史": "Obstetric & marital history",
    "症状学": "Symptomatology", "病史采集": "History taking", "录入": "Data entry", "核对": "Verification",

    "手术": "Surgery", "麻醉": "Anaesthesia", "知情同意": "Informed consent",
    "知情同意能力": "Capacity to consent", "术前准备": "Preoperative preparation",
    "术前禁食": "Preoperative fasting", "术前评估": "Preoperative assessment",
    "术前谈话": "Preoperative discussion", "术前等候区": "Preoperative waiting area",
    "术后病房": "Postoperative ward", "术后监护": "Postoperative monitoring",
    "术后镇痛": "Postoperative analgesia", "术式名称": "Procedure names",
    "手术排期": "Surgical scheduling", "日间": "Day-case", "二次手术": "Reoperation",
    "中转": "Conversion", "手术风险": "Surgical risk", "麻醉风险": "Anaesthetic risk",
    "麻醉方式": "Anaesthesia technique", "手术与麻醉记录": "Surgical & anaesthesia records",
    "风险告知": "Risk disclosure", "风险": "Risk", "评估": "Assessment",
    "替代方案": "Alternatives", "操作前告知": "Pre-procedure briefing",

    "妇科急症": "Gynaecological emergencies", "产科出血": "Obstetric haemorrhage",
    "子痫": "Eclampsia", "妊娠高血压": "Hypertensive disorders of pregnancy",
    "急产": "Precipitous labour", "分娩": "Delivery", "产后": "Postpartum",
    "产科问诊": "Obstetric consultation", "产科宣教": "Obstetric education", "产科病房": "Obstetric ward",
    "儿科诊室": "Paediatric clinic", "儿科问诊": "Paediatric consultation",
    "妇儿": "Women & children", "精神心理": "Mental health", "精神科急症": "Psychiatric emergencies",
    "精神药物": "Psychotropic medicines", "精神障碍分类": "Mental disorder classification",
    "心理危机干预": "Psychological crisis intervention", "危机干预": "Crisis intervention",
    "心理评估": "Psychological assessment", "情绪评估": "Emotional assessment",
    "自杀干预": "Suicide intervention", "自杀风险评估": "Suicide risk assessment",
    "非自愿住院": "Involuntary admission", "非自愿医疗": "Involuntary treatment",
    "约束": "Restraint", "保护": "Protection", "家庭暴力识别": "Intimate-partner violence screening",
    "未成年人保护": "Minor protection", "特殊人群": "Special populations", "优先": "Priority",
    "监护人": "Legal guardian",

    "医疗文书": "Medical documents", "病历文书": "Medical records", "病历书写": "Record writing",
    "病历管理": "Record management", "病历类型": "Record types", "病历登记": "Record registration",
    "病程记录": "Progress notes", "抢救记录": "Resuscitation record", "死亡记录": "Death record",
    "死亡证明": "Death certificate", "诊断证明": "Medical certificate", "病假条": "Sick note",
    "转诊单": "Referral form", "申请单": "Request form", "转诊接收": "Referral acceptance",
    "转诊沟通": "Referral communication", "电子病历": "Electronic medical record",
    "诊断与鉴别": "Diagnosis & differential", "护理记录": "Nursing records",
    "护理评估": "Nursing assessment", "护理操作": "Nursing procedures", "护理交代": "Nursing handover",
    "病区安排": "Ward allocation", "病房管理": "Ward management", "病房交接": "Ward handover",
    "病房安全": "Ward safety", "病房布置": "Ward layout", "病房沟通": "Ward communication",
    "病房等级": "Ward class", "病房习俗": "Ward customs", "探视": "Visiting",
    "陪护": "Caregiver accompaniment", "出院小结": "Discharge summary", "出院交代": "Discharge instructions",
    "出院安排": "Discharge planning", "出院沟通": "Discharge communication", "离院交代": "Discharge briefing",
    "随访安排": "Follow-up arrangements", "社区随访": "Community follow-up",
    "居家访视": "Home visit", "转院": "Transfer", "转运": "Transfer",
    "院前转运": "Prehospital transport", "院前现场": "Prehospital scene",
    "院前急救": "Prehospital emergency care", "院外接诊": "Out-of-hospital intake",
    "院外转运": "Out-of-hospital transport", "转运交接": "Transport handover",
    "转运安排": "Transport arrangements", "转运监护": "Transport monitoring",
    "急救呼叫": "Emergency call", "出车": "Dispatch", "急救调度": "Emergency dispatch",
    "急诊调度": "Emergency dispatch", "调度中心": "Dispatch centre",
    "救护车": "Ambulance", "急救站": "First-aid station", "急救现场": "Emergency scene",
    "现场": "Scene", "场所": "Setting", "公共场合": "Public setting",
    "遗体": "Deceased body", "遗体处理": "Body handling", "遗体处置": "Body disposition",
    "遗体跨境转运": "Cross-border repatriation of remains", "死亡判定": "Determination of death",
    "死亡告知": "Death notification", "死亡处置": "Death procedures", "尸检": "Autopsy",
    "器官捐献": "Organ donation", "器官捐献沟通": "Organ donation conversation",
    "器官捐献法律": "Organ donation law", "捐献谈话": "Donation conversation",
    "医疗损害": "Medical harm", "事故": "Incident", "医疗差错": "Medical error", "过失": "Negligence",
    "医疗免责": "Liability waiver", "司法鉴定": "Forensic assessment", "鉴定": "Expert opinion",
    "举证": "Burden of proof", "强制报告": "Mandatory reporting", "治安": "Public security",
    "隐私": "Privacy", "信息保护": "Information protection", "数据保护": "Data protection",
    "国籍": "Nationality", "无国籍": "Statelessness", "难民": "Refugees", "遣返": "Repatriation",
    "护照": "Passport", "旅行证件": "Travel documents", "领事保护": "Consular protection",
    "领事协助": "Consular assistance", "领事通知": "Consular notification",
    "领事事务": "Consular affairs", "领事馆": "Consulate", "身份核验": "Identity verification",
    "翻译": "Translation", "口译服务": "Interpreting services", "语言与文化初筛": "Language & culture screening",
    "语言选择": "Language choice", "语言与族群": "Language & ethnicity",

    # 场景（临床场所）
    "急诊": "Emergency", "急诊入口": "Emergency entrance", "急诊大厅": "Emergency hall",
    "急诊科": "Emergency department", "急诊诊室": "Emergency consultation room",
    "急诊药房": "Emergency pharmacy", "急诊评估": "Emergency assessment",
    "急诊接诊": "Emergency intake", "门急诊接诊": "Outpatient & emergency intake",
    "门诊": "Outpatient", "门诊登记": "Outpatient registration", "门诊诊室": "Outpatient clinic",
    "诊室": "Consultation room", "诊区": "Consultation area", "接诊区": "Intake area",
    "分诊台": "Triage desk", "分诊区": "Triage area", "分诊问诊": "Triage interview",
    "挂号处": "Registration desk", "挂号登记": "Registration", "收费处": "Billing desk",
    "收费窗口": "Billing window", "保险窗口": "Insurance desk", "医务处": "Medical affairs office",
    "投诉办": "Complaints office", "投诉处理": "Complaint handling", "警务室": "Police post",
    "病历室": "Medical records room", "谈话室": "Consultation room", "导管室": "Catheterisation lab",
    "复位室": "Reduction room", "清创室": "Debridement room", "石膏室": "Plaster room",
    "换药室": "Dressing room", "雾化室": "Nebulisation room", "输液室": "Infusion room",
    "配液中心": "IV compounding centre", "输血科": "Blood bank", "药房沟通": "Pharmacy communication",
    "抢救室": "Resuscitation room", "抢救室外": "Outside resuscitation room",
    "观察室": "Observation unit", "恢复室": "Recovery room", "监护室": "Monitoring unit",
    "手术室": "Operating theatre", "住院处": "Admissions office", "住院日程": "Inpatient schedule",
    "住院配餐": "Inpatient meals", "日间病房": "Day ward", "夜间病房": "Night ward",
    "术后病房": "Postoperative ward", "探视病房": "Visiting ward", "探视管理": "Visiting management",
    "病房": "Ward", "病房外": "Outside the ward", "病区走廊": "Ward corridor",
    "病区": "Ward area", "床旁": "Bedside", "床旁查体": "Bedside examination",
    "床旁护理": "Bedside nursing", "床位安排": "Bed allocation", "床旁": "Bedside",
    "太平间": "Mortuary", "太平": "Mortuary", "导管": "Catheter", "护士站": "Nursing station",
    "骨科诊室": "Orthopaedic clinic", "麻醉门诊": "Anaesthesia clinic", "感染科": "Infectious diseases unit",
    "节庆急诊": "Festival-period emergency care", "节庆": "Festival",
    "用药": "Medication", "给药": "Drug administration", "给药交接": "Medication handover",
    "输血同意": "Transfusion consent", "输血用药": "Transfusion medication",
    "接种": "Vaccination", "影像检查": "Imaging examination", "心理评估": "Psychological assessment",
    "告别离院": "Farewell at discharge", "称呼患者": "Addressing the patient",
    "登记问诊": "Registration interview", "递交单据": "Submitting documents",
    "费用告知": "Cost disclosure", "费用沟通": "Cost communication",
    "营养宣教": "Nutrition education", "营养评估": "Nutrition assessment",
    "诊室": "Consultation room", "病房": "Ward",

    # 沟通 / 语用 / 语言
    "沟通": "Communication", "医患沟通": "Clinician–patient communication",
    "医护沟通": "Clinical-team communication", "家属沟通": "Family communication",
    "家属谈话": "Family conversation", "告知谈话": "Disclosure conversation",
    "坏消息告知": "Breaking bad news", "告知": "Disclosure", "谈话": "Conversation",
    "问诊": "Consultation", "问诊沟通": "Consultation communication",
    "单独问诊": "Private consultation", "创伤问诊": "Trauma consultation",
    "沟通确认": "Confirmation", "沟通协调": "Coordination", "沟通语用": "Pragmatics",
    "沟通与拒绝": "Communication & refusal", "拒绝与代答": "Refusal & answering for others",
    "应答与同意": "Response & consent", "应答": "Response", "同意": "Consent",
    "应答简略": "Minimal responses", "应答语": "Response forms",
    "情绪表达": "Emotional expression", "情绪与面子": "Emotion & face",
    "情态表达": "Modality", "程度强调": "Intensifiers", "程度表达": "Degree expressions",
    "痛苦表达": "Expressions of pain", "症状表达": "Symptom descriptions", "症状": "Symptom",
    "否定表达": "Negation", "否定与反诘": "Negation & rhetorical questions",
    "存在句式": "Existential constructions", "存在表达": "Existential expressions",
    "完成体": "Perfective aspect", "时体标记": "Tense–aspect markers",
    "语序倒置": "Inverted word order", "语法简化": "Grammatical simplification",
    "动词搭配": "Verb collocations", "动词迁移": "Verb transfer",
    "借词搭配": "Loanword collocations", "借词表达": "Loanword expressions",
    "词汇转义": "Semantic shift", "词汇迁移": "Lexical transfer",
    "语气词": "Modal particles", "敬语助词": "Honorific particles",
    "自称与代词": "Self-reference & pronouns", "请求语气": "Request politeness",
    "疑问句式": "Question forms", "问答": "Q&A", "制度用语": "Institutional register",
    "语用礼貌": "Pragmatic politeness", "礼貌与委婉": "Politeness & hedging",
    "礼貌用语": "Polite formulas", "致谢": "Thanks", "致谢语": "Thank-you formulas",
    "告别致谢": "Farewell thanks", "问候": "Greetings", "问候礼": "Greeting etiquette",
    "问候语": "Greeting formulas", "问候简略": "Shortened greetings", "日常称呼": "Everyday address",
    "称呼": "Address", "称谓": "Address terms", "敬称": "Honorific",
    "敬称前缀": "Honorific prefixes", "敬语": "Honorific language",
    "敬语应答": "Honorific responses", "尊称": "Honorific address",
    "称谓敬称": "Honorific address terms", "称谓敬语": "Honorific address language",
    "称谓习惯": "Addressing customs", "称谓沟通": "Address in communication",
    "职务称谓": "Official titles", "专业称谓": "Professional titles",
    "医疗称谓": "Clinical titles", "宗教称谓": "Religious titles",
    "封衔": "Titles of nobility", "文莱头衔": "Bruneian titles", "文莱敬称": "Bruneian honorifics",
    "马来族称谓": "Malay address terms", "国名称谓": "Country names",
    "性别称谓": "Gendered address", "年轻男性称谓": "Address for young men",
    "长辈称呼": "Address for elders", "长者优先": "Elders first", "尊卑与长幼": "Hierarchy & seniority",
    "姓名": "Personal names", "姓名结构": "Name structure", "姓名顺序": "Name order",
    "亲属称谓": "Kinship terms", "亲属与决策": "Family & decision-making",
    "人情与决策": "Reciprocity & decision-making", "恩情与决策": "Gratitude & decision-making",
    "关系与顺从": "Relationships & deference", "体面与自尊": "Dignity & self-esteem",
    "面子与羞耻": "Face & shame", "面子尊严": "Face & dignity",
    "沉默与面子": "Silence & face", "目光接触": "Eye contact", "目光与姿态": "Gaze & posture",
    "称呼": "Address", "致谢": "Thanks",

    # 宗教 / 民俗 / 文化
    "宗教": "Religion", "宗教与人生礼仪": "Religion & life-cycle rites",
    "宗教与功德": "Religion & merit", "宗教与文化禁忌": "Religious & cultural taboos",
    "宗教人员": "Religious personnel", "宗教仪式": "Religious rites",
    "宗教器物": "Religious objects", "宗教场所": "Religious site",
    "宗教实践": "Religious practice", "宗教联络": "Religious liaison",
    "宗教节日": "Religious festivals", "宗教行为": "Religious conduct",
    "宗教裁决": "Religious rulings", "宗教禁忌": "Religious taboo",
    "宗教与功德": "Religion & merit", "宗教场所": "Religious site",
    "佛教节日": "Buddhist festivals", "佛教造像": "Buddhist iconography",
    "佛像": "Buddha images", "佛像恭敬": "Reverence for Buddha images",
    "佛塔礼仪": "Stupa etiquette", "业报观": "Karma beliefs", "亡魂观念": "Beliefs about the dead",
    "僧侣": "Monastics", "僧侣供养": "Supporting monastics", "僧侣戒律": "Monastic precepts",
    "僧侣接触": "Contact with monastics", "僧侣施舍": "Alms to monastics",
    "僧侣禁忌": "Monastic taboos", "僧侣称谓": "Monastic address",
    "僧尼称谓": "Monk & nun address", "布施": "Almsgiving", "布施与功德": "Almsgiving & merit",
    "布施托钵": "Alms round", "寺院功能": "Temple functions", "寺院禁忌": "Temple taboos",
    "出家仪式": "Ordination ceremony", "诵经": "Chanting", "诵经护佑": "Chanting for protection",
    "净礼": "Ritual purification", "祈祷与治疗": "Prayer & treatment",
    "印度教仪式": "Hindu rituals", "印度教节日": "Hindu festivals",
    "伊斯兰日常": "Islamic daily life", "斋戒": "Fasting", "斋戒与持戒": "Fasting & observance",
    "斋戒开斋": "Ramadan & Eid", "斋期与饮食": "Fasting & diet",
    "圣事": "Sacraments", "圣周": "Holy Week", "圣水": "Holy water", "圣诞季": "Christmas season",
    "教父母": "Godparents", "朝觐称谓": "Hajj-related titles", "王室与法律": "Royalty & law",
    "王室僧侣": "Royalty & monastics", "王室敏感": "Royal sensitivities",
    "超度": "Rites for the deceased", "祖先祭祀": "Ancestor worship", "祭供": "Offerings",
    "祭祖节期": "Ancestral festival dates", "禳灾仪式": "Averting-misfortune rites",
    "民间仪式": "Folk rituals", "民间信仰": "Folk beliefs",
    "民间病因表达": "Folk idioms of illness", "民间病因观": "Folk aetiology",
    "鬼神与灵魂": "Spirits & souls", "神灵信仰": "Spirit beliefs", "地方神灵": "Local deities",
    "护身物": "Protective objects", "护身符": "Amulets", "焚香": "Incense burning",
    "择日与占卜": "Auspicous dates & divination", "数字忌讳": "Number taboos",
    "头脚禁忌": "Head & feet taboos", "头部与脚": "Head & feet",
    "左手禁忌": "Left-hand taboos", "手部禁忌": "Hand taboos",
    "递物接物": "Giving & receiving objects", "递物用手": "Hand used to hand over objects",
    "性别接触": "Cross-gender contact", "性别隐私": "Gender privacy",
    "性别隔离": "Gender segregation", "身体修饰": "Body adornment",
    "身体礼仪": "Body etiquette", "身体禁忌": "Body taboos",
    "日常织物": "Everyday textiles", "服饰与检查": "Clothing & examination",
    "探视礼仪": "Visiting etiquette", "宴请礼仪": "Banquet etiquette",
    "餐桌礼仪": "Table manners", "饮食禁忌": "Dietary taboos",
    "饮食与禁忌": "Food & taboos", "饮食与行为禁忌": "Food & conduct taboos",
    "饮食与用药": "Food & medication", "饮食用语": "Food vocabulary",
    "饮食环境": "Dining environment", "饮食": "Diet",
    "用餐": "Meals", "用餐安排": "Meal arrangements", "用餐沟通": "Meal communication",
    "用餐配餐": "Meal service", "配餐沟通": "Meal-service communication",
    "饮食交代": "Dietary instructions", "饮食宣教": "Dietary education", "饮食指导": "Dietary guidance",
    "礼物颜色": "Gift colours", "电力与设备": "Electricity & equipment",
    "居住与地址": "Residence & address", "居住形态": "Living arrangements",
    "社区与用药": "Community & medication", "社区互助": "Community mutual aid",
    "社区空间": "Community spaces", "社区随访": "Community follow-up",
    "基层制度": "Grassroots institutions", "认证制度": "Certification systems",
    "族群与国籍": "Ethnicity & nationality", "族群与宗教": "Ethnicity & religion",
    "族群与身份": "Ethnicity & identity", "族群分类": "Ethnic classification",
    "族群敏感": "Ethnic sensitivities", "族群登记": "Ethnicity registration",
    "族群称谓争议": "Disputed ethnonyms", "族群贬称": "Derogatory ethnonyms",
    "国家理念": "National ideals", "国家象征": "National symbols",
    "华族长辈": "Chinese elders", "祖辈照护": "Grandparent caregiving",
    "历史创伤": "Historical trauma", "宿命与依从": "Fatalism & adherence",
    "生死与宿命": "Life, death & fate", "生死观": "Views on life & death",
    "生殖": "Reproduction", "法律禁令": "Legal prohibitions",
    "传统医疗": "Traditional medicine", "传统医药": "Traditional medicine",
    "传统治疗": "Traditional healing", "传统疗法": "Traditional therapies", "外治法": "External therapies",
    "洁净观念": "Purity concepts", "仪式主持": "Ritual officiants",
    "丧礼": "Funeral rites", "丧葬": "Funeral customs", "丧葬与书写": "Funerals & writing",
    "丧葬习俗": "Funeral customs", "丧葬仪式": "Funeral ceremonies",
    "丧葬焚烧": "Funeral burning", "丧葬节期": "Mourning periods", "殡葬": "Burial & funerals",
    "临终仪式": "End-of-life rites", "临终": "End of life",
    "临终关怀": "Palliative care", "临终照护": "End-of-life care", "安宁疗护": "Hospice care",
    "产后习俗": "Postpartum customs", "产后护理": "Postpartum care",
    "节庆与出院": "Festivals & discharge", "节庆与历法": "Festivals & calendars",
    "节庆与急诊": "Festivals & emergencies", "节庆布施": "Festival almsgiving",
    "节庆时间": "Festival timing", "节庆沟通": "Festival communication",
    "节庆礼俗": "Festival customs", "节庆禁忌": "Festival taboos",
    "泼水节": "Songkran", "点灯节": "Festival of Lights", "圣周": "Holy Week",
    "场所礼仪": "Setting etiquette", "场所缩略": "Place-name abbreviations",
    "场所": "Setting", "仪式": "Ritual", "礼仪": "Etiquette",
    "文化负载词": "Culture-loaded term", "文化": "Culture",
    "禁忌": "Taboo", "禁忌表述": "Taboo wording", "禁忌与慎用": "Contraindications & cautions",
    "时间表达": "Time expressions", "时间提示": "Time cues",
    "疼痛与程度": "Pain & intensity", "疼痛评估": "Pain assessment",
    "家庭与费用": "Family & costs", "医疗付费": "Paying for care",
    "治疗选择": "Treatment choices", "就医行为": "Help-seeking behaviour",
    "宿命": "Fate", "依从性": "Adherence", "医嘱": "Medical orders",
    "医嘱沟通": "Communicating medical orders", "沟通": "Communication",
    "抢救": "Resuscitation", "会诊与转科": "Consultation & transfer",
    "会诊": "Consultation", "转科": "Interdepartmental transfer",
    "用药交代话术": "Medication counselling scripts", "话术": "Scripts",
    "处方审核": "Prescription review", "处方": "Prescription",
    "药房": "Pharmacy", "药品": "Medicines", "药": "Medicine",
    "用法与服用时间": "Administration & timing", "用法": "Administration",
    "特殊人群用药": "Medication in special populations",
    "疫苗": "Vaccine", "接种": "Vaccination",
    "急救": "Emergency care", "急诊": "Emergency",
    "护理": "Nursing", "宣教": "Education", "沟通": "Communication",
    "登记": "Registration", "信息登记": "Information registration",
    "管理": "Management", "安排": "Arrangements",
    "交接": "Handover", "沟通": "Communication",
    "日常接触": "Everyday contact", "日常问候": "Everyday greetings",
    "现场": "Scene", "节庆": "Festival",
    "出院": "Discharge", "入院": "Admission", "入院评估": "Admission assessment",
    "入院沟通": "Admission communication", "住院": "Inpatient",
    "用药史采集": "Medication history taking",
    "坏消息": "Bad news", "风险": "Risk", "评估": "Assessment",
    "诊室": "Consultation room", "病房": "Ward", "病区": "Ward area",
    "问候": "Greetings", "称谓": "Address terms", "问诊": "Consultation",
    "查体": "Examination", "查体沟通": "Examination communication",
    "导诊": "Wayfinding", "手术表达": "Surgical phrasing",
    "检查表达": "Examination phrasing", "时间": "Time",
    "现场": "Scene", "单独": "Private", "公共": "Public",
    "宗教": "Religion", "节庆": "Festival",
    "与": "&",

    # 兜底单字 / 常见词
    "评估": "Assessment", "记录": "Record", "报告": "Report", "文书": "Document",
    "证明": "Certificate", "单据": "Documents", "通知": "Notification",
    "确认": "Confirmation", "核对": "Verification", "交代": "Instructions",
    "说明": "Explanation", "采集": "Collection", "处理": "Management",
    "处置": "Management", "监护": "Monitoring", "观察": "Observation",
    "康复": "Rehabilitation", "恢复": "Recovery", "复诊": "Follow-up visit",
    "入院": "Admission", "出院": "Discharge", "转诊": "Referral",
    "转运": "Transfer", "转运交接": "Transport handover",
    "交接": "Handover", "陪护": "Caregiver accompaniment",
    "探视": "Visiting", "候诊": "Waiting", "候诊区": "Waiting area",
    "挂号": "Registration", "收费": "Billing", "缴费": "Payment",
    "病历": "Medical record", "病程": "Clinical course",
    "医嘱": "Medical orders", "处方": "Prescription",
    "用药": "Medication", "给药": "Administration", "服药": "Medication intake",
    "注射": "Injection", "输液": "Infusion", "输血": "Transfusion",
    " Oxygen": " Oxygen",
}

# ---------------------------------------------------------------------------
# 3. 组合翻译
# ---------------------------------------------------------------------------
_SORTED = sorted(TOKENS.items(), key=lambda kv: (-len(kv[0]), kv[0]))


def compose(text: str) -> str:
    parts: list[str] = []
    i = 0
    while i < len(text):
        hit = None
        for zh, en in _SORTED:
            if text.startswith(zh, i):
                hit = (zh, en)
                break
        if hit is None:
            ch = text[i]
            if ch.isspace():
                parts.append(" ")
            elif ch.isascii() and (ch.isalnum() or ch in "-/&()"):
                parts.append(ch)
            else:
                parts.append(ch)   # 保留汉字 → 之后由 missing 检查拦下
            i += 1
        else:
            zh, en = hit
            if en:
                parts.append(en)
            i += len(zh)
    out = " ".join(p for p in parts if p and p != " ")
    out = re.sub(r"\s*&\s*", " & ", out)
    out = re.sub(r"\s+", " ", out).strip(" &")
    return out


def translate(value: str) -> str:
    if value in EXACT:
        return EXACT[value]
    if not CJK.search(value):
        return value
    return compose(value)


def collect() -> dict[str, list[str]]:
    if not DB.exists():
        raise SystemExit(f"database not found: {DB}")
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    out: dict[str, list[str]] = {}
    for table, cols in FIELDS.items():
        have = {r[1] for r in cur.execute(f"pragma table_info({table})")}
        for col in cols:
            if col not in have:
                continue
            for (raw,) in cur.execute(f"select distinct {col} from {table}"):
                if raw is None or str(raw).strip() == "":
                    continue
                val = str(raw).strip()
                out.setdefault(val, []).append(f"{table}.{col}")
    con.close()
    return out


def main() -> int:
    values = collect()
    labels = {v: translate(v) for v in sorted(values)}
    missing = sorted(v for v, en in labels.items() if CJK.search(en))
    payload = {
        "meta": {"total": len(labels), "missing": len(missing),
                 "source": "data/app.db", "policy": "display-only; DB values stay Chinese"},
        "labels": labels,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _OUT_JS.write_text(
        "/* Generated by scripts/build_en_labels.py — do not edit by hand. */\n"
        "window.WB_I18N_LABELS = " + json.dumps(labels, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    print(f"labels={len(labels)} missing={len(missing)}")
    if missing:
        print("UNTRANSLATED VALUES:")
        for v in missing:
            print(f"  {v!r} -> {labels[v]!r}")
        return 1
    print(f"wrote {OUT_JSON.name} and static/js/i18n-labels.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
