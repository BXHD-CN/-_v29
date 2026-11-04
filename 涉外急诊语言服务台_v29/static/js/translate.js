/* ============================================================
   翻译页脚本（原生 JS，无第三方库）
   - 依赖 window.App（T2 提供：api / requireLogin / toast / escapeHtml / fmtTime），
     缺失时使用本文件内置的等价兜底，保证页面可独立运行。
   - 仅本页使用：tr- 前缀的 DOM id 与状态。
   ============================================================ */
(function () {
  "use strict";

  var MAX_LEN = 5000;
  var LS_DRAFT = "resqai_tr_draft_v2";
  var LS_BACKUP = "resqai_tr_draft_backup_v2";
  var FALLBACK_LANGS = [
    { code: "zh", name: "中文" }, { code: "en", name: "英语" },
    { code: "vi", name: "越南语" }, { code: "th", name: "泰语" },
    { code: "id", name: "印尼语" }, { code: "ms", name: "马来语" }
  ];
  var PROVIDER_LABEL = {
    mock: "演示模式（mock）", deepseek: "DeepSeek", generic: "自定义 MT",
    mymemory: "MyMemory", local: "本地检索", none: "未配置"
  };
  var PROVIDER_LABEL_EN = {
    mock: "Demo mode (mock)", deepseek: "DeepSeek", generic: "Custom MT",
    mymemory: "MyMemory", local: "Local retrieval", none: "Not configured"
  };
  /* 超长提示的来源标签：enforceLimit() 的中文实参在英文模式下换成成稿英文 */
  var SOURCE_LABEL_EN = {
    "输入": "Input", "粘贴的": "Pasted text", "草稿": "Draft text",
    "输入的": "Input text", "历史记录": "History text"
  };

  var state = {
    langs: FALLBACK_LANGS.slice(),
    providers: {},
    busy: false,
    segments: [],
    last: null,
    history: [],
    historyOpen: false,
    historyLoaded: false,
    backup: null,
    draftTimer: 0,
    popoverIdx: -1,
    // 译文自由编辑：editMode 表示对照视图已切成可编辑 textarea，
    // editedTranslation 保存用户改后的最新全文（null = 未改动，用服务端原文）。
    editMode: false,
    editedTranslation: null,
    user: null            // 当前登录用户；匿名 null，用于跳过个人数据请求
  };

  function byId(id) { return document.getElementById(id); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  /* v=26 英文优先：带全角标点的动态串用成稿英文，避免短语替换留下
     "MT：MyMemory" / "provider：xxx（降级）" 这类中英标点混排。 */
  function isEnMode() {
    return !!(window.I18N && typeof window.I18N.lang === "function" && window.I18N.lang() === "en");
  }
  function enText(zh, en) { return isEnMode() ? en : zh; }

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
    var stack = document.querySelector(".tr-toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "tr-toast-stack";
      stack.setAttribute("aria-live", "polite");
      stack.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;flex-direction:column;gap:8px";
      document.body.appendChild(stack);
    }
    var node = document.createElement("div");
    node.textContent = String(message || "");
    var warn = kind === "error";
    node.style.cssText = "max-width:320px;padding:10px 14px;border-radius:8px;font-size:13px;line-height:1.5;color:#fff;box-shadow:0 8px 24px rgba(15,23,42,.2);background:" + (warn ? "#DC2626" : "#0F172A");
    stack.appendChild(node);
    setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 3200);
  }

  function getCookie(name) {
    var list = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < list.length; i++) {
      var pair = list[i].split("=");
      if (decodeURIComponent(pair[0]) === name) return decodeURIComponent(pair.slice(1).join("="));
    }
    return "";
  }
  function currentPath() {
    var file = location.pathname.split("/").pop() || "translate.html";
    return file + location.search;
  }
  function redirectToLogin() {
    // 会话失效：回到登录入口重新认证（未注册访客由服务端门禁直接送注册页）。
    window.location.href = "login.html?next=" + encodeURIComponent(currentPath());
  }

  function ApiError(status, message) {
    this.status = status;
    this.message = message || enText("请求失败", "Request failed");
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
      else {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(opts.body);
      }
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
      response = await fetch(path, {
        method: method, headers: headers, body: body,
        credentials: "same-origin", cache: "no-store"
      });
    } catch (err) {
      throw new ApiError(0, enText("网络异常，请检查网络后重试", "Network error. Please check your connection and try again."));
    }
    var text = await response.text();
    var data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (parseErr) { data = text; }
    }
    if (!response.ok) {
      var detail = data && typeof data === "object" ? (data.detail || data.message || "") : "";
      if (typeof detail !== "string") detail = JSON.stringify(detail);
      if (response.status === 401 && !opts.authOptional) redirectToLogin();
      var fallback = isEnMode()
        ? "Request failed (" + response.status + ")"
        : "请求失败（" + response.status + "）";
      throw new ApiError(response.status, detail || fallback);
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

  function statusOf(err) {
    if (!err) return 0;
    return err.status || err.code || (err.response && err.response.status) || 0;
  }
  function messageOf(err) {
    if (!err) return enText("未知错误", "Unknown error");
    return err.message || (err.detail && String(err.detail)) || enText("请求失败", "Request failed");
  }

  async function requireAuth() {
    // 注册前置门禁由服务端 shield.py 保证；这里只读取登录态，
    // 用于判断是否该发起「翻译历史」这类个人数据请求。
    if (app && typeof app.requireLogin === "function") {
      try { state.user = await app.requireLogin(); } catch (err) { state.user = null; }
    }
    return state.user;
  }

  /* ---------------- 语言与 provider ---------------- */
  function normalizeLangs(list) {
    if (!Array.isArray(list)) return FALLBACK_LANGS.slice();
    var out = [];
    list.forEach(function (item) {
      if (item && item.code) out.push({ code: String(item.code), name: String(item.name || item.code) });
    });
    return out.length ? out : FALLBACK_LANGS.slice();
  }
  function providerLabel(name) {
    var table = isEnMode() ? PROVIDER_LABEL_EN : PROVIDER_LABEL;
    if (!name) return table.none;
    return table[name] || String(name);
  }
  function fillSelect(select, selected) {
    select.innerHTML = "";
    state.langs.forEach(function (lang) {
      var option = document.createElement("option");
      option.value = lang.code;
      var lname = (window.I18N && typeof window.I18N.t === "function")
        ? window.I18N.t(lang.name) : lang.name;
      option.textContent = (window.I18N && typeof window.I18N.t === "function")
        ? window.I18N.t("{name}（{code}）", { name: lname, code: lang.code })
        : (lang.name + "（" + lang.code + "）");
      if (lang.code === selected) option.selected = true;
      select.appendChild(option);
    });
    if (selected && state.langs.some(function (l) { return l.code === selected; })) select.value = selected;
  }

  async function loadLanguages() {
    var srcSel = byId("tr-src-lang");
    var tgtSel = byId("tr-tgt-lang");
    var src = srcSel.value || "zh";
    var tgt = tgtSel.value || "en";
    try {
      var data = await api("/api/translate/languages", { silent: true });
      if (data && data.languages) state.langs = normalizeLangs(data.languages);
      if (data && data.providers) state.providers = data.providers;
    } catch (err) {
      if (statusOf(err) === 401) { redirectToLogin(); return; }
    }
    fillSelect(srcSel, src);
    fillSelect(tgtSel, readDraft() && readDraft().tgt ? readDraft().tgt : tgt);
    var chip = byId("tr-provider-chip");
    var mt = state.providers && state.providers.mt;
    if (mt) {
      chip.hidden = false;
      chip.textContent = enText("MT：", "MT: ") + providerLabel(mt);
      chip.title = "embedding=" + (state.providers.embedding || "-") + " / llm=" + (state.providers.llm || "-");
    }
  }

  /* ---------------- 计数与草稿 ---------------- */
  function updateCount() {
    var ta = byId("tr-source");
    var len = ta.value.length;
    var counter = byId("tr-char-count");
    counter.textContent = len + " / " + MAX_LEN;
    counter.classList.toggle("is-warn", len >= MAX_LEN - 500 && len <= MAX_LEN);
    counter.classList.toggle("is-over", len > MAX_LEN);
    var submit = byId("tr-submit");
    submit.disabled = state.busy || len === 0 || len > MAX_LEN;
  }
  function setCharError(message) {
    byId("tr-char-error").textContent = message || "";
  }
  function enforceLimit(source) {
    var ta = byId("tr-source");
    if (ta.value.length <= MAX_LEN) { setCharError(""); updateCount(); return; }
    ta.value = ta.value.slice(0, MAX_LEN);
    setCharError(enText(
      "超出 " + MAX_LEN + " 字上限，已截断为 " + MAX_LEN + " 字",
      "Exceeded the " + MAX_LEN + "-character limit; trimmed to " + MAX_LEN + " characters."));
    updateCount();
    var sourceKey = source || "输入";
    var sourceLabel = isEnMode() ? (SOURCE_LABEL_EN[sourceKey] || "Input") : sourceKey;
    toast(enText(
      sourceLabel + "内容超过 " + MAX_LEN + " 字，已截断",
      sourceLabel + " exceeded " + MAX_LEN + " characters and was trimmed."));
  }

  function readDraft() {
    try { return JSON.parse(localStorage.getItem(LS_DRAFT) || "null"); } catch (err) { return null; }
  }
  function saveDraftNow() {
    var text = byId("tr-source").value;
    var payload = { text: text, src: byId("tr-src-lang").value, tgt: byId("tr-tgt-lang").value, ts: Date.now() };
    try {
      if (!text.trim()) localStorage.removeItem(LS_DRAFT);
      else localStorage.setItem(LS_DRAFT, JSON.stringify(payload));
    } catch (err) { /* 隐私模式忽略 */ }
  }
  function scheduleDraftSave() {
    window.clearTimeout(state.draftTimer);
    state.draftTimer = window.setTimeout(saveDraftNow, 500);
  }
  function readBackup() {
    try { return JSON.parse(localStorage.getItem(LS_BACKUP) || "null"); } catch (err) { return null; }
  }
  function writeBackup(payload) {
    try {
      if (payload) localStorage.setItem(LS_BACKUP, JSON.stringify(payload));
      else localStorage.removeItem(LS_BACKUP);
    } catch (err) { /* ignore */ }
  }
  function renderDraftUi() {
    var draftHint = byId("tr-draft-hint");
    var restored = state.restoredDraft;
    var backup = state.backup;
    if (restored && !backup) {
      draftHint.hidden = false;
      byId("tr-draft-time").textContent = fmtTime(restored.ts);
    } else {
      draftHint.hidden = true;
    }
    var restoreBtn = byId("tr-draft-restore");
    restoreBtn.hidden = !backup;
    if (backup) restoreBtn.textContent = isEnMode()
      ? "Restore draft (" + fmtTime(backup.ts) + ")"
      : "恢复草稿（" + fmtTime(backup.ts) + "）";
  }
  function restoreDraft() {
    var draft = readDraft();
    if (!draft || !draft.text) return;
    var ta = byId("tr-source");
    ta.value = draft.text;
    if (draft.src) fillSelect(byId("tr-src-lang"), draft.src);
    if (draft.tgt) fillSelect(byId("tr-tgt-lang"), draft.tgt);
    state.restoredDraft = draft;
    enforceLimit("草稿");
    renderDraftUi();
  }

  /* ---------------- 句子切分与对齐 ---------------- */
  var SENT_RE = /[^。！？!?；;\n]+[。！？!?；;]?/g;
  function splitSentences(text) {
    var out = [];
    var rest = String(text || "");
    var match;
    SENT_RE.lastIndex = 0;
    while ((match = SENT_RE.exec(rest)) !== null) {
      var piece = match[0];
      if (!piece || !piece.trim()) continue;
      var start = match.index;
      out.push({ text: piece, start: start, end: start + piece.length });
    }
    if (!out.length && String(text || "").trim()) out.push({ text: String(text), start: 0, end: String(text).length });
    return out;
  }

  function normalizeSegments(data, sourceText) {
    var segments = [];
    if (data && Array.isArray(data.segments) && data.segments.length) {
      data.segments.forEach(function (seg) {
        if (!seg) return;
        segments.push({
          src: String(seg.src || seg.source || ""),
          tgt: String(seg.tgt || seg.target || seg.translation || ""),
          terms: Array.isArray(seg.terms) ? seg.terms : [],
          pairs: Array.isArray(seg.pairs) ? seg.pairs : [],
          auto: false
        });
      });
      if (segments.length) return segments;
    }
    var translation = String((data && (data.translation || data.target_text)) || "");
    var srcSent = splitSentences(sourceText);
    var tgtSent = splitSentences(translation);
    if (!srcSent.length) srcSent = [{ text: sourceText, start: 0, end: String(sourceText).length }];
    if (!tgtSent.length) tgtSent = [{ text: translation, start: 0, end: translation.length }];
    if (tgtSent.length === 1 && srcSent.length > 1) {
      var wholeTgt = translation;
      srcSent.forEach(function (sent, index) {
        segments.push({
          src: sent.text, tgt: index === 0 ? wholeTgt : "", terms: [], pairs: [], auto: true,
          srcStart: sent.start, srcEnd: sent.end
        });
      });
      return segments;
    }
    var count = Math.max(srcSent.length, tgtSent.length);
    for (var i = 0; i < count; i += 1) {
      var srcPart = srcSent[i] || null;
      var tgtPart = tgtSent[i] || null;
      segments.push({
        src: srcPart ? srcPart.text : "",
        tgt: tgtPart ? tgtPart.text : "",
        terms: [], pairs: [], auto: true,
        srcStart: srcPart ? srcPart.start : -1,
        srcEnd: srcPart ? srcPart.end : -1
      });
    }
    return segments;
  }

  function attachTerms(segments, data, sourceText) {
    var locked = (data && Array.isArray(data.locked_terms)) ? data.locked_terms : [];
    var pairs = (data && Array.isArray(data.context_pairs)) ? data.context_pairs : [];
    segments.forEach(function (seg) { if (!seg) return; if (!seg.pairs || !seg.pairs.length) seg.pairs = pairs.slice(0, 3); });
    locked.forEach(function (term) {
      if (!term) return;
      var start = typeof term.start === "number" ? term.start : -1;
      if (start < 0 && term.matched) start = String(sourceText).indexOf(term.matched);
      var target = null;
      if (start >= 0) {
        for (var i = 0; i < segments.length; i += 1) {
          var seg = segments[i];
          if (typeof seg.srcStart === "number" && seg.srcStart >= 0) {
            if (start >= seg.srcStart && start < seg.srcEnd) { target = seg; break; }
          } else if (seg.src && term.matched && seg.src.indexOf(term.matched) !== -1) {
            target = seg;
          }
        }
      }
      if (!target) target = segments[0];
      if (!target) return;
      var duplicated = target.terms.some(function (existing) {
        return existing && existing.term_id === term.term_id && (existing.must_use || existing.en) === (term.must_use || term.en);
      });
      if (!duplicated) target.terms.push(term);
    });
  }

  /* ---------------- 译文自由编辑 ---------------- */
  // 译文不再是固定的分句 span：随时可切成 textarea 自由改，改动即时写回，
  // 复制 / 重译 / 交换语言都读取这里的最新全文。
  function currentTranslation() {
    if (state.editedTranslation !== null) return state.editedTranslation;
    if (state.last && state.last.data) {
      return String(state.last.data.translation || state.last.data.target_text || "");
    }
    return "";
  }
  function setEditedTranslation(text) {
    state.editedTranslation = text;
    if (state.last && state.last.data) state.last.data.translation = text;
  }
  function resetEditUi() {
    var editor = byId("tr-target-edit");
    if (editor) { editor.hidden = true; editor.value = ""; }
    var output = byId("tr-output");
    if (output) output.classList.remove("is-editing");
    var btn = byId("tr-edit-tgt");
    if (btn) {
      btn.disabled = true;
      btn.textContent = enText("编辑译文", "Edit translation");
      btn.classList.remove("is-active");
    }
    state.editMode = false;
    state.editedTranslation = null;
  }
  function applyEditedSegments() {
    // 用编辑后的全文重新按句对齐，并尽量保留已附着的术语与参考语料
    var srcText = (state.last && state.last.text) || byId("tr-source").value || "";
    var old = state.segments;
    var rebuilt = normalizeSegments({ translation: currentTranslation() }, srcText);
    rebuilt.forEach(function (seg, i) {
      if (old[i]) { seg.terms = old[i].terms || []; seg.pairs = old[i].pairs || []; }
    });
    state.segments = rebuilt;
  }
  function enterEditMode() {
    var text = currentTranslation();
    if (!text) { toast(enText("暂无可编辑的译文", "No translation available to edit"), "error"); return; }
    var editor = byId("tr-target-edit");
    editor.value = text;
    editor.hidden = false;
    byId("tr-tgt-segs").hidden = true;
    byId("tr-out-empty").hidden = true;
    byId("tr-terms").hidden = true;
    byId("tr-notes").hidden = true;
    byId("tr-output").classList.add("is-editing");
    state.editMode = true;
    var btn = byId("tr-edit-tgt");
    btn.textContent = enText("完成编辑", "Done editing");
    btn.classList.add("is-active");
    closePopover();
    editor.focus();
  }
  function exitEditMode(announce) {
    if (!state.editMode) return;
    var editor = byId("tr-target-edit");
    setEditedTranslation(editor.value);
    applyEditedSegments();
    editor.hidden = true;
    byId("tr-output").classList.remove("is-editing");
    state.editMode = false;
    var btn = byId("tr-edit-tgt");
    btn.textContent = enText("编辑译文", "Edit translation");
    btn.classList.remove("is-active");
    // 只重渲染译文侧，不改动原文侧的编辑/对照状态
    var tgtBox = byId("tr-tgt-segs");
    tgtBox.innerHTML = state.segments.map(function (seg, index) {
      return segHtml(seg.tgt, index, "tgt") + " ";
    }).join("");
    tgtBox.hidden = false;
    byId("tr-out-empty").hidden = true;
    if (state.last && state.last.data) {
      renderTermsSummary(state.last.data);
      renderNotes(state.last.data);
    }
    byId("tr-copy").disabled = !currentTranslation();
    if (announce !== false) toast(enText("译文已更新，可继续编辑或复制", "Translation updated. Keep editing or copy it."), "success");
  }

  /* ---------------- 渲染 ---------------- */
  function setBusy(busy) {
    state.busy = busy;
    var submit = byId("tr-submit");
    submit.classList.toggle("is-busy", busy);
    submit.textContent = busy ? enText("翻译中…", "Translating…") : enText("翻译", "Translate");
    submit.setAttribute("aria-busy", busy ? "true" : "false");
    updateCount();
  }

  function resetResult() {
    state.segments = [];
    state.popoverIdx = -1;
    byId("tr-src-segs").hidden = true;
    byId("tr-src-segs").innerHTML = "";
    byId("tr-tgt-segs").hidden = true;
    byId("tr-tgt-segs").innerHTML = "";
    byId("tr-out-empty").hidden = false;
    byId("tr-src-empty").hidden = true;
    byId("tr-source").hidden = false;
    byId("tr-edit-src").hidden = true;
    byId("tr-terms").hidden = true;
    byId("tr-terms-list").innerHTML = "";
    byId("tr-degraded").hidden = true;
    byId("tr-notes").hidden = true;
    byId("tr-result-provider").textContent = "";
    byId("tr-copy").disabled = true;
    byId("tr-retranslate").disabled = true;
    resetEditUi();
    closePopover();
  }

  function segHtml(text, index, side) {
    var emptyText = enText("（该句无对应文本）", "(No corresponding text for this sentence)");
    var content = text && text.trim() ? esc(text) : '<span class="tr-seg--empty">' + emptyText + "</span>";
    return '<span class="tr-seg" role="listitem" tabindex="0" data-idx="' + index + '" data-side="' + side + '">' + content + "</span>";
  }

  function renderSegments() {
    var srcBox = byId("tr-src-segs");
    var tgtBox = byId("tr-tgt-segs");
    var srcHtml = state.segments.map(function (seg, index) { return segHtml(seg.src, index, "src") + " "; }).join("");
    var tgtHtml = state.segments.map(function (seg, index) { return segHtml(seg.tgt, index, "tgt") + " "; }).join("");
    srcBox.innerHTML = srcHtml;
    tgtBox.innerHTML = tgtHtml;
    srcBox.hidden = false;
    tgtBox.hidden = false;
    byId("tr-out-empty").hidden = true;
    byId("tr-src-empty").hidden = true;
    byId("tr-source").hidden = true;
    byId("tr-edit-src").hidden = false;
  }

  function renderTermsSummary(data) {
    var locked = (data && Array.isArray(data.locked_terms)) ? data.locked_terms : [];
    var box = byId("tr-terms");
    var list = byId("tr-terms-list");
    if (!locked.length) { box.hidden = true; list.innerHTML = ""; return; }
    byId("tr-terms-count").textContent = String(locked.length);
    var seen = {};
    var items = [];
    locked.forEach(function (term) {
      var key = (term.term_id || term.zh || "") + "::" + (term.must_use || term.en || "");
      if (seen[key]) return;
      seen[key] = true;
      items.push(term);
    });
    list.innerHTML = items.map(function (term) {
      var srcWord = term.matched || term.zh || "";
      var tgtWord = term.must_use || term.en || "";
      return "<li>" + esc(srcWord) + " → " + esc(tgtWord) + "</li>";
    }).join("");
    box.hidden = false;
  }

  function renderNotes(data) {
    var notes = (data && Array.isArray(data.notes)) ? data.notes : [];
    var box = byId("tr-notes");
    if (!notes.length) { box.hidden = true; return; }
    byId("tr-notes-list").innerHTML = notes.map(function (note) { return "<li>" + esc(note) + "</li>"; }).join("");
    box.hidden = false;
  }

  function renderResult(data, sourceText) {
    var translation = String((data && (data.translation || data.target_text)) || "");
    var provider = (data && (data.provider || data.engine)) || "";
    var degraded = !!(data && data.degraded);
    var fallbackTag = degraded ? enText("（降级）", " (fallback)") : "";
    byId("tr-result-provider").textContent = provider
      ? enText("provider：", "Provider: ") + providerLabel(provider) + fallbackTag : "";
    var degradedBox = byId("tr-degraded");
    if (degraded) {
      degradedBox.hidden = false;
      degradedBox.textContent = enText(
        "当前为降级结果：上游模型或机器翻译额度不可用，已使用本地演示兜底。译文仅供沟通参考，重要内容请人工核对。",
        "Fallback result: the upstream model or machine-translation quota was unavailable, so a local demo fallback was used. For communication reference only; have critical content reviewed by a human.");
    } else {
      degradedBox.hidden = true;
      degradedBox.textContent = "";
    }
    // 新译文到达：清除上一次的人工修改，回到干净的对照视图
    resetEditUi();
    state.segments = normalizeSegments(data, sourceText);
    attachTerms(state.segments, data, sourceText);
    renderSegments();
    renderTermsSummary(data);
    renderNotes(data);
    byId("tr-copy").disabled = !translation;
    byId("tr-retranslate").disabled = false;
    state.last = { text: sourceText, src: byId("tr-src-lang").value, tgt: byId("tr-tgt-lang").value, data: data };
    var editBtn = byId("tr-edit-tgt");
    if (editBtn) editBtn.disabled = !translation;
  }

  /* ---------------- 双向高亮与浮层 ---------------- */
  function setHot(index, on) {
    ["tr-src-segs", "tr-tgt-segs"].forEach(function (id) {
      qsa('.tr-seg[data-idx="' + index + '"]', byId(id)).forEach(function (node) {
        node.classList.toggle("is-hot", on);
      });
    });
  }
  function segFromEvent(event) {
    var node = event.target;
    while (node && node !== document && !(node.classList && node.classList.contains("tr-seg"))) node = node.parentNode;
    if (!node || node === document) return null;
    return node;
  }

  function termLine(term) {
    var zh = term.zh || term.matched || "";
    var en = term.must_use || term.en || "";
    var domainValue = (window.I18N && typeof window.I18N.label === "function")
      ? window.I18N.label(term.domain) : term.domain;
    var domain = term.domain ? enText("（", "(") + domainValue + enText("）", ")") : "";
    return "<li><span class=\"tr-term-zh\">" + esc(zh) + "</span> → <span class=\"tr-term-en\">" + esc(en) + "</span><span class=\"tr-popover__empty\"> " + esc(domain) + "</span></li>";
  }

  function openPopover(index, x, y) {
    var seg = state.segments[index];
    if (!seg) return;
    state.popoverIdx = index;
    var pop = byId("tr-popover");
    byId("tr-popover-title").textContent = isEnMode()
      ? "Sentence " + (index + 1) : "第 " + (index + 1) + " 句";
    byId("tr-popover-src").textContent = seg.src || enText("（无原文）", "(No source text)");
    byId("tr-popover-tgt").textContent = seg.tgt || enText("（无译文）", "(No translation)");
    var terms = seg.terms || [];
    byId("tr-popover-terms").innerHTML = terms.length
      ? terms.map(termLine).join("")
      : '<li class="tr-popover__empty">本句未命中锁定术语</li>';
    var pairs = (seg.pairs || []).filter(function (pair) { return pair && (pair.zh || pair.en); });
    byId("tr-popover-pairs").innerHTML = pairs.length
      ? pairs.slice(0, 3).map(function (pair) {
          return "<li><div>" + esc(pair.zh || "") + "</div><div class=\"tr-popover__empty\">" + esc(pair.en || "") + "</div></li>";
        }).join("")
      : '<li class="tr-popover__empty">暂无参考语料</li>';
    pop.hidden = false;
    var width = pop.offsetWidth;
    var height = pop.offsetHeight;
    var left = Math.min(x + 12, window.innerWidth - width - 12);
    if (left < 12) left = 12;
    var top = y + 14;
    if (top + height > window.innerHeight - 12) {
      top = y - height - 14;
      if (top < 12) top = 12;
    }
    pop.style.left = left + "px";
    pop.style.top = top + "px";
    byId("tr-popover-close").focus();
  }
  function closePopover() {
    var pop = byId("tr-popover");
    if (!pop) return;
    pop.hidden = true;
    state.popoverIdx = -1;
  }
  // 滚动/缩放时先查内存状态，避免每次滚动都做一次 DOM 查询与属性读取
  function closePopoverIfOpen() {
    if (state.popoverIdx >= 0) closePopover();
  }

  /* ---------------- 翻译提交 ---------------- */
  async function submit() {
    if (state.busy) return;
    var ta = byId("tr-source");
    var text = ta.value;
    if (!text.trim()) {
      setCharError(enText("请输入或粘贴原文", "Enter or paste source text"));
      ta.focus();
      return;
    }
    if (text.length > MAX_LEN) { enforceLimit("输入的"); return; }
    setCharError("");
    setBusy(true);
    try {
      var data = await api("/api/translate", {
        method: "POST",
        body: { text: text, src: byId("tr-src-lang").value, tgt: byId("tr-tgt-lang").value },
        silent: true
      });
      if (!data || (!data.translation && !data.segments)) throw new ApiError(0, "服务端未返回译文");
      renderResult(data, text);
      saveDraftNow();
      if (state.historyOpen) loadHistory(true);
      toast(enText("翻译完成", "Translation complete"), "success");
    } catch (err) {
      if (window.console && window.console.error) window.console.error("[translate]", (err && err.stack) || err);
      var status = statusOf(err);
      if (status === 401) { redirectToLogin(); return; }
      var failPrefix = enText("翻译失败：", "Translation failed: ");
      if (status === 429) setCharError(enText(
        "请求过于频繁：每分钟最多 10 次，请稍后再试",
        "Rate limit reached: at most 10 requests per minute. Please try again shortly."));
      else if (status === 403) setCharError(enText(
        "CSRF 校验失败，请刷新页面后重试",
        "CSRF check failed. Please refresh the page and try again."));
      else setCharError(failPrefix + messageOf(err));
      toast(failPrefix + messageOf(err), "error");
    } finally {
      setBusy(false);
    }
  }

  /* ---------------- 历史 ---------------- */
  function historyItemText(item) {
    return item.source_text || item.text || item.source || item.query || "";
  }
  function historyItemTgt(item) {
    return item.translation || item.target_text || item.target || "";
  }
  function historyItemLangs(item) {
    var src = item.src || item.source_lang || "zh";
    var tgt = item.tgt || item.target_lang || "en";
    return { src: src, tgt: tgt };
  }
  function renderHistoryGap() {
    byId("tr-history-loading").hidden = true;
    byId("tr-history-list").hidden = true;
    var empty = byId("tr-history-empty");
    empty.hidden = false;
    empty.textContent = enText(
      "后端历史接口（/api/me/translations）暂未启用，历史列表不可用；当前输入仍保存在本机草稿。",
      "The history endpoint (/api/me/translations) is not enabled, so the list is unavailable. Your current input is still saved as a local draft.");
  }
  function renderHistory() {
    var list = byId("tr-history-list");
    byId("tr-history-loading").hidden = true;
    if (!state.history.length) {
      list.hidden = true;
      var empty = byId("tr-history-empty");
      empty.hidden = false;
      empty.textContent = enText(
        "暂无历史记录。登录后每次翻译会保存在你的账户下。",
        "No history yet. Once signed in, every translation is saved to your account.");
      updateHistoryCount(0);
      return;
    }
    byId("tr-history-empty").hidden = true;
    list.hidden = false;
    list.innerHTML = state.history.map(function (item, index) {
      var langs = historyItemLangs(item);
      var text = historyItemText(item) || enText("（无原文）", "(No source text)");
      var tgtText = historyItemTgt(item);
      return '<li><button class="tr-history__item" type="button" data-index="' + index + '">' +
        '<span class="tr-history__item-text">' + esc(text.slice(0, 120)) + "</span>" +
        '<span class="tr-history__item-meta"><span>' + esc(langs.src.toUpperCase() + " → " + langs.tgt.toUpperCase()) + "</span>" +
        "<span>" + esc(fmtTime(item.created_at || item.at || item.ts)) + "</span>" +
        (tgtText ? "<span>" + esc(tgtText.slice(0, 24)) + "…</span>" : "") + "</span></button>" +
        '<button class="tr-history__del" type="button" data-del="' + index + '" aria-label="' +
          enText("删除这条历史", "Delete this history item") + '">✕</button></li>';
    }).join("");
    updateHistoryCount(state.history.length);
  }
  function updateHistoryCount(count) {
    var badge = byId("tr-history-count");
    badge.hidden = !count;
    badge.textContent = String(count);
  }
  async function loadHistory(force) {
    if (state.historyLoaded && !force) return;
    state.historyLoaded = true;
    // 会话未建立时不请求个人历史：避免 401 控制台报错，也不影响翻译本身。
    if (!state.user) {
      state.history = [];
      byId("tr-history-loading").hidden = true;
      byId("tr-history-empty").hidden = false;
      byId("tr-history-empty").textContent = enText(
        "翻译历史仅对已登录用户保存；可在「我的资产」查看。",
        "Translation history is saved only for signed-in users; view it in My Assets.");
      return;
    }
    try {
      var data = await api("/api/me/translations?limit=20", { silent: true });
      state.history = Array.isArray(data) ? data : ((data && (data.items || data.translations)) || []);
      renderHistory();
    } catch (err) {
      var status = statusOf(err);
      if (status === 401) {
        // 会话失效时没有个人翻译历史：不跳页，明确说明后可继续翻译。
        byId("tr-history-loading").hidden = true;
        byId("tr-history-empty").hidden = false;
        byId("tr-history-empty").textContent = enText(
          "翻译历史仅对已登录用户保存；可在「我的资产」查看。",
          "Translation history is saved only for signed-in users; view it in My Assets.");
        return;
      }
      if (status === 404 || status === 405 || status === 501) { renderHistoryGap(); return; }
      byId("tr-history-loading").hidden = true;
      byId("tr-history-empty").hidden = false;
      byId("tr-history-empty").textContent = enText("历史加载失败：", "Could not load history: ") + messageOf(err);
    }
  }
  function backupCurrentDraft() {
    var text = byId("tr-source").value;
    if (!text.trim()) return;
    if (state.backup && state.backup.text === text) return;
    state.backup = { text: text, ts: Date.now(), src: byId("tr-src-lang").value, tgt: byId("tr-tgt-lang").value };
    writeBackup(state.backup);
    renderDraftUi();
  }
  function applyHistoryItem(item) {
    backupCurrentDraft();
    var ta = byId("tr-source");
    ta.value = historyItemText(item);
    var langs = historyItemLangs(item);
    fillSelect(byId("tr-src-lang"), langs.src);
    fillSelect(byId("tr-tgt-lang"), langs.tgt);
    resetResult();
    enforceLimit("历史记录");
    setCharError("");
    var tgtText = historyItemTgt(item);
    if (tgtText) {
      renderResult({
        translation: tgtText, provider: item.provider || "", degraded: false,
        locked_terms: item.locked_terms || [], context_pairs: item.context_pairs || [], notes: []
      }, ta.value);
    }
    byId("tr-draft-hint").hidden = true;
    toast(enText("已载入历史记录", "History item loaded"));
  }
  async function deleteHistoryItem(index) {
    var item = state.history[index];
    if (!item) return;
    var id = item.id || item.translation_id || item.pk;
    if (id === undefined || id === null) { toast(enText("该历史记录缺少编号，无法删除", "This history item has no ID and cannot be deleted"), "error"); return; }
    try {
      await api("/api/me/translations/" + encodeURIComponent(id), { method: "DELETE", silent: true });
      state.history.splice(index, 1);
      renderHistory();
      toast(enText("已删除", "Deleted"), "success");
    } catch (err) {
      var status = statusOf(err);
      if (status === 401) { redirectToLogin(); return; }
      toast(enText("删除失败：", "Could not delete: ") + messageOf(err), "error");
    }
  }

  /* ---------------- 抽屉与交互绑定 ---------------- */
  function setHistoryOpen(open) {
    state.historyOpen = open;
    var drawer = byId("tr-history");
    var backdrop = byId("tr-backdrop");
    drawer.classList.toggle("is-open", open);
    drawer.setAttribute("aria-hidden", open ? "false" : "true");
    backdrop.hidden = !open;
    byId("tr-history-toggle").setAttribute("aria-expanded", open ? "true" : "false");
    if (open) loadHistory(false);
  }

  function bindEvents() {
    var ta = byId("tr-source");
    var editor = byId("tr-editor");
    ta.addEventListener("input", function () {
      state.restoredDraft = null;
      byId("tr-draft-hint").hidden = true;
      enforceLimit();
      scheduleDraftSave();
    });
    ta.addEventListener("paste", function () { window.setTimeout(function () { enforceLimit("粘贴的"); scheduleDraftSave(); }, 0); });
    ta.addEventListener("keydown", function (event) {
      // 中文输入法选字期间的 Enter 绝不能触发翻译（isComposing / keyCode 229）
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key !== "Enter") return;
      if (event.shiftKey || event.altKey) return; // Shift+Enter 保留换行
      event.preventDefault();
      submit(); // 纯 Enter 与 Ctrl / ⌘ + Enter 都直接出译文，无需动鼠标
    });
    byId("tr-submit").addEventListener("click", submit);
    byId("tr-edit-tgt").addEventListener("click", function () {
      if (state.editMode) exitEditMode(); else enterEditMode();
    });
    byId("tr-target-edit").addEventListener("input", function () {
      // 改动即时写回：复制 / 重译 / 交换语言立刻拿到最新全文
      setEditedTranslation(this.value);
      byId("tr-copy").disabled = !this.value.trim();
    });
    byId("tr-target-edit").addEventListener("keydown", function (event) {
      if (event.key === "Escape") { event.preventDefault(); exitEditMode(); }
    });
    byId("tr-clear").addEventListener("click", function () {
      ta.value = "";
      try { localStorage.removeItem(LS_DRAFT); localStorage.removeItem(LS_BACKUP); } catch (err) { /* ignore */ }
      state.backup = null;
      state.restoredDraft = null;
      resetResult();
      enforceLimit();
      renderDraftUi();
      ta.focus();
      toast(enText("已清空", "Cleared"));
    });
    byId("tr-edit-src").addEventListener("click", function () {
      byId("tr-src-segs").hidden = true;
      byId("tr-source").hidden = false;
      byId("tr-edit-src").hidden = true;
      ta.focus();
    });
    byId("tr-swap").addEventListener("click", function () {
      var srcSel = byId("tr-src-lang");
      var tgtSel = byId("tr-tgt-lang");
      var src = srcSel.value;
      srcSel.value = tgtSel.value;
      tgtSel.value = src;
      var swapped = currentTranslation();
      if (swapped) {
        ta.value = swapped;
        resetResult();
        enforceLimit();
        toast(enText("已交换语言，并把译文放入原文框", "Languages swapped; the translation is now the source text."));
      } else {
        toast(enText("已交换语言", "Languages swapped"));
      }
      scheduleDraftSave();
    });
    byId("tr-copy").addEventListener("click", async function () {
      var text = currentTranslation();
      if (!text) { toast(enText("暂无可复制的译文", "No translation to copy"), "error"); return; }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) await navigator.clipboard.writeText(text);
        else throw new Error("no clipboard");
        toast(enText("已复制译文", "Translation copied"), "success");
      } catch (err) {
        var helper = document.createElement("textarea");
        helper.value = text;
        helper.setAttribute("readonly", "readonly");
        helper.style.cssText = "position:fixed;left:-9999px;top:0";
        document.body.appendChild(helper);
        helper.select();
        try { document.execCommand("copy"); toast(enText("已复制译文", "Translation copied"), "success"); }
        catch (copyErr) { toast(enText("复制失败，请手动选择文本", "Copy failed; please select the text manually"), "error"); }
        document.body.removeChild(helper);
      }
    });
    byId("tr-retranslate").addEventListener("click", function () {
      if (!state.last) { toast(enText("暂无可重译的内容", "Nothing to retranslate"), "error"); return; }
      submit();
    });
    byId("tr-history-toggle").addEventListener("click", function () { setHistoryOpen(!state.historyOpen); });
    byId("tr-history-close").addEventListener("click", function () { setHistoryOpen(false); });
    byId("tr-backdrop").addEventListener("click", function () { setHistoryOpen(false); });
    byId("tr-draft-clear").addEventListener("click", function () {
      try { localStorage.removeItem(LS_DRAFT); localStorage.removeItem(LS_BACKUP); } catch (err) { /* ignore */ }
      state.backup = null;
      state.restoredDraft = null;
      renderDraftUi();
      toast(enText("草稿已清除", "Draft cleared"));
    });
    byId("tr-draft-restore").addEventListener("click", function () {
      var backup = state.backup || readBackup();
      if (!backup || !backup.text) { toast(enText("没有可恢复的草稿", "No draft to restore"), "error"); return; }
      ta.value = backup.text;
      if (backup.src) fillSelect(byId("tr-src-lang"), backup.src);
      if (backup.tgt) fillSelect(byId("tr-tgt-lang"), backup.tgt);
      resetResult();
      enforceLimit("草稿");
      state.backup = null;
      writeBackup(null);
      state.restoredDraft = { text: backup.text, ts: backup.ts };
      saveDraftNow();
      renderDraftUi();
      toast(enText("已恢复草稿", "Draft restored"));
    });

    [byId("tr-src-segs"), byId("tr-tgt-segs")].forEach(function (container) {
      container.addEventListener("mouseover", function (event) {
        var seg = segFromEvent(event);
        if (seg) setHot(seg.getAttribute("data-idx"), true);
      });
      container.addEventListener("mouseout", function (event) {
        var seg = segFromEvent(event);
        if (seg) setHot(seg.getAttribute("data-idx"), false);
      });
      container.addEventListener("focusin", function (event) {
        var seg = segFromEvent(event);
        if (seg) setHot(seg.getAttribute("data-idx"), true);
      });
      container.addEventListener("focusout", function (event) {
        var seg = segFromEvent(event);
        if (seg) setHot(seg.getAttribute("data-idx"), false);
      });
      container.addEventListener("click", function (event) {
        var seg = segFromEvent(event);
        if (!seg) return;
        event.preventDefault();
        openPopover(parseInt(seg.getAttribute("data-idx"), 10), event.clientX, event.clientY);
      });
      container.addEventListener("keydown", function (event) {
        var seg = segFromEvent(event);
        if (!seg) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          var rect = seg.getBoundingClientRect();
          openPopover(parseInt(seg.getAttribute("data-idx"), 10), rect.left, rect.bottom);
        }
      });
    });

    byId("tr-history-list").addEventListener("click", function (event) {
      var delBtn = event.target.closest ? event.target.closest("[data-del]") : null;
      if (delBtn) { event.stopPropagation(); deleteHistoryItem(parseInt(delBtn.getAttribute("data-del"), 10)); return; }
      var itemBtn = event.target.closest ? event.target.closest("[data-index]") : null;
      if (itemBtn) applyHistoryItem(state.history[parseInt(itemBtn.getAttribute("data-index"), 10)]);
    });

    byId("tr-popover-close").addEventListener("click", closePopover);
    document.addEventListener("click", function (event) {
      if (byId("tr-popover").hidden) return;
      if (event.target.closest && event.target.closest("#tr-popover")) return;
      if (event.target.closest && event.target.closest(".tr-seg")) return;
      closePopover();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        if (!byId("tr-popover").hidden) { closePopover(); return; }
        if (state.historyOpen) setHistoryOpen(false);
      }
    });
    window.addEventListener("resize", closePopoverIfOpen);
    window.addEventListener("scroll", closePopoverIfOpen, true);
  }

  /* ---------------- 启动 ---------------- */
  function boot() {
    bindEvents();
    state.backup = readBackup();
    restoreDraft();
    updateCount();
    renderDraftUi();
    requireAuth().then(function () {
      // 语言列表是公共数据，始终加载；历史仅在已登录时请求（匿名由 loadHistory 直接给出提示）。
      // 两者互不依赖，并行加载，缩短首屏可交互等待。
      return Promise.all([loadLanguages(), loadHistory(false)]);
    }).catch(function (err) {
      if (statusOf(err) !== 401) toast(enText("初始化失败：", "Initialization failed: ") + messageOf(err), "error");
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
