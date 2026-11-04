/* 涉外急诊语言服务台 · 云服务客户端（全应用只初始化一次）
 * - 形态：plain HTML 无构建步骤 → CDN IIFE 全局 WorkBuddyCloud；
 *   CDN 不可达时自动回退到同源托管的同一份 @dev 构建（vendor/），避免整站云功能失效。
 * - 全站共用这一个 client：Auth / Database / Storage / LLM 都从 ERCloud.client() 取。
 * - 初始化参数只能来自 WB_PUBLIC_CONFIG（publicConfig），endpoint 为必填。
 */
(function () {
  "use strict";
  var cfg = window.WB_PUBLIC_CONFIG || null;
  var state = { ok: false, reason: "", cloud: null };

  function hasSdk() {
    return !!(window.WorkBuddyCloud &&
      typeof window.WorkBuddyCloud.createWorkBuddyCloud === "function");
  }

  function loadLocalSdk() {
    return new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = "vendor/workbuddy-cloud-sdk.global.js?v=13";
      s.onload = function () { resolve(); };
      s.onerror = function () { resolve(); };
      document.head.appendChild(s);
    });
  }

  function init() {
    if (!cfg) {
      state.reason = "缺少云服务配置（cloud-config.js 未加载）";
      return;
    }
    if (!hasSdk()) {
      state.reason = "云端 SDK 未能加载：CDN 与本地副本均不可用，请检查网络后刷新页面。";
      return;
    }
    try {
      state.cloud = window.WorkBuddyCloud.createWorkBuddyCloud({
        endpoint: cfg.endpoint,
        oauthRelayBaseUrl: cfg.oauthRelayBaseUrl,
        publishableKey: cfg.publishableKey
      });
      state.ok = true;
      state.reason = "";
    } catch (e) {
      state.reason = "云端 SDK 初始化失败：" + (e && e.message ? e.message : "未知错误");
    }
  }

  var ready = (function () {
    if (hasSdk()) {
      init();
      return Promise.resolve(state);
    }
    return loadLocalSdk().then(function () {
      init();
      return state;
    });
  })();

  function errText(e) {
    if (!e) return "未知错误";
    if (typeof e === "string") return e;
    if (e.message) return String(e.message);
    if (e.error && e.error.message) return String(e.error.message);
    try { return JSON.stringify(e); } catch (_) { return String(e); }
  }

  window.ERCloud = {
    config: cfg,
    ready: ready,
    state: state,
    errText: errText,
    client: function () { return state.cloud; },
    // 统一身份门禁：用户级 Database / Storage 读写前必须调用
    requireSession: function () {
      if (!state.ok || !state.cloud) return Promise.resolve(null);
      return state.cloud.auth.getSession().then(function (r) {
        if (!r || r.error || !r.data) return null;
        return r.data;
      }).catch(function () { return null; });
    }
  };
})();
