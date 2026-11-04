/* ============================================================
   患者情况告知单 · 语音适配器（v=27）
   ------------------------------------------------------------
   与翻译页适配器的根本差别：告知单的终点不是「一段文本」，而是
   「已有采集表的结构化字段」。因此本文件做三件事：

   1) 确定性受控词表抽取（零出网、可解释、可复现）
      - 只把说得明确的内容映射到既有圈选项（与 patient-check.js 的
        OPTIONS 及后端 DETAIL_GROUP 逐字一致）；
      - 否定词抑制（"没有发烧" 不圈「发热」）；
      - 歧义抑制（"可能 / 好像 / maybe" 不圈选；"肚子 / 腹部" 这类
        部位不明确的说法根本不进词表，绝不猜上腹还是下腹）；
      - 一切未匹配的内容都不猜标签，完整保留到「患者原话」字段。
      - 不做翻译、不做诊断、不做语言质量评估、不澄清文化或信息问题。

   2) 独立预览面板（不调用 patient-check.js 的 render()）
      未确认前不写 sessionStorage、不出现「保存到云端」入口、
      不生成告知单；确认后才复用既有表单 submit() → render()。

   3) 一次人工确认 + 一键撤销
      A+B 自动：识别后自动抽取、自动填入采集表、自动生成预览；
      确认 = 点「确认并生成告知单」触发既有 form.submit；
      撤销 = 还原确认前的圈选状态与原话，不留下任何语音痕迹。
      C 层「自动提交 / 自动留档」默认不开启。
   ============================================================ */
(function () {
  "use strict";

  /* ---------------- 受控词表：与 patient-check.js / 后端逐字一致 ---------------- */
  var PARTS = ["头部", "眼", "耳", "鼻/咽喉", "颈", "胸", "上腹", "下腹", "腰背", "肩",
    "上肢/手臂", "手/腕", "髋", "下肢/腿", "膝", "足/踝", "全身", "皮肤"];
  var SYMPTOMS = ["乏力", "疼痛", "发热", "头晕", "恶心/呕吐", "咳嗽", "呼吸困难", "心悸",
    "麻木", "肿胀", "出血", "皮疹", "腹泻", "失眠", "食欲下降", "意识模糊"];
  var DETAILS = ["突发", "持续性", "间歇性", "慢性疼痛", "反复发作", "夜间加重", "逐渐加重",
    "轻微", "中度", "剧痛", "难以忍受", "钝痛", "刺痛/锐痛", "胀痛", "烧灼痛", "绞痛",
    "压迫感", "放射痛", "活动后加重", "休息缓解", "按压加重", "体位相关", "进食相关",
    "伴发热", "伴呕吐", "伴出汗", "伴麻木", "伴呼吸困难"];

  /* 口述说法 → 规范圈选项。长词在前由 extract() 统一排序，短词只作兜底。
     刻意不收 "肚子 / 腹部 / 上半身 / 下半身"：部位不明确，不猜。 */
  var RULES = {
    parts: [
      ["上肢/手臂", "上肢/手臂"], ["鼻/咽喉", "鼻/咽喉"], ["下肢/腿", "下肢/腿"],
      ["手/腕", "手/腕"], ["足/踝", "足/踝"],
      ["上腹部", "上腹"], ["上肚子", "上腹"], ["心窝", "上腹"], ["上腹", "上腹"],
      ["下腹部", "下腹"], ["小肚子", "下腹"], ["小腹", "下腹"], ["下腹", "下腹"],
      ["腰背部", "腰背"], ["后腰", "腰背"], ["后背", "腰背"], ["腰部", "腰背"], ["腰背", "腰背"],
      ["胸口", "胸"], ["胸部", "胸"], ["前胸", "胸"], ["胸", "胸"],
      ["脑袋", "头部"], ["头疼", "头部"], ["头痛", "头部"], ["头昏", "头部"], ["头部", "头部"],
      ["眼睛", "眼"], ["眼部", "眼"], ["眼", "眼"],
      ["耳朵", "耳"], ["耳部", "耳"], ["耳", "耳"],
      ["鼻咽喉", "鼻/咽喉"], ["鼻子", "鼻/咽喉"], ["嗓子", "鼻/咽喉"], ["喉咙", "鼻/咽喉"], ["咽喉", "鼻/咽喉"],
      ["脖子", "颈"], ["颈部", "颈"], ["颈", "颈"],
      ["肩膀", "肩"], ["肩部", "肩"], ["肩", "肩"],
      ["上肢", "上肢/手臂"], ["手臂", "上肢/手臂"], ["胳膊", "上肢/手臂"],
      ["手腕", "手/腕"], ["手部", "手/腕"], ["手掌", "手/腕"],
      ["髋部", "髋"], ["胯部", "髋"], ["髋", "髋"],
      ["下肢", "下肢/腿"], ["腿部", "下肢/腿"], ["大腿", "下肢/腿"], ["小腿", "下肢/腿"], ["腿", "下肢/腿"],
      ["膝盖", "膝"], ["膝关节", "膝"], ["膝", "膝"],
      ["脚踝", "足/踝"], ["脚部", "足/踝"], ["足部", "足/踝"], ["脚", "足/踝"],
      ["浑身", "全身"], ["整个身子", "全身"], ["全身", "全身"],
      ["皮肤", "皮肤"], ["皮上", "皮肤"],
      ["chest", "胸"], ["upper abdomen", "上腹"], ["lower abdomen", "下腹"],
      ["headache", "头部"], ["head", "头部"], ["eye", "眼"], ["ear", "耳"],
      ["throat", "鼻/咽喉"], ["neck", "颈"], ["back", "腰背"], ["shoulder", "肩"],
      ["arm", "上肢/手臂"], ["wrist", "手/腕"], ["hand", "手/腕"], ["hip", "髋"],
      ["knee", "膝"], ["ankle", "足/踝"], ["foot", "足/踝"], ["leg", "下肢/腿"],
      ["whole body", "全身"], ["skin", "皮肤"]
    ],
    symptoms: [
      ["恶心/呕吐", "恶心/呕吐"], ["呼吸困难", "呼吸困难"], ["食欲下降", "食欲下降"], ["意识模糊", "意识模糊"],
      ["乏力", "乏力"], ["没力气", "乏力"], ["没劲", "乏力"], ["疲劳", "乏力"], ["疲倦", "乏力"], ["虚弱", "乏力"],
      ["疼痛", "疼痛"], ["疼", "疼痛"], ["痛", "疼痛"],
      ["发热", "发热"], ["发烧", "发热"], ["高热", "发热"], ["体温高", "发热"],
      ["头晕", "头晕"], ["眩晕", "头晕"],
      ["恶心", "恶心/呕吐"], ["想吐", "恶心/呕吐"], ["呕吐", "恶心/呕吐"], ["吐了", "恶心/呕吐"],
      ["咳嗽", "咳嗽"], ["咳", "咳嗽"],
      ["喘不上气", "呼吸困难"], ["喘不过气", "呼吸困难"], ["呼吸急促", "呼吸困难"],
      ["气短", "呼吸困难"], ["喘", "呼吸困难"],
      ["心悸", "心悸"], ["心慌", "心悸"], ["心跳快", "心悸"],
      ["麻木", "麻木"], ["发麻", "麻木"], ["没知觉", "麻木"],
      ["肿胀", "肿胀"], ["肿了", "肿胀"], ["浮肿", "肿胀"],
      ["出血", "出血"], ["流血", "出血"],
      ["皮疹", "皮疹"], ["起疹子", "皮疹"], ["红疹", "皮疹"],
      ["腹泻", "腹泻"], ["拉肚子", "腹泻"],
      ["失眠", "失眠"], ["睡不着", "失眠"], ["睡不好", "失眠"],
      ["没胃口", "食欲下降"], ["吃不下", "食欲下降"], ["不想吃", "食欲下降"],
      ["神志不清", "意识模糊"], ["迷糊", "意识模糊"],
      ["shortness of breath", "呼吸困难"], ["hard to breathe", "呼吸困难"],
      ["loss of appetite", "食欲下降"], ["no appetite", "食欲下降"],
      ["nausea", "恶心/呕吐"], ["vomiting", "恶心/呕吐"], ["vomit", "恶心/呕吐"],
      ["throw up", "恶心/呕吐"], ["pain", "疼痛"], ["ache", "疼痛"], ["sore", "疼痛"],
      ["hurts", "疼痛"], ["fever", "发热"], ["temperature", "发热"],
      ["dizzy", "头晕"], ["dizziness", "头晕"], ["lightheaded", "头晕"],
      ["cough", "咳嗽"], ["dyspnoea", "呼吸困难"], ["dyspnea", "呼吸困难"],
      ["breathless", "呼吸困难"], ["palpitations", "心悸"], ["racing heart", "心悸"],
      ["numbness", "麻木"], ["numb", "麻木"], ["swelling", "肿胀"], ["swollen", "肿胀"],
      ["bleeding", "出血"], ["rash", "皮疹"], ["diarrhea", "腹泻"], ["diarrhoea", "腹泻"],
      ["insomnia", "失眠"], ["confusion", "意识模糊"], ["confused", "意识模糊"],
      ["fatigue", "乏力"], ["weak", "乏力"], ["tired", "乏力"]
    ],
    details: [
      ["刺痛/锐痛", "刺痛/锐痛"], ["慢性疼痛", "慢性疼痛"], ["反复发作", "反复发作"],
      ["夜间加重", "夜间加重"], ["逐渐加重", "逐渐加重"], ["难以忍受", "难以忍受"],
      ["烧灼痛", "烧灼痛"], ["压迫感", "压迫感"], ["放射痛", "放射痛"],
      ["活动后加重", "活动后加重"], ["休息缓解", "休息缓解"], ["按压加重", "按压加重"],
      ["体位相关", "体位相关"], ["进食相关", "进食相关"],
      ["伴发热", "伴发热"], ["伴呕吐", "伴呕吐"], ["伴出汗", "伴出汗"],
      ["伴麻木", "伴麻木"], ["伴呼吸困难", "伴呼吸困难"],
      ["一阵一阵", "间歇性"], ["一阵阵", "间歇性"], ["时好时坏", "间歇性"],
      ["断断续续", "间歇性"], ["间歇性", "间歇性"],
      ["持续性", "持续性"], ["一直", "持续性"], ["持续", "持续性"], ["连续", "持续性"], ["不停", "持续性"],
      ["突发", "突发"], ["突然", "突发"], ["一下子", "突发"], ["忽然", "突发"],
      ["老毛病", "慢性疼痛"], ["慢性", "慢性疼痛"], ["长期", "慢性疼痛"],
      ["又犯了", "反复发作"], ["复发", "反复发作"], ["反复", "反复发作"],
      ["晚上加重", "夜间加重"], ["夜里加重", "夜间加重"], ["夜里更", "夜间加重"],
      ["越来越", "逐渐加重"], ["慢慢加重", "逐渐加重"],
      ["轻微", "轻微"], ["一点点", "轻微"], ["有点", "轻微"],
      ["中度", "中度"], ["中等", "中度"],
      ["疼得厉害", "剧痛"], ["痛得厉害", "剧痛"], ["很疼", "剧痛"], ["非常疼", "剧痛"],
      ["剧烈", "剧痛"], ["剧痛", "剧痛"],
      ["受不了", "难以忍受"], ["忍不住", "难以忍受"],
      ["钝痛", "钝痛"], ["闷痛", "钝痛"],
      ["刺痛", "刺痛/锐痛"], ["锐痛", "刺痛/锐痛"], ["针扎", "刺痛/锐痛"], ["刀割样", "刺痛/锐痛"],
      ["胀痛", "胀痛"], ["发胀", "胀痛"],
      ["灼烧", "烧灼痛"], ["火烧", "烧灼痛"],
      ["绞着疼", "绞痛"], ["绞痛", "绞痛"],
      ["胸口压", "压迫感"], ["压着", "压迫感"],
      ["串着疼", "放射痛"], ["放射到", "放射痛"],
      ["走路加重", "活动后加重"], ["一动就", "活动后加重"], ["活动后", "活动后加重"],
      ["休息后好", "休息缓解"], ["躺下好", "休息缓解"],
      ["一按就疼", "按压加重"], ["压痛", "按压加重"],
      ["改变体位", "体位相关"], ["翻身", "体位相关"], ["弯腰", "体位相关"],
      ["吃东西", "进食相关"], ["吃完", "进食相关"], ["饭后", "进食相关"], ["进食后", "进食相关"],
      ["伴有发热", "伴发热"], ["还发烧", "伴发热"], ["加上发烧", "伴发热"],
      ["伴有呕吐", "伴呕吐"], ["还吐", "伴呕吐"], ["加上呕吐", "伴呕吐"],
      ["冒冷汗", "伴出汗"], ["出冷汗", "伴出汗"], ["出汗", "伴出汗"],
      ["还麻", "伴麻木"], ["还喘", "伴呼吸困难"],
      ["sudden", "突发"], ["suddenly", "突发"], ["persistent", "持续性"],
      ["constant", "持续性"], ["continuous", "持续性"], ["intermittent", "间歇性"],
      ["on and off", "间歇性"], ["comes and goes", "间歇性"], ["chronic", "慢性疼痛"],
      ["recurrent", "反复发作"], ["worse at night", "夜间加重"],
      ["worsening", "逐渐加重"], ["getting worse", "逐渐加重"],
      ["mild", "轻微"], ["slight", "轻微"], ["moderate", "中度"],
      ["severe pain", "剧痛"], ["intense pain", "剧痛"], ["unbearable", "难以忍受"],
      ["dull pain", "钝痛"], ["dull ache", "钝痛"], ["sharp pain", "刺痛/锐痛"],
      ["stabbing", "刺痛/锐痛"], ["burning pain", "烧灼痛"], ["burning", "烧灼痛"],
      ["colicky", "绞痛"], ["cramping", "绞痛"], ["cramps", "绞痛"],
      ["pressure", "压迫感"], ["tightness", "压迫感"], ["radiating", "放射痛"],
      ["worse on exertion", "活动后加重"], ["worse with activity", "活动后加重"],
      ["relieved by rest", "休息缓解"], ["better with rest", "休息缓解"],
      ["tender to touch", "按压加重"], ["positional", "体位相关"],
      ["after eating", "进食相关"], ["after meals", "进食相关"], ["with food", "进食相关"],
      ["with fever", "伴发热"], ["with vomiting", "伴呕吐"], ["sweating", "伴出汗"],
      ["with numbness", "伴麻木"], ["with shortness of breath", "伴呼吸困难"]
    ]
  };

  // 否定 / 不确定修饰：出现在别名之前 4 个字符内即抑制该次匹配。
  var RE_NEG = /(没有|没|并无|否认|排除|未见|不伴|不是|无|不)\s*$/;
  var RE_NEG_EN = /\b(?:no|not|without|denies|deny|negative for|free of)\s+$/i;
  var RE_HEDGE = /(可能|好像|大概|也许|或许|不确定|疑似|怀疑)\s*$/;
  var RE_HEDGE_EN = /(?:maybe|possibly|perhaps|might be|not sure)\s+$/i;

  var SORTED = {};
  Object.keys(RULES).forEach(function (kind) {
    SORTED[kind] = RULES[kind].slice().sort(function (a, b) { return b[0].length - a[0].length; });
  });

  /**
   * 确定性抽取：只输出已存在的规范圈选项，其余一律留在患者原话里。
   *
   * 「按类别消费字符跨度」是关键：别名按长度降序处理，命中或被否定抑制后
   * 都把该段字符标记为已消费，短别名不得再从长短语内部二次匹配。
   * 否则 "没有疼痛" 会先被长别名「疼痛」判定为否定，随后单字别名「痛」
   * 的前缀变成 "没有疼" 而绕过否定检测，误圈「疼痛」。
   * 消费按类别独立，保证 "伴呼吸困难" 同时命中「伴随症状」与「呼吸困难」。
   */
  function extract(rawText) {
    var text = String(rawText || "").toLowerCase();
    var out = { parts: [], symptoms: [], details: [], suppressed: [], quote: String(rawText || "").trim() };
    Object.keys(SORTED).forEach(function (kind) {
      var consumed = new Array(text.length);
      SORTED[kind].forEach(function (rule) {
        var alias = rule[0], target = rule[1];
        if (out[kind].indexOf(target) !== -1) return;   // 已命中就不再找同义别名
        var pos = 0, hit = false, blocked = false, idx, end, i, overlap, before;
        while ((idx = text.indexOf(alias, pos)) !== -1) {
          end = idx + alias.length;
          overlap = false;
          for (i = idx; i < end; i += 1) { if (consumed[i]) { overlap = true; break; } }
          if (!overlap) {
            before = text.slice(Math.max(0, idx - 6), idx);
            var neg = RE_NEG.test(before) || RE_NEG_EN.test(before) ||
              RE_HEDGE.test(before) || RE_HEDGE_EN.test(before);
            for (i = idx; i < end; i += 1) consumed[i] = true;
            if (neg) { blocked = true; }
            else { hit = true; break; }
          }
          pos = end;
        }
        if (hit) out[kind].push(target);
        else if (blocked && out.suppressed.indexOf(target) === -1) out.suppressed.push(target);
      });
    });
    out.parts.sort(function (a, b) { return PARTS.indexOf(a) - PARTS.indexOf(b); });
    out.symptoms.sort(function (a, b) { return SYMPTOMS.indexOf(a) - SYMPTOMS.indexOf(b); });
    out.details.sort(function (a, b) { return DETAILS.indexOf(a) - DETAILS.indexOf(b); });
    return out;
  }

  /* ---------------- 既有采集表（只读 DOM 操作，不改 patient-check.js） ---------------- */
  var CHIP_BOXES = { parts: "pc-parts-chips", symptoms: "pc-symptoms-chips", details: "pc-details-chips" };
  var core = null;
  var snapshot = null;

  function byId(id) { return document.getElementById(id); }
  function t(zh, en) { return core ? core.t(zh, en) : zh; }
  function chipNodes(boxId) {
    var box = byId(boxId);
    return box ? Array.prototype.slice.call(box.querySelectorAll(".pc-chip")) : [];
  }
  function setChip(node, on) {
    node.classList.toggle("is-on", on);
    node.setAttribute("aria-pressed", on ? "true" : "false");
    var mark = node.querySelector(".pc-chip__mark");
    if (mark) mark.textContent = on ? "✓" : "";
  }
  function onValues(boxId) {
    return chipNodes(boxId).filter(function (n) { return n.classList.contains("is-on"); })
      .map(function (n) { return n.getAttribute("data-value"); });
  }
  function takeSnapshot() {
    return {
      parts: onValues(CHIP_BOXES.parts), symptoms: onValues(CHIP_BOXES.symptoms),
      details: onValues(CHIP_BOXES.details), freeText: byId("pc-free-text").value
    };
  }
  function applySnapshot(snap) {
    Object.keys(CHIP_BOXES).forEach(function (kind) {
      var wanted = (snap && snap[kind]) || [];
      chipNodes(CHIP_BOXES[kind]).forEach(function (node) {
        setChip(node, wanted.indexOf(node.getAttribute("data-value")) !== -1);
      });
    });
    byId("pc-free-text").value = (snap && snap.freeText) || "";
  }
  function fillForm(result, transcript) {
    applySnapshot(snapshot);                       // 每次重算都从确认前的状态出发，避免叠加
    Object.keys(CHIP_BOXES).forEach(function (kind) {
      var wanted = result[kind] || [];
      chipNodes(CHIP_BOXES[kind]).forEach(function (node) {
        var value = node.getAttribute("data-value");
        if (wanted.indexOf(value) !== -1) setChip(node, true);
      });
    });
    var base = (snapshot && snapshot.freeText) ? snapshot.freeText.replace(/\s+$/, "") : "";
    var quote = String(transcript || "").trim().slice(0, 1000);
    byId("pc-free-text").value = base ? (base + "\n" + quote).slice(0, 1000) : quote;
  }

  /* ---------------- 独立预览（绝不调用 render()） ---------------- */
  function chipLabel(value) {
    if (!core || !core.isEn()) return value;
    var mapped = core.t(value, "");
    return mapped || value;
  }
  function groupHtml(label, items) {
    if (!items.length) return "";
    return '<div class="voice-preview__group"><span class="voice-preview__label">' +
      core.esc(label) + "</span>" + items.map(function (value) {
        return '<span class="voice-preview__tag">' + core.esc(chipLabel(value)) + "</span>";
      }).join("") + "</div>";
  }
  function renderPreview(result) {
    var box = byId("voice-check-preview");
    if (!box) return;
    var html = "";
    html += '<div class="voice-preview__head"><strong>' +
      core.esc(t("自动识别到的圈选项（请核对）", "Auto-matched selections (please review)")) +
      "</strong><span>" + core.esc(t("预览 · 未生成告知单", "Preview · no sheet generated")) + "</span></div>";
    html += groupHtml(t("01 不适部位", "01 Affected areas"), result.parts);
    html += groupHtml(t("02 不适症状", "02 Symptoms"), result.symptoms);
    html += groupHtml(t("03 症状细节", "03 Symptom details"), result.details);
    if (!result.parts.length && !result.symptoms.length && !result.details.length) {
      html += '<p class="voice-preview__empty">' + core.esc(t(
        "没有匹配到明确的圈选项。识别文本会完整保留在「患者原话」里，系统不会猜测标签。",
        "No clear selection matched. The transcript is kept verbatim under the patient's own words; no labels are guessed.")) +
        "</p>";
    }
    html += '<div class="voice-preview__quote"><span>' +
      core.esc(t("04 患者原话（照录，不改写）", "04 Patient's own words (verbatim)")) +
      "</span><p>" + core.esc(result.quote) + "</p></div>";
    if (result.suppressed.length) {
      html += '<p class="voice-preview__note">' + core.esc(t(
        "已按否定 / 不确定表述跳过：" , "Skipped due to negation or uncertainty: ")) +
        core.esc(result.suppressed.map(chipLabel).join("；")) + "</p>";
    }
    html += '<p class="voice-preview__boundary">' + core.esc(t(
      "本预览只做内容转达：不翻译、不诊断、不评估表达质量，不澄清文化或信息问题；确认前不生成告知单、不写入本地缓存、不保存到云端。",
      "This preview only relays content: no translation, no diagnosis, no language-quality judgement, and no cultural or information clarification. Nothing is generated, cached or saved to the cloud before you confirm.")) +
      "</p>";
    box.innerHTML = html;
    box.hidden = false;
  }
  function clearPreview() {
    var box = byId("voice-check-preview");
    if (box) { box.innerHTML = ""; box.hidden = true; }
  }
  function run(text) {
    var transcript = String(text || "").trim();
    if (!transcript) { clearPreview(); if (snapshot) applySnapshot(snapshot); return; }
    if (!snapshot) snapshot = takeSnapshot();
    var result = extract(transcript);
    fillForm(result, transcript);
    renderPreview(result);
  }

  /* ---------------- 确认 / 撤销 ---------------- */
  function submitExistingForm() {
    var form = byId("pc-form");
    if (!form) return;
    clearPreview();
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  }
  function undo() {
    if (snapshot) applySnapshot(snapshot);
    snapshot = null;
    clearPreview();
  }

  function mount() {
    if (!window.VoiceCore || !byId("voice-box") || !byId("pc-form")) return;
    core = window.VoiceCore.mount({
      demoSample: "我从今天早上开始上腹部一阵一阵地绞痛，剧痛，进食相关，还伴呕吐，没有发烧。",
      demoSampleEn: "Since this morning I have had intermittent colicky pain in the upper abdomen, severe pain, worse after eating, with vomiting, no fever.",
      applyLabel: { zh: "确认并生成告知单", en: "Confirm & build handoff sheet" },
      applyOnlyLabel: { zh: "仅填入表单", en: "Fill the form only" },
      applyNote: {
        zh: "识别后已自动填入上方采集表并生成预览；确认后才调用既有的「生成给医生的告知单」，撤销可完整还原。",
        en: "The form above is auto-filled and previewed after recognition. Only on confirm is the existing 'Generate handoff sheet' action used; Undo fully restores the form."
      },
      onResult: function (text) { run(text); },
      onTextChange: function (text) { run(text); },
      onApply: function () { submitExistingForm(); snapshot = null; },
      onApplyOnly: function () {
        clearPreview(); snapshot = null;
        window.VoiceCore.toast(t("已填入采集表，未生成告知单。", "Form filled; no sheet generated."), "success");
      },
      onUndo: undo
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();

  // 暴露给本地自检 / 教学演示：纯函数，不触碰 DOM。
  window.VoiceCheckExtract = extract;
})();
