/* ============================================================
   语言质量维护页脚本（原生 JS，无第三方库）
   - 依赖 window.App（api / requireLogin / toast / escapeHtml / fmtTime），
     缺失时使用内置兜底，保证页面可独立运行。
   - 三个 Tab：术语 / 平行语料 / 东盟本地语；公共库只读，个人库可增删改。
   ============================================================ */
(function () {
  "use strict";

  // 第 4 个 Tab = 跨文化表达（文化表达 738 条 + 英语变体 150 条）。
  // 患者快速检查表已升级为与翻译平级的一级页面 check.html，不再作为本页 Tab。
  var TABS = ["terms", "corpus", "local", "culture"];
  var TAB_LABEL = {
    terms: "术语", corpus: "平行语料", local: "东盟本地语",
    culture: "跨文化表达"
  };
  var PAGE_SIZE = 20;
  var MAX_IMPORT = 5 * 1024 * 1024;

  var state = {
    tab: "terms",
    scope: "public",
    q: "",
    page: 1,
    total: 0,
    items: [],
    meta: { terms: null, corpus: null, local: null },
    selectedId: null,
    selectedItem: null,
    mode: "view",
    pendingDelete: false,
    busy: false,
    counts: { terms: 0, corpus: 0 },
    searchTimer: 0
  };

  function byId(id) { return document.getElementById(id); }
  function closest(node, selector) {
    while (node && node !== document) {
      if (node.nodeType === 1 && node.matches && node.matches(selector)) return node;
      node = node.parentNode;
    }
    return null;
  }

  var app = window.App || null;
  function esc(value) {
    if (app && typeof app.escapeHtml === "function") return app.escapeHtml(value);
    if (value === null || value === undefined) return "";
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function fmtTime(value) {
    if (app && typeof app.fmtTime === "function") return app.fmtTime(value);
    if (!value) return "—";
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value).slice(0, 16);
    function p(n) { return n < 10 ? "0" + n : "" + n; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }
  function toast(message, kind) {
    if (app && typeof app.toast === "function") { app.toast(message, kind); return; }
    var stack = document.querySelector(".ql-toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "ql-toast-stack";
      stack.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;flex-direction:column;gap:8px";
      document.body.appendChild(stack);
    }
    var node = document.createElement("div");
    node.textContent = String(message || "");
    node.style.cssText = "max-width:320px;padding:10px 14px;border-radius:8px;font-size:13px;color:#fff;box-shadow:0 8px 24px rgba(15,23,42,.2);background:" + (kind === "error" ? "#DC2626" : "#0F172A");
    stack.appendChild(node);
    setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 3200);
  }

  function getCookie(name) {
    var list = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < list.length; i += 1) {
      var pair = list[i].split("=");
      if (decodeURIComponent(pair[0]) === name) return decodeURIComponent(pair.slice(1).join("="));
    }
    return "";
  }
  function currentPath() {
    var file = location.pathname.split("/").pop() || "quality.html";
    return file + location.search;
  }
  function redirectToLogin() {
    // 会话失效：回到登录入口重新认证（未注册访客由服务端门禁直接送注册页）。
    window.location.href = "login.html?next=" + encodeURIComponent(currentPath());
  }

  function ApiError(status, message) {
    this.status = status;
    this.message = message || "请求失败";
  }
  ApiError.prototype = Object.create(Error.prototype);

  async function localApi(path, options) {
    var opts = options || {};
    var method = String(opts.method || "GET").toUpperCase();
    var headers = {};
    var key;
    if (opts.headers) {
      for (key in opts.headers) {
        if (Object.prototype.hasOwnProperty.call(opts.headers, key)) headers[key] = opts.headers[key];
      }
    }
    var body;
    if (opts.body !== undefined && opts.body !== null) {
      if (typeof opts.body === "string") body = opts.body;
      else { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
    }
    if (window.I18N && typeof window.I18N.lang === "function") {
      headers["X-Lang"] = window.I18N.lang();
    }
    if (method !== "GET" && method !== "HEAD") {
      var csrf = getCookie("csrf_token");
      if (csrf) headers["X-CSRF-Token"] = csrf;
    }
    var response;
    try {
      response = await fetch(path, { method: method, headers: headers, body: body, credentials: "same-origin", cache: "no-store" });
    } catch (err) { throw new ApiError(0, "网络异常，请检查网络后重试"); }
    var text = await response.text();
    var data = null;
    if (text) { try { data = JSON.parse(text); } catch (parseErr) { data = text; } }
    if (!response.ok) {
      var detail = data && typeof data === "object" ? (data.detail || data.message || "") : "";
      if (typeof detail !== "string") detail = JSON.stringify(detail);
      if (response.status === 401 && !opts.authOptional) redirectToLogin();
      throw new ApiError(response.status, detail || ("请求失败（" + response.status + "）"));
    }
    return data;
  }
  function api(path, options) {
    if (app && typeof app.api === "function") {
      try { return Promise.resolve(app.api(path, options)); }
      catch (err) { return Promise.reject(err); }
    }
    return localApi(path, options);
  }
  function tr(zh, vars) {
    return (window.I18N && typeof window.I18N.t === "function")
      ? window.I18N.t(zh, vars) : applyVars(zh, vars);
  }
  function applyVars(text, vars) {
    if (!vars) return text;
    return String(text).replace(/\{(\w+)\}/g, function (m, k) {
      return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m;
    });
  }
  /* 英文模式「英文优先显示」：只调整术语 / 语料 / 例句的展示主副行顺序，
     不改动知识库数据本身（中文原文、英文译法都照原值渲染）。
     中文模式保持原有「中文主行 + 英文副行」不变。 */
  function isEn() {
    return !!(window.I18N && typeof window.I18N.lang === "function" && window.I18N.lang() === "en");
  }
  function displayPair(zh, en) {
    if (!isEn()) return { primary: zh || "", secondary: en || "" };
    if (!en) return { primary: zh || "", secondary: "" };
    return { primary: en, secondary: zh || "" };
  }
  function relPairHtml(zh, en) {
    var pair = displayPair(zh, en);
    return '<div class="ql-rel__zh">' + esc(pair.primary) + '</div>' +
      '<div class="ql-rel__en">' + esc(pair.secondary) + '</div>';
  }
  function detailHeadingHtml(zh, en, emptyZh, emptyEn) {
    if (isEn() && en) {
      return "<h2>" + esc(en) + "</h2>" + '<p class="ql-detail__sub">' + esc(zh || "") + "</p>";
    }
    return "<h2>" + esc(zh || emptyZh) + "</h2>" +
      '<p class="ql-detail__sub">' + esc(en || emptyEn) + "</p>";
  }
  /* v=26 英文优先：知识库里「只有中文」的元数据枚举（领域、场景、语体、
     审核状态、国家、禁忌级别……）通过 I18N.label() 换成英文展示；
     数据库中文原值保持不变，<option value> 与后端筛选参数仍是中文。 */
  function label(zh) {
    return (window.I18N && typeof window.I18N.label === "function")
      ? window.I18N.label(zh) : (zh === null || zh === undefined ? "" : String(zh));
  }
  function dataHtml(value) { return esc(label(value)); }
  function countSuffix(count) {
    if (!count) return "";
    return isEn() ? " (" + count + ")" : "（" + count + "）";
  }
  function optText(name, count) { return label(name) + countSuffix(count); }
  function statusOf(err) {
    if (!err) return 0;
    return err.status || err.code || (err.response && err.response.status) || 0;
  }
  function messageOf(err) {
    if (!err) return "未知错误";
    return err.message || (err.detail && String(err.detail)) || "请求失败";
  }
  async function requireAuth() {
    // 注册前置门禁由服务端 shield.py 保证；这里只读取登录态，
    // 供个人数据请求判断是否真的需要发出。
    if (app && typeof app.requireLogin === "function") {
      try { return await app.requireLogin(); } catch (err) { return null; }
    }
    return null;
  }

  /* ---------------- 提示条 ---------------- */
  function showBanner(message, kind) {
    var banner = byId("ql-banner");
    banner.hidden = false;
    banner.className = "ql-banner" + (kind === "error" ? " is-error" : kind === "ok" ? " is-ok" : "");
    byId("ql-banner-text").textContent = message;
  }
  function hideBanner() { byId("ql-banner").hidden = true; }

  /* ---------------- Tab / URL ---------------- */
  function tabFromUrl() {
    var params = new URLSearchParams(location.search);
    var tab = params.get("tab") || "";
    // 兼容旧链接：患者快速检查表已独立为 check.html
    if (tab === "patient-check" || tab === "check") return "patient-check";
    if (TABS.indexOf(tab) === -1) {
      var hash = (location.hash || "").replace("#", "").toLowerCase();
      tab = TABS.indexOf(hash) !== -1 ? hash : "terms";
    }
    return tab;
  }
  function updateUrl(tab) {
    // 只改 tab，保留原有查询参数（尤其是线上分享链接的 sharecode 会话参数），
    // 避免 replaceState 把访问会话参数抹掉导致后续请求被发布平台拒绝。
    try {
      var params = new URLSearchParams(location.search);
      params.set("tab", tab);
      history.replaceState(null, "", "quality.html?" + params.toString());
    } catch (err) { /* ignore */ }
  }
  /* ---------------- 子功能 Tab：跨文化表达（语言质量模块内） ----------------
     文化表达 / 英语变体的检索界面由 culture.js 提供，作为本页第 4 个 Tab 嵌入；
     切到该 Tab 时隐藏术语/语料的列表、工具条与详情，避免两套控件互相干扰。 */
  function showCultureTab(on) {
    // 工具条在 HTML 里只有 class、没有 id，用 class 兜底
    var toolbar = byId("ql-toolbar") || document.querySelector(".ql-toolbar");
    if (toolbar) toolbar.hidden = on;
    ["ql-body", "ql-note"].forEach(function (id) {
      var node = byId(id);
      if (node) node.hidden = on;
    });
    var banner = byId("ql-banner");
    if (banner) banner.hidden = true;   // 提示条只在有消息时显示，不随 Tab 切换被误放开
    var panel = byId("cx-panel");
    if (panel) panel.hidden = !on;
    if (on) {
      TABS.forEach(function (item) {
        var button = byId("ql-tab-" + item);
        if (!button) return;
        var active = item === "culture";
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (window.CulturePage && typeof window.CulturePage.mount === "function") window.CulturePage.mount();
    } else if (window.CulturePage && typeof window.CulturePage.unmount === "function") {
      window.CulturePage.unmount();
    }
  }
  function setTab(tab) {
    if (TABS.indexOf(tab) === -1) tab = "terms";
    if (tab === "culture") {
      state.tab = "culture";
      showCultureTab(true);
      updateUrl("culture");
      return;
    }
    showCultureTab(false);
    state.tab = tab;
    state.page = 1;
    state.q = "";
    state.selectedId = null;
    state.selectedItem = null;
    state.mode = "view";
    state.pendingDelete = false;
    byId("ql-search").value = "";
    byId("ql-search").placeholder = tr("搜索{tab}…", { tab: tr(TAB_LABEL[tab]) });
    TABS.forEach(function (item) {
      var btn = byId("ql-tab-" + item);
      var active = item === tab;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (tab === "local") setScope("public", true);
    configureFilters();
    resetDetail();
    updateUrl(tab);
    loadList();
    loadMeta(tab);
  }

  /* ---------------- 范围与筛选 ---------------- */
  function setScope(scope, silent) {
    state.scope = scope;
    var buttons = document.querySelectorAll(".ql-scope__btn");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-scope") === scope);
    });
    configureFilters();
    if (!silent) { state.page = 1; state.selectedId = null; resetDetail(); loadList(); }
  }
  function configureFilters() {
    var isLocal = state.tab === "local";
    var isMine = state.scope === "mine";
    byId("ql-scope").hidden = isLocal;
    byId("ql-filter-lang-wrap").hidden = isMine;
    byId("ql-filter-domain-wrap").hidden = isMine || state.tab !== "terms";
    byId("ql-actions").hidden = isLocal;
    byId("ql-new").hidden = isLocal;
    byId("ql-list-scope").textContent = isMine ? "我的条目" : "公共库";
    byId("ql-note").textContent = isLocal
      ? "本地语 1,040 条为只读对照数据，全部标记「待母语审校」；仅作沟通参考，不替代人工翻译。"
      : "公共库为只读资产；个人库仅自己可见，可导入导出与增删改。";
  }
  function loadMeta(tab) {
    if (state.meta[tab]) { fillFilters(); return; }
    api("/api/" + (tab === "terms" ? "terms/meta" : tab === "corpus" ? "corpus/meta" : "local-terms/meta"), { silent: true })
      .then(function (data) {
        state.meta[tab] = data || {};
        fillFilters();
      })
      .catch(function (err) {
        if (statusOf(err) === 401) { redirectToLogin(); return; }
        showBanner("筛选项加载失败：" + messageOf(err), "error");
      });
  }
  function fillFilters() {
    var langSel = byId("ql-filter-lang");
    var domSel = byId("ql-filter-domain");
    var previousLang = langSel.value;
    var previousDomain = domSel.value;
    var meta = state.meta[state.tab] || {};
    var langs = Array.isArray(meta.langs) ? meta.langs : [];
    var domains = Array.isArray(meta.domains) ? meta.domains : [];
    // <option value> 必须是数据库中文原值（含 id/ms/th/vi 等语言代码），
    // 否则后端 WHERE 失效；英文模式只替换显示文本。
    var langOptions = '<option value="">' + esc(tr("全部")) + "</option>";
    langs.forEach(function (item) {
      var value = state.tab === "local" ? (item.code || item.name) : item.name;
      if (value) langOptions += '<option value="' + esc(value) + '">' + esc(optText(item.name || item.code, item.count)) + "</option>";
    });
    langSel.innerHTML = langOptions;
    var domainOptions = '<option value="">' + esc(tr("全部")) + "</option>";
    domains.forEach(function (item) {
      if (!item || !item.name) return;
      domainOptions += '<option value="' + esc(item.name) + '">' + esc(optText(item.name, item.count)) + "</option>";
    });
    domSel.innerHTML = domainOptions;
    if (previousLang) langSel.value = previousLang;
    if (previousDomain) domSel.value = previousDomain;
  }

  /* ---------------- 列表 ---------------- */
  function listUrl() {
    var params = new URLSearchParams();
    params.set("page", String(state.page));
    params.set("page_size", String(PAGE_SIZE));
    if (state.q) params.set("q", state.q);
    if (state.scope === "public") {
      var lang = byId("ql-filter-lang").value;
      var domain = byId("ql-filter-domain").value;
      if (lang) params.set("lang", lang);
      if (domain && state.tab === "terms") params.set("domain", domain);
    }
    var path;
    if (state.scope === "mine" && state.tab !== "local") path = "/api/me/" + state.tab;
    else if (state.tab === "terms") path = "/api/terms";
    else if (state.tab === "corpus") path = "/api/corpus";
    else path = "/api/local-terms";
    return path + "?" + params.toString();
  }
  async function loadList() {
    var loading = byId("ql-list-loading");
    loading.hidden = false;
    byId("ql-list-empty").hidden = true;
    byId("ql-items").innerHTML = "";
    try {
      var data = await api(listUrl(), { silent: true });
      state.items = (data && data.items) || [];
      state.total = (data && (data.total || (data.items || []).length)) || 0;
      state.items = state.items;
      renderList();
    } catch (err) {
      state.items = [];
      state.total = 0;
      var status = statusOf(err);
      if (status === 401) { redirectToLogin(); return; }
      loading.hidden = true;
      byId("ql-list-empty").hidden = false;
      byId("ql-list-empty").textContent = "列表加载失败：" + messageOf(err);
      byId("ql-list-count").textContent = "共 0 条";
      renderPager();
    }
  }
  function renderList() {
    var loading = byId("ql-list-loading");
    loading.hidden = true;
    var list = byId("ql-items");
    byId("ql-list-count").textContent = tr("共 {n} 条", { n: state.total.toLocaleString("zh-CN") });
    var head = byId("ql-head-count");
    head.textContent = tr("{scope}{tab} · 当前 {n} 条", {
      scope: state.scope === "public" ? tr("公共") : tr("我的"),
      tab: tr(TAB_LABEL[state.tab]), n: state.total.toLocaleString("zh-CN")
    });
    if (!state.items.length) {
      list.innerHTML = "";
      byId("ql-list-empty").hidden = false;
      byId("ql-list-empty").textContent = "没有匹配的条目";
      renderPager();
      return;
    }
    byId("ql-list-empty").hidden = true;
    list.innerHTML = state.items.map(function (item, index) {
      var id = item.id;
      var active = state.selectedId === id;
      var primary = "";
      var secondary = "";
      var tags = [];
      var pair;
      if (state.tab === "local") {
        // 本地语原文属于数据内容，始终作为主行；英文模式把英文释义提到中文之前
        primary = item.local_text || item.zh || "";
        secondary = isEn()
          ? [item.en, item.zh].filter(Boolean).join(" · ")
          : [item.zh, item.en].filter(Boolean).join(" · ");
        tags.push('<span class="ql-tag">' + dataHtml(item.lang || item.lang_code || "") + "</span>");
        if (item.audit_status) tags.push('<span class="ql-tag ql-tag--warn">' + dataHtml(item.audit_status) + "</span>");
      } else if (state.tab === "corpus") {
        pair = displayPair(item.zh, item.en);
        primary = pair.primary;
        secondary = pair.secondary;
        if (item.register) tags.push('<span class="ql-tag">' + dataHtml(item.register) + "</span>");
        if (item.lang_pair) tags.push('<span class="ql-tag">' + dataHtml(item.lang_pair) + "</span>");
        if (state.scope === "mine") tags.push('<span class="ql-tag ql-tag--mine">' + esc(isEn() ? "Mine" : "我的") + "</span>");
        if (item.audit_status) tags.push('<span class="ql-tag">' + dataHtml(item.audit_status) + "</span>");
      } else {
        pair = displayPair(item.zh, item.en);
        primary = pair.primary;
        secondary = pair.secondary;
        if (item.lang_pair) tags.push('<span class="ql-tag">' + dataHtml(item.lang_pair) + "</span>");
        if (item.domain) tags.push('<span class="ql-tag">' + dataHtml(item.domain) + "</span>");
        if (state.scope === "mine") tags.push('<span class="ql-tag ql-tag--mine">' + esc(isEn() ? "Mine" : "我的") + "</span>");
        if (item.audit_status) tags.push('<span class="ql-tag">' + dataHtml(item.audit_status) + "</span>");
      }
      return '<li><button class="ql-item' + (active ? " is-active" : "") + '" type="button" data-index="' + index + '"' +
        (active ? ' aria-current="true"' : "") + ">" +
        '<span class="ql-item__zh">' + esc(primary) + "</span>" +
        (secondary ? '<span class="ql-item__en">' + esc(secondary) + "</span>" : "") +
        (tags.length ? '<span class="ql-item__meta">' + tags.join("") + "</span>" : "") +
        "</button></li>";
    }).join("");
    renderPager();
  }
  function renderPager() {
    var pages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
    if (state.page > pages) state.page = pages;
    byId("ql-page-info").textContent = tr("第 {p} / {t} 页", { p: state.page, t: pages });
    byId("ql-prev").disabled = state.page <= 1;
    byId("ql-next").disabled = state.page >= pages;
  }
  function goPage(delta) {
    var pages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
    var next = state.page + delta;
    if (next < 1 || next > pages) return;
    state.page = next;
    loadList();
  }

  /* ---------------- 详情：公共 / 个人 / 本地语 ---------------- */
  function resetDetail() {
    state.mode = "view";
    state.pendingDelete = false;
    byId("ql-detail-head").hidden = true;
    byId("ql-detail-empty").hidden = false;
    byId("ql-detail-body").hidden = true;
    byId("ql-detail-body").innerHTML = "";
    byId("ql-detail-badge").textContent = "";
    byId("ql-detail-empty").innerHTML = "<p>从左侧选择一个条目查看详情。</p><p class=\"ql-detail__tip\">术语详情下方会列出关联语料；语料详情会显示关联术语。</p>";
    byId("ql-body").classList.remove("is-detail");
  }
  function setMobileDetail(show) {
    byId("ql-body").classList.toggle("is-detail", !!show);
  }
  function markActive(id) {
    state.selectedId = id;
    var buttons = document.querySelectorAll(".ql-item");
    Array.prototype.forEach.call(buttons, function (btn) {
      var item = state.items[parseInt(btn.getAttribute("data-index"), 10)];
      var active = item && item.id === id;
      btn.classList.toggle("is-active", !!active);
      if (active) btn.setAttribute("aria-current", "true"); else btn.removeAttribute("aria-current");
    });
  }
  async function selectItem(item) {
    if (!item) return;
    state.selectedItem = item;
    state.mode = "view";
    state.pendingDelete = false;
    markActive(item.id);
    setMobileDetail(true);
    byId("ql-detail-empty").hidden = true;
    byId("ql-detail-body").hidden = false;
    var body = byId("ql-detail-body");
    body.innerHTML = '<p class="ql-empty">正在加载详情…</p>';
    byId("ql-detail-head").hidden = false;
    byId("ql-detail-badge").textContent = tr("{tab}{scope}", { tab: tr(TAB_LABEL[state.tab]), scope: state.scope === "mine" ? tr(" · 我的条目") : tr(" · 公共库") });
    if (state.scope === "mine") {
      if (state.tab === "terms") renderTermForm(item, "edit");
      else if (state.tab === "corpus") renderCorpusForm(item, "edit");
      return;
    }
    try {
      if (state.tab === "terms") {
        var detail = await api("/api/terms/" + encodeURIComponent(item.id), { silent: true });
        renderTermDetail(detail || item);
      } else if (state.tab === "corpus") {
        var cdetail = await api("/api/corpus/" + encodeURIComponent(item.id), { silent: true });
        renderCorpusDetail(cdetail || item);
      } else {
        renderLocalDetail(item);
      }
    } catch (err) {
      if (statusOf(err) === 401) { redirectToLogin(); return; }
      body.innerHTML = '<p class="ql-empty">详情加载失败：' + esc(messageOf(err)) + "</p>";
    }
  }

  function sourceHtml(item) {
    var out = [];
    var sources = Array.isArray(item.sources) ? item.sources : [];
    sources.forEach(function (source) {
      if (!source || !source.code) return;
      var label = source.code + (source.name ? " · " + source.name : "");
      if (source.url) out.push('<a href="' + esc(source.url) + '" target="_blank" rel="noopener noreferrer">' + esc(label) + "</a>");
      else out.push("<span>" + esc(label) + "</span>");
    });
    if (!out.length && item.source_code) {
      var codes = String(item.source_code).split(/[、,，\s]+/).filter(Boolean);
      codes.forEach(function (code) {
        out.push('<a href="/api/sources/' + encodeURIComponent(code) + '" target="_blank" rel="noopener noreferrer">' + esc(code) + "</a>");
      });
    }
    if (!out.length) return '<span class="ql-tag">未标注来源</span>';
    return out.join(" ");
  }
  function tagsHtml(items) {
    return '<div class="ql-detail__tags">' + items.map(function (item) {
      if (!item) return "";
      return '<span class="ql-tag ' + esc(item.cls || "") + '">' + esc(item.text) + "</span>";
    }).join("") + "</div>";
  }
  function fieldsHtml(pairs) {
    var rendered = pairs.filter(function (pair) { return pair && pair[1] !== "" && pair[1] !== null && pair[1] !== undefined; });
    if (!rendered.length) return "";
    // dd 里是知识库原文 / 枚举数据，显式跳过界面翻译，避免短语替换把
    // 数据原文改写成半译串；英文展示由 dataHtml() 在生成时决定。
    return '<dl class="ql-fields">' + rendered.map(function (pair) {
      return "<dt>" + esc(pair[0]) + '</dt><dd data-i18n-skip>' + pair[1] + "</dd>";
    }).join("") + "</dl>";
  }
  function safeHtmlText(value) {
    if (value === null || value === undefined || value === "") return "";
    return esc(String(value));
  }
  function samplesHtml(samples) {
    if (!samples) return "";
    var rows = [];
    if (Array.isArray(samples)) {
      samples.forEach(function (sample) {
        if (sample === null || sample === undefined) return;
        if (typeof sample === "string") rows.push('<div class="ql-rel__item"><div class="ql-rel__zh">' + esc(sample) + "</div></div>");
        else if (typeof sample === "object") {
          rows.push('<div class="ql-rel__item">' + relPairHtml(sample.zh || sample.text || "", sample.en || "") + "</div>");
        }
      });
    } else if (typeof samples === "string") {
      rows.push('<div class="ql-rel__item"><div class="ql-rel__zh">' + esc(samples) + "</div></div>");
    }
    return rows.length ? '<div class="ql-rel">' + rows.join("") + "</div>" : "";
  }

  function renderTermDetail(item) {
    var tags = [];
    if (item.audit_status) tags.push({ text: label(item.audit_status), cls: /待/.test(item.audit_status) ? "ql-tag--warn" : "ql-tag--ok" });
    if (item.lang_pair) tags.push({ text: label(item.lang_pair) });
    if (item.domain) tags.push({ text: label(item.domain) + (item.subdomain ? " / " + label(item.subdomain) : "") });
    var defines = [
      ["中文释义", safeHtmlText(item.definition_zh)],
      ["英文释义", safeHtmlText(item.definition_en)]
    ];
    if (isEn()) defines.reverse();   // 英文模式：英文释义在前
    var rows = [
      ["术语编号", safeHtmlText(item.term_id)],
      ["缩写", safeHtmlText(item.abbreviation)]
    ].concat(defines, [
      ["来源文件", safeHtmlText(item.source_file)],
      ["来源", sourceHtml(item)]
    ]);
    var html = "";
    html += detailHeadingHtml(item.zh, item.en, "（无中文名）", "（无英文名）");
    html += tagsHtml(tags);
    html += fieldsHtml(rows);
    var samples = samplesHtml(item.samples);
    if (samples) html += "<h3>例句 / 用法</h3>" + samples;
    html += "<h3>关联语料</h3><div class=\"ql-rel\" id=\"ql-rel-corpus\"><p class=\"ql-empty\">正在加载关联语料…</p></div>";
    html += '<div class="ql-actions-row">' +
      '<button class="ql-btn ql-btn--primary" type="button" data-action="adopt">加入我的库</button>' +
      '<button class="ql-btn" type="button" data-action="goto-corpus">在语料中查看</button>' +
      "</div>";
    byId("ql-detail-body").innerHTML = html;
    loadRelatedCorpus(item);
  }
  function loadRelatedCorpus(item) {
    var box = byId("ql-rel-corpus");
    if (!box) return;
    var termId = item.term_id || "";
    var url = termId
      ? "/api/corpus?term_id=" + encodeURIComponent(termId) + "&page_size=5"
      : "/api/corpus?q=" + encodeURIComponent(item.zh || "") + "&page_size=5";
    api(url, { silent: true }).then(function (data) {
      var items = (data && data.items) || [];
      if (!items.length) { box.innerHTML = '<p class="ql-empty">暂无关联语料</p>'; return; }
      box.innerHTML = items.slice(0, 5).map(function (row) {
        return '<div class="ql-rel__item"><div class="ql-rel__row"><div>' + relPairHtml(row.zh || "", row.en || "") + '</div>' +
          '<button class="ql-btn ql-btn--sm" type="button" data-action="goto-corpus" data-zh="' + esc(row.zh || "") + '">查看</button></div></div>';
      }).join("") + '<p class="ql-detail__tip">' + esc(tr("共 {n} 条，仅显示前 5 条。", { n: String((data && data.total) || items.length) })) + "</p>";
    }).catch(function (err) {
      if (statusOf(err) === 401) { redirectToLogin(); return; }
      box.innerHTML = '<p class="ql-empty">关联语料加载失败：' + esc(messageOf(err)) + "</p>";
    });
  }

  function renderCorpusDetail(item) {
    var tags = [];
    if (item.audit_status) tags.push({ text: label(item.audit_status), cls: /待/.test(item.audit_status) ? "ql-tag--warn" : "" });
    if (item.lang_pair) tags.push({ text: label(item.lang_pair) });
    if (item.register) tags.push({ text: label(item.register) });
    var html = "";
    html += detailHeadingHtml(item.zh, item.en, "（无中文句）", "（无英文句）");
    html += tagsHtml(tags);
    html += fieldsHtml([
      ["语料编号", safeHtmlText(item.corpus_id)],
      ["关联术语编号", safeHtmlText(item.term_id)],
      ["领域", dataHtml(item.domain)],
      ["来源文件", safeHtmlText(item.source_file)],
      ["来源", sourceHtml(item)]
    ]);
    html += "<h3>关联术语</h3><div class=\"ql-rel\" id=\"ql-rel-term\"><p class=\"ql-empty\">正在加载关联术语…</p></div>";
    html += '<div class="ql-actions-row">' +
      '<button class="ql-btn ql-btn--primary" type="button" data-action="adopt">加入我的库</button>' +
      "</div>";
    byId("ql-detail-body").innerHTML = html;
    loadRelatedTerm(item);
  }
  function loadRelatedTerm(item) {
    var box = byId("ql-rel-term");
    if (!box) return;
    if (!item.term_id) { box.innerHTML = '<p class="ql-empty">该句对未关联术语</p>'; return; }
    function accept(row) {
      if (!row || !row.term_id) return null;
      return row.term_id === item.term_id ? row : null;
    }
    var tasks = [];
    var idMatch = /^T-(\d+)$/.exec(String(item.term_id));
    if (idMatch) tasks.push(function () {
      return api("/api/terms/" + idMatch[1], { silent: true }).then(accept).catch(function () { return null; });
    });
    tasks.push(function () {
      return api("/api/terms?q=" + encodeURIComponent(item.term_id) + "&page_size=5", { silent: true })
        .then(function (data) { return accept(((data && data.items) || [])[0]); }).catch(function () { return null; });
    });
    tasks.push(function () {
      return api("/api/terms?q=" + encodeURIComponent(String(item.zh || "").slice(0, 6)) + "&page_size=10", { silent: true })
        .then(function (data) {
          var rows = (data && data.items) || [];
          var hit = null;
          rows.forEach(function (row) { if (!hit && row.zh === item.zh) hit = row; });
          return hit;
        }).catch(function () { return null; });
    });
    var lookup = Promise.resolve(null);
    tasks.forEach(function (task) { lookup = lookup.then(function (found) { return found ? found : task(); }); });
    lookup.then(function (hit) {
      if (!hit) {
        box.innerHTML = '<p class="ql-empty">术语表中未匹配到「' + esc(String(item.zh || "").slice(0, 20)) + '」，关联编号：' + esc(item.term_id) + "</p>";
        return;
      }
      box.innerHTML = '<div class="ql-rel__item"><div class="ql-rel__row"><div>' + relPairHtml(hit.zh || "", hit.en || "") + '</div>' +
        '<button class="ql-btn ql-btn--sm" type="button" data-action="goto-term" data-zh="' + esc(hit.zh || "") + '">查看术语</button></div></div>';
    }).catch(function (err) {
      if (statusOf(err) === 401) { redirectToLogin(); return; }
      box.innerHTML = '<p class="ql-empty">关联术语加载失败：' + esc(messageOf(err)) + "</p>";
    });
  }

  function renderLocalDetail(item) {
    var tags = [{ text: label(item.lang || item.lang_code || "") }];
    if (item.audit_status) tags.push({ text: label(item.audit_status), cls: /待/.test(item.audit_status) ? "ql-tag--warn" : "ql-tag--ok" });
    if (item.category) tags.push({ text: label(item.category) });
    var html = "";
    html += "<h2>" + esc(item.local_text || item.zh || "（无本地语原文）") + "</h2>";
    html += '<p class="ql-detail__sub">' + esc(isEn()
      ? [item.en, item.zh].filter(Boolean).join(" · ")
      : [item.zh, item.en].filter(Boolean).join(" · ")) + "</p>";
    html += tagsHtml(tags);
    html += fieldsHtml([
      ["条目编号", safeHtmlText(item.local_id)],
      ["罗马化", safeHtmlText(item.romanization)],
      ["发音提示", safeHtmlText(item.pron_hint)],
      ["语用提示", safeHtmlText(item.usage_note)],
      ["领域 / 场景", esc([item.domain, item.scene].filter(Boolean).map(label).join(" / "))],
      ["来源", sourceHtml(item)]
    ]);
    if (/待/.test(String(item.audit_status || ""))) {
      html += '<p class="ql-def">' + esc(isEn()
        ? "This entry is marked " + label(item.audit_status) + ": it has not been reviewed by a native speaker. Please confirm manually before clinical use."
        : "该条目状态为「" + item.audit_status + "」：尚未经母语使用者复核，正式沟通场景请人工确认。") + "</p>";
    }
    html += '<div class="ql-actions-row"><span class="ql-detail__tip">东盟本地语为只读对照数据，不可编辑。</span></div>';
    byId("ql-detail-body").innerHTML = html;
  }

  /* ---------------- 表单：个人库增删改 ---------------- */
  function fieldHtml(id, label, value, options) {
    var opts = options || {};
    var required = opts.required ? '<span class="ql-field__req">*</span>' : "";
    if (opts.type === "textarea") {
      return '<div class="ql-field"><label for="' + id + '">' + esc(label) + required + "</label>" +
        '<textarea id="' + id + '" name="' + id + '">' + esc(value || "") + "</textarea></div>";
    }
    if (opts.type === "select") {
      // value 保留数据库中文枚举（书面/口语/语种对），显示文本在英文模式换成英文
      var optionsHtml = (opts.options || []).map(function (option) {
        var text = option ? label(option) : (isEn() ? "(empty)" : "（空）");
        return '<option value="' + esc(option) + '"' + (option === value ? " selected" : "") + ">" + esc(text) + "</option>";
      }).join("");
      return '<div class="ql-field"><label for="' + id + '">' + esc(label) + required + "</label>" +
        '<select id="' + id + '" name="' + id + '">' + optionsHtml + "</select></div>";
    }
    return '<div class="ql-field"><label for="' + id + '">' + esc(label) + required + "</label>" +
      '<input id="' + id + '" name="' + id + '" type="text" value="' + esc(value || "") + '"' +
      (opts.placeholder ? ' placeholder="' + esc(opts.placeholder) + '"' : "") + "></div>";
  }
  function formActionsHtml(showDelete) {
    return '<div class="ql-actions-row">' +
      '<button class="ql-btn ql-btn--primary" type="submit" data-action="save">保存</button>' +
      '<button class="ql-btn" type="button" data-action="cancel-edit">取消</button>' +
      (showDelete ? '<button class="ql-btn ql-btn--danger" type="button" data-action="delete">删除</button>' : "") +
      "</div>" +
      '<p class="ql-form__error" id="ql-form-error" role="alert"></p>';
  }
  function renderTermForm(item, mode) {
    state.mode = mode;
    var isEdit = mode === "edit";
    var data = item || {};
    var langOptions = ["zh-en", "zh-vi", "zh-th", "zh-id", "zh-ms", "en-zh"];
    var html = '<form class="ql-form" id="ql-form" novalidate>' +
      (isEdit ? "<h2>编辑我的术语</h2>" : "<h2>新建我的术语</h2>") +
      '<p class="ql-detail__sub">个人库仅自己可见，可自由编辑；公共库只读。</p>' +
      fieldHtml("ql-f-zh", "中文", data.zh, { required: true, placeholder: "如：预检分诊" }) +
      fieldHtml("ql-f-en", "英文", data.en, {}) +
      fieldHtml("ql-f-lang", "语种对", data.lang_pair || "zh-en", { type: "select", options: langOptions }) +
      fieldHtml("ql-f-domain", "领域", data.domain, { placeholder: "如：急诊分诊" }) +
      fieldHtml("ql-f-definition", "释义", data.definition, { type: "textarea" }) +
      fieldHtml("ql-f-note", "备注", data.note, { type: "textarea" }) +
      '<div class="ql-form__row">' +
      fieldHtml("ql-f-source-code", "来源代号", data.source_code, { placeholder: "如：T03" }) +
      fieldHtml("ql-f-source-url", "来源链接", data.source_url, { placeholder: "https://" }) +
      "</div>" +
      formActionsHtml(isEdit) +
      "</form>";
    byId("ql-detail-body").innerHTML = html;
    var first = byId("ql-f-zh");
    if (first) first.focus();
  }
  function renderCorpusForm(item, mode) {
    state.mode = mode;
    var isEdit = mode === "edit";
    var data = item || {};
    var langOptions = ["zh-en", "zh-vi", "zh-th", "zh-id", "zh-ms", "en-zh"];
    var html = '<form class="ql-form" id="ql-form" novalidate>' +
      (isEdit ? "<h2>编辑我的语料</h2>" : "<h2>新建我的语料</h2>") +
      '<p class="ql-detail__sub">句对要求中英文都填写；从公共库「加入我的库」会复制为独立副本。</p>' +
      fieldHtml("ql-f-zh", "中文句", data.zh, { required: true, type: "textarea" }) +
      fieldHtml("ql-f-en", "英文句", data.en, { required: true, type: "textarea" }) +
      fieldHtml("ql-f-lang", "语种对", data.lang_pair || "zh-en", { type: "select", options: langOptions }) +
      fieldHtml("ql-f-register", "语体", data.register || "", { type: "select", options: ["", "书面", "口语"] }) +
      fieldHtml("ql-f-term-id", "关联术语编号", data.term_id, { placeholder: "如：T-0024" }) +
      fieldHtml("ql-f-note", "备注", data.note, { type: "textarea" }) +
      '<div class="ql-form__row">' +
      fieldHtml("ql-f-source-code", "来源代号", data.source_code, {}) +
      fieldHtml("ql-f-source-url", "来源链接", data.source_url, {}) +
      "</div>" +
      formActionsHtml(isEdit) +
      "</form>";
    byId("ql-detail-body").innerHTML = html;
    var first = byId("ql-f-zh");
    if (first) first.focus();
  }
  function formValue(id) {
    var node = byId(id);
    return node ? node.value.trim() : "";
  }
  async function saveForm() {
    var isTerms = state.tab === "terms";
    var payload;
    if (isTerms) {
      payload = {
        zh: formValue("ql-f-zh"), en: formValue("ql-f-en"), lang_pair: formValue("ql-f-lang") || "zh-en",
        domain: formValue("ql-f-domain"), definition: formValue("ql-f-definition"),
        note: formValue("ql-f-note"), source_code: formValue("ql-f-source-code"), source_url: formValue("ql-f-source-url")
      };
    } else {
      payload = {
        zh: formValue("ql-f-zh"), en: formValue("ql-f-en"), lang_pair: formValue("ql-f-lang") || "zh-en",
        register_kind: formValue("ql-f-register"), term_id: formValue("ql-f-term-id"),
        note: formValue("ql-f-note"), source_code: formValue("ql-f-source-code"), source_url: formValue("ql-f-source-url")
      };
    }
    var errorBox = byId("ql-form-error");
    if (!payload.zh) { if (errorBox) errorBox.textContent = "请填写中文"; return; }
    if (!isTerms && !payload.en) { if (errorBox) errorBox.textContent = "请填写英文句"; return; }
    var isEdit = state.mode === "edit" && state.selectedItem && state.selectedItem.id;
    var path = "/api/me/" + state.tab + (isEdit ? "/" + state.selectedItem.id : "");
    var method = isEdit ? "PUT" : "POST";
    try {
      var saved = await api(path, { method: method, body: payload, silent: true });
      toast(isEdit ? "已保存" : "已新建", "success");
      state.scope = "mine";
      setScope("mine", true);
      state.mode = "view";
      await loadList();
      if (saved && saved.id) {
        var found = state.items.filter(function (row) { return row.id === saved.id; })[0];
        if (found) selectItem(found);
      }
    } catch (err) {
      var status = statusOf(err);
      if (status === 401) { redirectToLogin(); return; }
      var message = status === 409 ? "已存在同名词条/句对" : messageOf(err);
      if (errorBox) errorBox.textContent = "保存失败：" + message;
      toast("保存失败：" + message, "error");
    }
  }
  async function deleteSelected() {
    if (!state.selectedItem) return;
    try {
      await api("/api/me/" + state.tab + "/" + state.selectedItem.id, { method: "DELETE", silent: true });
      toast("已删除", "success");
      resetDetail();
      state.selectedId = null;
      loadList();
    } catch (err) {
      if (statusOf(err) === 401) { redirectToLogin(); return; }
      toast("删除失败：" + messageOf(err), "error");
    }
  }
  function confirmDeleteHtml() {
    return '<div class="ql-actions-row"><span class="ql-detail__tip">确认删除这条「我的条目」？删除后不可恢复。</span>' +
      '<button class="ql-btn ql-btn--danger" type="button" data-action="confirm-delete">确认删除</button>' +
      '<button class="ql-btn" type="button" data-action="cancel-delete">取消</button></div>';
  }

  /* ---------------- 加入我的库 ---------------- */
  async function adoptSelected() {
    if (!state.selectedItem) return;
    var path = "/api/me/" + state.tab + "/import/" + encodeURIComponent(state.selectedItem.id);
    try {
      await api(path, { method: "POST", silent: true });
      toast("已加入我的库", "success");
      state.counts[state.tab] = (state.counts[state.tab] || 0) + 1;
    } catch (err) {
      var status = statusOf(err);
      if (status === 401) { redirectToLogin(); return; }
      if (status === 409) { toast("该条目已在你的库中", "error"); return; }
      toast("加入失败：" + messageOf(err), "error");
    }
  }

  /* ---------------- 导入导出 ---------------- */
  async function rawFetch(url, options) {
    var opts = options || {};
    var method = String(opts.method || "GET").toUpperCase();
    var headers = {};
    if (method !== "GET" && method !== "HEAD") {
      var csrf = getCookie("csrf_token");
      if (csrf) headers["X-CSRF-Token"] = csrf;
    }
    var response = await fetch(url, { method: method, headers: headers, body: opts.body, credentials: "same-origin", cache: "no-store" });
    if (response.status === 401) { redirectToLogin(); throw new ApiError(401, "请先登录"); }
    return response;
  }
  function downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }
  function filenameFrom(response, fallback) {
    var disposition = response.headers.get("content-disposition") || "";
    var match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
    if (match && match[1]) {
      try { return decodeURIComponent(match[1]); } catch (err) { return match[1]; }
    }
    return fallback;
  }
  async function exportMyData(format) {
    if (state.tab === "local") { toast("本地语为只读资产，不支持导出个人库", "error"); return; }
    var kind = state.tab;
    var tried = [];
    var candidates = format === "json"
      ? ["/api/me/" + kind + "/export.xlsx?format=json"]
      : ["/api/me/" + kind + "/export.xlsx?format=xlsx", "/api/me/" + kind + "/export.csv"];
    for (var i = 0; i < candidates.length; i += 1) {
      var url = candidates[i];
      try {
        var response = await rawFetch(url);
        if (response.status === 404 || response.status === 405 || response.status === 415) { tried.push(response.status); continue; }
        if (!response.ok) { tried.push(response.status); continue; }
        var contentType = response.headers.get("content-type") || "";
        if (contentType.indexOf("json") !== -1 && format === "json") {
          var data = await response.json();
          downloadBlob(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), "my_" + kind + ".json");
          toast("已导出 JSON", "success");
          return;
        }
        if (contentType.indexOf("json") !== -1) { tried.push("json-not-file"); continue; }
        var blob = await response.blob();
        var fallbackName = "my_" + kind + (format === "json" ? ".json" : url.indexOf(".csv") !== -1 ? ".csv" : ".xlsx");
        downloadBlob(blob, filenameFrom(response, fallbackName));
        toast(url.indexOf(".csv") !== -1 ? "后端暂未提供 Excel，已导出 CSV" : "已导出文件", "success");
        return;
      } catch (err) {
        if (statusOf(err) === 401) return;
        tried.push(statusOf(err) || messageOf(err));
      }
    }
    if (format === "json") {
      try {
        var rows = await fetchAllMine(kind);
        var payload = { kind: kind, exported_at: new Date().toISOString(), count: rows.length, items: rows };
        downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }), "my_" + kind + ".json");
        showBanner(tr("后端导出接口未启用，已在前端生成 JSON（{n} 条）。", { n: rows.length }), "ok");
        return;
      } catch (clientErr) {
        if (statusOf(clientErr) === 401) return;
        showBanner("导出失败：" + messageOf(clientErr), "error");
        return;
      }
    }
    showBanner("后端导出接口尚未实现（尝试：" + tried.join(" / ") + "）。请在完成后重试，或先用「导出 JSON」（前端生成）。", "error");
  }
  async function fetchAllMine(kind) {
    var rows = [];
    var page = 1;
    var pageSize = 100;
    for (var guard = 0; guard < 20; guard += 1) {
      var data = await api("/api/me/" + kind + "?page=" + page + "&page_size=" + pageSize, { silent: true });
      var items = (data && data.items) || [];
      rows = rows.concat(items);
      var total = (data && data.total) || rows.length;
      if (rows.length >= total || !items.length) break;
      page += 1;
    }
    return rows;
  }
  function readFileAsText(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result || "")); };
      reader.onerror = function () { reject(new Error("读取文件失败")); };
      reader.readAsText(file, "utf-8");
    });
  }
  function importEntries(kind, entries) {
    var successes = 0;
    var failures = [];
    var queue = entries.slice(0, 300);
    function step(index) {
      if (index >= queue.length) return Promise.resolve();
      var entry = queue[index] || {};
      var payload;
      if (kind === "terms") {
        payload = { zh: entry.zh || "", en: entry.en || "", lang_pair: entry.lang_pair || "zh-en", domain: entry.domain || "", definition: entry.definition || entry.definition_zh || "", note: entry.note || "", source_code: entry.source_code || "", source_url: entry.source_url || "" };
      } else {
        payload = { zh: entry.zh || "", en: entry.en || "", lang_pair: entry.lang_pair || "zh-en", register_kind: entry.register_kind || entry.register || "", term_id: entry.term_id || "", note: entry.note || "", source_code: entry.source_code || "", source_url: entry.source_url || "" };
      }
      if (!payload.zh) { failures.push({ row: index + 1, reason: "缺少 zh" }); return step(index + 1); }
      return api("/api/me/" + kind, { method: "POST", body: payload, silent: true })
        .then(function () { successes += 1; return step(index + 1); })
        .catch(function (err) {
          failures.push({ row: index + 1, reason: statusOf(err) === 409 ? "重复条目" : messageOf(err) });
          return step(index + 1);
        });
    }
    return step(0).then(function () { return { successes: successes, failures: failures }; });
  }
  async function handleImportFile(file) {
    if (!file) return;
    if (file.size > MAX_IMPORT) { showBanner("文件超过 5MB，请拆分后再导入", "error"); return; }
    var name = String(file.name || "").toLowerCase();
    var isJson = name.endsWith(".json");
    var isXlsx = name.endsWith(".xlsx") || name.endsWith(".xls");
    if (!isJson && !isXlsx) { showBanner("只支持 .xlsx / .xls / .json 文件", "error"); return; }
    showBanner("正在导入 " + file.name + "…");
    setBusy(true);
    try {
      var form = new FormData();
      form.append("file", file);
      var response = await rawFetch("/api/me/" + state.tab + "/import", { method: "POST", body: form });
      if (response.status === 404 || response.status === 405 || response.status === 415) {
        if (isJson) {
          var text = await readFileAsText(file);
          var parsed = JSON.parse(text);
          var entries = Array.isArray(parsed) ? parsed : (parsed.items || parsed.terms || parsed.corpus || []);
          var result = await importEntries(state.tab, entries);
          showImportResult(result.successes, result.failures);
          await refreshAfterImport();
          return;
        }
        showBanner("后端导入接口（/api/me/" + state.tab + "/import）尚未实现，Excel 导入需后端支持；可先用 JSON 导入。", "error");
        return;
      }
      if (!response.ok) {
        var data = null;
        try { data = await response.json(); } catch (parseErr) { data = null; }
        throw new ApiError(response.status, (data && data.detail) || "导入失败（" + response.status + "）");
      }
      var payload = null;
      try { payload = await response.json(); } catch (parseErr) { payload = null; }
      var ok = (payload && (payload.created || payload.success || payload.imported || payload.ok_count)) || 0;
      var skipped = (payload && (payload.skipped || 0)) || 0;
      var failed = ((payload && (payload.failed || payload.error_count)) || 0) + skipped;
      var errors = (payload && (payload.errors || payload.failures)) || [];
      showImportResult(ok, failed, errors);
      if (skipped) showBanner(tr("导入完成：成功 {a} 条，跳过 {b} 条（已存在），失败 {c} 条", { a: ok, b: skipped, c: (payload && payload.failed) || 0 }), "ok");
      await refreshAfterImport();
    } catch (err) {
      if (statusOf(err) === 401) return;
      showBanner("导入失败：" + messageOf(err), "error");
    } finally {
      setBusy(false);
      byId("ql-import-file").value = "";
    }
  }
  function showImportResult(successes, failures, errors) {
    var failCount = 0;
    var failList = [];
    if (typeof failures === "number") failCount = failures;
    if (Array.isArray(failures)) { failList = failures; failCount = failures.length; }
    if (Array.isArray(errors)) failList = failList.concat(errors);
    var detail = "";
    if (failList.length) {
      detail = "；失败示例：" + failList.slice(0, 5).map(function (row) {
        if (typeof row === "string") return row;
        return "第" + (row.row || row.index || "?") + " 行 " + (row.reason || row.error || row.message || "格式错误");
      }).join("；");
    }
    showBanner("导入完成：成功 " + (successes || 0) + " 条，失败 " + failCount + " 条" + detail, failCount ? "error" : "ok");
  }
  async function refreshAfterImport() {
    if (state.scope !== "mine") setScope("mine", true);
    state.page = 1;
    await loadList();
  }
  function setBusy(busy) {
    state.busy = busy;
    ["ql-new", "ql-export-xlsx", "ql-export-json", "ql-import"].forEach(function (id) {
      var btn = byId(id);
      if (btn) btn.disabled = busy;
    });
  }

  /* ---------------- 详情事件 ---------------- */
  function bindDetailEvents() {
    var body = byId("ql-detail-body");
    body.addEventListener("submit", function (event) {
      event.preventDefault();
      saveForm();
    });
    body.addEventListener("click", function (event) {
      var target = closest(event.target, "[data-action]");
      if (!target) return;
      var action = target.getAttribute("data-action");
      if (action === "adopt") { adoptSelected(); return; }
      if (action === "goto-corpus") {
        var zh = target.getAttribute("data-zh") || "";
        switchTopic("corpus", zh);
        return;
      }
      if (action === "goto-term") {
        var termZh = target.getAttribute("data-zh") || "";
        switchTopic("terms", termZh);
        return;
      }
      if (action === "cancel-edit") {
        if (state.selectedItem) selectItem(state.selectedItem);
        else resetDetail();
        return;
      }
      if (action === "save") { event.preventDefault(); saveForm(); return; }
      if (action === "delete") {
        state.pendingDelete = true;
        var actionsRow = closest(target, ".ql-actions-row");
        if (actionsRow) actionsRow.outerHTML = confirmDeleteHtml();
        return;
      }
      if (action === "confirm-delete") { deleteSelected(); return; }
      if (action === "cancel-delete") {
        state.pendingDelete = false;
        if (state.selectedItem) selectItem(state.selectedItem);
        return;
      }
    });
  }
  function switchTopic(tab, searchText) {
    state.tab = tab;
    setTab(tab);
    if (searchText) {
      byId("ql-search").value = searchText;
      state.q = searchText;
      state.page = 1;
      loadList();
    }
  }

  /* ---------------- 事件绑定与启动 ---------------- */
  function bindEvents() {
    TABS.forEach(function (tab) {
      byId("ql-tab-" + tab).addEventListener("click", function () { setTab(tab); });
    });
    byId("ql-search").addEventListener("input", function (event) {
      state.q = String(event.target.value || "").trim();
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(function () {
        state.page = 1;
        state.selectedId = null;
        resetDetail();
        loadList();
      }, 300);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".ql-scope__btn"), function (btn) {
      btn.addEventListener("click", function () { setScope(btn.getAttribute("data-scope")); });
    });
    byId("ql-filter-lang").addEventListener("change", function () { state.page = 1; loadList(); });
    byId("ql-filter-domain").addEventListener("change", function () { state.page = 1; loadList(); });
    byId("ql-prev").addEventListener("click", function () { goPage(-1); });
    byId("ql-next").addEventListener("click", function () { goPage(1); });
    byId("ql-items").addEventListener("click", function (event) {
      var button = closest(event.target, ".ql-item");
      if (!button) return;
      var item = state.items[parseInt(button.getAttribute("data-index"), 10)];
      if (item) selectItem(item);
    });
    byId("ql-new").addEventListener("click", function () {
      if (state.tab === "local") { toast("本地语为只读，不能新建", "error"); return; }
      state.mode = "create";
      state.selectedId = null;
      state.selectedItem = null;
      markActive(null);
      byId("ql-detail-head").hidden = false;
      byId("ql-detail-badge").textContent = "新建 · 我的条目";
      byId("ql-detail-empty").hidden = true;
      byId("ql-detail-body").hidden = false;
      setMobileDetail(true);
      if (state.tab === "terms") renderTermForm(null, "create");
      else renderCorpusForm(null, "create");
    });
    byId("ql-back").addEventListener("click", function () { setMobileDetail(false); });
    byId("ql-banner-close").addEventListener("click", hideBanner);
    byId("ql-export-xlsx").addEventListener("click", function () { exportMyData("xlsx"); });
    byId("ql-export-json").addEventListener("click", function () { exportMyData("json"); });
    byId("ql-import").addEventListener("click", function () {
      if (state.tab === "local") { toast("本地语为只读，不支持导入", "error"); return; }
      byId("ql-import-file").click();
    });
    byId("ql-import-file").addEventListener("change", function (event) {
      var file = event.target.files && event.target.files[0];
      if (file) handleImportFile(file);
    });
    bindDetailEvents();
  }

  async function loadMyCounts(user) {
    // 匿名访客不发起任何个人数据请求：既避免 401 控制台报错，也少一次无用往返。
    if (!user) return;
    try {
      var data = await api("/api/me/overview", { silent: true, authOptional: true });
      state.counts.terms = (data && data.my_terms) || 0;
      state.counts.corpus = (data && data.my_corpus) || 0;
      var mineBtn = document.querySelector('.ql-scope__btn[data-scope="mine"]');
      if (mineBtn) mineBtn.textContent = tr("我的条目（{n}）", { n: state.counts.terms + state.counts.corpus });
    } catch (err) { /* 统计失败不影响主流程 */ }
  }

  function boot() {
    state.tab = tabFromUrl();
    // 旧链接 /quality.html?tab=patient-check 平滑迁移到新的一级页面。
    if (state.tab === "patient-check") {
      var params = new URLSearchParams(location.search);
      params.delete("tab");
      var query = params.toString();
      location.replace("check.html" + (query ? "?" + query : ""));
      return;
    }
    bindEvents();
    setTab(state.tab);
    // 页面门禁由 shield.py 保证；requireAuth 只读取登录态，
    // 只有已登录用户才去请求个人统计，避免无谓的 401。
    requireAuth().then(function (user) { return loadMyCounts(user); })
      .catch(function () { /* 个人统计失败不影响公共检索 */ });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
