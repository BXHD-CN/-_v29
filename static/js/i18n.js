/* 涉外急诊语言服务台 · 全站中英双语运行时
 * - 中文模式：直接渲染源码中的中文（零改动、零风险）
 * - 英文模式：按 window.WB_I18N_DATA.dict 做「整串精确匹配」，
 *   再按 phrases 做「长键优先的子串替换」，覆盖静态 HTML、属性、
 *   JS 动态拼串、问答气泡与错误提示。
 * - 含内联标签的长段落改用 data-i18n-en 指定一次成稿的英文（[[...]] 会
 *   还原成 <strong>），避免短语拼接在标签接缝处丢空格、把英文挤成一团。
 * - 切换语言 = 记忆偏好 + 重载：保证两种语言渲染同一份 DOM / 同一批数据，
 *   内容完整一致，且不会残留上一语言的半截文本。
 * - 语料 / 术语 / 资讯 / 问答引用原文属于知识库数据，按语言服务台定位保持原语种，
 *   不参与界面翻译（标注 data-i18n-skip 的容器一律跳过）。
 */
(function () {
  "use strict";

  var DATA = window.WB_I18N_DATA || { dict: {}, phrases: [], templates: {} };
  var DICT = DATA.dict || {};
  var TEMPLATES = DATA.templates || {};
  var PHRASES = (DATA.phrases || []).slice().sort(function (a, b) {
    return b[0].length - a[0].length;
  });
  var STORAGE_KEY = "wb_lang";
  var RE_CJK = /[\u4e00-\u9fff]/;
  var ATTRS = ["placeholder", "title", "aria-label", "alt", "content", "data-label"];
  // OPTION 的文字是界面标签，需要翻译；但它的 value 属于数据，translateElement
  // 只翻译按钮类控件的 value，所以 OPTION 不进跳过名单。
  // TEXTAREA 只跳过其「文本内容」（用户输入 / 译文属于数据），属性仍要翻译，
  // 所以不放在 SKIP_TAGS 里，而由 translateText / walk 单独拦文本节点。
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1 };
  // 知识库数据容器：里面的中文是内容本身，不是界面文案，不翻译
  var SKIP_CLASS = /(?:ql-item__|ql-dval|ql-def|cx-dval|cx-quote|cx-warn|cx-vs__box|cx-meaning|cx-item__recsub|news-title|news-sub|news-summary|qa-source-full__text|qa-answer-text|pc-slip__body|pc-chief__text|pc-quote|pc-collected|cl-list__meta|tr-seg__|tr-history__item-text|tr-popover__item|term-zh|term-en|wrap-anywhere|data-table)/;

  // 知识库「枚举型」数据的英文对照：领域分类、审核状态、语种、国家/地区、
  // 文化表达类型、禁忌级别、资讯来源等。这些值来自数据库而不是界面文案，
  // 界面字典未覆盖，单独维护，避免把数据枚举混进以中文原文为键的翻译字典。
  // I18N.data() 只做整串精确匹配，不做短语替换，保证数据原文不被改写。
  var DATA_EN = {
    // 15 个领域分类 + 本地语扩展
    "分诊与接诊": "Triage & Intake",
    "病史采集与查体": "History Taking & Examination",
    "生命体征与危重症": "Vital Signs & Critical Care",
    "急救复苏与气道": "Resuscitation & Airway",
    "创伤与外科急症": "Trauma & Surgical Emergencies",
    "内科急症与中毒": "Medical Emergencies & Poisoning",
    "妇儿与精神心理": "Women, Children & Mental Health",
    "沟通与合规": "Communication & Compliance",
    "药品与用药交代": "Medication & Counselling",
    "检验与影像报告": "Lab & Imaging Reports",
    "医疗文书与证明": "Medical Records & Certificates",
    "手术与麻醉知情同意": "Surgical & Anaesthesia Consent",
    "传染病与公共卫生应急": "Communicable Disease & Public Health Emergency",
    "精神卫生与非自愿医疗": "Mental Health & Involuntary Care",
    "医疗法律与领事事务": "Medical Law & Consular Affairs",
    "东盟文化": "ASEAN Culture",
    "未分类": "Uncategorised",
    // 审核状态 / 语域 / 条目类别
    "来源核验": "Source verified",
    "待母语审校": "Pending native-speaker review",
    "书面": "Written",
    "书面语": "Written",
    "口语": "Spoken",
    "未标注": "Unspecified",
    "术语": "Terms",
    "文化表达": "Cultural expressions",
    // 语种（字典已覆盖 4 个东盟语种，这里补齐其余）
    "缅甸语": "Burmese", "老挝语": "Lao", "菲律宾语": "Filipino",
    "阿拉伯语": "Arabic", "高棉语": "Khmer", "英语变体": "English variety",
    "印尼语": "Indonesian", "泰语": "Thai", "越南语": "Vietnamese", "马来语": "Malay",
    // 国家 / 地区
    "东盟通用": "ASEAN-wide", "印尼": "Indonesia", "文莱": "Brunei",
    "新加坡": "Singapore", "柬埔寨": "Cambodia", "泰国": "Thailand",
    "缅甸": "Myanmar", "老挝": "Laos", "菲律宾": "Philippines",
    "越南": "Vietnam", "马来西亚": "Malaysia",
    // 文化表达类型 / 禁忌级别
    "宗教禁忌": "Religious taboo", "文化负载词": "Culture-loaded term",
    "礼仪称谓": "Honorific address",
    "无": "None", "橙": "Orange", "红": "Red", "黄": "Yellow",
    // 资讯来源与中文化方式
    "联合国新闻": "UN News", "联合国新闻（中文版）": "UN News (Chinese)",
    "USGS 地震": "USGS Earthquakes", "中文版源": "Chinese-language source",
    "机器翻译": "Machine translation", "原文待译": "Awaiting translation"
  };

  // v=26：scripts/build_en_labels.py 从 data/app.db 生成的全量映射（727 条），
  // 覆盖 subdomain(223) / subcategory(256) / scene(204+) 等长尾中文枚举。
  // 数据库中文值保持不变（后端筛选参数），这里只用于英文模式的展示层。
  // 生成表优先，DATA_EN 仅补齐库中不存在的界面型枚举。
  var LABELS = (function () {
    var out = {};
    var generated = window.WB_I18N_LABELS || {};
    Object.keys(generated).forEach(function (key) { out[key] = generated[key]; });
    Object.keys(DATA_EN).forEach(function (key) {
      if (!Object.prototype.hasOwnProperty.call(out, key)) out[key] = DATA_EN[key];
    });
    return out;
  })();

  var current = null;

  function lang() {
    if (current) return current;
    var saved = "";
    try { saved = window.localStorage.getItem(STORAGE_KEY) || ""; } catch (err) { saved = ""; }
    current = saved === "en" ? "en" : "zh";
    return current;
  }

  function isEn() { return lang() === "en"; }

  function applyVars(text, vars) {
    if (!vars) return text;
    return String(text).replace(/\{(\w+)\}/g, function (match, key) {
      return Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : match;
    });
  }

  function replacePhrases(text) {
    var out = String(text);
    for (var index = 0; index < PHRASES.length; index++) {
      var pair = PHRASES[index];
      if (out.indexOf(pair[0]) === -1) continue;
      out = out.split(pair[0]).join(pair[1]);
    }
    return out;
  }

  /** 翻译单个字符串：整串精确 → 模板（含 {var}）→ 长键子串。
   *  注意：模板键可能只由 ASCII + 全角标点组成（如 "{name}（{code}）"），
   *  不含汉字。必须先做 DICT / TEMPLATES 精确匹配再判断「无需翻译」，
   *  否则这类模板会被提前 return，留下 "Chinese（zh）" 之类的全角残留。 */
  function t(zh, vars) {
    var source = String(zh === null || zh === undefined ? "" : zh);
    // 中文模式也要把 {var} 填回去，否则模板串会原样显示占位符。
    if (!isEn()) return applyVars(source, vars);
    if (Object.prototype.hasOwnProperty.call(DICT, source)) return applyVars(DICT[source], vars);
    if (Object.prototype.hasOwnProperty.call(TEMPLATES, source)) return applyVars(TEMPLATES[source], vars);
    if (!RE_CJK.test(source)) return applyVars(source, vars);
    var replaced = replacePhrases(source);
    return replaced === source ? source : replaced;
  }

  /** 数据枚举英文化：整串精确匹配（生成标签表 → 界面字典 → 原值），
   *  不走短语替换，避免把知识库数据原文改写成半译串。中文模式原样返回。 */
  function dataText(zh) {
    var source = String(zh === null || zh === undefined ? "" : zh);
    if (!source) return "";
    if (!isEn()) return source;
    if (Object.prototype.hasOwnProperty.call(LABELS, source)) return LABELS[source];
    if (Object.prototype.hasOwnProperty.call(DICT, source)) return DICT[source];
    return source;
  }
  /** 供列表判断某个中文元数据是否有可用的英文标签。生成表覆盖全库 727 个
   *  枚举值，因此正常情况下英文模式不会再出现未翻译的中文元数据。 */
  function dataMapped(zh) {
    var source = String(zh === null || zh === undefined ? "" : zh);
    return !!source && (Object.prototype.hasOwnProperty.call(LABELS, source) ||
      Object.prototype.hasOwnProperty.call(DICT, source));
  }
  /** 数据字段别名：label() 用于「只有中文」的元数据标签。 */
  function label(zh) { return dataText(zh); }
  /** 中英双版本字段：英文模式英文主行 / 中文副行；中文模式保持原顺序。
   *  只有中文时，英文模式优先用生成的英文标签做主行，中文降为副行。 */
  function pair(zh, en) {
    var a = zh === null || zh === undefined ? "" : String(zh);
    var b = en === null || en === undefined ? "" : String(en);
    if (!isEn()) return { primary: a, secondary: b };
    if (b) return { primary: b, secondary: a };
    var mapped = dataText(a);
    return mapped !== a ? { primary: mapped, secondary: a } : { primary: a, secondary: "" };
  }

  function skipped(element) {
    if (!element || element.nodeType !== 1) return false;
    if (element.hasAttribute && element.hasAttribute("data-i18n-skip")) return true;
    if (SKIP_TAGS[element.tagName]) return true;
    var cls = element.className || "";
    if (typeof cls === "string" && SKIP_CLASS.test(cls)) return true;
    return false;
  }

  function translateText(node) {
    var raw = node.nodeValue;
    if (!raw || !RE_CJK.test(raw)) return;
    var parent = node.parentNode;
    if (parent && (parent.tagName === "TEXTAREA" || skipped(parent))) return;
    var trimmed = raw.trim();
    if (trimmed && Object.prototype.hasOwnProperty.call(DICT, trimmed)) {
      var exact = DICT[trimmed];
      if (exact !== trimmed) node.nodeValue = raw.replace(trimmed, exact);
      return;
    }
    // HTML 源码里的长句常被换行 / 缩进切开；折叠空白后再做一次整串匹配，
    // 保证长说明文字（首页、云端资产、告知单说明）在英文模式下也整段替换。
    var collapsed = trimmed.replace(/\s+/g, " ");
    if (collapsed !== trimmed && Object.prototype.hasOwnProperty.call(DICT, collapsed)) {
      node.nodeValue = raw.replace(trimmed, DICT[collapsed]);
      return;
    }
    var replaced = replacePhrases(raw);
    if (replaced !== raw) node.nodeValue = replaced;
  }

  function translateAttr(element, name) {
    if (!element.hasAttribute(name)) return;
    var raw = element.getAttribute(name) || "";
    if (!raw || !RE_CJK.test(raw)) return;
    var trimmed = raw.trim();
    var out = null;
    if (Object.prototype.hasOwnProperty.call(DICT, trimmed)) out = DICT[trimmed];
    else {
      var replaced = replacePhrases(raw);
      if (replaced !== raw) out = replaced;
    }
    if (out !== null && out !== raw) element.setAttribute(name, out);
  }

  function translateElement(element) {
    if (skipped(element)) return;
    // value 仅翻译按钮类控件；<option>/<input> 的 value 是数据，不动
    if (element.tagName === "INPUT" || element.tagName === "BUTTON") {
      var type = (element.getAttribute("type") || "").toLowerCase();
      if (element.tagName === "BUTTON" || type === "submit" || type === "button" || type === "reset") {
        translateAttr(element, "value");
      }
    }
    for (var i = 0; i < ATTRS.length; i++) translateAttr(element, ATTRS[i]);
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { translateText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) {
      if (skipped(root)) return;
      translateElement(root);
    }
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode: function (node) {
        if (node.nodeType === 1 && skipped(node)) return NodeFilter.FILTER_REJECT;
        if (node.nodeType === 3 && node.parentNode && node.parentNode.tagName === "TEXTAREA") return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var node = walker.nextNode();
    while (node) {
      if (node.nodeType === 3) translateText(node);
      else translateElement(node);
      node = walker.nextNode();
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * 长段落「整段英文」替换。
   * 中文长句被 <strong> 切成多个文本节点时，逐节点做短语子串替换会在接缝处
   * 丢空格（如 "typedAffected"、"relays:No"），英文读起来很挤。凡带
   * data-i18n-en 的元素，英文模式直接写入一次成稿的完整英文文案，不参与
   * 短语拼接；文案中 [[...]] 还原成 <strong>，与中文版强调位置对应。
   * 处理过的元素加 data-i18n-skip，避免运行时与 MutationObserver 二次翻译。
   */
  function swapEnBlocks(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll ? scope.querySelectorAll("[data-i18n-en]") : [];
    Array.prototype.forEach.call(nodes, function (element) {
      if (element.getAttribute("data-i18n-applied") === "1") return;
      var raw = element.getAttribute("data-i18n-en") || "";
      var html = escapeHtml(raw).replace(/\[\[(.+?)\]\]/g, "<strong>$1</strong>");
      element.innerHTML = html;
      element.setAttribute("data-i18n-applied", "1");
      element.setAttribute("data-i18n-skip", "");
    });
  }

  function apply(root) {
    if (!isEn()) return;
    try { walk(root || document.documentElement); } catch (err) {
      if (window.console) window.console.warn("i18n apply:", err);
    }
  }

  var pending = null;
  var scheduled = false;
  function schedule(nodes) {
    if (!isEn()) return;
    pending = pending ? pending.concat(nodes) : nodes;
    if (scheduled) return;
    scheduled = true;
    // 关键：不要只用 requestAnimationFrame 触发翻译。后台标签页 / 无合成器
    // （headless、省电模式）里 RAF 可能永远不触发，pending 会永久卡住，
    // 导致后续所有动态插入的中文界面文案都不翻译。setTimeout 是确定性兜底。
    setTimeout(function () {
      scheduled = false;
      var list = pending || [];
      pending = null;
      for (var i = 0; i < list.length; i++) {
        try { walk(list[i]); } catch (err) {
          if (window.console) window.console.warn("i18n walk:", err);
        }
      }
    }, 0);
  }

  function observe() {
    if (!window.MutationObserver || !isEn()) return;
    var observer = new MutationObserver(function (records) {
      var nodes = [];
      for (var i = 0; i < records.length; i++) {
        var rec = records[i];
        if (rec.type === "childList") {
          for (var j = 0; j < rec.addedNodes.length; j++) nodes.push(rec.addedNodes[j]);
        } else if (rec.type === "characterData") {
          nodes.push(rec.target);
        } else if (rec.type === "attributes") {
          nodes.push(rec.target);
        }
      }
      if (nodes.length) schedule(nodes);
    });
    observer.observe(document.documentElement, {
      childList: true, subtree: true, characterData: true,
      attributes: true, attributeFilter: ATTRS.concat(["value"])
    });
  }

  function setLang(next) {
    var value = next === "en" ? "en" : "zh";
    try { window.localStorage.setItem(STORAGE_KEY, value); } catch (err) { /* 隐私模式 */ }
    document.documentElement.lang = value === "en" ? "en" : "zh-CN";
    // 保留当前查询串（含发布平台的 sharecode），避免切换语言后访问会话丢失
    window.location.reload();
  }

  function toggle() { setLang(isEn() ? "zh" : "en"); }

  /** 页头 / 页脚共用的语言切换器；容器标记 data-i18n-skip，按钮文字不被二次翻译。 */
  function switcherHtml() {
    var active = lang();
    var ariaLabel = active === "en" ? "Language" : "语言";
    return '<div class="lang-switch" role="group" aria-label="' + ariaLabel + '" data-i18n-skip>' +
      '<button type="button" class="lang-switch__btn' + (active === "zh" ? " is-active" : "") +
        '" data-lang="zh" aria-pressed="' + (active === "zh" ? "true" : "false") + '">中文</button>' +
      '<span class="lang-switch__sep" aria-hidden="true">/</span>' +
      '<button type="button" class="lang-switch__btn' + (active === "en" ? " is-active" : "") +
        '" data-lang="en" aria-pressed="' + (active === "en" ? "true" : "false") + '">EN</button>' +
      '</div>';
  }

  function bindSwitcher(root) {
    var scope = root || document;
    var buttons = scope.querySelectorAll ? scope.querySelectorAll(".lang-switch__btn") : [];
    Array.prototype.forEach.call(buttons, function (button) {
      if (button.getAttribute("data-lang-bound") === "1") return;
      button.setAttribute("data-lang-bound", "1");
      button.addEventListener("click", function () {
        var target = button.getAttribute("data-lang") || "zh";
        if (target !== lang()) setLang(target);
      });
    });
  }

  // 立即同步 <html lang>，避免英文模式下先闪一帧中文 lang 标记
  try {
    document.documentElement.lang = isEn() ? "en" : "zh-CN";
  } catch (err) { /* 忽略 */ }

  window.I18N = {
    t: t,
    data: dataText,
    dataMapped: dataMapped,
    label: label,
    pair: pair,
    labels: LABELS,
    lang: lang,
    isEn: isEn,
    setLang: setLang,
    toggle: toggle,
    apply: apply,
    switcherHtml: switcherHtml,
    bindSwitcher: bindSwitcher,
    meta: DATA.meta || {}
  };

  function onReady() {
    // 先做整段英文替换，再启动逐节点翻译与 MutationObserver：
    // swapEnBlocks 给元素打上 data-i18n-skip，后续 walk / observe 都会跳过，
    // 且此时 observer 尚未启动，替换 innerHTML 不会触发回环。
    if (isEn()) swapEnBlocks(document.documentElement);
    apply(document.documentElement);
    observe();
    bindSwitcher(document);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
