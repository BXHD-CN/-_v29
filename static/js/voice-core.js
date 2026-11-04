/* ============================================================
   共用语音内核（v=28）· window.VoiceCore
   ------------------------------------------------------------
   定位：语音是「输入旁路适配层」，不是新的翻译器 / 新的告知单引擎。
   - 只负责：能力探测 → 麦克风语音 → 一段「可编辑文本」→ 交给页面适配器；
   - 不知道 /api/translate 与 /api/patient-check 的存在；
   - 默认绝不自动提交、自动翻译、自动留档：必须由用户点确认按钮；
   - 音频只在内存中，服务端不落盘、不写库；回听用 blob: URL，
     丢弃 / 撤销时立即 revokeObjectURL。

   ★ v=28 核心修正：识别文本必须真正来自「用户说的话」。
     默认 = 真实识别（live），两条真实通道按可用性自动选择：
       1) browser：浏览器原生 Web Speech API（Chrome / Edge），零密钥、
          识别结果直接来自麦克风，不经过后端；
       2) server ：录音上传 /api/speech/recognize，服务端 ASR_PROVIDER=http
          中转真实 ASR。
     「演示模拟」（demo）必须用户手动切换，且明确标注「不解析麦克风声音」，
     识别文本 = 用户自己填写的模拟口述内容，绝不冒充真实识别结果。
     两条真实通道都不可用时，明确报错并引导切换，不再静默返回示例句。

   页面适配器：voice-translate.js / voice-check.js，通过 VoiceCore.mount()
   注入标签、示例文本与 onApply / onApplyOnly / onUndo / onTextChange 回调。
   既有 translate.js / patient-check.js 的 submit() / render() 零改动。
   ============================================================ */
(function () {
  "use strict";

  var S = {
    opts: {}, status: null, busy: false, phase: "idle",
    mode: "live", liveKind: "", demo: false,
    recorder: null, stream: null, chunks: [], mime: "", simulated: false,
    startedAt: 0, durationMs: 0, timerId: 0, audioUrl: "",
    lastResult: null, changeTimer: 0,
    // 浏览器原生识别
    recognition: null, finalText: "", interimText: "", recError: "",
    stopping: false, endGuard: 0
  };

  function byId(id) { return document.getElementById(id); }
  function isEn() {
    return !!(window.I18N && typeof window.I18N.isEn === "function" && window.I18N.isEn());
  }
  /**
   * 双语文案：适配器给了成稿英文时优先用成稿英文，避免字典的「短语子串替换」
   * 把一句中文翻成中英混排的半截文案。没给兜底英文时才走全站字典。
   */
  function t(zh, en) {
    if (!isEn()) return zh;
    var mapped = "";
    if (window.I18N && typeof window.I18N.t === "function") {
      mapped = window.I18N.t(zh);
    }
    if (en && (!mapped || mapped === zh || /[\u4e00-\u9fff]/.test(mapped))) return en;
    return mapped || zh;
  }
  function esc(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function getCookie(name) {
    var list = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < list.length; i += 1) {
      var pair = list[i].split("=");
      if (decodeURIComponent(pair[0]) === name) return decodeURIComponent(pair.slice(1).join("="));
    }
    return "";
  }
  function toast(message, kind) {
    if (window.App && typeof window.App.toast === "function") window.App.toast(message, kind);
  }
  function setStatus(message, kind) {
    var node = byId("voice-status");
    if (!node) return;
    node.textContent = message || "";
    node.className = "voice-box__status" + (kind ? " is-" + kind : "");
    node.hidden = !message;
  }
  function fmt(ms) {
    var total = Math.max(0, Math.floor(ms / 1000));
    var m = Math.floor(total / 60), s = total % 60;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }
  function currentLang() {
    var node = document.querySelector('input[name="voice-lang"]:checked');
    return node ? node.value : (isEn() ? "en" : "zh");
  }
  function currentMode() {
    var node = document.querySelector('input[name="voice-mode"]:checked');
    return node ? node.value : "live";
  }
  function micSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }
  function SpeechCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }
  function serverLive() {
    return !!(S.status && S.status.provider === "http");
  }

  /** getUserMedia 超时保护：无头浏览器 / 被静默搁置的权限请求会永远 pending。 */
  function getMicWithTimeout(ms) {
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = window.setTimeout(function () {
        settled = true;
        reject(new Error("microphone_timeout"));
      }, ms);
      var pending;
      try { pending = navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (err) { window.clearTimeout(timer); settled = true; reject(err); return; }
      pending.then(function (stream) {
        window.clearTimeout(timer);
        if (settled) {
          try { stream.getTracks().forEach(function (track) { track.stop(); }); } catch (e) { /* ignore */ }
          return;
        }
        settled = true;
        resolve(stream);
      }, function (err) {
        window.clearTimeout(timer);
        if (settled) return;
        settled = true;
        reject(err);
      });
    });
  }

  function pickMime() {
    var candidates = [
      "audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus",
      "audio/mp4", "audio/mpeg"
    ];
    if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== "function") return "";
    for (var i = 0; i < candidates.length; i += 1) {
      if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
    }
    return "";
  }
  function extFor(mime) {
    if (/ogg/.test(mime)) return "ogg";
    if (/mp4|mpeg|aac/.test(mime)) return "m4a";
    return "webm";
  }
  function releaseStream() {
    if (S.stream) {
      try { S.stream.getTracks().forEach(function (track) { track.stop(); }); } catch (e) { /* ignore */ }
    }
    S.stream = null;
  }
  function releaseUrl() {
    if (S.audioUrl) {
      try { URL.revokeObjectURL(S.audioUrl); } catch (e) { /* ignore */ }
    }
    S.audioUrl = "";
  }
  function releaseRecognition() {
    if (S.recognition) {
      try { S.recognition.onresult = S.recognition.onerror = S.recognition.onend = null; } catch (e) { /* ignore */ }
      try { S.recognition.abort(); } catch (e) { /* ignore */ }
    }
    S.recognition = null;
  }

  /* ---------------- 模式与识别来源（UI 可见） ---------------- */
  function liveCapability() {
    if (SpeechCtor()) return "browser";
    if (serverLive() && micSupported()) return "server";
    return "none";
  }
  function updateModeUi(initial) {
    var mode = currentMode();
    var capability = liveCapability();
    var badge = byId("voice-badge"), note = byId("voice-mode-note"), demo = byId("voice-demo");
    if (badge) badge.hidden = false;
    if (mode === "demo") {
      if (badge) badge.textContent = t("演示模拟", "DEMO SIMULATION");
      if (demo) demo.hidden = false;
      if (note) note.textContent = t("识别文本 = 下方填写内容，不解析麦克风声音",
        "Result = the text below; the microphone is not analysed.");
    } else if (capability === "browser") {
      if (badge) badge.textContent = t("浏览器实时识别", "LIVE · BROWSER");
      if (demo) demo.hidden = true;
      if (note) note.textContent = t("由浏览器直接转写你说的话（Chrome / Edge）",
        "Your speech is transcribed directly by the browser (Chrome / Edge).");
    } else if (capability === "server") {
      if (badge) badge.textContent = t("服务端识别", "LIVE · SERVER");
      if (demo) demo.hidden = true;
      if (note) note.textContent = t("录音上传至服务端 ASR 后返回识别文本",
        "Audio is uploaded to the server ASR, which returns the transcript.");
    } else {
      if (badge) badge.textContent = t("真实识别不可用", "LIVE UNAVAILABLE");
      if (demo) demo.hidden = true;
      if (note) note.textContent = t("需 Chrome / Edge 浏览器语音识别，或配置 ASR_PROVIDER=http；也可切到演示模拟",
        "Requires browser speech recognition in Chrome / Edge, or ASR_PROVIDER=http. You can switch to Demo simulation.");
    }
    if (initial) {
      if (mode === "demo") {
        setStatus(t("当前是演示模拟：识别文本来自下方输入框，不会解析麦克风声音。",
          "Demo simulation: the result comes from the box below; the microphone is not analysed."), "warn");
      } else if (capability === "none") {
        setStatus(t("当前环境无法做真实语音识别，请切换到「演示模拟」，或配置服务端 ASR 后重试。",
          "Live recognition is unavailable here. Switch to Demo simulation, or configure a server ASR."), "warn");
      } else {
        setStatus(t("语音输入为可选辅助；识别文本需经你确认才会使用。",
          "Voice input is optional. Nothing is used until you confirm."), "");
      }
    }
  }

  /* ---------------- 控件状态机 ---------------- */
  function setControls(phase) {
    S.phase = phase;
    var rec = byId("voice-record"), stop = byId("voice-stop");
    var apply = byId("voice-apply"), second = byId("voice-apply-secondary");
    var undo = byId("voice-undo"), clip = byId("voice-clip");
    var transcript = byId("voice-transcript");
    var recording = phase === "recording";
    var done = phase === "done";
    // 不再因「真实通道不可用」把按钮置灰：允许点击并给出明确原因，比点了没反应友好。
    rec.disabled = recording || phase === "busy";
    rec.textContent = recording ? t("录音中…", "Recording…") : t("开始录音", "Start recording");
    stop.disabled = !recording;
    if (apply) apply.disabled = !done;
    if (second) second.hidden = !done || !S.opts.applyOnlyLabel;
    if (undo) undo.hidden = !done || !S.opts.onUndo;
    if (clip) clip.hidden = !done || !S.audioUrl;
    if (transcript) transcript.hidden = !(done || (phase === "busy" && byId("voice-text").value));
  }

  function beginTimer() {
    S.startedAt = Date.now();
    S.durationMs = 0;
    byId("voice-timer").textContent = "00:00";
    window.clearInterval(S.timerId);
    S.timerId = window.setInterval(function () {
      var elapsed = Date.now() - S.startedAt;
      byId("voice-timer").textContent = fmt(elapsed);
      var limit = (S.status && S.status.max_duration_ms) || 60000;
      if (elapsed >= limit) {
        setStatus(t("已达最长录音时长，自动停止。", "Maximum recording length reached; stopping automatically."), "warn");
        stopRecording();
      }
    }, 250);
  }
  function endTimer() {
    window.clearInterval(S.timerId);
    S.timerId = 0;
    S.durationMs = S.startedAt ? Date.now() - S.startedAt : 0;
  }

  /* ---------------- 录音启动 ---------------- */
  function startDemo() {
    S.liveKind = "demo";
    S.simulated = true;
    S.chunks = [];
    releaseUrl();
    beginTimer();
    setControls("recording");
    setStatus(t("演示模拟计时中…点「停止并识别」查看结果（不会解析麦克风声音）。",
      "Demo timer running… press Stop & recognise (microphone is not analysed)."), "rec");
  }

  /** 浏览器原生真实识别：结果直接来自麦克风，不经过后端。 */
  function startLiveBrowser() {
    var Ctor = SpeechCtor();
    if (!Ctor) return false;
    var rec;
    try {
      rec = new Ctor();
      rec.lang = currentLang() === "en" ? "en-US" : "zh-CN";
      rec.continuous = true;
      rec.interimResults = true;
      rec.maxAlternatives = 1;
    } catch (e) { return false; }
    S.finalText = "";
    S.interimText = "";
    S.recError = "";
    S.stopping = false;
    rec.onresult = function (event) {
      var interim = "";
      for (var i = event.resultIndex; i < event.results.length; i += 1) {
        var item = event.results[i];
        var piece = item && item[0] && item[0].transcript ? item[0].transcript : "";
        if (item.isFinal) S.finalText += piece;
        else interim += piece;
      }
      S.interimText = interim;
      // 实时把「已确认 + 临时」结果显示出来，说的时候就能看见文字在长
      byId("voice-text").value = (S.finalText + S.interimText).trim();
      byId("voice-transcript").hidden = false;
    };
    rec.onerror = function (event) {
      var reason = (event && event.error) || "unknown";
      S.recError = reason;
      // 致命错误立即收束，避免界面永远停在「录音中…」；
      // no-speech / aborted 等瞬时错误交给 onend 自动续接，不打断用户说话。
      if (reason === "not-allowed" || reason === "service-not-allowed" || reason === "audio-capture") {
        S.stopping = true;
        window.clearTimeout(S.endGuard);
        S.endGuard = window.setTimeout(finishBrowser, 250);
      }
    };
    rec.onend = function () {
      if (S.stopping) { finishBrowser(); return; }
      // Chrome / Edge 的 continuous 识别会在一段静音后自行 onend；
      // 用户尚未点「停止并识别」时自动续接，保证「说的每一句」都能转成文字。
      if (S.phase === "recording" && S.liveKind === "browser" && !S.recError) {
        try { rec.start(); return; } catch (e) { /* 落到下方兜底 */ }
      }
      S.stopping = true;
      finishBrowser();
    };
    try { rec.start(); }
    catch (e) { releaseRecognition(); return false; }
    S.recognition = rec;
    S.liveKind = "browser";
    S.simulated = false;
    beginTimer();
    setControls("recording");
    setStatus(t("正在听你说话…说完点「停止并识别」。",
      "Listening… press Stop & recognise when done."), "rec");
    return true;
  }

  async function startLiveServer() {
    if (!micSupported()) {
      return fail(t("当前环境不支持录音，请使用 HTTPS 与 Chrome / Edge 浏览器。",
        "Recording is not supported here. Use HTTPS with Chrome or Edge."));
    }
    try { S.stream = await getMicWithTimeout(4000); }
    catch (err) {
      releaseStream();
      return fail(t("无法使用麦克风，请检查浏览器权限后重试。",
        "Cannot access the microphone. Check browser permissions and retry."));
    }
    var mime = pickMime();
    try {
      S.recorder = mime ? new MediaRecorder(S.stream, { mimeType: mime }) : new MediaRecorder(S.stream);
    } catch (err) {
      releaseStream();
      return fail(t("浏览器无法创建录音器，请换用 Chrome / Edge 重试。",
        "This browser cannot start a recording. Try Chrome or Edge."));
    }
    S.chunks = [];
    S.mime = S.recorder.mimeType || mime || "audio/webm";
    S.simulated = false;
    S.recorder.ondataavailable = function (event) {
      if (event.data && event.data.size) S.chunks.push(event.data);
    };
    S.recorder.onstop = function () { onStopped(new Blob(S.chunks, { type: S.mime })); };
    try { S.recorder.start(200); }
    catch (err) {
      releaseStream();
      return fail(t("录音启动失败，请重试或改用键盘输入。",
        "Could not start recording. Retry or type instead."));
    }
    S.liveKind = "server";
    beginTimer();
    setControls("recording");
    setStatus(t("正在录音…说完后点「停止并识别」。",
      "Recording… press Stop & recognise when done."), "rec");
  }

  async function startRecording() {
    if (S.busy) return;
    S.busy = true;
    S.mode = currentMode();
    clearTranscript(false);
    setControls("busy");
    try {
      if (S.mode === "demo") {
        setStatus(t("正在准备演示模拟…", "Preparing demo simulation…"), "busy");
        return startDemo();
      }
      setStatus(t("正在启动语音识别…", "Starting speech recognition…"), "busy");
      if (startLiveBrowser()) return;
      if (serverLive()) return await startLiveServer();
      return fail(t(
        "当前环境无法做真实语音识别：浏览器未提供语音识别能力，服务端也未配置 ASR。请改用 Chrome / Edge，或配置 ASR_PROVIDER=http，也可手动切到「演示模拟」。",
        "Live recognition is unavailable: this browser has no speech recognition and no server ASR is configured. Use Chrome / Edge, set ASR_PROVIDER=http, or switch to Demo simulation."));
    } finally {
      S.busy = false;
    }
  }

  /* ---------------- 停止与结果 ---------------- */
  function liveFailureMessage(reason) {
    if (reason === "not-allowed" || reason === "service-not-allowed") {
      return t("麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试。",
        "Microphone permission was denied. Allow it in the address bar and retry.");
    }
    if (reason === "network") {
      return t("浏览器语音识别服务不可达（可能被网络限制）。可配置 ASR_PROVIDER=http 走服务端识别，或手动切到「演示模拟」。",
        "Browser speech service is unreachable (possibly network-restricted). Set ASR_PROVIDER=http for server recognition, or switch to Demo simulation.");
    }
    if (reason === "no-speech") {
      return t("没有听到声音，请靠近麦克风再说一遍。",
        "No speech detected. Please speak closer to the microphone and retry.");
    }
    if (reason === "audio-capture") {
      return t("未检测到可用麦克风，请检查设备后重试。",
        "No microphone was found. Check your device and retry.");
    }
    return t("未能完成语音识别，请重试；如需离线演示可手动切到「演示模拟」。",
      "Speech recognition did not complete. Retry, or switch to Demo simulation for an offline demo.");
  }

  function finishBrowser() {
    if (!S.stopping) return;
    S.stopping = false;
    window.clearTimeout(S.endGuard);
    endTimer();
    releaseRecognition();
    var text = (S.finalText || "").trim();
    if (!text) return fail(liveFailureMessage(S.recError));
    finish({
      text: text, lang: currentLang(), confidence: 0,
      duration_ms: S.durationMs, provider: "browser", demo: false,
      request_id: "browser"
    });
  }

  function stopRecording() {
    if (S.phase !== "recording") return;
    setControls("busy");
    if (S.liveKind === "browser") {
      setStatus(t("正在整理识别文本…", "Finalising transcript…"), "busy");
      S.stopping = true;
      S.finalText = S.finalText || "";
      S.interimText = "";
      // 丢弃尚未确认的临时片段，只保留 final 结果
      byId("voice-text").value = S.finalText.trim();
      try { S.recognition.stop(); } catch (e) { /* onend 不触发时由守护定时器兜底 */ }
      window.clearTimeout(S.endGuard);
      S.endGuard = window.setTimeout(finishBrowser, 2000);
      return;
    }
    endTimer();
    setStatus(t("正在识别…", "Recognising…"), "busy");
    if (S.liveKind === "demo") {
      // 演示模拟：给接口一个最小合法音频体，mock ASR 不解析音频，只回显 demo_text。
      onStopped(new Blob([new Uint8Array([0, 0, 0, 0])], { type: "audio/webm" }));
      return;
    }
    try { S.recorder.stop(); }
    catch (err) { onStopped(new Blob(S.chunks, { type: S.mime || "audio/webm" })); }
  }

  function onStopped(blob) {
    releaseStream();
    releaseUrl();
    if (!blob || !blob.size) {
      return fail(t("没有录到声音，请重试或改用键盘输入。",
        "No audio captured. Retry or type instead."));
    }
    if (S.status && blob.size > S.status.max_audio_bytes) {
      return fail(t("录音文件过大，请缩短录音后重试。",
        "The recording is too large. Record a shorter clip and retry."));
    }
    if (!S.simulated) {
      S.audioUrl = URL.createObjectURL(blob);
      byId("voice-playback").src = S.audioUrl;
    }
    recognizeServer(blob);
  }

  function readJson(response) {
    return response.text().then(function (raw) {
      var data = null;
      if (raw) { try { data = JSON.parse(raw); } catch (e) { data = raw; } }
      if (!response.ok) {
        var detail = data && typeof data === "object" ? data.detail : data;
        var message = (detail && typeof detail === "object" && detail.message) || detail || "";
        var err = new Error(String(message || t("语音识别失败", "Speech recognition failed")));
        err.status = response.status;
        err.code = (detail && typeof detail === "object" && detail.code) || "";
        throw err;
      }
      return data;
    });
  }

  function providerLabel(result) {
    if (result.demo) return t("演示模拟 · 不解析声音", "Demo simulation · no audio analysis");
    if (result.provider === "browser") return t("浏览器实时识别", "Live browser recognition");
    if (result.provider === "http") return t("服务端识别 · http", "Server ASR · http");
    return t("识别服务：" + (result.provider || "-"), "Provider: " + (result.provider || "-"));
  }

  /** 统一结果出口：browser / server / demo 三条通道共用，适配器无需区分来源。 */
  function finish(result) {
    S.busy = false;
    S.lastResult = result || {};
    var text = String(S.lastResult.text || "").trim();
    byId("voice-text").value = text;
    byId("voice-transcript").hidden = false;
    byId("voice-demo-note").hidden = !S.lastResult.demo;
    byId("voice-provider").textContent = providerLabel(S.lastResult);
    setControls("done");
    setStatus(S.lastResult.demo
      ? t("演示模拟完成：文本来自你填写的内容，不是麦克风声音，请先核对。",
        "Demo simulation complete: the text is what you typed, not your speech. Please review.")
      : t("识别完成，文本来自刚才的语音，请先核对再决定是否使用。",
        "Recognition complete. The text comes from your speech; please review before using it."), "ok");
    if (S.opts.onResult) S.opts.onResult(text, S.lastResult);
  }

  function recognizeServer(blob) {
    S.busy = true;
    var form = new FormData();
    form.append("audio", blob, "speech." + extFor(blob.type || S.mime));
    form.append("lang", currentLang());
    form.append("duration_ms", String(S.durationMs));
    // 只有用户手动选择了「演示模拟」才回显模拟文本；真实识别绝不携带 demo_text。
    if (S.mode === "demo") form.append("demo_text", byId("voice-demo-input").value || "");
    var headers = { "X-Lang": isEn() ? "en" : "zh" };
    var csrf = getCookie("csrf_token");
    if (csrf) headers["X-CSRF-Token"] = csrf;
    fetch("/api/speech/recognize", {
      method: "POST", body: form, headers: headers,
      credentials: "same-origin", cache: "no-store"
    }).then(readJson).then(function (data) {
      // 服务端处于 mock 时，真实模式不允许把示例文本冒充识别结果。
      if (S.mode !== "demo" && data && data.demo) {
        return fail(t(
          "服务端目前是演示 ASR（未配置真实识别），无法把音频转成文字。请改用浏览器语音识别，配置 ASR_PROVIDER=http，或手动切到「演示模拟」。",
          "The server is in demo ASR mode and cannot transcribe audio. Use browser speech recognition, set ASR_PROVIDER=http, or switch to Demo simulation."));
      }
      finish(data || {});
    }).catch(function (err) {
      if (S.phase === "done") return;
      var msg = err.status === 401
        ? t("登录状态已失效，请重新登录后再使用语音输入。",
          "Your session expired. Please sign in again to use voice input.")
        : (err.message || t("语音识别失败，请重试或改用键盘输入。",
          "Speech recognition failed. Retry or type instead."));
      fail(msg);
    });
  }

  function fail(message) {
    S.busy = false;
    S.stopping = false;
    window.clearTimeout(S.endGuard);
    endTimer();
    releaseRecognition();
    releaseStream();
    setControls("idle");
    // 失败后刷新模式角标/说明，避免仍显示「LIVE · BROWSER」而实际已不可用。
    try { updateModeUi(false); } catch (e) { /* 不影响错误提示 */ }
    setStatus(message, "error");
    toast(message, "error");
  }

  /* ---------------- 结果区 ---------------- */
  function clearTranscript(revoke) {
    window.clearTimeout(S.changeTimer);
    byId("voice-text").value = "";
    byId("voice-transcript").hidden = true;
    byId("voice-demo-note").hidden = true;
    byId("voice-provider").textContent = "";
    byId("voice-timer").textContent = "00:00";
    if (revoke !== false) {
      releaseUrl();
      var audio = byId("voice-playback");
      if (audio) { audio.removeAttribute("src"); audio.load(); }
      S.lastResult = null;
    }
  }
  function undo() {
    if (S.opts.onUndo) {
      try { S.opts.onUndo(); } catch (err) { /* 适配器异常不阻塞内核复位 */ }
    }
    clearTranscript(true);
    setControls("idle");
    updateModeUi(false);
    setStatus(t("已撤销，表单内容未被语音结果覆盖。",
      "Undone. The form was not overwritten by the voice result."), "ok");
  }
  function apply(only) {
    if (S.phase !== "done") return;
    var text = byId("voice-text").value.trim();
    if (!text) {
      fail(t("识别文本为空，请重新录音或改用键盘输入。",
        "The recognised text is empty. Record again or type instead."));
      return;
    }
    var handler = only ? S.opts.onApplyOnly : S.opts.onApply;
    if (typeof handler !== "function") return;
    try { handler(text, S.lastResult); }
    catch (err) { fail(t("写入失败：" + err.message, "Could not apply: " + err.message)); }
  }

  /* ---------------- 装配 ---------------- */
  function mount(options) {
    if (!byId("voice-box")) return null;
    S.opts = options || {};
    var primary = byId("voice-apply"), second = byId("voice-apply-secondary");
    var note = byId("voice-apply-note");
    if (primary) primary.textContent = t(S.opts.applyLabel.zh, S.opts.applyLabel.en);
    if (second) {
      second.textContent = S.opts.applyOnlyLabel
        ? t(S.opts.applyOnlyLabel.zh, S.opts.applyOnlyLabel.en) : "";
      second.hidden = true;
    }
    if (note && S.opts.applyNote) note.textContent = t(S.opts.applyNote.zh, S.opts.applyNote.en);

    byId("voice-record").addEventListener("click", startRecording);
    byId("voice-stop").addEventListener("click", stopRecording);
    byId("voice-undo").addEventListener("click", undo);
    byId("voice-discard").addEventListener("click", undo);
    if (primary) primary.addEventListener("click", function () { apply(false); });
    if (second) second.addEventListener("click", function () { apply(true); });
    byId("voice-text").addEventListener("input", function () {
      window.clearTimeout(S.changeTimer);
      var value = this.value;
      S.changeTimer = window.setTimeout(function () {
        if (S.opts.onTextChange) S.opts.onTextChange(value, S.lastResult);
      }, 300);
    });
    Array.prototype.forEach.call(document.querySelectorAll('input[name="voice-mode"]'), function (radio) {
      radio.addEventListener("change", function () { updateModeUi(true); });
    });
    Array.prototype.forEach.call(document.querySelectorAll('input[name="voice-lang"]'), function (radio) {
      radio.addEventListener("change", function () { updateModeUi(false); });
    });

    setControls("idle");
    updateModeUi(true);
    loadStatus();
    return api();
  }

  function loadStatus() {
    return fetch("/api/speech/status", {
      headers: { "X-Lang": isEn() ? "en" : "zh" },
      credentials: "same-origin", cache: "no-store"
    }).then(readJson).then(function (data) {
      S.status = data || {};
      S.demo = !!S.status.demo;
      var sample = isEn()
        ? (S.opts.demoSampleEn || S.opts.demoSample || "")
        : (S.opts.demoSample || "");
      var input = byId("voice-demo-input");
      if (input) input.value = sample;
      updateModeUi(true);
      setControls(S.phase);
    }).catch(function () {
      S.status = null;
      S.demo = false;
      updateModeUi(true);
      setControls(S.phase);
    });
  }

  function api() {
    return {
      t: t, isEn: isEn, esc: esc, toast: toast, setStatus: setStatus,
      status: function () { return S.status; },
      mode: function () { return currentMode(); },
      liveCapability: liveCapability,
      clear: function () { clearTranscript(true); setControls("idle"); }
    };
  }

  window.VoiceCore = { mount: mount, t: t, isEn: isEn, esc: esc, toast: toast };
})();
