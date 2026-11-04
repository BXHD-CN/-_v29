/* ============================================================
   患者情况告知单（一级功能页 check.html，与「翻译」平级，注册登录后可用）
   ------------------------------------------------------------
   与翻译 / 语言质量检查明确区分：
   - 单栏「采集 → 交接单」，没有原文框 / 译文框，也不调用 /api/translate；
   - 采集 = 圈选 / 输入的不适部位、不适症状、症状细节（含疼痛特征）与患者原话；
   - 输出 = 把患者自述按临床交接习惯结构化整理后「转达给医生」；
   - 不做准确性 / 清晰度 / 跨文化适配性评估，不给待补充 / 待澄清，
     不做文化风险提示，页面与接口都不产出、不展示任何译文。
   ============================================================ */
(function () {
  "use strict";

  /* ---------------- 圈选项清单（与后端 DETAIL_GROUP 逐字一致） ---------------- */
  var OPTIONS = {
    parts: [
      "头部", "眼", "耳", "鼻/咽喉", "颈", "胸", "上腹", "下腹", "腰背", "肩",
      "上肢/手臂", "手/腕", "髋", "下肢/腿", "膝", "足/踝", "全身", "皮肤"
    ],
    symptoms: [
      "乏力", "疼痛", "发热", "头晕", "恶心/呕吐", "咳嗽", "呼吸困难", "心悸",
      "麻木", "肿胀", "出血", "皮疹", "腹泻", "失眠", "食欲下降", "意识模糊"
    ],
    detailGroups: [
      { label: "时间进程", items: ["突发", "持续性", "间歇性", "慢性疼痛", "反复发作", "夜间加重", "逐渐加重"] },
      { label: "程度", items: ["轻微", "中度", "剧痛", "难以忍受"] },
      { label: "性质", items: ["钝痛", "刺痛/锐痛", "胀痛", "烧灼痛", "绞痛", "压迫感", "放射痛"] },
      { label: "诱因 / 缓解", items: ["活动后加重", "休息缓解", "按压加重", "体位相关", "进食相关"] },
      { label: "伴随症状", items: ["伴发热", "伴呕吐", "伴出汗", "伴麻木", "伴呼吸困难"] }
    ]
  };
  var SCENE_HINT = {
    consultation: "用于面对面分诊与病史采集",
    record: "用于病历文书的客观记录与留痕"
  };
  var CHIP_BOXES = ["pc-parts-chips", "pc-symptoms-chips", "pc-details-chips"];
  var TEXT_FIELDS = ["pc-part-other", "pc-symptom-other", "pc-detail-other", "pc-free-text"];
  /* 明确写在页面上的边界标签；后端也会回传 no_translation / no_quality_judgement */
  var BOUNDARY = ["不翻译", "不诊断", "不评估表达质量", "不澄清文化或信息问题"];

  var state = { scene: "consultation", busy: false, last: null };
  var app = window.App || null;

  function byId(id) { return document.getElementById(id); }
  function all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function closest(node, selector) {
    while (node && node !== document) {
      if (node.nodeType === 1 && node.matches && node.matches(selector)) return node;
      node = node.parentNode;
    }
    return null;
  }
  function esc(value) {
    if (app && typeof app.escapeHtml === "function") return app.escapeHtml(value);
    if (value === null || value === undefined) return "";
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function toast(message, kind) {
    if (app && typeof app.toast === "function" && byId("toast-stack")) {
      app.toast(message, kind);
      return;
    }
    var stack = document.querySelector(".pc-toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "pc-toast-stack";
      stack.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;flex-direction:column;gap:8px";
      document.body.appendChild(stack);
    }
    var node = document.createElement("div");
    node.textContent = String(message || "");
    node.style.cssText = "max-width:340px;padding:10px 14px;border-radius:8px;font-size:15px;color:#fff;box-shadow:0 8px 24px rgba(15,23,42,.2);background:" +
      (kind === "error" ? "#9F1239" : "#17130F");
    stack.appendChild(node);
    window.setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, 3200);
  }
  function messageOf(err) {
    if (!err) return "未知错误";
    return err.message || (err.detail && String(err.detail)) || "请求失败";
  }
  function getCookie(name) {
    var list = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < list.length; i += 1) {
      var pair = list[i].split("=");
      if (decodeURIComponent(pair[0]) === name) return decodeURIComponent(pair.slice(1).join("="));
    }
    return "";
  }
  async function localApi(path, options) {
    var opts = options || {};
    var method = String(opts.method || "GET").toUpperCase();
    var headers = {};
    var body;
    if (opts.body !== undefined && opts.body !== null) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.body);
    }
    if (window.I18N && typeof window.I18N.lang === "function") {
      headers["X-Lang"] = window.I18N.lang();
    }
    if (method !== "GET" && method !== "HEAD") {
      var csrf = getCookie("csrf_token");
      if (csrf) headers["X-CSRF-Token"] = csrf;
    }
    var response = await fetch(path, {
      method: method, headers: headers, body: body,
      credentials: "same-origin", cache: "no-store"
    });
    var text = await response.text();
    var data = null;
    if (text) { try { data = JSON.parse(text); } catch (e) { data = text; } }
    if (!response.ok) {
      var err = new Error((data && typeof data === "object" && (data.detail || data.message)) ||
        ("请求失败（" + response.status + "）"));
      err.status = response.status;
      throw err;
    }
    return data;
  }
  function api(path, options) {
    var opts = options || {};
    opts.silent = true;
    // 注册前置门禁：不再声明 authOptional，401 交由 app.js 统一回注册入口。
    if (app && typeof app.api === "function") {
      try { return Promise.resolve(app.api(path, opts)); }
      catch (e) { return Promise.reject(e); }
    }
    return localApi(path, opts);
  }

  /* ---------------- 采集表 ---------------- */
  function chipHtml(value) {
    return '<button type="button" class="pc-chip" data-value="' + esc(value) + '" aria-pressed="false">' +
      '<span class="pc-chip__mark" aria-hidden="true"></span>' + esc(value) + "</button>";
  }
  function buildChips() {
    byId("pc-parts-chips").innerHTML = OPTIONS.parts.map(chipHtml).join("");
    byId("pc-symptoms-chips").innerHTML = OPTIONS.symptoms.map(chipHtml).join("");
    var html = "";
    OPTIONS.detailGroups.forEach(function (group) {
      html += '<p class="pc-chips__label">' + esc(group.label) + "</p>";
      html += group.items.map(chipHtml).join("");
    });
    byId("pc-details-chips").innerHTML = html;
  }
  function picked(boxId) {
    return all(".pc-chip.is-on", byId(boxId)).map(function (node) {
      return node.getAttribute("data-value");
    });
  }
  function collect() {
    return {
      scene: state.scene,
      parts: picked("pc-parts-chips"),
      part_other: byId("pc-part-other").value.trim(),
      symptoms: picked("pc-symptoms-chips"),
      symptom_other: byId("pc-symptom-other").value.trim(),
      details: picked("pc-details-chips"),
      detail_other: byId("pc-detail-other").value.trim(),
      free_text: byId("pc-free-text").value.trim(),
      country: byId("pc-country").value
    };
  }
  function hasContent(payload) {
    return payload.parts.length || payload.part_other || payload.symptoms.length ||
      payload.symptom_other || payload.details.length || payload.detail_other || payload.free_text;
  }
  function fmtList(list, other) {
    var merged = (list || []).slice();
    if (other) merged.push(other);
    return merged.length ? merged.join("、") : "未填写";
  }

  /* ---------------- 告知单渲染（无译文、无检查结论） ---------------- */
  function boundaryHtml() {
    return '<ul class="pc-boundary">' + BOUNDARY.map(function (text) {
      return '<li class="pc-boundary__item">' + esc(text) + "</li>";
    }).join("") + "</ul>";
  }

  function render(data) {
    var box = byId("pc-result");
    if (!data || data.empty) {
      box.innerHTML = '<div class="pc-empty">' +
        esc((data && data.message) || "尚未采集到患者内容，请先圈选或填写至少一项。") + "</div>";
      box.hidden = false;
      return;
    }
    state.last = data;

    var html = "";
    html += '<div class="pc-handoff">';
    html += '<div class="pc-handoff__head">';
    html += '<div><p class="pc-result__head">患者情况告知单 · 已生成</p>' +
      '<h3 class="pc-handoff__title">交给医生前请再核对一遍</h3></div>';
    html += '<span class="pc-handoff__scene">' + esc(data.scene || "问诊沟通") + "</span>";
    html += "</div>";
    html += '<p class="pc-handoff__purpose">' + esc(data.purpose || "") + "；以下为患者自述的结构化转达。</p>";
    html += boundaryHtml();

    /* 主诉：医生最先看的一句话 */
    html += '<div class="pc-chief">' +
      '<span class="pc-chief__label">主诉 / CHIEF COMPLAINT</span>' +
      '<p class="pc-chief__text">' + esc(data.chief_complaint || "患者尚未描述具体不适") + "</p></div>";

    /* 编号分项：完全照后端 sections，不加工、不评判 */
    html += '<ol class="pc-sections">';
    (data.sections || []).forEach(function (section) {
      html += '<li class="pc-section">' +
        '<span class="pc-section__no">' + esc(section.no) + "</span>" +
        '<span class="pc-section__label">' + esc(section.label) + "</span>" +
        '<span class="pc-section__text">' + esc(section.text) + "</span></li>";
    });
    html += "</ol>";

    /* 可编辑的整单全文：交给医生前允许人工微调措辞，但默认就是后端原文 */
    html += '<div class="pc-slip">';
    html += '<div class="pc-slip__head"><span>交接单全文（可直接复制 / 打印交给医生）</span>' +
      '<button class="pc-btn pc-btn--sm" id="pc-copy" type="button">复制全文</button></div>';
    html += '<textarea id="pc-handoff-text" class="pc-slip__text" rows="12" spellcheck="false"></textarea>';
    html += '<p class="pc-slip__tip">默认文本由系统按临床交接习惯整理，患者原话照录；如需调整，可直接在上方编辑后再复制。</p>';
    html += "</div>";

    /* 采集内容回显（折叠，避免干扰主单） */
    var submitted = data.submitted || {};
    html += '<details class="pc-collected"><summary>查看本次采集的原始内容</summary><div class="pc-submitted">';
    html += "<p><strong>场景：</strong>" + esc(submitted.scene || data.scene || "") +
      (submitted.country ? " · <strong>文化/国家：</strong>" + esc(submitted.country) : "") + "</p>";
    html += "<p><strong>不适部位：</strong>" + esc(fmtList(submitted.parts, submitted.part_other)) + "</p>";
    html += "<p><strong>不适症状：</strong>" + esc(fmtList(submitted.symptoms, submitted.symptom_other)) + "</p>";
    var detailParts = [];
    var byGroup = submitted.details_by_group || {};
    Object.keys(byGroup).forEach(function (key) {
      detailParts.push(key + "：" + (byGroup[key] || []).join("、"));
    });
    if (submitted.detail_other) detailParts.push("其他：" + submitted.detail_other);
    html += "<p><strong>症状细节：</strong>" +
      esc(detailParts.length ? detailParts.join("；") : "未填写") + "</p>";
    if (submitted.free_text) {
      html += "<p><strong>患者原话：</strong>" + esc(submitted.free_text) + "</p>";
    }
    html += "</div></details>";
    html += "</div>";

    html += '<p class="pc-disclaimer">' + esc(data.disclaimer || "") + "</p>";

    /* 云端留档：只把「告知单」带去云端资产，不产出译文、不生成检查结论 */
    var shareCode = new URLSearchParams(location.search).get("sharecode");
    var cloudHref = "cloud.html?from=check" +
      (shareCode ? "&sharecode=" + encodeURIComponent(shareCode) : "");
    html += '<div class="pc-cloud">' +
      '<span class="pc-cloud__label">想把这张告知单留档？</span>' +
      '<a class="pc-cloud__btn" href="' + esc(cloudHref) + '">保存到云端 →</a>' +
      '<small>云端身份 · 交接单记录 · 交接单文件</small></div>';
    try {
      sessionStorage.setItem("er_last_check", JSON.stringify(data));
    } catch (_) { /* 隐私模式下不可写时跳过，不影响告知单本身 */ }

    box.innerHTML = html;
    box.hidden = false;
    var area = byId("pc-handoff-text");
    if (area) area.value = data.handoff_text || "";
    var copyBtn = byId("pc-copy");
    if (copyBtn) copyBtn.addEventListener("click", copyHandoff);
  }

  async function copyHandoff() {
    var area = byId("pc-handoff-text");
    if (!area) return;
    var text = area.value || "";
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        area.focus();
        area.select();
        document.execCommand("copy");
      }
      toast("告知单已复制，可直接交给医生");
    } catch (err) {
      area.focus();
      area.select();
      toast("自动复制不可用，已选中全文，请按 Ctrl+C", "error");
    }
  }

  /* ---------------- 提交与事件 ---------------- */
  async function submit(event) {
    event.preventDefault();
    if (state.busy) return;
    var payload = collect();
    if (!hasContent(payload)) {
      toast("请先圈选或输入至少一项患者信息", "error");
      return;
    }
    state.busy = true;
    var button = byId("pc-submit");
    button.disabled = true;
    button.textContent = "整理中…";
    try {
      var data = await api("/api/patient-check", { method: "POST", body: payload });
      /* 双保险：若后端意外回传译文或质量评估字段，前端一律不渲染 */
      if (data &&
          (data.translation || data.rec_en || data.standard_en || data.target_text ||
           data.overall || data.dimensions || data.culture_notes || data.missing_elements)) {
        throw new Error("接口返回了非告知单内容，已阻止展示");
      }
      render(data);
      var box = byId("pc-result");
      if (box.scrollIntoView) box.scrollIntoView({ behavior: "smooth", block: "start" });
      toast("告知单已生成，可复制后交给医生");
    } catch (err) {
      toast("生成失败：" + messageOf(err), "error");
    } finally {
      state.busy = false;
      button.disabled = false;
      button.textContent = "生成给医生的告知单";
    }
  }

  function bind() {
    byId("pc-form").addEventListener("submit", submit);

    CHIP_BOXES.forEach(function (boxId) {
      byId(boxId).addEventListener("click", function (event) {
        var chip = closest(event.target, ".pc-chip");
        if (!chip) return;
        var on = chip.classList.toggle("is-on");
        chip.setAttribute("aria-pressed", on ? "true" : "false");
        var mark = chip.querySelector(".pc-chip__mark");
        if (mark) mark.textContent = on ? "✓" : "";
      });
    });

    all(".pc-scene__btn").forEach(function (button) {
      button.addEventListener("click", function () {
        state.scene = button.getAttribute("data-scene") || "consultation";
        all(".pc-scene__btn").forEach(function (other) {
          other.classList.toggle("is-active", other === button);
        });
        byId("pc-scene-hint").textContent = SCENE_HINT[state.scene] || SCENE_HINT.consultation;
      });
    });

    byId("pc-reset").addEventListener("click", function () {
      all(".pc-chip.is-on").forEach(function (chip) {
        chip.classList.remove("is-on");
        chip.setAttribute("aria-pressed", "false");
        var mark = chip.querySelector(".pc-chip__mark");
        if (mark) mark.textContent = "";
      });
      TEXT_FIELDS.forEach(function (id) { byId(id).value = ""; });
      byId("pc-country").value = "";
      var box = byId("pc-result");
      box.hidden = true;
      box.innerHTML = "";
      state.last = null;
      toast("已清空，可重新填写");
    });
  }

  function boot() {
    buildChips();
    bind();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
