/* 首页 V4：复古科技 + 3D 交互（线框球 / 3D 卡片环 / 知识图 / 剪报） */
"use strict";

(function () {
  var CATEGORIES = [
    { key: "terms", label: "术语", color: "#2F6F6B", countKey: "terms", unit: "条", href: "quality.html#terms" },
    { key: "corpus", label: "平行语料", color: "#4B6784", countKey: "corpus", unit: "句", href: "quality.html#corpus" },
    { key: "local", label: "本地语", color: "#6E4B63", countKey: "local_terms", unit: "条", href: "quality.html#local" },
    { key: "news", label: "资讯", color: "#C0522B", countKey: "news", unit: "条", href: "news.html" },
    { key: "sources", label: "来源", color: "#D9A227", countKey: "sources", unit: "个", href: "" },
    { key: "chunks", label: "知识切片", color: "#5C6B3F", countKey: "chunks", unit: "片", href: "" }
  ];
  var PROVIDER_LABEL = {
    local: "LOCAL HASH", bigmodel: "BIGMODEL", mock: "MOCK", deepseek: "DEEPSEEK",
    mymemory: "MYMEMORY", none: "NONE", generic: "GENERIC"
  };
  var overview = { counts: {}, providers: {}, latest: [] };

  function byId(id) { return document.getElementById(id); }
  function fmt(n) { var v = Number(n); if (!isFinite(v)) return "—"; try { return v.toLocaleString("zh-CN"); } catch (e) { return String(v); } }
  function esc(v) { if (v == null) return ""; return String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  // 业主要求首页线框球 / 卡片环 / 知识图常驻动画：不因系统「减少动态效果」
  // 而降级为静帧。恒返回 false，禁止再改回 prefers-reduced-motion 判断。
  function reduceMotion() { return false; }
  function isMobile() { return window.matchMedia && window.matchMedia("(max-width: 767px)").matches; }
  function isEn() {
    return !!(window.I18N && typeof window.I18N.lang === "function" && window.I18N.lang() === "en");
  }
  function t(zh, vars) {
    return (window.I18N && typeof window.I18N.t === "function") ? window.I18N.t(zh, vars) : zh;
  }
  function fmtDate(v) {
    if (!v) return "—";
    var d = new Date(v);
    if (isNaN(d.getTime())) return String(v).slice(0, 10);
    function p(n) { return n < 10 ? "0" + n : "" + n; }
    return d.getFullYear() + "." + p(d.getMonth() + 1) + "." + p(d.getDate());
  }
  function sourceLabel(s) {
    return { un: "UN NEWS", un_zh: "UN NEWS (ZH)", reliefweb: "RELIEFWEB", usgs: "USGS" }[s] || String(s || "SOURCE").toUpperCase();
  }

  // ---------------- 数据 ----------------
  function loadOverview() {
    var api = window.App && window.App.api;
    if (!api) { render({}); return; }
    api("/api/public/overview", { silent: true }).then(function (data) { overview = data || {}; render(overview); })
      .catch(function () { render({}); });
  }

  function animateCount(el, to) {
    if (!el) return;
    var target = Number(to);
    if (!isFinite(target)) { el.textContent = "—"; return; }
    if (reduceMotion() || target < 100) { el.textContent = fmt(target); return; }
    var t0 = performance.now();
    (function step(now) {
      var p = Math.min(1, (now - t0) / 1000);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(Math.round(target * eased));
      if (p < 1) window.requestAnimationFrame(step);
    })(t0);
  }

  function render(data) {
    var c = (data && data.counts) || {};
    animateCount(byId("hero-stat-terms"), c.terms);
    animateCount(byId("hero-stat-corpus"), c.corpus);
    animateCount(byId("hero-stat-local"), c.local_terms);
    var p = (data && data.providers) || {};
    var note = byId("hero-provider-note");
    if (note) note.textContent = "VEC " + (PROVIDER_LABEL[p.embedding] || p.embedding || "—") +
      " · GEN " + (PROVIDER_LABEL[p.llm] || p.llm || "—") + " · MT " + (PROVIDER_LABEL[p.mt] || p.mt || "—");
    renderLegend(c);
    renderNews((data && data.latest) || []);
    graphData = c;
  }

  function renderLegend(counts) {
    var host = byId("kb-list");
    if (!host) return;
    host.innerHTML = '<li class="kb-list-title mono">' + esc(t("INDEX / 分类索引")) + '</li>' + CATEGORIES.map(function (cat) {
      return '<li><span class="legend-name"><span class="legend-dot" style="background:' + cat.color + '"></span>' +
        esc(t(cat.label)) + '</span><span class="legend-count">' +
        t("{n} " + cat.unit, { n: fmt(counts[cat.countKey]) }) + "</span></li>";
    }).join("");
  }

  function renderNews(items) {
    var host = byId("home-news");
    if (!host) return;
    if (!items.length) {
      host.innerHTML = '<div class="clipping"><p class="news-title">' +
        esc(isEn() ? "No news yet. Please check back later." : "暂无资讯，稍后再来。") + '</p></div>';
      return;
    }
    host.innerHTML = items.slice(0, 3).map(function (item) {
      // 英文模式：英文标题主行、中文标题副行；中文模式保持原样。
      var zh = item.title_zh || item.title || "";
      var en = item.title_en || "";
      var primary = isEn() ? (en || zh) : zh;
      var secondary = isEn() && en && zh && zh !== en ? zh : "";
      return '<a class="clipping" href="news.html">' +
        '<div class="news-meta"><span>' + esc(sourceLabel(item.source)) + '</span><span>' + esc(fmtDate(item.published_at)) + '</span></div>' +
        '<p class="news-title">' + esc(primary || t("（无标题）")) + '</p>' +
        (secondary ? '<p class="news-sub">' + esc(secondary) + '</p>' : '') +
        '<span class="news-en">READ CLIPPING →</span></a>';
    }).join("");
  }

  // ---------------- 线框球 ----------------
  var orb = { canvas: null, ctx: null, dpr: 1, w: 0, h: 0, rx: -0.35, ry: 0.6, drag: false, lx: 0, ly: 0, raf: 0, running: false };

  function setupOrb() {
    orb.canvas = byId("orb-canvas");
    if (!orb.canvas || !orb.canvas.getContext) return;
    orb.ctx = orb.canvas.getContext("2d");
    resizeOrb();
    bindOrb();
    startOrb();
  }

  function resizeOrb() {
    if (!orb.canvas) return;
    var rect = orb.canvas.parentElement.getBoundingClientRect();
    orb.dpr = Math.min(window.devicePixelRatio || 1, 2);
    orb.w = Math.max(rect.width, 200); orb.h = Math.max(rect.height, 160);
    orb.canvas.width = Math.floor(orb.w * orb.dpr);
    orb.canvas.height = Math.floor(orb.h * orb.dpr);
    orb.ctx.setTransform(orb.dpr, 0, 0, orb.dpr, 0, 0);
  }

  function projectSphere(lat, lon, radius) {
    var x = radius * Math.cos(lat) * Math.cos(lon);
    var y = radius * Math.sin(lat);
    var z = radius * Math.cos(lat) * Math.sin(lon);
    var cy = Math.cos(orb.ry), sy = Math.sin(orb.ry);
    var x1 = x * cy + z * sy;
    var z1 = -x * sy + z * cy;
    var cx = Math.cos(orb.rx), sx = Math.sin(orb.rx);
    var y1 = y * cx - z1 * sx;
    var z2 = y * sx + z1 * cx;
    var scale = 1 + z2 / (radius * 4);
    return { x: orb.w / 2 + x1 * scale, y: orb.h / 2 + y1 * scale, depth: z2 };
  }

  function drawOrb(now) {
    if (!orb.ctx) return;
    now = now || 0;
    var ctx = orb.ctx, w = orb.w, h = orb.h;
    ctx.clearRect(0, 0, w, h);
    var radius = Math.min(w, h) * 0.36;
    var cx0 = w / 2, cy0 = h / 2;

    ctx.save();
    ctx.strokeStyle = "rgba(244,236,221,.08)";
    ctx.beginPath(); ctx.arc(cx0, cy0, radius * 1.22, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([2, 6]);
    ctx.beginPath(); ctx.arc(cx0, cy0, radius * 1.42, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();

    // 外环卫星点：两颗沿虚线轨道反向环绕，带短尾迹
    var satAngle = now / 1300;
    for (var s = 0; s < 2; s++) {
      var sa = satAngle * (s === 0 ? 1 : -1) + s * Math.PI;
      var sx = cx0 + Math.cos(sa) * radius * 1.22;
      var sy = cy0 + Math.sin(sa) * radius * 1.22;
      ctx.strokeStyle = "rgba(217,162,39,.4)";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(cx0, cy0, radius * 1.22, sa - 0.55 * (s === 0 ? 1 : -1), sa, s === 0 ? false : true);
      ctx.stroke();
      ctx.fillStyle = "rgba(240,178,60,.95)";
      ctx.beginPath(); ctx.arc(sx, sy, 2.6, 0, Math.PI * 2); ctx.fill();
    }

    var lat, lon, i, pt, prev;
    for (lat = -Math.PI / 3; lat <= Math.PI / 3 + 0.01; lat += Math.PI / 6) {
      ctx.beginPath();
      for (i = 0; i <= 48; i++) {
        lon = (Math.PI * 2 * i) / 48;
        pt = projectSphere(lat, lon, radius);
        if (i === 0) ctx.moveTo(pt.x, pt.y); else ctx.lineTo(pt.x, pt.y);
      }
      ctx.strokeStyle = "rgba(217,162,39,.34)";
      ctx.lineWidth = 1; ctx.stroke();
    }
    for (i = 0; i < 12; i++) {
      lon = (Math.PI * 2 * i) / 12;
      ctx.beginPath();
      for (var j = 0; j <= 36; j++) {
        lat = -Math.PI / 2 + (Math.PI * j) / 36;
        pt = projectSphere(lat, lon, radius);
        if (j === 0) ctx.moveTo(pt.x, pt.y); else ctx.lineTo(pt.x, pt.y);
      }
      ctx.strokeStyle = "rgba(244,236,221,.20)";
      ctx.lineWidth = 1; ctx.stroke();
    }

    var nodes = [[0.2, 0.4], [1.2, 2.1], [2.6, 4.1], [3.6, 1.2], [4.8, 3.3], [5.6, 5.2]];
    var projected = nodes.map(function (pair) {
      return projectSphere(pair[0] - Math.PI / 2, pair[1], radius);
    });

    // 节点链路：流动虚线，表示语料 / 术语在知识网络中流动
    ctx.save();
    ctx.setLineDash([3, 5]);
    ctx.lineDashOffset = -(now / 45) % 8;
    for (i = 0; i < projected.length; i++) {
      var a = projected[i], b = projected[(i + 1) % projected.length];
      var depthAlpha = 0.18 + 0.3 * (((a.depth + b.depth) / (radius * 2) + 1) / 2);
      ctx.strokeStyle = "rgba(192,82,43," + depthAlpha.toFixed(2) + ")";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    ctx.restore();

    // 数据节点：呼吸式脉动（半径 + 亮度），背面节点自动变暗
    nodes.forEach(function (pair, ni) {
      pt = projected[ni];
      var depth01 = (pt.depth / radius + 1) / 2;
      var pulse = 0.5 + 0.5 * Math.sin(now / 320 + ni * 1.15);
      var r = 2.6 + pulse * 1.6 + depth01 * 0.8;
      var alpha = 0.35 + 0.45 * depth01 + pulse * 0.2;
      ctx.fillStyle = "rgba(192,82,43," + Math.min(alpha, 1).toFixed(2) + ")";
      ctx.beginPath(); ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2); ctx.fill();
      if (depth01 > 0.45) {
        ctx.strokeStyle = "rgba(240,178,60," + (0.25 + pulse * 0.35).toFixed(2) + ")";
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(pt.x, pt.y, r + 3 + pulse * 2.5, 0, Math.PI * 2); ctx.stroke();
      }
    });

    // 雷达扫描线：自上而下周期扫过球体（裁剪在球内）
    var sweepT = (now % 3400) / 3400;
    var sweepY = cy0 - radius * 1.05 + sweepT * radius * 2.1;
    ctx.save();
    ctx.beginPath(); ctx.arc(cx0, cy0, radius, 0, Math.PI * 2); ctx.clip();
    var grad = ctx.createLinearGradient(0, sweepY - 16, 0, sweepY + 2);
    grad.addColorStop(0, "rgba(217,162,39,0)");
    grad.addColorStop(1, "rgba(217,162,39,.3)");
    ctx.fillStyle = grad;
    ctx.fillRect(cx0 - radius, sweepY - 16, radius * 2, 18);
    ctx.restore();

    ctx.fillStyle = "rgba(244,236,221,.55)";
    ctx.font = '9px "Courier New", monospace';
    ctx.textAlign = "center";
    ctx.fillText("KB / " + fmt(graphData.terms || 0), cx0, orb.h - 10);
  }

  function bindOrb() {
    orb.canvas.addEventListener("pointerdown", function (e) {
      orb.drag = true; orb.lx = e.clientX; orb.ly = e.clientY;
      orb.canvas.setPointerCapture && orb.canvas.setPointerCapture(e.pointerId);
    });
    orb.canvas.addEventListener("pointermove", function (e) {
      if (!orb.drag) return;
      orb.ry += (e.clientX - orb.lx) * 0.008;
      orb.rx += (e.clientY - orb.ly) * 0.006;
      orb.rx = Math.max(-1.1, Math.min(1.1, orb.rx));
      orb.lx = e.clientX; orb.ly = e.clientY;
    });
    orb.canvas.addEventListener("pointerup", function () { orb.drag = false; });
    orb.canvas.addEventListener("pointercancel", function () { orb.drag = false; });
  }

  function orbLoop(now) {
    if (!orb.running) return;
    if (!orb.drag) { orb.ry += 0.006; }
    drawOrb(now);
    orb.raf = window.requestAnimationFrame(orbLoop);
  }
  // 2026-11-03：业主要求线框球常驻动画，不再按 prefers-reduced-motion 降级为静帧
  function startOrb() { drawOrb(); if (orb.running) return; orb.running = true; orb.raf = window.requestAnimationFrame(orbLoop); }
  function stopOrb() { orb.running = false; if (orb.raf) { window.cancelAnimationFrame(orb.raf); orb.raf = 0; } }

  // ---------------- 3D 卡片环 ----------------
  var ring = { rotation: 0, radius: 520, dragging: false, startX: 0, startRot: 0, moved: 0, cards: [], auto: true };

  function setupCarousel() {
    var stage = byId("carousel-stage");
    if (!stage) return;
    ring.cards = Array.prototype.slice.call(stage.querySelectorAll(".cap-card"));
    var w = window.innerWidth;
    ring.radius = w < 1100 ? 470 : 540;
    positionRing();
    if (isMobile()) return;
    var startAuto = function () { ring.auto = true; };
    stage.addEventListener("pointerdown", function (e) {
      ring.dragging = true; ring.startX = e.clientX; ring.startRot = ring.rotation; ring.moved = 0; ring.auto = false;
      stage.setPointerCapture && stage.setPointerCapture(e.pointerId);
    });
    stage.addEventListener("pointermove", function (e) {
      if (!ring.dragging) return;
      var dx = e.clientX - ring.startX;
      ring.moved = Math.max(ring.moved, Math.abs(dx));
      ring.rotation = ring.startRot + dx * 0.25;
      positionRing();
    });
    stage.addEventListener("pointerup", function () {
      if (!ring.dragging) return;
      ring.dragging = false;
      if (ring.moved < 6) { /* 交给 click 处理 */ }
      window.setTimeout(startAuto, 1200);
    });
    stage.addEventListener("pointercancel", function () { ring.dragging = false; });
    ring.cards.forEach(function (card) {
      card.addEventListener("click", function (e) {
        if (ring.moved > 8) { e.preventDefault(); e.stopPropagation(); ring.moved = 0; return; }
        if (card.tagName === "BUTTON" && window.App && window.App.openQa) {
          e.preventDefault(); window.App.openQa();
        }
      });
    });
    var prev = byId("car-prev"), next = byId("car-next");
    if (prev) prev.addEventListener("click", function () { ring.rotation += 60; positionRing(); });
    if (next) next.addEventListener("click", function () { ring.rotation -= 60; positionRing(); });
    window.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { ring.rotation += 60; positionRing(); }
      if (e.key === "ArrowRight") { ring.rotation -= 60; positionRing(); }
    });
    autoRotate();
  }

  function positionRing() {
    if (!ring.cards.length) return;
    var step = 360 / ring.cards.length;
    ring.cards.forEach(function (card, i) {
      var angle = step * i + ring.rotation;
      card.style.transform = "rotateY(" + angle + "deg) translateZ(" + ring.radius + "px)";
      card.style.opacity = "1";
    });
    var stage = byId("carousel-stage");
    if (stage) stage.style.transform = "rotateX(-6deg) rotateY(" + (0) + "deg)";
  }

  function autoRotate() {
    if (reduceMotion()) return;
    (function frame() {
      if (ring.auto && !ring.dragging) { ring.rotation -= 0.12; positionRing(); }
      window.requestAnimationFrame(frame);
    })();
  }

  // ---------------- 知识图 ----------------
  var graph = { canvas: null, ctx: null, dpr: 1, w: 0, h: 0, nodes: [], hover: -1, t: 0, raf: 0, running: false };
  var graphData = {};

  function setupGraph() {
    graph.canvas = byId("kb-canvas");
    if (!graph.canvas || !graph.canvas.getContext) return;
    graph.ctx = graph.canvas.getContext("2d");
    resizeGraph(); buildNodes();
    bindGraph(); startGraph();
  }

  function resizeGraph() {
    if (!graph.canvas) return;
    var wrap = graph.canvas.parentElement;
    graph.dpr = Math.min(window.devicePixelRatio || 1, 2);
    graph.w = Math.max(wrap.clientWidth, 260);
    graph.h = Math.max(wrap.clientHeight, 260);
    graph.canvas.width = Math.floor(graph.w * graph.dpr);
    graph.canvas.height = Math.floor(graph.h * graph.dpr);
    graph.ctx.setTransform(graph.dpr, 0, 0, graph.dpr, 0, 0);
  }

  function buildNodes() {
    graph.nodes = CATEGORIES.map(function (cat, i) {
      return { cat: cat, angle: (Math.PI * 2 / CATEGORIES.length) * i, x: 0, y: 0, r: 22 };
    });
  }

  function layoutNodes(t) {
    var cx = graph.w / 2, cy = graph.h / 2;
    var rx = Math.min(graph.w * 0.32, 240), ry = Math.min(graph.h * 0.30, 130);
    graph.nodes.forEach(function (n, i) {
      var a = n.angle + t * 0.18;
      n.x = cx + Math.cos(a) * rx;
      n.y = cy + Math.sin(a) * ry;
      n.scale = 0.75 + 0.25 * Math.sin(a);
    });
    graph.cx = cx; graph.cy = cy;
  }

  function drawGraph() {
    var ctx = graph.ctx;
    ctx.clearRect(0, 0, graph.w, graph.h);
    if (!graph.nodes.length) return;

    ctx.save();
    ctx.strokeStyle = "rgba(244,236,221,.10)";
    ctx.setLineDash([3, 8]);
    ctx.beginPath(); ctx.ellipse(graph.cx, graph.cy, Math.min(graph.w * 0.32, 240) * 1.1, Math.min(graph.h * 0.30, 130) * 1.1, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    graph.nodes.forEach(function (n, i) {
      var grad = ctx.createLinearGradient(graph.cx, graph.cy, n.x, n.y);
      grad.addColorStop(0, "rgba(244,236,221,.30)");
      grad.addColorStop(1, n.cat.color);
      ctx.strokeStyle = grad; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(graph.cx, graph.cy); ctx.lineTo(n.x, n.y); ctx.stroke();

      var next = graph.nodes[(i + 1) % graph.nodes.length];
      ctx.strokeStyle = "rgba(244,236,221,.10)";
      ctx.beginPath(); ctx.moveTo(n.x, n.y); ctx.lineTo(next.x, next.y); ctx.stroke();

      var t = (graph.t * 0.30 + i * 0.16) % 1;
      ctx.fillStyle = n.cat.color;
      ctx.globalAlpha = 0.35 + 0.5 * Math.sin(t * Math.PI);
      ctx.beginPath(); ctx.arc(graph.cx + (n.x - graph.cx) * t, graph.cy + (n.y - graph.cy) * t, 2, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
    });

    var pulse = (Math.sin(graph.t * 2) + 1) / 2;
    ctx.fillStyle = "rgba(217,162,39,.16)";
    ctx.beginPath(); ctx.arc(graph.cx, graph.cy, 46 + pulse * 6, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#17130F"; ctx.strokeStyle = "#D9A227"; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(graph.cx, graph.cy, 30, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#F4ECDD"; ctx.font = '10px "Courier New", monospace'; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("KB", graph.cx, graph.cy);

    graph.nodes.forEach(function (n, i) {
      var r = n.r * (n.scale || 1);
      ctx.fillStyle = "rgba(16,13,10,.95)";
      ctx.strokeStyle = n.cat.color; ctx.lineWidth = i === graph.hover ? 2.6 : 1.6;
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = n.cat.color;
      ctx.beginPath(); ctx.arc(n.x, n.y, 3, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#F4ECDD";
      ctx.font = '12px Georgia, "Songti SC", serif'; ctx.textAlign = "center";
      ctx.fillText(n.cat.label, n.x, n.y + r + 16);
      ctx.fillStyle = "rgba(244,236,221,.55)";
      ctx.font = '10px "Courier New", monospace';
      ctx.fillText(fmt(graphData[n.cat.countKey]), n.x, n.y + r + 30);
    });
  }

  function graphHit(px, py) {
    for (var i = graph.nodes.length - 1; i >= 0; i--) {
      var n = graph.nodes[i], dx = px - n.x, dy = py - n.y;
      var r = n.r * (n.scale || 1) + 12;
      if (dx * dx + dy * dy <= r * r) return i;
    }
    return -1;
  }

  function bindGraph() {
    graph.canvas.addEventListener("pointermove", function (e) {
      var rect = graph.canvas.getBoundingClientRect();
      var idx = graphHit(e.clientX - rect.left, e.clientY - rect.top);
      graph.hover = idx;
      var tip = byId("kb-tooltip");
      if (idx >= 0 && tip) {
        var n = graph.nodes[idx];
        tip.hidden = false;
        tip.textContent = n.cat.label + " · " + fmt(graphData[n.cat.countKey]) + " " + n.cat.unit;
        tip.style.left = Math.max(8, Math.min(e.clientX - rect.left - 40, graph.w - 150)) + "px";
        tip.style.top = Math.max(8, e.clientY - rect.top - 46) + "px";
        graph.canvas.style.cursor = n.cat.href ? "pointer" : "default";
      } else if (tip) {
        tip.hidden = true; graph.canvas.style.cursor = "default";
      }
    });
    graph.canvas.addEventListener("pointerleave", function () { graph.hover = -1; var tip = byId("kb-tooltip"); if (tip) tip.hidden = true; });
    graph.canvas.addEventListener("click", function (e) {
      var rect = graph.canvas.getBoundingClientRect();
      var idx = graphHit(e.clientX - rect.left, e.clientY - rect.top);
      if (idx >= 0 && graph.nodes[idx].cat.href) window.location.href = graph.nodes[idx].cat.href;
    });
  }

  function graphLoop(now) {
    if (!graph.running) return;
    graph.t = now / 1000;
    layoutNodes(graph.t);
    drawGraph();
    graph.raf = window.requestAnimationFrame(graphLoop);
  }
  function startGraph() { layoutNodes(0.6); drawGraph(); if (graph.running || reduceMotion()) return; graph.running = true; graph.raf = window.requestAnimationFrame(graphLoop); }
  function stopGraph() { graph.running = false; if (graph.raf) { window.cancelAnimationFrame(graph.raf); graph.raf = 0; } }

  // ---------------- 通用交互 ----------------
  function ticker() {
    var track = byId("ticker-track");
    if (track) track.innerHTML = track.innerHTML + track.innerHTML;
  }

  function preloader() {
    var host = byId("preloader");
    if (!host) return;
    var bar = byId("preloader-bar"), pct = 18;
    var timer = window.setInterval(function () {
      pct = Math.min(pct + Math.random() * 24, 90);
      if (bar) bar.style.width = pct + "%";
    }, 120);
    window.setTimeout(function () {
      window.clearInterval(timer);
      if (bar) bar.style.width = "100%";
      host.classList.add("is-done");
      window.setTimeout(function () { host.style.display = "none"; }, 620);
    }, 820);
  }

  function reveal() {
    var items = Array.prototype.slice.call(document.querySelectorAll(".hero-copy > *, .hero-panel, .section-head, .clipping, .kb-panel, .carousel"));
    items.forEach(function (el) { el.classList.add("reveal"); });
    if (!("IntersectionObserver" in window) || reduceMotion()) { items.forEach(function (el) { el.classList.add("is-in"); }); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) { if (entry.isIntersecting) { entry.target.classList.add("is-in"); io.unobserve(entry.target); } });
    }, { threshold: 0.12 });
    items.forEach(function (el) { io.observe(el); });
    window.setTimeout(function () { items.forEach(function (el) { el.classList.add("is-in"); }); }, 1200);
  }

  function init() {
    preloader(); ticker(); reveal();
    loadOverview();
    setupOrb(); setupCarousel(); setupGraph();
    window.addEventListener("resize", function () {
      resizeOrb(); drawOrb();
      resizeGraph(); layoutNodes(graph.t || 0.6); drawGraph();
      if (isMobile()) { positionRing(); }
    }, { passive: true });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { stopOrb(); stopGraph(); } else { startOrb(); startGraph(); }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
