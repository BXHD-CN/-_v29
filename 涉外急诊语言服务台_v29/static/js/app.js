/* 涉外急诊语言服务台 · V2 全局壳（T2）
 * - window.App：api / requireLogin / currentUser / toast / escapeHtml / fmtTime /
 *   openQa / sectionColor / onReady，供 translate.js、quality.js 等页面脚本调用
 * - 全局导航（5 项）+ 登录态 + 右下角绿色问答悬浮窗（全站）
 * - 页面脚本：login / register / news / account（index 由 home.js 负责内容）
 * 颜色即功能：首页青、翻译蓝、语言质量紫、资讯橙、问答绿、我的灰
 */
"use strict";

(function () {
  // ---------------- 板块与导航 ----------------
  // 信息架构：患者检查表与「翻译」平级（玫红）；跨文化表达并入「语言质量」成为子功能（紫色）。
  // 内部 key 仍沿用 culture，是为了复用 base.css 已建立的玫红 --section 映射，
  // 保持 7 种功能色不增不减、颜色与功能一一对应。
  var SECTIONS = {
    home: { label: "首页", href: "index.html", color: "#0E7490", soft: "#E0F2FE" },
    translate: { label: "翻译", href: "translate.html", color: "#2563EB", soft: "#DBEAFE" },
    culture: { label: "患者检查表", href: "check.html", color: "#BE123C", soft: "#FFE4E6" },
    quality: { label: "语言质量", href: "quality.html", color: "#7C3AED", soft: "#EDE9FE" },
    news: { label: "资讯", href: "news.html", color: "#EA580C", soft: "#FFEDD5" },
    qa: { label: "问答", href: "qa.html", color: "#059669", soft: "#D1FAE5" },
    account: { label: "我的", href: "account.html", color: "#475569", soft: "#E2E8F0" }
  };
  var NAV_ITEMS = ["home", "translate", "culture", "quality", "news", "account"];
  /* v=27 英文页头修复：中文标签经字典直译后为 "Patient Handoff Sheet"、
     "Language Quality" 等长串，六项合计约 686px，超过 1280 视口页头可用宽度
     （636px），flex 被压缩后长标签折成三行并顶出页头。英文模式改用短标签，
     data-section 与功能色映射完全不变；完整名称仍保留在图例与各页面标题。 */
  var NAV_LABEL_EN = {
    home: "Home", translate: "Translate", culture: "Handoff",
    quality: "Quality", news: "News", account: "Assets"
  };
  function navLabel(key) {
    return isEn() ? (NAV_LABEL_EN[key] || SECTIONS[key].label) : SECTIONS[key].label;
  }
  // 全站唯一的功能色映射：色块出现在每个页面页脚，颜色与板块一一对应
  var FUNC_LEGEND = [
    { key: "home", label: "青 · 首页总览" },
    { key: "translate", label: "蓝 · 多语翻译" },
    { key: "culture", label: "玫红 · 患者检查表" },
    { key: "quality", label: "紫 · 语言质量（含跨文化表达）" },
    { key: "news", label: "橙 · 国际资讯" },
    { key: "qa", label: "绿 · 可溯源问答" },
    { key: "account", label: "灰 · 我的资产" }
  ];
  // 页头印章：把当前板块的功能色与功能名直接印在导航上
  var FUNC_STAMP = {
    translate: "蓝 / 多语翻译 · BLUE",
    culture: "玫红 / 患者检查表 · ROSE",
    quality: "紫 / 语言质量 · PURPLE",
    news: "橙 / 国际资讯 · ORANGE",
    qa: "绿 / 可溯源问答 · GREEN",
    account: "灰 / 我的资产 · SLATE"
  };
  // 英文界面用短印章：中文印章经字典直译后会变成 "ROSE / Patient Handoff Sheet · ROSE"
  // 这类长串，把页头右侧挤窄。英文模式直接输出短标签，既省空间又保留功能色语义。
  var FUNC_STAMP_EN = {
    translate: "TRANSLATE · BLUE",
    culture: "HANDOFF · ROSE",
    quality: "QUALITY · PURPLE",
    news: "SIGNALS · ORANGE",
    qa: "ASK · GREEN",
    account: "ASSETS · SLATE"
  };
  // 首页免登录（站点门面）+ 注册 / 登录入口；其余功能页仍要求有效会话。
  // 服务端 shield.py 的 GUEST_PAGES 与之保持同一白名单。
  var GUEST_PAGES = { index: true, home: true, register: true, login: true };
  var PAGE_SECTION = {
    index: "home", home: "home", login: "home", register: "home",
    translate: "translate", quality: "quality", news: "news", account: "account", qa: "qa",
    check: "culture",          // 患者检查表 = 玫红
    culture: "quality",        // 旧 culture.html 重定向到语言质量，归紫色
    cloud: "account"
  };

  var state = { page: "index", section: "home", user: null, meLoaded: false, csrf: "" };
  var mePromise = null;
  var readyResolve = null;
  var readyPromise = new Promise(function (resolve) { readyResolve = resolve; });
  var activeModal = null;

  // ---------------- 基础工具 ----------------
  function byId(id) { return document.getElementById(id); }
  function all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function setText(id, text) {
    var node = byId(id);
    if (node) node.textContent = text === undefined || text === null ? "" : String(text);
  }
  function pad2(number) { return number < 10 ? "0" + number : String(number); }
  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function fmtNumber(value) {
    var num = Number(value);
    if (!isFinite(num)) return "—";
    try { return num.toLocaleString("zh-CN"); } catch (err) { return String(num); }
  }
  function fmtTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value).slice(0, 16);
    return date.getFullYear() + "-" + pad2(date.getMonth() + 1) + "-" + pad2(date.getDate()) +
      " " + pad2(date.getHours()) + ":" + pad2(date.getMinutes());
  }
  function fmtDate(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value).slice(0, 10);
    return date.getFullYear() + "-" + pad2(date.getMonth() + 1) + "-" + pad2(date.getDate());
  }
  function todayString() {
    var date = new Date();
    return date.getFullYear() + "-" + pad2(date.getMonth() + 1) + "-" + pad2(date.getDate());
  }
  function truncate(text, max) {
    var value = String(text || "");
    return value.length <= max ? value : value.slice(0, max) + "…";
  }
  /** 动态拼串走统一翻译入口，保证中英两套文案覆盖同一批内容。 */
  function tr(zh, vars) {
    return (window.I18N && typeof window.I18N.t === "function") ? window.I18N.t(zh, vars) : zh;
  }
  function isEn() {
    return !!(window.I18N && typeof window.I18N.lang === "function" && window.I18N.lang() === "en");
  }
  /** 知识库里只有中文的枚举（来源、中文化方式、领域等）在英文模式换成英文标签。 */
  function enLabel(zh) {
    return (window.I18N && typeof window.I18N.label === "function") ? window.I18N.label(zh) : (zh || "");
  }
  /** 有中英双版本的数据：英文模式英文为主行、中文为副行。
   *  内容字段不做枚举翻译——只有中文时照录原文作为 source data。 */
  function enPair(zh, en) {
    if (!isEn()) return { primary: zh || "", secondary: en || "" };
    if (en) return { primary: en, secondary: zh || "" };
    return { primary: zh || "", secondary: "" };
  }
  /** 带全角标点的动态标签用成稿英文，避免短语替换留下「Access date：」这类混排。 */
  function enText(zh, en) { return isEn() ? en : zh; }
  function displayName(user) {
    if (!user) return "访客";
    return user.display_name || user.username || user.email || "用户";
  }
  function initialOf(name) {
    var value = String(name || "用").trim();
    return value ? value.slice(0, 1) : "用";
  }
  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var that = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(that, args); }, wait);
    };
  }
  function toast(message, kind) {
    var stack = byId("toast-stack");
    if (!stack) return;
    var node = document.createElement("div");
    node.className = "toast toast--" + (kind || "info");
    node.setAttribute("role", "status");
    node.textContent = String(message || "");
    stack.appendChild(node);
    setTimeout(function () { node.classList.add("is-leaving"); }, 2600);
    setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 3000);
  }
  function formatDetail(detail) {
    if (!detail) return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map(function (item) {
        if (item && typeof item === "object") {
          var loc = item.loc ? item.loc.join(".") : "";
          return (loc ? loc + "：" : "") + (item.msg || "");
        }
        return String(item);
      }).join("；");
    }
    if (typeof detail === "object") {
      try { return JSON.stringify(detail); } catch (err) { return ""; }
    }
    return String(detail);
  }

  // ---------------- CSRF / Cookie ----------------
  function getCookie(name) {
    var raw = document.cookie ? document.cookie.split("; ") : [];
    for (var index = 0; index < raw.length; index++) {
      var eq = raw[index].indexOf("=");
      if (eq > 0 && raw[index].slice(0, eq) === name) {
        try { return decodeURIComponent(raw[index].slice(eq + 1)); } catch (err) { return raw[index].slice(eq + 1); }
      }
    }
    return "";
  }
  function currentCsrf() {
    // 服务端按 Cookie 里的 csrf_token 做双提交校验，Cookie 才是唯一真源。
    // 旧实现优先读 localStorage，会话轮换 / 匿名 CSRF Cookie 覆盖后会出现
    // 「localStorage 旧 token ≠ Cookie 当前 token」→ 403（问答机器人故障根因）。
    var cookieToken = getCookie("csrf_token") || "";
    if (cookieToken) return cookieToken;
    try { return localStorage.getItem("csrf_token") || ""; } catch (err) { return ""; }
  }
  function syncCsrfFromCookie() {
    var fresh = getCookie("csrf_token") || "";
    if (fresh) setCsrf(fresh);
    return fresh;
  }
  function setCsrf(token) {
    if (!token) return;
    try { localStorage.setItem("csrf_token", token); } catch (err) { /* 忽略隐私模式 */ }
    state.csrf = token;
  }
  function clearCsrf() {
    try { localStorage.removeItem("csrf_token"); } catch (err) { /* 忽略 */ }
    state.csrf = "";
  }

  // ---------------- 页面路径与登录跳转 ----------------
  function currentPageFile() {
    var path = window.location.pathname || "/";
    var name = path.substring(path.lastIndexOf("/") + 1);
    if (!name || name.indexOf(".") === -1) return "index.html";
    return name;
  }
  function currentFileWithQuery() {
    return currentPageFile() + (window.location.search || "");
  }
  function safeNext(raw) {
    if (!raw) return "";
    var value = String(raw);
    if (value.indexOf("//") !== -1 || value.indexOf(":") !== -1) return "";
    if (!/^[A-Za-z0-9_-]+\.html(\?[A-Za-z0-9&=%.+_-]*)?$/.test(value)) return "";
    return value;
  }
  function loginUrl(next) {
    var target = next || currentFileWithQuery();
    return "login.html?next=" + encodeURIComponent(target);
  }
  function redirectToLogin() {
    window.location.replace(loginUrl());
  }
  /** 注册门禁：带上原始目标（含 sharecode）回注册入口，注册成功后原路返回。 */
  function registerUrl() {
    var target = currentFileWithQuery();
    var code = new URLSearchParams(window.location.search).get("sharecode");
    var url = "register.html?next=" + encodeURIComponent(target);
    if (code) url += "&sharecode=" + encodeURIComponent(code);
    return url;
  }
  function redirectToRegister() {
    window.location.replace(registerUrl());
  }

  // ---------------- fetch 封装 ----------------
  function ApiError(status, message, data) {
    this.name = "ApiError";
    this.status = status;
    this.message = message || "请求失败";
    this.data = data || null;
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  async function api(path, options) {
    var opts = options || {};
    var method = String(opts.method || "GET").toUpperCase();
    var headers = {};
    if (opts.headers) {
      Object.keys(opts.headers).forEach(function (key) { headers[key] = opts.headers[key]; });
    }
    var body = opts.body;
    if (body !== undefined && body !== null && typeof body !== "string" && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    // 全站双语：每次请求带上当前界面语言，服务端据此返回对应语言的
    // 错误文案、问答拒答、示例问题与告知单标签。
    if (window.I18N && typeof window.I18N.lang === "function") {
      headers["X-Lang"] = window.I18N.lang();
    }
    if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
      var token = currentCsrf();
      if (token) headers["X-CSRF-Token"] = token;
    }
    var response;
    try {
      response = await fetch(path, {
        method: method,
        headers: headers,
        body: body,
        credentials: "same-origin",
        cache: "no-store"
      });
    } catch (networkError) {
      if (!opts.silent) toast("网络异常，请检查网络后重试", "error");
      throw new ApiError(0, "网络异常", null);
    }
    var contentType = response.headers.get("content-type") || "";
    var data = null;
    if (contentType.indexOf("application/json") !== -1) {
      try { data = await response.json(); } catch (parseError) { data = null; }
    } else {
      try { data = await response.text(); } catch (textError) { data = null; }
    }
    var detail = "";
    if (data && typeof data === "object") detail = formatDetail(data.detail || data.message || "");

    if (response.status === 401) {
      // 首页免登录：匿名访客在首页只读统计 / 登录态探测上遇到 401 不应被送走；
      // 注册 / 登录入口同理。其余功能页仍统一回注册入口（带 next 与 sharecode）。
      // 静默的个人数据探测（authOptional）只抛错、不打断页面。
      var isAuthEndpoint = path.indexOf("/api/auth/") === 0;
      var isGuestPage = !!GUEST_PAGES[state.page];
      if (!opts.authOptional && !isAuthEndpoint && !isGuestPage) {
        if (!opts.silent) toast("请先注册并登录后再使用本站功能", "warn");
        redirectToRegister();
      }
      throw new ApiError(401, detail || "请先登录", data);
    }
    if (response.status === 403) {
      var message403 = detail || "无权访问";
      // CSRF 自愈：Cookie 轮换后用当前 Cookie 覆盖 localStorage 旧 token 并重试一次，
      // 避免访客 / 登录后第一次提交问答、翻译、告知单就撞上 403。
      if (!opts._csrfRetried && message403.indexOf("CSRF") !== -1 && syncCsrfFromCookie()) {
        var retryOpts = {};
        Object.keys(opts).forEach(function (key) { retryOpts[key] = opts[key]; });
        retryOpts._csrfRetried = true;
        return api(path, retryOpts);
      }
      if (!opts.silent) {
        if (message403.indexOf("CSRF") !== -1) toast("安全校验失败，请刷新页面后重试", "error");
        else toast(message403, "error");
      }
      throw new ApiError(403, message403, data);
    }
    if (response.status === 404) throw new ApiError(404, detail || "资源不存在", data);
    if (response.status === 429) {
      if (!opts.silent) toast(detail || "操作过快，请稍后再试", "warn");
      throw new ApiError(429, detail || "操作过快，请稍后再试", data);
    }
    if (!response.ok) {
      var failure = detail || ("请求失败（" + response.status + "）");
      if (!opts.silent) toast(failure, "error");
      throw new ApiError(response.status, failure, data);
    }
    return data;
  }

  // ---------------- 当前用户 / 登录守卫 ----------------
  function loadMe(force) {
    if (!force && mePromise) return mePromise;
    // /api/auth/me 是门禁白名单接口，匿名也返回 user=null；
    // 必须真正请求一次，才能判断「是否已注册并登录」。
    mePromise = api("/api/auth/me", { authOptional: true, silent: true }).then(function (data) {
      state.user = data && data.user ? data.user : null;
      state.meLoaded = true;
      return state.user;
    }).catch(function () {
      state.user = null;
      state.meLoaded = true;
      return null;
    });
    return mePromise;
  }
  function requireLogin() {
    // 注册门禁由 boot() 统一拦截；这里只返回当前登录态供页面脚本使用。
    return loadMe();
  }

  // ---------------- 全局壳：导航 / 页脚 ----------------
  function langSwitcherHtml() {
    return (window.I18N && typeof window.I18N.switcherHtml === "function")
      ? window.I18N.switcherHtml() : "";
  }
  function bindLangSwitcher(root) {
    if (window.I18N && typeof window.I18N.bindSwitcher === "function") {
      window.I18N.bindSwitcher(root || document);
    }
  }
  function navItemsHtml() {
    return NAV_ITEMS.map(function (key) {
      var item = SECTIONS[key];
      var active = key === state.section;
      return '<a class="nav-link' + (active ? ' is-active' : '') + '" href="' + item.href + '" data-section="' + key + '"' +
        (active ? ' aria-current="page"' : '') + ' data-i18n-skip><span class="nav-dot" aria-hidden="true"></span>' +
        escapeHtml(navLabel(key)) + '</a>';
    }).join('');
  }
  function authAreaHtml() {
    if (!state.meLoaded) return '<span class="muted small">加载中…</span>';
    if (state.user) {
      var name = displayName(state.user);
      return '<div class="user-menu" id="user-menu">' +
        '<button class="user-menu-btn" id="user-menu-btn" type="button" aria-haspopup="true" aria-expanded="false">' +
          '<span class="avatar" aria-hidden="true">' + escapeHtml(initialOf(name)) + '</span>' +
          '<span class="user-name">' + escapeHtml(name) + '</span>' +
        '</button>' +
        '<div class="user-menu-panel" id="user-menu-panel" hidden>' +
          '<a href="account.html">我的资产</a>' +
          '<button type="button" id="logout-btn">退出登录</button>' +
        '</div></div>';
    }
    var next = encodeURIComponent(currentFileWithQuery());
    return '<a class="btn btn--ghost btn--sm" href="login.html?next=' + next + '">登录</a>' +
      '<a class="btn btn--primary btn--sm" href="register.html">注册</a>';
  }
  function funcStampText() {
    var en = window.I18N && typeof window.I18N.lang === "function" && window.I18N.lang() === "en";
    var table = en ? FUNC_STAMP_EN : FUNC_STAMP;
    return table[state.section] || "";
  }
  function renderHeader() {
    var host = byId("site-header");
    if (!host) return;
    /* 英文模式：strong 会被 i18n 译成 "Emergency Language Desk"，若 small 仍是
       同一串英文，页头品牌出现两次重复且白占 288px。改短后与 hero 眉题也不再撞。 */
    var brandSub = isEn() ? "VOL. 01 · EDITION" : "Emergency Language Desk";
    host.innerHTML = '<div class="container header-inner">' +
      '<a class="brand" href="index.html" aria-label="涉外急诊语言服务台，返回首页">' +
        '<span class="brand-mark" aria-hidden="true">急</span>' +
        '<span class="brand-text"><strong>涉外急诊语言服务台</strong><small data-i18n-skip>' +
          escapeHtml(brandSub) + '</small></span>' +
      '</a>' +
      '<nav class="nav-links" aria-label="主导航">' + navItemsHtml() + '</nav>' +
      '<div class="nav-lang" id="nav-lang">' + langSwitcherHtml() + '</div>' +
      '<div class="nav-auth" id="nav-auth">' + authAreaHtml() + '</div>' +
      '<span class="func-stamp" aria-hidden="true">' + escapeHtml(funcStampText()) + '</span>' +
      '</div>';
    bindHeader();
    bindLangSwitcher(host);
  }
  var headerDocClickBound = false;
  function bindHeader() {
    var menu = byId("user-menu");
    var menuButton = byId("user-menu-btn");
    var panel = byId("user-menu-panel");
    if (menuButton && panel && menu) {
      menuButton.addEventListener("click", function (event) {
        event.stopPropagation();
        var open = !menu.classList.contains("is-open");
        menu.classList.toggle("is-open", open);
        panel.hidden = !open;
        menuButton.setAttribute("aria-expanded", open ? "true" : "false");
      });
      // 全局「点击空白处关闭菜单」只注册一次：renderHeader / refreshAuthArea
      // 会多次调用 bindHeader，逐次注册会累积监听器并持有多份旧 DOM 引用。
      if (!headerDocClickBound) {
        headerDocClickBound = true;
        document.addEventListener("click", function (event) {
          var m = byId("user-menu");
          var p = byId("user-menu-panel");
          var b = byId("user-menu-btn");
          if (!m || !m.classList.contains("is-open")) return;
          if (m.contains(event.target)) return;
          m.classList.remove("is-open");
          if (p) p.hidden = true;
          if (b) b.setAttribute("aria-expanded", "false");
        });
      }
    }
    var logoutButton = byId("logout-btn");
    if (logoutButton) logoutButton.addEventListener("click", logoutUser);
  }
  function renderBottomNav() {
    var host = byId("bottom-nav");
    if (!host) return;
    host.innerHTML = NAV_ITEMS.map(function (key) {
      var item = SECTIONS[key];
      var active = key === state.section;
      return '<a href="' + item.href + '" data-section="' + key + '" class="' + (active ? 'is-active' : '') + '"' +
        (active ? ' aria-current="page"' : '') + ' data-i18n-skip><span class="bottom-dot" aria-hidden="true"></span><span>' +
        escapeHtml(navLabel(key)) + '</span></a>';
    }).join("");
  }
  function renderFooter() {
    var host = byId("site-footer");
    if (!host) return;
    host.innerHTML = '<div class="container footer-inner">' +
      '<div class="footer-brand"><span class="footer-mark" aria-hidden="true">' +
        (isEn() ? "ER" : "急") + '</span><span>涉外急诊语言服务台</span></div>' +
      '<div class="footer-meta">' +
        // 整段成稿英文：短语替换会残留全角句号
        '<p data-i18n-skip>' + escapeHtml(enText(
          "数据来源：公开权威机构与许可条目，详见来源清单与各条详情。",
          "Data sources: public authoritative bodies and licensed items; see the source list and each item's details.")) + '</p>' +
        '<p data-i18n-skip>' + escapeHtml(enText(
          "© 2026 涉外急诊语言服务台 · 多媒体内容版权归原机构所有。",
          "© 2026 Emergency Language Desk · multimedia content copyright belongs to the original institutions.")) + '</p>' +
      '</div>' +
      '<div class="footer-links">' + NAV_ITEMS.map(function (key) {
        return '<a href="' + SECTIONS[key].href + '">' + escapeHtml(SECTIONS[key].label) + '</a>';
      }).join('') + '</div>' +
      '<div class="func-legend" aria-label="功能色对照表">' + FUNC_LEGEND.map(function (f) {
        return '<span class="func-legend__item"><i class="func-legend__swatch func-legend__swatch--' +
          f.key + '" aria-hidden="true"></i>' + escapeHtml(f.label) + '</span>';
      }).join('') + '</div>' +
      '<div class="footer-lang">' + langSwitcherHtml() + '</div>' +
      '</div>';
    bindLangSwitcher(host);
  }
  // 线上分享链接靠 ?sharecode=... 建立访问会话。把该参数透传到站内链接，
  // 这样把「患者快速检查表」直达链接发给病患、或从首页点进去时，会话参数不会丢。
  // 只处理站内相对 .html 链接；外链、纯锚点、已带 sharecode 的链接一律跳过。
  function propagateSharecode() {
    var code = new URLSearchParams(window.location.search).get("sharecode");
    if (!code) return;
    all("a[href]").forEach(function (link) {
      var href = link.getAttribute("href") || "";
      if (!href || href.charAt(0) === "#" || href.charAt(0) === "/" ||
          /^[a-z][a-z0-9+.-]*:/i.test(href) || href.indexOf("sharecode=") !== -1) return;
      if (!/\.html(?:[?#]|$)/.test(href)) return;
      link.setAttribute("href", href + (href.indexOf("?") === -1 ? "?" : "&") +
        "sharecode=" + encodeURIComponent(code));
    });
  }
  // 登录态变化只重建右上角账户区，避免整块 header / 底部导航二次重绘
  function refreshAuthArea() {
    var host = byId("nav-auth");
    if (!host) return;
    host.innerHTML = authAreaHtml();
    propagateSharecode();
    bindHeader();
  }
  function refreshAuthUi() {
    all('[data-auth="guest"]').forEach(function (node) { node.hidden = !!state.user; });
    all('[data-auth="user"]').forEach(function (node) { node.hidden = !state.user; });
  }
  async function logoutUser() {
    try {
      await api("/api/auth/logout", { method: "POST", silent: true, authOptional: true });
    } catch (error) { /* 退出失败也清理本地状态 */ }
    clearCsrf();
    state.user = null;
    App.currentUser = null;
    toast("已退出登录", "success");
    window.location.href = "index.html";
  }


  // ---------------- 弹窗（个人信息表单 / 二次确认） ----------------
  function openModal(options) {
    closeModal();
    var previous = document.activeElement;
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    var modal = document.createElement("div");
    modal.className = "modal" + (options.size === "sm" ? " modal--sm" : "");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    var titleId = "modal-title";
    modal.setAttribute("aria-labelledby", titleId);

    var head = document.createElement("div");
    head.className = "modal-head";
    head.innerHTML = '<h2 id="' + titleId + '">' + escapeHtml(options.title || "提示") + '</h2>';
    var closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "btn btn--ghost btn--icon";
    closeButton.setAttribute("aria-label", "关闭对话框");
    closeButton.textContent = "×";
    closeButton.addEventListener("click", closeModal);
    head.appendChild(closeButton);

    var body = document.createElement("div");
    body.className = "modal-body";
    if (options.content) body.innerHTML = options.content;

    var foot = document.createElement("div");
    foot.className = "modal-foot";
    (options.actions || []).forEach(function (action) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn " + (action.kind ? "btn--" + action.kind : "btn--ghost") +
        (action.align === "start" ? " modal-spacer" : "");
      button.textContent = action.label;
      if (action.disabled) button.disabled = true;
      if (action.onClick) {
        button.addEventListener("click", function (event) { action.onClick(event, modal, button); });
      }
      foot.appendChild(button);
    });
    if (!foot.children.length) foot.hidden = true;

    modal.appendChild(head);
    modal.appendChild(body);
    modal.appendChild(foot);
    backdrop.appendChild(modal);
    backdrop.addEventListener("mousedown", function (event) {
      if (event.target === backdrop) closeModal();
    });

    var info = {
      backdrop: backdrop,
      previous: previous,
      onClose: options.onClose || null,
      onKeydown: function (event) {
        if (event.key === "Escape") { event.preventDefault(); closeModal(); }
      }
    };
    activeModal = info;
    document.addEventListener("keydown", info.onKeydown);
    document.body.appendChild(backdrop);
    document.body.style.overflow = "hidden";
    if (options.onMount) options.onMount(modal);
    var firstField = modal.querySelector("input, select, textarea");
    if (firstField) firstField.focus();
    else closeButton.focus();
    return modal;
  }
  function closeModal() {
    if (!activeModal) return;
    var info = activeModal;
    activeModal = null;
    document.removeEventListener("keydown", info.onKeydown);
    if (info.backdrop && info.backdrop.parentNode) info.backdrop.parentNode.removeChild(info.backdrop);
    document.body.style.overflow = "";
    if (info.previous && info.previous.focus) {
      try { info.previous.focus(); } catch (err) { /* 忽略 */ }
    }
    if (info.onClose) {
      try { info.onClose(); } catch (err) { /* 忽略 */ }
    }
  }
  function confirmDialog(options) {
    return new Promise(function (resolve) {
      var settled = false;
      function done(value) {
        if (settled) return;
        settled = true;
        closeModal();
        resolve(value);
      }
      var content = '<p>' + escapeHtml(options.message || "") + '</p>' +
        (options.detail ? '<p class="muted small">' + escapeHtml(options.detail) + '</p>' : "");
      openModal({
        title: options.title || "确认操作",
        size: "sm",
        content: content,
        onClose: function () {
          if (!settled) { settled = true; resolve(false); }
        },
        actions: [
          { label: options.cancelLabel || "取消", kind: "ghost", onClick: function () { done(false); } },
          { label: options.confirmLabel || "确认", kind: options.danger ? "danger" : "primary", onClick: function () { done(true); } }
        ]
      });
    });
  }

  // ---------------- 问答悬浮窗（全站） ----------------
  var qaState = { open: false, busy: false, examplesLoaded: false };
  // 与 /api/qa/examples 保持同一主题域：全部为医疗 / 急诊 / 语言服务相关的库内题。
  // 每条带中英双版本，接口不可用时英文界面也不会出现中文预设。
  var QA_FALLBACK_EXAMPLES = [
    { question_zh: "急诊分诊台如何向患者说明候诊顺序？",
      question_en: "How does an emergency triage desk explain waiting order to patients in English?",
      in_scope: true },
    { question_zh: "“预检分诊”的标准英文术语是什么？",
      question_en: "What is the standard English term for “pre-examination triage”?",
      in_scope: true },
    { question_zh: "手术知情同意需要向患者说明哪些内容？",
      question_en: "What must be explained to a patient for surgical informed consent?",
      in_scope: true }
  ];

  function qaFloatHtml() {
    return '<button class="qa-orb" id="qa-orb" type="button" aria-label="打开可溯源问答" aria-expanded="false" aria-controls="qa-panel">' +
        '<span class="qa-orb-pulse" aria-hidden="true"></span>' +
        '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H9l-4.2 3.4A.8.8 0 0 1 3.5 18.8V5.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>' +
      '</button>' +
      '<section class="qa-panel" id="qa-panel" role="dialog" aria-modal="false" aria-labelledby="qa-panel-title" hidden>' +
        '<header class="qa-head">' +
          '<div class="qa-head-title"><span class="qa-dot" aria-hidden="true"></span><h2 id="qa-panel-title">可溯源问答</h2></div>' +
          '<button class="qa-close" id="qa-close" type="button" aria-label="关闭问答窗口">×</button>' +
        '</header>' +
        '<div class="qa-body" id="qa-body">' +
          '<div class="qa-intro" id="qa-intro">' +
            // 整段成稿英文：短语替换会留下「，/；/。」等全角标点与半译串
            '<p data-i18n-skip>' + (isEn()
              ? 'Answers are drawn only from knowledge-base chunks. <strong>Questions outside the knowledge base are always refused</strong>. The [n] marker opens the source text and its provenance.'
              : '只依据知识库切片作答，<strong>知识库外问题一律拒答</strong>；句末 [n] 可点开查看参考来源原文与出处。') + '</p>' +
            '<div class="qa-examples" id="qa-examples"><span class="skeleton skeleton--line-sm"></span></div>' +
          '</div>' +
          '<div class="qa-messages" id="qa-messages" role="log" aria-live="polite"></div>' +
        '</div>' +
        '<form class="qa-input-row" id="qa-form" novalidate>' +
          '<label class="sr-only" for="qa-input">输入问题</label>' +
          '<textarea id="qa-input" rows="1" maxlength="500" placeholder="输入问题，例如：预检分诊的英文术语是什么？"></textarea>' +
          '<button class="btn qa-send" id="qa-send" type="submit">发送</button>' +
        '</form>' +
        '<p class="qa-disclaimer" id="qa-disclaimer" data-i18n-skip>' +
          escapeHtml(enText("AI 生成内容，请核对原始来源。",
                            "AI-generated content — please verify against the original sources.")) + '</p>' +
      '</section>';
  }

  function injectQa() {
    if (byId("qa-float")) return;
    var host = document.createElement("div");
    host.className = "qa-float";
    host.id = "qa-float";
    host.innerHTML = qaFloatHtml();
    document.body.appendChild(host);
    bindQa();
  }

  function bindQa() {
    var orb = byId("qa-orb");
    var closeButton = byId("qa-close");
    var form = byId("qa-form");
    var input = byId("qa-input");
    if (orb) {
      orb.addEventListener("click", function () {
        // 注册前置门禁：问答机器人仅对已注册并登录的用户开放。
        if (!state.user) { redirectToRegister(); return; }
        showQaPanel(!qaState.open);
      });
    }
    if (closeButton) closeButton.addEventListener("click", function () { showQaPanel(false); });
    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        submitQa();
      });
    }
    if (input) {
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          submitQa();
        }
      });
      input.addEventListener("input", function () {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 108) + "px";
      });
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && qaState.open) showQaPanel(false);
    });
  }

  function showQaPanel(show) {
    var panel = byId("qa-panel");
    var orb = byId("qa-orb");
    if (!panel) return;
    qaState.open = !!show;
    panel.hidden = !show;
    if (orb) orb.setAttribute("aria-expanded", show ? "true" : "false");
    if (show) {
      if (!qaState.examplesLoaded) loadQaExamples();
      var input = byId("qa-input");
      if (input) setTimeout(function () { input.focus(); }, 60);
      scrollQaToBottom();
    }
  }

  function openQa(question) {
    // 首页免登录，但问答机器人仍只对已注册并登录的用户开放：
    // 匿名点击首页「可溯源问答」能力卡时平滑引导到注册入口，而不是静默无反应。
    if (!state.user) { redirectToRegister(); return; }
    injectQa();
    showQaPanel(true);
    if (question) {
      var input = byId("qa-input");
      if (input) input.value = question;
      submitQa();
    }
  }

  function loadQaExamples() {
    qaState.examplesLoaded = true;
    api("/api/qa/examples", { silent: true }).then(function (data) {
      var list = data && Array.isArray(data.examples) ? data.examples : [];
      renderQaExamples(list);
    }).catch(function () {
      renderQaExamples(QA_FALLBACK_EXAMPLES);
    });
  }

  function renderQaExamples(list) {
    var host = byId("qa-examples");
    if (!host) return;
    if (!list.length) {
      host.innerHTML = '<span class="muted tiny">' +
        escapeHtml(enText("暂无示例问题，可直接输入提问。", "No preset questions. Type your own question above.")) + '</span>';
      return;
    }
    host.innerHTML = list.slice(0, 6).map(function (item) {
      var value = typeof item === "string" ? { question: item, in_scope: true } : item;
      // 英文模式优先用英文预设；中文模式用规范中文问题。
      var canonical = value.question_zh || value.question || value.text || "";
      var question = isEn()
        ? (value.question_en || value.question || canonical)
        : (value.question || canonical);
      if (!question) return "";
      // 界面按语言展示，但提交时回传规范中文问题，保证中文知识库检索命中率一致。
      return '<button class="qa-chip" type="button" data-question="' + escapeHtml(canonical) +
        '" data-display="' + escapeHtml(question) + '"' +
        (value.note ? ' title="' + escapeHtml(value.note) + '"' : '') + '>' +
        escapeHtml(question) + '</button>';
    }).join("");
    host.onclick = function (event) {
      var button = event.target.closest ? event.target.closest("[data-question]") : null;
      if (!button) return;
      var input = byId("qa-input");
      var display = button.getAttribute("data-display") || button.getAttribute("data-question") || "";
      if (input) input.value = display;
      submitQa(button.getAttribute("data-question") || display);
    };
  }

  function scrollQaToBottom() {
    var body = byId("qa-body");
    if (body) body.scrollTop = body.scrollHeight;
  }

  function appendQaRow(role, innerHtml) {
    var host = byId("qa-messages");
    if (!host) return null;
    var row = document.createElement("div");
    row.className = "qa-msg qa-msg--" + role;
    var bubble = document.createElement("div");
    bubble.className = "qa-bubble";
    if (role === "bot") bubble.classList.add("qa-bubble--bot");
    bubble.innerHTML = innerHtml;
    row.appendChild(bubble);
    host.appendChild(row);
    scrollQaToBottom();
    return row;
  }

  function appendQaLoading() {
    var row = document.createElement("div");
    row.className = "qa-msg qa-msg--bot";
    row.innerHTML = '<div class="qa-bubble"><div class="qa-loading" aria-label="' +
      escapeHtml(tr("正在检索")) + '">' +
      '<span class="dot"></span><span class="dot"></span><span class="dot"></span><span>' +
      escapeHtml(tr("正在检索知识库…")) + '</span></div></div>';
    var host = byId("qa-messages");
    if (host) host.appendChild(row);
    scrollQaToBottom();
    return row;
  }

  function renderQaAnswerText(answer, citations) {
    var source = String(answer || "");
    var parts = [];
    var cursor = 0;
    var pattern = /\[(\d{1,2})\]/g;
    var match = pattern.exec(source);
    while (match !== null) {
      var index = Number(match[1]);
      if (index >= 1 && index <= citations.length) {
        if (match.index > cursor) parts.push(escapeHtml(source.slice(cursor, match.index)));
        parts.push('<button class="qa-cite" type="button" data-cite="' + index + '" aria-label="' +
          escapeHtml(enText("查看引用 " + index, "View citation " + index)) + '">[' + index + ']</button>');
        cursor = match.index + match[0].length;
      }
      match = pattern.exec(source);
    }
    parts.push(escapeHtml(source.slice(cursor)));
    return parts.join("").replace(/\n/g, "<br>");
  }

  function qaCitationsHtml(citations) {
    return '<div class="qa-citations"><p class="qa-citations__hint">' +
      escapeHtml(enText("参考来源 · 点开 [n] 查看原文与出处",
                        "Sources · expand [n] to read the original text and provenance")) + '</p>' +
      citations.map(function (item) {
        var meta = [];
        if (item.section) meta.push(enText("章节：", "Section: ") + item.section);
        if (item.page) meta.push(enText("页码：", "Page: ") + item.page);
        if (item.doc_id) meta.push(enText("来源编号：", "Source ID: ") + item.doc_id);
        if (typeof item.score === "number") meta.push(enText("相似度 ", "Similarity ") + item.score.toFixed(3));
        var chunkId = (item.chunk_id === null || item.chunk_id === undefined) ? "" : String(item.chunk_id);
        return '<details class="qa-citation" data-cite-index="' + escapeHtml(String(item.index)) +
          '" data-chunk-id="' + escapeHtml(chunkId) + '">' +
          '<summary>[' + escapeHtml(String(item.index)) + '] ' +
            escapeHtml(enText("参考来源", "Source")) + ' · ' +
            escapeHtml(item.title || enText("知识片段", "Knowledge chunk")) +
            (item.section ? " · " + escapeHtml(item.section) : "") + '</summary>' +
          '<div class="qa-citation-body">' +
            (item.snippet ? '<p>' + escapeHtml(item.snippet) + '</p>' : '') +
            (meta.length ? '<p>' + escapeHtml(meta.join(" · ")) + '</p>' : '') +
            '<div class="qa-source-full" data-loaded="0" hidden><span class="tiny">' +
              escapeHtml(tr("正在读取来源原文…")) + '</span></div>' +
            (item.source_url
              ? '<a href="' + escapeHtml(item.source_url) + '" target="_blank" rel="noopener noreferrer">' +
                escapeHtml(tr("打开原始链接 ↗")) + '</a>'
              : '<span class="tiny">' + escapeHtml(enText(
                  "该切片无外部链接，完整原文见上方展开内容",
                  "No external link for this chunk; full text is shown above")) + '</span>') +
          '</div></details>';
      }).join("") + '</div>';
  }

  function refusalText(reason) {
    var zh = "知识库中没有足够相关的资料，无法可靠回答这个问题。";
    var en = "The knowledge base has no sufficiently relevant material to answer this question reliably.";
    if (reason === "out_of_knowledge_base") {
      zh = "该问题不在知识库覆盖范围内，已拒绝回答。";
      en = "This question is outside the knowledge base; answer refused.";
    } else if (reason === "insufficient_evidence") {
      zh = "知识库中没有足够相关、可追溯的片段，已拒绝回答。";
      en = "The knowledge base has no sufficiently relevant, traceable chunks; answer refused.";
    } else if (reason === "no_relevant_chunk") {
      zh = "知识库中没有足够相关的资料（检索相似度低于阈值），因此不做推测性回答。";
      en = "No sufficiently relevant chunks were retrieved (below the similarity threshold); no speculative answer is given.";
    } else if (reason) {
      zh = "暂时无法回答：" + String(reason);
      en = "Unable to answer right now: " + String(reason);
    }
    return isEn() ? en : zh;
  }

  function appendQaAnswer(data) {
    var unsafe = data && data.unsafe === true;
    var refused = data && data.refused === true && !unsafe;
    var citations = data && Array.isArray(data.citations) ? data.citations : [];
    var menu = byId("qa-intro");
    if (menu) menu.hidden = true;
    var bubbleClass = "qa-bubble";
    if (unsafe) bubbleClass += " qa-bubble--unsafe";
    else if (refused) bubbleClass += " qa-bubble--refused";
    var content = "";
    if (unsafe) {
      content = '<p><strong>' + escapeHtml(enText("安全提示：", "Safety notice: ")) + '</strong>' +
        escapeHtml(data.answer || enText("该问题涉及敏感内容，已停止回答。",
          "This question involves sensitive content; the answer was stopped.")) + '</p>';
    } else if (refused) {
      content = '<p><strong>' + escapeHtml(enText("暂不回答：", "Answer refused: ")) + '</strong>' +
        escapeHtml(data.answer || refusalText(data.reason)) + '</p>' +
        '<p class="tiny">' + escapeHtml(enText(
          "可换一种问法，或改为与急诊沟通、术语、流程相关的问题。",
          "Try rephrasing, or ask about emergency communication, terminology or procedures.")) + '</p>';
    } else {
      content = '<div class="qa-answer-text">' + renderQaAnswerText(data.answer || "", citations) + '</div>';
      if (citations.length) content += qaCitationsHtml(citations);
    }
    var host = byId("qa-messages");
    var row = document.createElement("div");
    row.className = "qa-msg qa-msg--bot";
    var bubble = document.createElement("div");
    bubble.className = bubbleClass;
    bubble.innerHTML = content;
    row.appendChild(bubble);
    host.appendChild(row);
    bindQaCitationButtons(row);
    scrollQaToBottom();
    return row;
  }

  function bindQaCitationButtons(root) {
    if (!root || root.getAttribute("data-bind-cite") === "1") return;
    root.setAttribute("data-bind-cite", "1");
    root.addEventListener("click", function (event) {
      var button = event.target.closest ? event.target.closest(".qa-cite") : null;
      if (!button) return;
      var index = button.getAttribute("data-cite");
      var card = root.querySelector('.qa-citation[data-cite-index="' + index + '"]');
      if (!card) return;
      all(".qa-citation", root).forEach(function (item) { item.classList.remove("is-target"); });
      card.classList.add("is-target");
      card.open = true;   // 触发 toggle，自动加载该条来源全文
      card.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
    // 每条参考来源都可点开：展开时按切片编号拉取完整原文与出处。
    // 站内多数切片没有外部链接，这一步保证 [n] 永远有可核对的内容。
    all(".qa-citation", root).forEach(function (card) {
      card.addEventListener("toggle", function () {
        if (!card.open) return;
        var full = card.querySelector(".qa-source-full");
        if (!full || full.getAttribute("data-loaded") === "1") return;
        var chunkId = card.getAttribute("data-chunk-id") || "";
        full.hidden = false;
        if (!chunkId) {
          full.setAttribute("data-loaded", "1");
          full.innerHTML = '<span class="tiny">' + escapeHtml(enText(
            "该引用缺少切片编号，无法展开来源。",
            "This citation has no chunk ID and cannot be expanded.")) + '</span>';
          return;
        }
        api("/api/qa/source/" + encodeURIComponent(chunkId), { silent: true, authOptional: true })
          .then(function (data) {
            full.setAttribute("data-loaded", "1");
            var rows = [];
            if (data && data.title) rows.push("<strong>" + escapeHtml(enText("资料：", "Document: ")) + "</strong>" + escapeHtml(data.title));
            if (data && data.section) rows.push("<strong>" + escapeHtml(enText("章节：", "Section: ")) + "</strong>" + escapeHtml(data.section));
            if (data && data.page) rows.push("<strong>" + escapeHtml(enText("页码：", "Page: ")) + "</strong>" + escapeHtml(data.page));
            if (data && data.doc_id) rows.push("<strong>" + escapeHtml(enText("来源编号：", "Source ID: ")) + "</strong>" + escapeHtml(data.doc_id));
            if (data && data.license) rows.push("<strong>" + escapeHtml(enText("引用要求：", "Citation requirements: ")) + "</strong>" + escapeHtml(data.license));
            if (data && data.source_url) {
              rows.push('<a href="' + escapeHtml(data.source_url) +
                '" target="_blank" rel="noopener noreferrer">' + escapeHtml(tr("打开原始链接 ↗")) + '</a>');
            }
            var text = data && data.text
              ? escapeHtml(data.text).replace(/\n/g, "<br>")
              : enText("（暂无原文）", "(No source text available)");
            full.innerHTML = '<div class="qa-source-full__meta">' + rows.join("<br>") + '</div>' +
              '<div class="qa-source-full__text">' + text + '</div>';
          })
          .catch(function () {
            full.setAttribute("data-loaded", "1");
            full.innerHTML = '<span class="tiny">' + escapeHtml(enText(
              "来源原文加载失败，请稍后重试。",
              "Failed to load the source text. Please try again.")) + '</span>';
          });
      });
    });
  }

  async function submitQa(overrideQuestion) {
    if (qaState.busy) return;
    // 注册前置门禁：未登录不开放问答机器人。
    if (!state.user) { redirectToRegister(); return; }
    var input = byId("qa-input");
    if (!input) return;
    var display = String(input.value || "").trim();
    if (!display) { input.focus(); return; }
    var question = String(overrideQuestion || display).trim();
    if (question.length > 500) { toast(tr("问题最多 500 字"), "warn"); return; }

    qaState.busy = true;
    var sendButton = byId("qa-send");
    if (sendButton) sendButton.disabled = true;
    input.value = "";
    input.style.height = "auto";
    appendQaRow("user", escapeHtml(display));
    var loading = appendQaLoading();
    try {
      var data = await api("/api/qa", { method: "POST", body: { question: question },
                                        silent: true, authOptional: true });
      if (loading && loading.parentNode) loading.parentNode.removeChild(loading);
      appendQaAnswer(data || {});
    } catch (error) {
      if (loading && loading.parentNode) loading.parentNode.removeChild(loading);
      if (error && error.status === 401) {
        // 会话失效 / 未完成注册：回到注册入口，不在问答里给出越权或库外内容。
        redirectToRegister();
        return;
      }
      var message = error && error.status === 429
        ? tr("提问过于频繁，请稍后再试。")
        : tr("提问失败：{msg}", { msg: (error && error.message) || tr("请稍后重试") });
      appendQaRow("bot", '<p class="qa-bubble--refused-inline">' + escapeHtml(message) + '</p>');
    } finally {
      qaState.busy = false;
      if (sendButton) sendButton.disabled = false;
      if (input) input.focus();
    }
  }


  // ---------------- 通用表单工具 ----------------
  function setBusy(button, busy, busyText) {
    if (!button) return;
    if (busy) {
      if (!button.getAttribute("data-idle-label")) {
        button.setAttribute("data-idle-label", button.textContent || "");
      }
      button.disabled = true;
      button.innerHTML = '<span class="spinner" aria-hidden="true"></span>' + escapeHtml(busyText || "处理中…");
    } else {
      var label = button.getAttribute("data-idle-label");
      button.disabled = false;
      if (label) button.textContent = label;
    }
  }
  function setFieldError(id, message) {
    var node = byId(id);
    if (node) node.textContent = message || "";
  }
  function clearFieldErrors(ids) {
    (ids || []).forEach(function (id) { setFieldError(id, ""); });
  }
  function showFormError(id, message) {
    var node = byId(id);
    if (!node) return;
    node.hidden = false;
    node.textContent = message || "操作失败";
  }
  function hideFormError(id) {
    var node = byId(id);
    if (!node) return;
    node.hidden = true;
    node.textContent = "";
  }
  function loadingBlock(message) {
    return '<div class="loading-box"><p class="muted small">' + escapeHtml(message || "正在加载…") + '</p>' +
      '<span class="skeleton skeleton--text"></span><span class="skeleton skeleton--text"></span>' +
      '<span class="skeleton skeleton--line-sm"></span></div>';
  }
  function emptyHtml(title, desc) {
    return '<div class="empty"><div class="empty-icon" aria-hidden="true">—</div><h3>' + escapeHtml(title) + '</h3>' +
      '<p>' + escapeHtml(desc || "") + '</p></div>';
  }
  function pager(container, config) {
    if (!container) return;
    container.innerHTML = "";
    var total = Number(config.total) || 0;
    if (total <= 0) return;
    var pageSize = Number(config.pageSize) || 10;
    var page = Number(config.page) || 1;
    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    var info = document.createElement("span");
    info.className = "pager-info";
    info.textContent = tr("共 {n} 条 · 第 {p} / {t} 页",
      { n: fmtNumber(total), p: page, t: totalPages });
    container.appendChild(info);
    var controls = document.createElement("div");
    controls.className = "pager-controls";
    function addButton(label, target, options) {
      var settings = options || {};
      var button = document.createElement("button");
      button.type = "button";
      button.className = "pager-btn" + (settings.active ? " is-active" : "");
      button.textContent = label;
      if (settings.disabled) button.disabled = true;
      if (!settings.disabled && target !== page) {
        button.addEventListener("click", function () { config.onChange(target); });
      }
      controls.appendChild(button);
    }
    addButton("上一页", page - 1, { disabled: page <= 1 });
    var start = Math.max(1, page - 2);
    var end = Math.min(totalPages, start + 4);
    start = Math.max(1, end - 4);
    for (var index = start; index <= end; index++) {
      addButton(String(index), index, { active: index === page });
    }
    addButton("下一页", page + 1, { disabled: page >= totalPages });
    container.appendChild(controls);
  }
  function authErrorMessage(error, fallback) {
    if (!error || error.status === 0) return "网络异常，请检查网络后重试";
    if (error.status === 401) return "账号或密码错误";
    if (error.status === 403) return error.message || "账号已停用或无权访问";
    if (error.status === 409) return error.message || "邮箱或用户名已被占用";
    if (error.status === 422) return formatDetail(error.data && error.data.detail) || "提交内容不符合要求";
    if (error.status === 429) return error.message || "操作过快，请稍后再试";
    return error.message || fallback || "操作失败，请稍后重试";
  }

  // ---------------- 登录页 ----------------
  function initLogin() {
    var form = byId("login-form");
    if (!form) return;
    var params = new URLSearchParams(window.location.search);
    var next = safeNext(params.get("next"));
    var registerLink = byId("register-link");
    if (registerLink) registerLink.href = "register.html" + (next ? "?next=" + encodeURIComponent(next) : "");
    if (params.get("registered") === "1") {
      var success = byId("login-success");
      if (success) {
        success.hidden = false;
        success.textContent = "注册成功，请使用新账号登录。";
      }
    }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      submitLogin(next);
    });
  }
  async function submitLogin(next) {
    clearFieldErrors(["err-account", "err-password"]);
    hideFormError("login-error");
    var account = (byId("login-account").value || "").trim();
    var password = byId("login-password").value || "";
    var valid = true;
    if (account.length < 3) {
      setFieldError("err-account", "请输入邮箱或用户名（至少 3 个字符）");
      valid = false;
    }
    if (!password) {
      setFieldError("err-password", "请输入密码");
      valid = false;
    }
    if (!valid) return;
    var button = byId("login-submit");
    setBusy(button, true, "登录中…");
    try {
      var data = await api("/api/auth/login", {
        method: "POST",
        body: { account: account, password: password },
        silent: true,
        authOptional: true
      });
      setCsrf(data && data.csrf_token);
      state.user = data && data.user ? data.user : null;
      App.currentUser = state.user;
      toast("登录成功", "success");
      window.location.href = next || "index.html";
    } catch (error) {
      showFormError("login-error", authErrorMessage(error, "登录失败，请稍后重试"));
    } finally {
      setBusy(button, false);
    }
  }

  // ---------------- 注册页 ----------------
  function initRegister() {
    var form = byId("register-form");
    if (!form) return;
    var params = new URLSearchParams(window.location.search);
    var next = safeNext(params.get("next"));
    var loginLink = byId("login-link");
    if (loginLink) loginLink.href = "login.html" + (next ? "?next=" + encodeURIComponent(next) : "");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      submitRegister(next);
    });
  }
  function emailLooksValid(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }
  async function submitRegister(next) {
    clearFieldErrors(["err-email", "err-username", "err-password", "err-password2", "err-email"]);
    hideFormError("register-error");
    var email = (byId("register-email").value || "").trim();
    var username = (byId("register-username").value || "").trim();
    var password = byId("register-password").value || "";
    var password2 = byId("register-password2").value || "";
    var display = (byId("register-display").value || "").trim();
    var valid = true;
    if (!email) {
      setFieldError("err-email", "请输入邮箱");
      valid = false;
    } else if (!emailLooksValid(email)) {
      setFieldError("err-email", "邮箱格式不正确");
      valid = false;
    }
    if (!/^[A-Za-z0-9_]{3,32}$/.test(username)) {
      setFieldError("err-username", "用户名需为 3–32 位字母、数字或下划线");
      valid = false;
    }
    if (password.length < 8) {
      setFieldError("err-password", "密码至少 8 位");
      valid = false;
    } else if (password.length > 72) {
      setFieldError("err-password", "密码最多 72 位");
      valid = false;
    }
    if (password !== password2) {
      setFieldError("err-password2", "两次输入的密码不一致");
      valid = false;
    }
    if (display.length > 32) {
      setFieldError("err-display", "显示名称最多 32 个字符");
      valid = false;
    }
    if (!valid) return;

    var button = byId("register-submit");
    setBusy(button, true, "注册中…");
    try {
      await api("/api/auth/register", {
        method: "POST",
        body: { email: email, username: username, password: password, display_name: display },
        silent: true,
        authOptional: true
      });
    } catch (error) {
      showFormError("register-error", authErrorMessage(error, "注册失败，请稍后重试"));
      setBusy(button, false);
      return;
    }
    try {
      var loginData = await api("/api/auth/login", {
        method: "POST",
        body: { account: username, password: password },
        silent: true,
        authOptional: true
      });
      setCsrf(loginData && loginData.csrf_token);
      state.user = loginData && loginData.user ? loginData.user : null;
      App.currentUser = state.user;
      toast("注册成功，已自动登录", "success");
      window.location.href = next || "index.html";
    } catch (loginError) {
      toast("注册成功，请手动登录", "warn");
      window.location.href = "login.html?registered=1" + (next ? "&next=" + encodeURIComponent(next) : "");
    } finally {
      setBusy(button, false);
    }
  }

  // ---------------- 资讯页（注册登录后可见） ----------------
  var newsState = { status: "published", source: "", page: 1, pageSize: 10, total: 0 };

  function newsSourceBadge(item) {
    var source = item.source || "";
    // 后端可能已经按 X-Lang 返回英文 label；再经 enLabel() 兜底，两种路径都安全。
    var label = enLabel(item.source_label || source);
    var className = "badge--source-" + source;
    return '<span class="badge ' + className + '">' + escapeHtml(label) + '</span>';
  }
  function newsMethodBadge(item) {
    var method = item.translated_by || (item.title_zh ? "机器翻译" : "原文待译");
    var zh = item.translated_by_zh || method;
    var className = zh === "中文版源" || method === "Chinese-language source"
      ? "badge--status-ok"
      : (zh === "机器翻译" || method === "Machine translation" ? "badge--mt" : "badge--status-pending");
    return '<span class="badge ' + className + '">' + escapeHtml(enLabel(zh)) + '</span>';
  }
  function initNews() {
    all(".tab[data-status]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        var status = tab.getAttribute("data-status") || "published";
        if (status === newsState.status) return;
        newsState.status = status;
        newsState.page = 1;
        all(".tab[data-status]").forEach(function (item) {
          var active = item === tab;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-selected", active ? "true" : "false");
        });
        loadNews();
      });
    });
    var sourceSelect = byId("news-source");
    if (sourceSelect) {
      sourceSelect.addEventListener("change", function () {
        newsState.source = sourceSelect.value;
        newsState.page = 1;
        loadNews();
      });
    }
    loadNews();
  }
  function loadNews() {
    var host = byId("news-list");
    var meta = byId("news-meta");
    if (!host) return;
    host.innerHTML = '<div class="card"><span class="skeleton skeleton--title"></span>' +
      '<span class="skeleton skeleton--text"></span><span class="skeleton skeleton--line-sm"></span></div>';
    if (meta) meta.textContent = tr("正在加载资讯…");
    var params = ["status=" + encodeURIComponent(newsState.status), "page=" + newsState.page, "page_size=" + newsState.pageSize];
    if (newsState.source) params.push("source=" + encodeURIComponent(newsState.source));
    api("/api/news?" + params.join("&"), { silent: true }).then(function (data) {
      newsState.total = data.total || 0;
      renderNewsItems(data.items || []);
      if (meta) meta.textContent = tr("共 {n} 条资讯", { n: fmtNumber(newsState.total) });
      pager(byId("news-pager"), {
        page: newsState.page,
        pageSize: newsState.pageSize,
        total: newsState.total,
        onChange: function (page) { newsState.page = page; loadNews(); }
      });
    }).catch(function (error) {
      host.innerHTML = emptyHtml("资讯加载失败", error.message || "请稍后重试。");
      if (meta) meta.textContent = "加载失败";
    });
  }
  function renderNewsItems(items) {
    var host = byId("news-list");
    if (!host) return;
    if (!items.length) {
      host.innerHTML = emptyHtml("暂无资讯", "当前筛选条件下没有内容，可切换筛选或稍后再来。");
      return;
    }
    host.innerHTML = items.map(function (item) {
      // 英文模式：英文标题作主行，中文标题降为副行；中文模式保持原顺序。
      var pair = enPair(item.title_zh || "", item.title_en || "");
      var title = pair.primary || (isEn() ? "Untitled" : "（无标题）");
      var sub = pair.secondary && pair.secondary !== pair.primary ? pair.secondary : "";
      return '<article class="news-item" data-news-id="' + item.id + '">' +
        '<button class="news-item-head" type="button" data-news-toggle="' + item.id + '" aria-expanded="false">' +
          '<span class="grow">' +
            '<span class="news-meta">' + newsSourceBadge(item) + newsMethodBadge(item) +
              '<span class="muted tiny">' + escapeHtml(fmtTime(item.published_at)) + '</span></span>' +
            '<span class="news-title">' + escapeHtml(title) + '</span>' +
            (sub ? '<span class="news-sub">' + escapeHtml(sub) + '</span>' : '') +
          '</span>' +
          '<span class="news-caret" aria-hidden="true">' + escapeHtml(tr("展开")) + '</span>' +
        '</button>' +
        '<div class="news-detail" hidden></div></article>';
    }).join("");
    host.onclick = function (event) {
      var head = event.target.closest ? event.target.closest("[data-news-toggle]") : null;
      if (head) toggleNewsDetail(head);
    };
  }
  function toggleNewsDetail(head) {
    var article = head.closest(".news-item");
    var detail = article ? article.querySelector(".news-detail") : null;
    if (!detail) return;
    var caret = head.querySelector(".news-caret");
    var expanded = head.getAttribute("aria-expanded") === "true";
    if (expanded) {
      head.setAttribute("aria-expanded", "false");
      detail.hidden = true;
      if (caret) caret.textContent = tr("展开");
      return;
    }
    head.setAttribute("aria-expanded", "true");
    detail.hidden = false;
    if (caret) caret.textContent = tr("收起");
    if (detail.getAttribute("data-loaded") === "1") return;
    detail.innerHTML = loadingBlock("正在加载详情…");
    api("/api/news/" + head.getAttribute("data-news-toggle"), { silent: true }).then(function (data) {
      detail.innerHTML = renderNewsDetail(data || {});
      detail.setAttribute("data-loaded", "1");
    }).catch(function (error) {
      detail.innerHTML = '<p class="muted small">' +
        escapeHtml(tr("详情加载失败：{msg}", { msg: error.message || tr("请稍后重试。") })) + '</p>';
    });
  }
  function renderNewsDetail(data) {
    // 英文模式：英文摘要在前，中文摘要作为副行；中文模式保持原顺序。
    var pair = enPair(data.summary_zh || "", data.summary_en || "");
    var primary = pair.primary || (isEn() ? "No summary available." : "暂无中文摘要。");
    var secondary = pair.secondary && pair.secondary !== pair.primary ? pair.secondary : "";
    var link = data.url
      ? '<a href="' + escapeHtml(data.url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(tr("阅读原文 ↗")) + '</a>'
      : '<span class="muted tiny">' + escapeHtml(tr("无原文链接")) + '</span>';
    var accessLabel = isEn() ? "Access date: " : "访问日期：";
    var licenceLabel = isEn() ? "Licence: " : "许可：";
    var fetchedLabel = isEn() ? "Fetched at: " : "抓取时间：";
    return '<div class="news-meta">' + newsSourceBadge(data) + newsMethodBadge(data) + '</div>' +
      '<p>' + escapeHtml(primary) + '</p>' +
      (secondary ? '<p class="muted small wrap-anywhere">' + escapeHtml(secondary) + '</p>' : '') +
      '<div class="news-actions">' + link +
        '<span class="muted tiny">' + escapeHtml(accessLabel) + escapeHtml(data.access_date || todayString()) + '</span>' +
        (data.license ? '<span class="muted tiny wrap-anywhere">' + escapeHtml(licenceLabel) + escapeHtml(data.license) + '</span>' : '') +
        (data.fetched_at ? '<span class="muted tiny">' + escapeHtml(fetchedLabel) + escapeHtml(fmtTime(data.fetched_at)) + '</span>' : '') +
      '</div>';
  }


  // ---------------- 我的（私有术语 / 语料） ----------------
  var LANG_PAIRS = [
    { value: "zh-en", label: "中文 → 英文" },
    { value: "en-zh", label: "英文 → 中文" },
    { value: "zh-vi", label: "中文 → 越南语" },
    { value: "zh-th", label: "中文 → 泰语" },
    { value: "zh-id", label: "中文 → 印尼语" },
    { value: "zh-ms", label: "中文 → 马来语" }
  ];
  var REGISTER_OPTIONS = [
    { value: "", label: "未标注" },
    { value: "书面", label: "书面语" },
    { value: "口语", label: "口语" }
  ];
  var accountState = { tab: "terms", q: "", page: 1, pageSize: 10, total: 0, items: [] };

  function optionsHtml(list, selected) {
    return (list || []).map(function (item) {
      return '<option value="' + escapeHtml(String(item.value)) + '"' +
        (String(item.value) === String(selected) ? " selected" : "") + '>' + escapeHtml(String(item.label)) + '</option>';
    }).join("");
  }
  function accountErrorMessage(error) {
    if (!error || error.status === 0) return "网络异常，请稍后重试";
    if (error.status === 409) return error.message || "已存在同名词条";
    if (error.status === 422) return formatDetail(error.data && error.data.detail) || "提交内容不符合要求";
    if (error.status === 404) return "条目不存在或无权访问";
    return error.message || "保存失败，请稍后重试";
  }
  function initAccount() {
    var greeting = byId("account-greeting");
    if (greeting) greeting.textContent = tr("你好，{name}（@{user}）· 这里的数据仅本人可见",
      { name: displayName(state.user), user: (state.user && state.user.username) || "" });
    loadAccountOverview();
    bindAccountTabs();
    bindAccountToolbar();
    loadAccountList();
  }
  function loadAccountOverview() {
    api("/api/me/overview", { silent: true }).then(function (data) {
      setText("overview-terms", fmtNumber(data.my_terms));
      setText("overview-corpus", fmtNumber(data.my_corpus));
      setText("overview-chunks", fmtNumber(data.chunks));
      if (data.user) {
        setText("account-greeting", tr("你好，{name}（@{user}）· 这里的数据仅本人可见",
          { name: displayName(data.user), user: data.user.username || "" }));
      }
    }).catch(function () { /* 概览失败不阻塞 */ });
  }
  function bindAccountTabs() {
    all(".tab[data-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        var tabName = tab.getAttribute("data-tab");
        if (tabName === accountState.tab) return;
        accountState.tab = tabName;
        accountState.page = 1;
        accountState.q = "";
        var search = byId("account-search");
        if (search) search.value = "";
        all(".tab[data-tab]").forEach(function (item) {
          var active = item === tab;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-selected", active ? "true" : "false");
        });
        var newButton = byId("new-btn");
        if (newButton) newButton.textContent = tabName === "terms" ? "新建术语" : "新建语料";
        if (search) search.placeholder = tabName === "terms" ? "搜索中文、英文或领域" : "搜索原文或译文";
        loadAccountList();
      });
    });
  }
  function bindAccountToolbar() {
    var search = byId("account-search");
    if (search) {
      var runSearch = function () {
        accountState.q = (search.value || "").trim();
        accountState.page = 1;
        loadAccountList();
      };
      search.addEventListener("input", debounce(runSearch, 350));
      search.addEventListener("keydown", function (event) {
        if (event.key === "Enter") { event.preventDefault(); runSearch(); }
      });
    }
    var exportButton = byId("export-btn");
    if (exportButton) {
      exportButton.addEventListener("click", function () { downloadCsv(accountState.tab); });
    }
    var newButton = byId("new-btn");
    if (newButton) {
      newButton.addEventListener("click", function () {
        if (accountState.tab === "terms") openTermModal(null);
        else openCorpusModal(null);
      });
    }
  }
  function accountEndpoint() {
    return accountState.tab === "terms" ? "/api/me/terms" : "/api/me/corpus";
  }
  function loadAccountList() {
    var panel = byId("account-panel");
    if (!panel) return;
    panel.innerHTML = loadingBlock(tr("正在加载我的{tab}…",
      { tab: accountState.tab === "terms" ? tr("术语") : tr("语料") }));
    var url = accountEndpoint() + "?q=" + encodeURIComponent(accountState.q) +
      "&page=" + accountState.page + "&page_size=" + accountState.pageSize;
    api(url, { silent: true }).then(function (data) {
      accountState.total = data.total || 0;
      accountState.items = data.items || [];
      if (accountState.tab === "terms") renderAccountTerms(accountState.items);
      else renderAccountCorpus(accountState.items);
      renderAccountPager();
    }).catch(function (error) {
      panel.innerHTML = emptyHtml("加载失败", error.message || "请稍后重试。");
      accountState.items = [];
      renderAccountPager();
    });
  }
  function renderAccountPager() {
    pager(byId("account-pager"), {
      page: accountState.page,
      pageSize: accountState.pageSize,
      total: accountState.total,
      onChange: function (page) { accountState.page = page; loadAccountList(); }
    });
  }
  function bindAccountRowActions(tbody) {
    if (!tbody) return;
    tbody.onclick = function (event) {
      var button = event.target.closest ? event.target.closest("button[data-action]") : null;
      if (!button) return;
      var id = Number(button.getAttribute("data-id"));
      var item = accountState.items.filter(function (entry) { return Number(entry.id) === id; })[0];
      if (!item) return;
      if (button.getAttribute("data-action") === "edit") {
        if (accountState.tab === "terms") openTermModal(item);
        else openCorpusModal(item);
      } else {
        deleteAccountItem(item);
      }
    };
  }
  function renderAccountTerms(items) {
    var panel = byId("account-panel");
    if (!items.length) {
      panel.innerHTML = emptyHtml("还没有私有术语", "新建一条术语，或到「语言质量」页把公共术语加入我的库。");
      return;
    }
    var rows = items.map(function (item, index) {
      var rowNumber = (accountState.page - 1) * accountState.pageSize + index + 1;
      return "<tr>" +
        '<td class="col-num">' + rowNumber + "</td>" +
        '<td class="term-zh" data-label="中文术语">' + escapeHtml(item.zh) + "</td>" +
        '<td class="term-en" data-label="英文译法">' + escapeHtml(item.en || "—") + "</td>" +
        '<td data-label="语种">' + escapeHtml(item.lang_pair || "—") + "</td>" +
        '<td data-label="领域">' + escapeHtml(item.domain || "—") + "</td>" +
        '<td class="nowrap" data-label="更新时间">' + escapeHtml(fmtDate(item.updated_at)) + "</td>" +
        '<td class="cell-actions" data-label="操作">' +
          '<button class="btn btn--ghost btn--sm" type="button" data-action="edit" data-id="' + item.id + '">编辑</button> ' +
          '<button class="btn btn--ghost btn--sm" type="button" data-action="delete" data-id="' + item.id + '">删除</button>' +
        "</td></tr>";
    }).join("");
    panel.innerHTML = '<div class="table-wrap"><table class="data-table">' +
      '<caption class="sr-only">我的私有术语列表</caption>' +
      "<thead><tr><th class=\"col-num\">#</th><th>中文术语</th><th>英文译法</th><th>语种</th><th>领域</th><th>更新时间</th><th>操作</th></tr></thead>" +
      "<tbody>" + rows + "</tbody></table></div>";
    bindAccountRowActions(panel.querySelector("tbody"));
  }
  function renderAccountCorpus(items) {
    var panel = byId("account-panel");
    if (!items.length) {
      panel.innerHTML = emptyHtml("还没有私有语料", "新建一条语料，或到「语言质量」页把公共句对加入我的库。");
      return;
    }
    var rows = items.map(function (item, index) {
      var rowNumber = (accountState.page - 1) * accountState.pageSize + index + 1;
      return "<tr>" +
        '<td class="col-num">' + rowNumber + "</td>" +
        '<td class="wrap-anywhere" data-label="中文原文">' + escapeHtml(item.zh) + "</td>" +
        '<td class="wrap-anywhere" data-label="英文译文">' + escapeHtml(item.en || "—") + "</td>" +
        '<td data-label="语种">' + escapeHtml(item.lang_pair || "—") + "</td>" +
        '<td data-label="语域">' + escapeHtml(item.register || "—") + "</td>" +
        '<td class="nowrap" data-label="更新时间">' + escapeHtml(fmtDate(item.updated_at)) + "</td>" +
        '<td class="cell-actions" data-label="操作">' +
          '<button class="btn btn--ghost btn--sm" type="button" data-action="edit" data-id="' + item.id + '">编辑</button> ' +
          '<button class="btn btn--ghost btn--sm" type="button" data-action="delete" data-id="' + item.id + '">删除</button>' +
        "</td></tr>";
    }).join("");
    panel.innerHTML = '<div class="table-wrap"><table class="data-table">' +
      '<caption class="sr-only">我的私有语料列表</caption>' +
      "<thead><tr><th class=\"col-num\">#</th><th>中文原文</th><th>英文译文</th><th>语种</th><th>语域</th><th>更新时间</th><th>操作</th></tr></thead>" +
      "<tbody>" + rows + "</tbody></table></div>";
    bindAccountRowActions(panel.querySelector("tbody"));
  }
  function downloadCsv(kind) {
    var link = document.createElement("a");
    link.href = "/api/me/" + kind + "/export.csv";
    link.setAttribute("download", "my_" + kind + ".csv");
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast("已开始下载 CSV（仅含本人数据）", "success");
  }
  function openTermModal(item) {
    var editing = !!item;
    var value = item || {};
    var content = '<form id="term-form" class="form-grid" novalidate>' +
      '<div class="field"><label for="term-zh">中文术语 *</label>' +
        '<input id="term-zh" type="text" maxlength="255" value="' + escapeHtml(value.zh || "") + '">' +
        '<p class="field-error" id="term-zh-error"></p></div>' +
      '<div class="field"><label for="term-en">英文译法</label>' +
        '<input id="term-en" type="text" maxlength="255" value="' + escapeHtml(value.en || "") + '"></div>' +
      '<div class="field"><label for="term-lang-pair">语种对</label>' +
        '<select id="term-lang-pair">' + optionsHtml(LANG_PAIRS, value.lang_pair || "zh-en") + '</select></div>' +
      '<div class="field"><label for="term-domain">领域</label>' +
        '<input id="term-domain" type="text" maxlength="64" value="' + escapeHtml(value.domain || "") + '"></div>' +
      '<div class="field field--full"><label for="term-definition">释义</label>' +
        '<textarea id="term-definition" rows="3" maxlength="2000">' + escapeHtml(value.definition || "") + '</textarea></div>' +
      '<div class="field field--full"><label for="term-note">备注</label>' +
        '<textarea id="term-note" rows="2" maxlength="1000">' + escapeHtml(value.note || "") + '</textarea></div>' +
      '<div class="field"><label for="term-source-code">来源代码</label>' +
        '<input id="term-source-code" type="text" maxlength="64" value="' + escapeHtml(value.source_code || "") + '"></div>' +
      '<div class="field"><label for="term-source-url">来源链接</label>' +
        '<input id="term-source-url" type="url" maxlength="512" value="' + escapeHtml(value.source_url || "") + '"></div>' +
      '<div class="notice notice--error field--full" id="modal-error" role="alert" hidden></div>' +
      "</form>";
    openModal({
      title: editing ? "编辑术语" : "新建术语",
      content: content,
      actions: [
        { label: "取消", kind: "ghost", onClick: closeModal },
        { label: editing ? "保存修改" : "创建术语", kind: "primary", onClick: function () { submitTermForm(editing, item); } }
      ],
      onMount: function (modal) {
        var form = modal.querySelector("#term-form");
        if (form) form.addEventListener("submit", function (event) { event.preventDefault(); submitTermForm(editing, item); });
      }
    });
  }
  async function submitTermForm(editing, original) {
    clearFieldErrors(["term-zh-error"]);
    hideFormError("modal-error");
    var zh = (byId("term-zh").value || "").trim();
    if (!zh) {
      setFieldError("term-zh-error", "中文术语不能为空");
      byId("term-zh").focus();
      return;
    }
    var payload = {
      zh: zh,
      en: (byId("term-en").value || "").trim(),
      lang_pair: byId("term-lang-pair").value || "zh-en",
      domain: (byId("term-domain").value || "").trim(),
      definition: (byId("term-definition").value || "").trim(),
      note: (byId("term-note").value || "").trim(),
      source_code: (byId("term-source-code").value || "").trim(),
      source_url: (byId("term-source-url").value || "").trim()
    };
    var url = editing ? "/api/me/terms/" + original.id : "/api/me/terms";
    try {
      await api(url, { method: editing ? "PUT" : "POST", body: payload, silent: true });
      closeModal();
      toast(editing ? "已保存修改" : "已创建术语", "success");
      if (!editing) accountState.page = 1;
      loadAccountList();
      loadAccountOverview();
    } catch (error) {
      showFormError("modal-error", accountErrorMessage(error));
    }
  }
  function openCorpusModal(item) {
    var editing = !!item;
    var value = item || {};
    var content = '<form id="corpus-form" class="form-grid" novalidate>' +
      '<div class="field field--full"><label for="corpus-zh">中文原文 *</label>' +
        '<textarea id="corpus-zh" rows="3" maxlength="2000">' + escapeHtml(value.zh || "") + '</textarea>' +
        '<p class="field-error" id="corpus-zh-error"></p></div>' +
      '<div class="field field--full"><label for="corpus-en">英文译文 *</label>' +
        '<textarea id="corpus-en" rows="3" maxlength="2000">' + escapeHtml(value.en || "") + '</textarea>' +
        '<p class="field-error" id="corpus-en-error"></p></div>' +
      '<div class="field"><label for="corpus-lang-pair">语种对</label>' +
        '<select id="corpus-lang-pair">' + optionsHtml(LANG_PAIRS, value.lang_pair || "zh-en") + '</select></div>' +
      '<div class="field"><label for="corpus-register">语域</label>' +
        '<select id="corpus-register">' + optionsHtml(REGISTER_OPTIONS, value.register || "") + '</select></div>' +
      '<div class="field"><label for="corpus-term-id">关联术语 ID</label>' +
        '<input id="corpus-term-id" type="text" maxlength="32" value="' + escapeHtml(value.term_id || "") + '"></div>' +
      '<div class="field"><label for="corpus-source-code">来源代码</label>' +
        '<input id="corpus-source-code" type="text" maxlength="64" value="' + escapeHtml(value.source_code || "") + '"></div>' +
      '<div class="field field--full"><label for="corpus-source-url">来源链接</label>' +
        '<input id="corpus-source-url" type="url" maxlength="512" value="' + escapeHtml(value.source_url || "") + '"></div>' +
      '<div class="field field--full"><label for="corpus-note">备注</label>' +
        '<textarea id="corpus-note" rows="2" maxlength="1000">' + escapeHtml(value.note || "") + '</textarea></div>' +
      '<div class="notice notice--error field--full" id="modal-error" role="alert" hidden></div>' +
      "</form>";
    openModal({
      title: editing ? "编辑语料" : "新建语料",
      content: content,
      actions: [
        { label: "取消", kind: "ghost", onClick: closeModal },
        { label: editing ? "保存修改" : "创建语料", kind: "primary", onClick: function () { submitCorpusForm(editing, item); } }
      ],
      onMount: function (modal) {
        var form = modal.querySelector("#corpus-form");
        if (form) form.addEventListener("submit", function (event) { event.preventDefault(); submitCorpusForm(editing, item); });
      }
    });
  }
  async function submitCorpusForm(editing, original) {
    clearFieldErrors(["corpus-zh-error", "corpus-en-error"]);
    hideFormError("modal-error");
    var zh = (byId("corpus-zh").value || "").trim();
    var en = (byId("corpus-en").value || "").trim();
    var valid = true;
    if (!zh) { setFieldError("corpus-zh-error", "中文原文不能为空"); valid = false; }
    if (!en) { setFieldError("corpus-en-error", "英文译文不能为空"); valid = false; }
    if (!valid) return;
    var payload = {
      zh: zh,
      en: en,
      lang_pair: byId("corpus-lang-pair").value || "zh-en",
      register_kind: byId("corpus-register").value || "",
      term_id: (byId("corpus-term-id").value || "").trim(),
      note: (byId("corpus-note").value || "").trim(),
      source_code: (byId("corpus-source-code").value || "").trim(),
      source_url: (byId("corpus-source-url").value || "").trim()
    };
    var url = editing ? "/api/me/corpus/" + original.id : "/api/me/corpus";
    try {
      await api(url, { method: editing ? "PUT" : "POST", body: payload, silent: true });
      closeModal();
      toast(editing ? "已保存修改" : "已创建语料", "success");
      if (!editing) accountState.page = 1;
      loadAccountList();
      loadAccountOverview();
    } catch (error) {
      showFormError("modal-error", accountErrorMessage(error));
    }
  }
  async function deleteAccountItem(item) {
    var isTerm = accountState.tab === "terms";
    var label = isTerm ? item.zh : truncate(item.zh, 24);
    var confirmed = await confirmDialog({
      title: "删除确认",
      message: "确定删除「" + label + "」吗？",
      detail: "删除后不可恢复；该操作只影响你的私有库，不影响公共库。",
      confirmLabel: "删除",
      danger: true
    });
    if (!confirmed) return;
    try {
      await api((isTerm ? "/api/me/terms/" : "/api/me/corpus/") + item.id, { method: "DELETE", silent: true });
      toast("已删除", "success");
      if (accountState.items.length === 1 && accountState.page > 1) accountState.page -= 1;
      loadAccountList();
      loadAccountOverview();
    } catch (error) {
      toast(tr("删除失败：{msg}", { msg: error.message || tr("请稍后重试") }), "error");
    }
  }

  // ---------------- 公开接口：window.App（供 T3 页面脚本调用） ----------------
  var App = {
    api: api,
    requireLogin: requireLogin,
    currentUser: null,
    toast: toast,
    escapeHtml: escapeHtml,
    fmtTime: fmtTime,
    fmtDate: fmtDate,
    fmtNumber: fmtNumber,
    openQa: openQa,
    sectionColor: function (name) { return (SECTIONS[name] || SECTIONS.home).color; },
    sectionSoft: function (name) { return (SECTIONS[name] || SECTIONS.home).soft; },
    sections: SECTIONS,
    navItems: NAV_ITEMS.slice(),
    loginUrl: loginUrl,
    gotoLogin: redirectToLogin,
    ready: readyPromise,
    onReady: function (callback) { return readyPromise.then(callback); }
  };
  window.App = App;

  // ---------------- 启动 ----------------
  var PAGE_INIT = {
    index: function () { /* 首页数据与 Canvas 由 home.js 处理 */ },
    login: initLogin,
    register: initRegister,
    news: initNews,
    account: initAccount,
    // 旧的独立跨文化页已并入语言质量模块，保留路径做平滑重定向（含 sharecode）。
    culture: function () {
      var params = new URLSearchParams(window.location.search);
      params.set("tab", "culture");
      window.location.replace("quality.html?" + params.toString());
    }
  };

  function boot() {
    state.page = document.body.getAttribute("data-page") || "index";
    var section = document.body.getAttribute("data-section") || PAGE_SECTION[state.page] || "home";
    state.section = section;
    document.body.setAttribute("data-section", section);
    renderHeader();
    renderBottomNav();
    renderFooter();
    propagateSharecode();
    refreshAuthUi();

    // 首页免登录 + 功能页注册门禁：GUEST_PAGES 内的页面（首页 / 注册 / 登录）
    // 匿名可看；其余页面要求有效会话。服务端 SecurityMiddleware 同步对所有功能
    // API 做 401、对功能页面做 302，前端这层负责把访客平滑送回注册入口并保留
    // sharecode 与原始目标。
    var needsAuth = !GUEST_PAGES[state.page];
    loadMe().then(function (user) {
      App.currentUser = user;
      state.meLoaded = true;
      refreshAuthArea();
      refreshAuthUi();
      if (needsAuth && !user) {
        redirectToRegister();
        return;
      }
      if ((state.page === "login" || state.page === "register") && user) {
        var params = new URLSearchParams(window.location.search);
        var next = safeNext(params.get("next"));
        window.location.replace(next || "index.html");
        return;
      }
      // 问答机器人悬浮球只对已注册并登录的用户注入。
      if (user) injectQa();
      var init = PAGE_INIT[state.page];
      if (typeof init === "function") {
        try {
          init();
        } catch (error) {
          if (window.console) window.console.error(error);
          toast("页面初始化失败，请刷新重试", "error");
        }
      }
      // 兼容旧链接：index.html?qa=1 直接展开问答悬浮窗
      if (new URLSearchParams(window.location.search).get("qa") === "1") {
        window.setTimeout(function () {
          try { openQa(); } catch (error) { if (window.console) window.console.error(error); }
        }, 60);
      }
      readyResolve();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
