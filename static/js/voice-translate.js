/* ============================================================
   翻译页语音适配器（v=27）
   ------------------------------------------------------------
   语音是「原文输入框的输入旁路」：
     麦克风 → /api/speech/recognize → 可编辑识别文本 → 人工确认
     → 写入 #tr-source → 点既有 #tr-submit（复用 translate.js 的 submit()）
     → POST /api/translate → 既有 renderResult()

   零改动承诺：本文件不调用、不覆盖、不重写 translate.js 的 submit()
   与 renderResult()，也不改 /api/translate 的请求契约；只是往原文框里
   「放一段文字」，再触发既有的按钮点击。默认绝不自动翻译。
   ============================================================ */
(function () {
  "use strict";

  function byId(id) { return document.getElementById(id); }
  function isEn() { return !!(window.I18N && window.I18N.isEn && window.I18N.isEn()); }

  /** 识别文本规范化：只做排版级整理，不改写患者 / 医护原话。 */
  function normalize(text, lang) {
    var out = String(text || "").replace(/\r/g, "")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    // 中文 ASR 偶尔在汉字之间插空格（"胸 痛"），合并；英文模式不动。
    if (lang === "zh" || !isEn()) {
      out = out.replace(/([\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])/g, "$1");
    }
    return out;
  }

  function writeSource(text, result) {
    var ta = byId("tr-source");
    if (!ta) throw new Error("原文框不存在");
    // 若当前处于「逐句对照」视图，先按既有按钮回到可编辑原文框。
    var editSrc = byId("tr-edit-src");
    if (ta.hidden && editSrc && !editSrc.hidden) editSrc.click();
    var clean = normalize(text, result && result.lang);
    if (!clean) throw new Error(isEn() ? "The recognised text is empty." : "识别文本为空");
    var existing = ta.value.replace(/\s+$/, "");
    ta.value = existing ? existing + "\n" + clean : clean;
    if (ta.value.length > 5000) ta.value = ta.value.slice(0, 5000);
    // 触发既有 input 监听：字数统计、上限校验、草稿保存全部照旧生效。
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    return clean;
  }

  function mount() {
    if (!window.VoiceCore || !byId("voice-box") || !byId("tr-source")) return;
    window.VoiceCore.mount({
      demoSample: "患者主诉胸部持续疼痛两小时，伴呼吸困难，活动后加重。",
      demoSampleEn: "The patient reports chest pain for two hours, with shortness of breath.",
      applyLabel: { zh: "确认并翻译", en: "Confirm & translate" },
      applyOnlyLabel: { zh: "仅写入原文", en: "Write to source only" },
      applyNote: {
        zh: "确认后写入左侧原文框；「仅写入原文」不会触发翻译，之后按 Enter 或点「翻译」即可。",
        en: "Confirm writes the text into the source box. 'Write to source only' does not translate; press Enter or click Translate afterwards."
      },
      onResult: function (text, result) {
        var box = byId("voice-text");
        if (box) box.value = normalize(text, result && result.lang);
      },
      onApply: function (text, result) {
        writeSource(text, result);
        var submit = byId("tr-submit");
        if (!submit || submit.disabled) {
          window.VoiceCore.toast(
            isEn() ? "Text written. Adjust the source length before translating."
              : "已写入原文框；内容为空或超长时请调整后再翻译。", "warn");
          return;
        }
        // 复用既有提交：不改 translate.js 的任何一行。
        submit.click();
        window.VoiceCore.toast(
          isEn() ? "Source text written; existing translation flow started."
            : "已写入原文并沿用既有翻译流程", "success");
      },
      onApplyOnly: function (text, result) {
        writeSource(text, result);
        byId("tr-source").focus();
        window.VoiceCore.toast(
          isEn() ? "Written to the source box. No translation was triggered."
            : "已写入原文框，未触发翻译，可自行修改后按 Enter", "success");
      }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
