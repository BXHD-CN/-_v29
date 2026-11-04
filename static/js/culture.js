/* 跨文化表达 · 语言质量模块内的子功能：文化表达与禁忌（738）+ 英语变体改写（150）
 * 依赖 app.js 暴露的 window.App（api / escapeHtml / toast）
 * 不再自动启动：由 quality.js 切到「跨文化表达」Tab 时调用 window.CulturePage.mount()。
 */
"use strict";

(function () {
  var App = window.App;
  if (!App) return;

  var PAGE_SIZE = 20;
  var state = {
    tab: "culture",       // culture | variants
    q: "",
    country: "",
    ctype: "",
    level: "",
    variant: "",
    page: 1,
    total: 0,
    pages: 1,
    items: [],
    activeId: null,
    metaLoaded: false,
    reqSeq: 0
  };

  var meta = { culture: null, variants: null };

  function byId(id) { return document.getElementById(id); }
  function esc(v) { return App.escapeHtml(v); }
  function num(v) { return App.fmtNumber(v); }

  /* v=26 英文优先：数据库里的国家、类型、级别、场景、子类等只有中文枚举，
     通过生成表 I18N.label() 换成英文显示；<option value> 与后端筛选参数
     仍然保持中文原值，避免筛选失效。 */
  function isEn() {
    return !!(window.I18N && typeof window.I18N.lang === "function" && window.I18N.lang() === "en");
  }
  function labelOf(zh) {
    return (window.I18N && typeof window.I18N.label === "function")
      ? window.I18N.label(zh) : (zh === null || zh === undefined ? "" : String(zh));
  }
  function pairOf(zh, en) {
    if (!isEn()) return { primary: zh || "", secondary: en || "" };
    return en ? { primary: en, secondary: zh || "" } : { primary: zh || "", secondary: "" };
  }
  function countSuffix(n) { return n ? (isEn() ? " (" + n + ")" : "（" + n + "）") : ""; }

  function setOptions(select, list, placeholder) {
    if (!select) return;
    var current = select.value;
    var html = '<option value="">' + esc(tr(placeholder || "全部")) + "</option>";
    (list || []).forEach(function (item) {
      html += '<option value="' + esc(item.name) + '">' + esc(labelOf(item.name)) +
        countSuffix(num(item.count)) + "</option>";
    });
    select.innerHTML = html;
    if (current && list && list.some(function (i) { return i.name === current; })) {
      select.value = current;
    } else {
      select.value = "";
    }
  }

  // ---------------- 元数据 ----------------
  async function loadMeta() {
    try {
      var results = await Promise.all([
        App.api("/api/culture/meta", { silent: true }),
        App.api("/api/variants/meta", { silent: true })
      ]);
      meta.culture = results[0];
      meta.variants = results[1];
      applyMeta();
      state.metaLoaded = true;
    } catch (error) {
      if (window.console) console.error(error);
    }
  }

  function applyMeta() {
    var c = meta.culture;
    var v = meta.variants;

    if (c) {
      byId("cx-num-culture").textContent = num(c.total);
      setOptions(byId("cx-filter-country"), c.countries, "全部国家");
      setOptions(byId("cx-filter-type"), c.types, "全部类型");
      setOptions(byId("cx-filter-level"), c.levels, "全部级别");
    }
    if (v) {
      byId("cx-num-variants").textContent = num(v.total);
      setOptions(byId("cx-filter-variant"), v.variants, "全部变体");
    }
    if (c && v) {
      byId("cx-head-count").textContent =
        tr("文化表达 {n} 条 · 英语变体 {v} 条 · 覆盖 {c} 个国家与地区", {
          n: num(c.total), v: num(v.total), c: c.countries ? c.countries.length : 0
        });
    }
  }

  // ---------------- 列表 ----------------
  function buildQuery() {
    var params = ["page=" + state.page, "page_size=" + PAGE_SIZE];
    if (state.q) params.push("q=" + encodeURIComponent(state.q));
    if (state.country) params.push("country=" + encodeURIComponent(state.country));
    if (state.tab === "culture") {
      if (state.ctype) params.push("ctype=" + encodeURIComponent(state.ctype));
      if (state.level) params.push("level=" + encodeURIComponent(state.level));
      return "/api/culture?" + params.join("&");
    }
    if (state.variant) params.push("variant=" + encodeURIComponent(state.variant));
    return "/api/variants?" + params.join("&");
  }

  function levelClass(level) {
    return level && ["红", "橙", "黄"].indexOf(level) >= 0 ? level : "无";
  }

  function cultureItemHtml(item) {
    // rec_en 是本模块的主推表述，英文模式保持英文主行、中文降为副行；
    // 中文模式沿用原有「推荐英文」单行展示，不改变既有阅读习惯。
    var pair = pairOf(item.rec_zh || "", item.rec_en || "");
    var rec = isEn() ? (pair.primary || item.rec_en || "") : (item.rec_en || item.rec_zh || "");
    var sub = isEn() ? pair.secondary : "";
    return '<li class="cx-item' + (String(item.id) === String(state.activeId) ? " is-active" : "") +
      '" data-id="' + item.id + '" data-expr="' + esc(item.expr_id) + '" tabindex="0" role="button">' +
      '<div class="cx-item__top">' +
      '<span class="cx-item__orig">' + esc(item.original) + "</span>" +
      '<span class="cx-lv cx-lv--' + levelClass(item.taboo_level) + '">' + esc(labelOf(item.taboo_level || "无")) + "</span>" +
      "</div>" +
      '<div class="cx-item__rec">' + esc(rec) + "</div>" +
      (sub ? '<div class="cx-item__recsub" lang="zh" data-i18n-skip>' + esc(sub) + "</div>" : "") +
      '<div class="cx-item__meta">' +
      '<span class="cx-chip cx-chip--rose">' + esc(labelOf(item.country)) + "</span>" +
      '<span class="cx-chip">' + esc(labelOf(item.ctype)) + "</span>" +
      (item.scene ? '<span class="cx-chip">' + esc(labelOf(item.scene)) + "</span>" : "") +
      '<span class="cx-chip">' + esc(item.expr_id) + "</span>" +
      "</div></li>";
  }

  function variantItemHtml(item) {
    return '<li class="cx-item' + (String(item.id) === String(state.activeId) ? " is-active" : "") +
      '" data-id="' + item.id + '" data-expr="' + esc(item.variant_id) + '" tabindex="0" role="button">' +
      '<div class="cx-item__top">' +
      '<span class="cx-item__orig">' + esc(item.original) + "</span>" +
      "</div>" +
      '<div class="cx-item__rec">→ ' + esc(item.standard_en) + "</div>" +
      '<div class="cx-item__meta">' +
      '<span class="cx-chip cx-chip--rose">' + esc(item.variant) + "</span>" +
      '<span class="cx-chip">' + esc(labelOf(item.country)) + "</span>" +
      '<span class="cx-chip">' + esc(item.variant_id) + "</span>" +
      "</div></li>";
  }

  function renderList() {
    var host = byId("cx-items");
    var empty = byId("cx-list-empty");
    var loading = byId("cx-list-loading");
    if (!host) return;
    host.innerHTML = state.items.map(function (item) {
      return state.tab === "culture" ? cultureItemHtml(item) : variantItemHtml(item);
    }).join("");
    empty.hidden = state.items.length !== 0;
    loading.hidden = true;
    byId("cx-list-count").textContent = tr("共 {n} 条", { n: num(state.total) });
    byId("cx-list-hint").textContent = state.items.length ? "" : "可调整筛选条件";
    byId("cx-page-info").textContent = tr("第 {p} / {t} 页", { p: state.page, t: state.pages });
    byId("cx-prev").disabled = state.page <= 1;
    byId("cx-next").disabled = state.page >= state.pages;
    byId("cx-pager").hidden = state.pages <= 1;

    Array.prototype.forEach.call(host.querySelectorAll(".cx-item"), function (node) {
      node.addEventListener("click", function () {
        openDetail(node.getAttribute("data-expr"));
      });
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openDetail(node.getAttribute("data-expr"));
        }
      });
    });
  }

  async function loadList(resetDetail) {
    var seq = ++state.reqSeq;
    byId("cx-list-loading").hidden = false;
    byId("cx-list-empty").hidden = true;
    try {
      var data = await App.api(buildQuery(), { silent: true });
      if (seq !== state.reqSeq) return;
      state.total = data.total || 0;
      state.pages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
      state.items = data.items || [];
      renderList();
      if (resetDetail) clearDetail();
    } catch (error) {
      if (seq !== state.reqSeq) return;
      byId("cx-list-loading").hidden = true;
      state.items = [];
      state.total = 0;
      state.pages = 1;
      renderList();
      if (window.console) console.error(error);
      App.toast("加载失败：" + (error.message || "请稍后重试"), "error");
    }
  }

  // ---------------- 详情 ----------------
  function clearDetail() {
    state.activeId = null;
    byId("cx-detail-empty").hidden = false;
    byId("cx-detail-body").hidden = true;
    byId("cx-detail-head").hidden = true;
    byId("cx-detail-body").innerHTML = "";
  }

  function sourcesHtml(list) {
    if (!list || !list.length) {
      return '<p class="cx-dval" style="color:var(--cx-none);font-size:13px">' +
        esc(isEn() ? "No verifiable external link is registered for this entry."
                   : "该条目未登记可核查外链。") + "</p>";
    }
    return '<div class="cx-src">' + list.map(function (s) {
      return '<div class="cx-src__item">' +
        '<div class="cx-src__name">' + esc(s.code) + "　" + esc(s.name) + "</div>" +
        (s.org ? '<div class="cx-src__org">' + esc(s.org) + "</div>" : "") +
        (s.url ? '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(s.url) + "</a>" : "") +
        "</div>";
    }).join("") + "</div>";
  }

  function row(label, value, extraClass) {
    if (!value) return "";
    return '<div class="cx-drow"><span class="cx-dlabel">' + esc(label) + "</span>" +
      '<div class="cx-dval' + (extraClass ? " " + extraClass : "") + '">' + esc(value) + "</div></div>";
  }

  function cultureDetailHtml(d) {
    var html = '<h2 class="cx-dtitle">' + esc(d.original) + "</h2>" +
      '<p class="cx-dsub">' + esc(d.expr_id) + " · " + esc(labelOf(d.country)) + " · " + esc(labelOf(d.ctype)) +
      (d.subcategory ? " / " + esc(labelOf(d.subcategory)) : "") +
      " · " + esc(tr("禁忌级别")) + ' <span class="cx-lv cx-lv--' + levelClass(d.taboo_level) + '">' +
      esc(labelOf(d.taboo_level)) + "</span></p>";

    // 英文模式：英文主推表述与英文例句在前，中文原文作为次级「source data」呈现。
    html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("推荐英文")) + "</span>" +
      '<div class="cx-dval cx-dval--big">' + esc(d.rec_en || "—") + "</div></div>";
    if (isEn() && d.example_en) {
      html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("英文例句")) + "</span>" +
        '<div class="cx-dval cx-dval--en">' + esc(d.example_en) + "</div></div>";
    }
    if (isEn()) {
      html += '<div class="cx-dsection">' + esc(tr("Original Chinese notes · source data")) + "</div>";
    }
    html += row(tr("推荐中文"), d.rec_zh);
    html += row(tr("原词语言"), labelOf(d.original_lang));
    html += row(tr("字面义"), d.literal_zh);

    if (d.risk) {
      html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("直译风险")) + "</span>" +
        '<div class="cx-warn">' + esc(d.risk) + "</div></div>";
    }
    if (d.usage_note) {
      html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("语用与禁忌提示")) + "</span>" +
        '<div class="cx-quote">' + esc(d.usage_note) + "</div></div>";
    }

    html += row(tr("使用场景"), labelOf(d.scene));
    if (d.example_zh) {
      html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("中文例句")) + "</span>" +
        '<div class="cx-dval">' + esc(d.example_zh) + "</div></div>";
    }
    if (!isEn() && d.example_en) {
      html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("英文例句")) + "</span>" +
        '<div class="cx-dval cx-dval--en">' + esc(d.example_en) + "</div></div>";
    }
    html += row(tr("来源文件"), d.source_file);
    html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("可核查来源")) + "</span>" + sourcesHtml(d.sources) + "</div>";
    return html;
  }

  function variantDetailHtml(d) {
    var html = '<h2 class="cx-dtitle">' + esc(d.original) + "</h2>" +
      '<p class="cx-dsub">' + esc(d.variant_id) + " · " + esc(d.variant) + " · " + esc(labelOf(d.country)) + "</p>";

    html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("原句 → 标准英语")) + '</span><div class="cx-vs">' +
      '<div class="cx-vs__box cx-vs__box--src"><div class="cx-vs__label">' + esc(tr("变体原句")) + "</div>" + esc(d.original) + "</div>" +
      '<div class="cx-vs__box cx-vs__box--dst"><div class="cx-vs__label">' + esc(tr("标准英语")) + "</div>" + esc(d.standard_en) + "</div>" +
      "</div></div>";

    if (d.medical_en) {
      html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("医疗场景改写")) + "</span>" +
        '<div class="cx-quote">' + esc(d.medical_en) + "</div></div>";
    }

    // 中文释义 / 特征属于库内原始注记，英文模式归入次级 source data 分组
    if (isEn()) html += '<div class="cx-dsection">Original Chinese notes · source data</div>';
    html += row(tr("变体特征"), d.features);
    html += row(tr("直译成中文"), d.literal_zh);
    html += row(tr("实际意思"), d.meaning_zh);
    if (d.register_note) {
      html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("语气与礼貌提示")) + "</span>" +
        '<div class="cx-warn">' + esc(d.register_note) + "</div></div>";
    }
    html += '<div class="cx-drow"><span class="cx-dlabel">' + esc(tr("可核查来源")) + "</span>" + sourcesHtml(d.sources) + "</div>";
    return html;
  }

  async function openDetail(exprId) {
    if (!exprId) return;
    var url = state.tab === "culture"
      ? "/api/culture/" + encodeURIComponent(exprId)
      : "/api/variants/" + encodeURIComponent(exprId);
    try {
      var data = await App.api(url, { silent: true });
      state.activeId = data.id;
      byId("cx-detail-empty").hidden = true;
      byId("cx-detail-head").hidden = false;
      byId("cx-detail-badge").textContent = exprId;
      var body = byId("cx-detail-body");
      body.innerHTML = state.tab === "culture" ? cultureDetailHtml(data) : variantDetailHtml(data);
      body.hidden = false;
      body.scrollTop = 0;
      Array.prototype.forEach.call(byId("cx-items").querySelectorAll(".cx-item"), function (node) {
        node.classList.toggle("is-active", String(node.getAttribute("data-id")) === String(data.id));
      });
      if (window.matchMedia && window.matchMedia("(max-width: 980px)").matches) {
        byId("cx-detail").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      App.toast("详情加载失败：" + (error.message || "请稍后重试"), "error");
    }
  }

  // ---------------- 交互 ----------------
  function switchTab(tab) {
    if (state.tab === tab) return;
    state.tab = tab;
    state.page = 1;
    state.items = [];
    state.activeId = null;
    byId("cx-tab-culture").classList.toggle("is-active", tab === "culture");
    byId("cx-tab-culture").setAttribute("aria-selected", tab === "culture" ? "true" : "false");
    byId("cx-tab-variants").classList.toggle("is-active", tab === "variants");
    byId("cx-tab-variants").setAttribute("aria-selected", tab === "variants" ? "true" : "false");
    byId("cx-filter-type-wrap").hidden = tab !== "culture";
    byId("cx-filter-level-wrap").hidden = tab !== "culture";
    byId("cx-filter-variant-wrap").hidden = tab !== "variants";
    byId("cx-legend").hidden = tab !== "culture";
    byId("cx-search").placeholder = tab === "culture"
      ? tr("搜索原词 / 推荐译法 / 语用提示…")
      : tr("搜索原句 / 标准英语 / 中文意思…");
    clearDetail();
    loadList(true);
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(null, args); }, wait);
    };
  }

  function bind() {
    byId("cx-tab-culture").addEventListener("click", function () { switchTab("culture"); });
    byId("cx-tab-variants").addEventListener("click", function () { switchTab("variants"); });

    var onSearch = debounce(function () {
      state.q = byId("cx-search").value.trim();
      state.page = 1;
      loadList(true);
    }, 280);
    byId("cx-search").addEventListener("input", onSearch);

    byId("cx-filter-country").addEventListener("change", function () {
      state.country = this.value;
      state.page = 1;
      loadList(true);
    });
    byId("cx-filter-type").addEventListener("change", function () {
      state.ctype = this.value;
      state.page = 1;
      loadList(true);
    });
    byId("cx-filter-level").addEventListener("change", function () {
      state.level = this.value;
      state.page = 1;
      loadList(true);
    });
    byId("cx-filter-variant").addEventListener("change", function () {
      state.variant = this.value;
      state.page = 1;
      loadList(true);
    });

    byId("cx-reset").addEventListener("click", function () {
      state.q = ""; state.country = ""; state.ctype = ""; state.level = ""; state.variant = "";
      state.page = 1;
      byId("cx-search").value = "";
      ["cx-filter-country", "cx-filter-type", "cx-filter-level", "cx-filter-variant"].forEach(function (id) {
        var node = byId(id);
        if (node) node.value = "";
      });
      clearDetail();
      loadList(true);
    });

    byId("cx-prev").addEventListener("click", function () {
      if (state.page <= 1) return;
      state.page -= 1;
      loadList(false);
      byId("cx-list-count").scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    byId("cx-next").addEventListener("click", function () {
      if (state.page >= state.pages) return;
      state.page += 1;
      loadList(false);
      byId("cx-list-count").scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    byId("cx-back").addEventListener("click", function () {
      clearDetail();
      loadList(false);
    });
  }

  function tr(zh, vars) {
    if (window.I18N && typeof window.I18N.t === "function") return window.I18N.t(zh, vars);
    if (!vars) return zh;
    return String(zh).replace(/\{(\w+)\}/g, function (m, k) {
      return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m;
    });
  }
  var mounted = false;
  function init() {
    if (mounted) return;   // 幂等：Tab 来回切换不重复绑定事件、不重复拉取元数据
    mounted = true;
    bind();
    byId("cx-filter-variant-wrap").hidden = true;
    loadMeta();
    loadList(false);
  }

  // 供 quality.js 调度；unmount 保留状态，切走再切回不丢失筛选条件。
  window.CulturePage = { mount: init, unmount: function () {} };
})();
