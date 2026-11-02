// Copyright (C) 2025 Intel Corporation; SPDX-License-Identifier: Apache-2.0
// Concept graph view on the Retrieve tab: a pool's OKF concepts and their links
// (GET /v1/libraries/{lib}/asset_pools/{pool}/graph), laid out by a small force
// simulation and drawn on a <canvas> so a thousand-plus nodes stay smooth.
//
// After an `rrf` or `graph` retrieval the engine reports what graph search
// walked (RetrieveResult.graph_traces); the view then highlights the seeds, the
// concepts reached at each hop, the edges crossed, and the concepts whose
// chunks made it into the result.

const GraphView = (() => {
const stage = $("g-stage"), canvas = $("g-canvas"), ctx = canvas.getContext("2d");
const PALETTE = ["#4c8dff", "#2bd4a7", "#b48cff", "#ffb547", "#ff7aa8", "#5ad1e6", "#9bd35a", "#f08c5a", "#c9a0ff", "#7fd1b9"];
const HOP_COLORS = ["#ff9f43", "#ffd166", "#7bdff2", "#a0c4ff"];   // seed, hop 1, 2, 3+
const OVERRIDE_COLOR = "#e86bd6";
// Where a concept comes from (`origin` in the graph API).
const ORIGINS = { uploaded: "Uploaded bundle", generated: "Extracted from documents", both: "Uploaded override of an extracted concept" };

let G = null;            // {nodes, edges, byId, adj, labels, total, truncated, lib, pool}
let TRACES = {};         // pool id -> trace (from the last retrieval)
let T = null;            // trace applied to G: {seeds, hop, hits, walked}
let view = { k: 1, x: 0, y: 0 };   // screen = world * k + (x, y)
let alpha = 0, raf = 0, fitted = false;
let hover = null, selected = null, found = new Set();
let loadSeq = 0, loading = "";   // "lib|pool" being fetched
const cache = new Map(); // "lib|pool" -> raw graph response

// ---- pools with a graph source --------------------------------------------------
function graphPools(lib) {
  if (!lib) return [];
  const graphSources = new Set(lib.sources.filter(s => s.type === "graph").map(s => s.id));
  return lib.asset_pools.filter(p => p.source_statuses.some(st => graphSources.has(st.source_id)));
}
const libOf = (name) => LIBRARIES.find(l => l.name === name);
// Keep the picker in step with the Retrieve tab's library; prefer `want`.
function syncPools(want) {
  const lib = libOf($("q-library").value), pools = graphPools(lib), sel = $("g-pool");
  const cur = want || sel.value;
  sel.innerHTML = pools.map(p => `<option value="${esc(p.id)}">${esc(p.name || p.id)}</option>`).join("");
  if (pools.some(p => p.id === cur)) sel.value = cur;
  const pool = sel.value;
  if (!lib || !pool) { G = null; setMsg(lib ? t("No asset pool in this library has a graph source.") : t("Create or select an asset library first")); renderInfo(); renderLegend(); draw(); return; }
  if ((!G || G.lib !== lib.name || G.pool !== pool) && loading !== lib.name + "|" + pool) load(lib.name, pool);
}
// A graph source that finished syncing has a new graph: drop the cached copy
// and reload it if it is the one shown.
const seen = new Map();  // "lib|pool" -> graph sources' status signature
function noteStatuses() {
  for (const lib of LIBRARIES) {
    const graphSources = new Set(lib.sources.filter(s => s.type === "graph").map(s => s.id));
    for (const p of lib.asset_pools) {
      const key = lib.name + "|" + p.id;
      const sig = JSON.stringify(p.source_statuses.filter(st => graphSources.has(st.source_id))
        .map(st => [st.source_id, SourceStatus.source(st), st.indexed_revision, st.updated_at, st.extraction?.outdated, st.extraction?.last?.finished_at]));
      const before = seen.get(key); seen.set(key, sig);
      if (before === undefined || before === sig) continue;
      cache.delete(key);
      if (G && G.lib === lib.name && G.pool === p.id) load(lib.name, p.id, true);
    }
  }
  if ($("q-library").value) syncPools();
}
$("g-pool").addEventListener("change", () => load($("q-library").value, $("g-pool").value));
$("g-reload").addEventListener("click", () => load($("q-library").value, $("g-pool").value, true));

function setMsg(m) { $("g-msg").textContent = m || ""; }

// ---- loading + model ------------------------------------------------------------
async function load(lib, pool, force = false) {
  if (!lib || !pool) return;
  const key = lib + "|" + pool, seq = ++loadSeq;
  let data = !force && cache.get(key);
  if (!data) {
    G = null; draw(); setMsg(t("Loading graph…")); loading = key;
    try { data = await api("GET", `/v1/libraries/${enc(lib)}/asset_pools/${enc(pool)}/graph`); }
    catch (err) { if (seq === loadSeq) { loading = ""; setMsg(err.message); renderInfo(); renderLegend(); } return; }
    cache.set(key, data);
  }
  if (seq !== loadSeq) return;
  loading = "";
  build(lib, pool, data);
}
function build(lib, pool, data) {
  const byId = new Map(), adj = new Map(), labels = new Map();
  const nodes = data.nodes.map((n, i) => {
    // Phyllotaxis start: deterministic, evenly spread, no overlaps.
    const r = 12 * Math.sqrt(i + 1), a = i * 2.39996;
    const node = { ...n, x: r * Math.cos(a), y: r * Math.sin(a), vx: 0, vy: 0, r: 3.5 + Math.min(9, Math.sqrt(n.degree) * 1.4) };
    byId.set(n.id, node); adj.set(n.id, []);
    labels.set(n.label, (labels.get(n.label) || 0) + 1);
    return node;
  });
  const edges = [];
  for (const e of data.edges) {
    const s = byId.get(e.source), tg = byId.get(e.target);
    if (!s || !tg) continue;
    edges.push({ s, t: tg, relation: e.relation });
    adj.get(s.id).push({ id: tg.id, relation: e.relation });
    adj.get(tg.id).push({ id: s.id, relation: e.relation });
  }
  const order = [...labels.entries()].sort((a, b) => b[1] - a[1]).map(([l]) => l);
  G = { nodes, edges, byId, adj, labels: order, total: data.total, truncated: data.truncated, lib, pool };
  selected = hover = null; found = new Set(); fitted = false;
  const current = libOf(lib)?.asset_pools.find(item => item.id === pool);
  const states = (current?.source_statuses || []).filter(status => status.extraction);
  const state = states.length ? SourceStatus.pool({source_statuses: states}) : "ready";
  setMsg(nodes.length ? "" : state !== "ready" ? t(SourceStatus.appearance(state).label)
    : t("This pool's graph has no concepts yet. Ingest an OKF bundle into it."));
  applyTrace(); renderLegend(); renderInfo();
  reheat(1);
}
const colorOf = (label) => PALETTE[Math.max(0, G.labels.indexOf(label)) % PALETTE.length];

// ---- traces -----------------------------------------------------------------------
// `traces` from a retrieval; switch to a traced pool if the shown one has none.
function showTraces(traces, preferPool) {
  TRACES = {};
  for (const tr of traces || []) TRACES[tr.asset_pool_id] = tr;
  const pools = Object.keys(TRACES);
  const target = TRACES[preferPool] ? preferPool : TRACES[$("g-pool").value] ? $("g-pool").value : pools[0];
  if (target && target !== $("g-pool").value) { syncPools(target); return; }
  applyTrace(); renderLegend(); renderInfo(); draw();
}
function clearTraces() { TRACES = {}; applyTrace(); renderLegend(); renderInfo(); draw(); }
function applyTrace() {
  const tr = G && TRACES[G.pool];
  if (!tr) { T = null; return; }
  const hop = new Map(), hits = new Map(), walked = new Set();
  tr.concepts.forEach(c => { hop.set(c.id, c.hop); if (c.hit_chunk_ids.length) hits.set(c.id, c.hit_chunk_ids); });
  tr.edges.forEach(e => { walked.add(e.source + "\u0000" + e.target); walked.add(e.target + "\u0000" + e.source); });
  T = { seeds: new Set(tr.seeds), hop, hits, walked };
  // Pull the walk into view once the layout has settled.
  if (fitted) fit(true);
}
const inTrace = (n) => !T || T.hop.has(n.id);

// ---- force layout -------------------------------------------------------------------
const K = 34, CELL = 90;
function tick() {
  const nodes = G.nodes, n = nodes.length;
  // Repulsion between nearby nodes, bucketed on a grid (cheap, local).
  const grid = new Map();
  for (const a of nodes) {
    const key = Math.floor(a.x / CELL) + "," + Math.floor(a.y / CELL);
    (grid.get(key) || grid.set(key, []).get(key)).push(a);
  }
  for (const [key, cell] of grid) {
    const [cx, cy] = key.split(",").map(Number);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      const other = grid.get((cx + dx) + "," + (cy + dy)); if (!other) continue;
      // Every ordered pair is visited once (from a's cell), so push `a` only.
      for (const a of cell) for (const b of other) {
        if (a === b) continue;
        let x = a.x - b.x, y = a.y - b.y, d2 = x * x + y * y;
        if (d2 < 0.01) { x = Math.random() - 0.5; y = Math.random() - 0.5; d2 = 0.5; }
        const f = (K * K) / d2 * 0.05;
        a.vx += x * f; a.vy += y * f;
      }
    }
  }
  // Springs along edges.
  for (const e of G.edges) {
    const x = e.t.x - e.s.x, y = e.t.y - e.s.y, d = Math.sqrt(x * x + y * y) || 1;
    const f = (d - K * 1.3) / d * 0.06;
    e.s.vx += x * f; e.s.vy += y * f; e.t.vx -= x * f; e.t.vy -= y * f;
  }
  // Gravity keeps components (and loners) together; then integrate.
  const g = n > 300 ? 0.012 : 0.02;
  for (const a of nodes) {
    if (a.fixed) { a.vx = a.vy = 0; continue; }
    a.vx = (a.vx - a.x * g) * 0.55; a.vy = (a.vy - a.y * g) * 0.55;
    const step = Math.min(18, Math.hypot(a.vx, a.vy)) / (Math.hypot(a.vx, a.vy) || 1);
    a.x += a.vx * step * alpha; a.y += a.vy * step * alpha;
  }
}
function reheat(a) {
  alpha = Math.max(alpha, a);
  if (!raf) raf = requestAnimationFrame(frame);
}
function frame() {
  raf = 0;
  if (G && G.nodes.length && alpha > 0.02) {
    const start = performance.now();
    do { tick(); alpha *= 0.985; } while (alpha > 0.02 && performance.now() - start < 12);
    // Follow the layout while it spreads out, then leave the view to the user.
    if (!fitted) { fit(); if (alpha < 0.3) { fitted = true; if (T) fit(true); } }
  }
  draw();
  if (G && alpha > 0.02) raf = requestAnimationFrame(frame);
}

// ---- view ---------------------------------------------------------------------------
function resize() {
  const r = stage.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, r.width * dpr); canvas.height = Math.max(1, r.height * dpr);
  draw();
}
new ResizeObserver(resize).observe(stage);
// Fit everything, or (onlyTrace) the traversed part.
function fit(onlyTrace = false) {
  if (!G || !G.nodes.length) return;
  let pts = G.nodes;
  if (onlyTrace && T) { const sub = G.nodes.filter(n => T.hop.has(n.id)); if (sub.length) pts = sub; }
  const xs = pts.map(n => n.x), ys = pts.map(n => n.y);
  const minX = Math.min(...xs) - 30, maxX = Math.max(...xs) + 30, minY = Math.min(...ys) - 30, maxY = Math.max(...ys) + 30;
  const r = stage.getBoundingClientRect();
  view.k = Math.max(0.05, Math.min(3, Math.min(r.width / (maxX - minX), r.height / (maxY - minY))));
  view.x = r.width / 2 - view.k * (minX + maxX) / 2; view.y = r.height / 2 - view.k * (minY + maxY) / 2;
  draw();
}
$("g-fit").addEventListener("click", () => fit(!!T));
const toWorld = (sx, sy) => ({ x: (sx - view.x) / view.k, y: (sy - view.y) / view.k });
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function draw() {
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!G) return;
  const k = view.k, only = $("g-only").checked && T;
  const text = css("--text"), muted = css("--muted"), bg = css("--bg"), hit = css("--accent2");
  ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * view.x, dpr * view.y);
  const visible = (n) => !only || T.hop.has(n.id);
  const focus = selected ? new Set([selected.id, ...G.adj.get(selected.id).map(x => x.id)]) : null;

  // Edges: everything faint, then the walked ones on top.
  ctx.lineWidth = 1 / k;
  ctx.strokeStyle = muted; ctx.globalAlpha = T ? 0.08 : 0.3;
  ctx.beginPath();
  for (const e of G.edges) {
    if (!visible(e.s) || !visible(e.t)) continue;
    ctx.moveTo(e.s.x, e.s.y); ctx.lineTo(e.t.x, e.t.y);
  }
  ctx.stroke();
  if (focus) {
    ctx.globalAlpha = 0.85; ctx.strokeStyle = css("--accent"); ctx.lineWidth = 1.6 / k; ctx.beginPath();
    for (const nb of G.adj.get(selected.id)) { const o = G.byId.get(nb.id); ctx.moveTo(selected.x, selected.y); ctx.lineTo(o.x, o.y); }
    ctx.stroke();
  }
  if (T) {
    ctx.globalAlpha = 0.95; ctx.lineWidth = 2.4 / k; ctx.strokeStyle = HOP_COLORS[0]; ctx.beginPath();
    for (const e of G.edges) if (T.walked.has(e.s.id + "\u0000" + e.t.id)) { ctx.moveTo(e.s.x, e.s.y); ctx.lineTo(e.t.x, e.t.y); }
    ctx.stroke();
  }

  // Nodes.
  for (const n of G.nodes) {
    if (!visible(n)) continue;
    const r = Math.max(n.r, 2.2 / k);
    let fill = colorOf(n.label), a = 1;
    if (T) {
      if (T.hop.has(n.id)) fill = HOP_COLORS[Math.min(T.hop.get(n.id), HOP_COLORS.length - 1)];
      else a = 0.13;
    }
    if (focus && !focus.has(n.id)) a = Math.min(a, 0.25);
    if (found.size && !found.has(n.id)) a = Math.min(a, 0.2);
    ctx.globalAlpha = a; ctx.fillStyle = fill;
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fill();
    ctx.lineWidth = 1.2 / k; ctx.strokeStyle = bg; ctx.stroke();
    if (n.origin === "both") {   // an uploaded concept overriding an extracted one
      ctx.save(); ctx.globalAlpha = Math.max(a, 0.35); ctx.strokeStyle = OVERRIDE_COLOR; ctx.lineWidth = 1.6 / k;
      ctx.setLineDash([3 / k, 2 / k]); ctx.beginPath(); ctx.arc(n.x, n.y, r + 2.5 / k, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    }
    if (T && T.hits.has(n.id)) { ctx.globalAlpha = 1; ctx.strokeStyle = hit; ctx.lineWidth = 3 / k; ctx.beginPath(); ctx.arc(n.x, n.y, r + 3.5 / k, 0, Math.PI * 2); ctx.stroke(); }
    if (T && T.seeds.has(n.id)) { ctx.globalAlpha = 1; ctx.strokeStyle = HOP_COLORS[0]; ctx.lineWidth = 2 / k; ctx.beginPath(); ctx.arc(n.x, n.y, r + 7 / k, 0, Math.PI * 2); ctx.stroke(); }
    if (n === selected || n === hover) { ctx.globalAlpha = 1; ctx.strokeStyle = text; ctx.lineWidth = 2 / k; ctx.beginPath(); ctx.arc(n.x, n.y, r + 2 / k, 0, Math.PI * 2); ctx.stroke(); }
  }

  // Labels: the interesting nodes always; everything once zoomed in.
  ctx.globalAlpha = 1;
  ctx.font = `${12 / k}px system-ui, sans-serif`; ctx.textBaseline = "middle";
  const r = stage.getBoundingClientRect(), tl = toWorld(0, 0), br = toWorld(r.width, r.height);
  let budget = 250;
  for (const n of G.nodes) {
    if (!visible(n) || n.x < tl.x || n.x > br.x || n.y < tl.y || n.y > br.y) continue;
    const important = n === selected || n === hover || found.has(n.id) || (T && (T.seeds.has(n.id) || T.hits.has(n.id))) || (focus && focus.has(n.id));
    if (!important && (k < 1.4 || --budget < 0)) continue;
    const label = n.title.length > 40 ? n.title.slice(0, 39) + "…" : n.title;
    ctx.lineWidth = 3 / k; ctx.strokeStyle = bg; ctx.strokeText(label, n.x + n.r + 4 / k, n.y);
    ctx.fillStyle = important ? text : muted; ctx.fillText(label, n.x + n.r + 4 / k, n.y);
  }
}

// ---- interaction ------------------------------------------------------------------
function nodeAt(sx, sy) {
  if (!G) return null;
  const p = toWorld(sx, sy), only = $("g-only").checked && T;
  let best = null, bestD = Infinity;
  for (const n of G.nodes) {
    if (only && !T.hop.has(n.id)) continue;
    const d = Math.hypot(n.x - p.x, n.y - p.y), r = Math.max(n.r, 2.2 / view.k) + 4 / view.k;
    if (d < r && d < bestD) { best = n; bestD = d; }
  }
  return best;
}
const local = (e) => { const r = stage.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
let drag = null;
stage.addEventListener("pointerdown", e => {
  if (!G) return;
  const [sx, sy] = local(e), n = nodeAt(sx, sy);
  drag = { sx, sy, vx: view.x, vy: view.y, node: n, moved: false };
  stage.setPointerCapture(e.pointerId);
  if (!n) stage.classList.add("panning");
});
stage.addEventListener("pointermove", e => {
  const [sx, sy] = local(e);
  if (!drag) {
    const n = nodeAt(sx, sy);
    if (n !== hover) { hover = n; draw(); }
    const tip = $("g-tip");
    if (n) {
      const hop = T && T.hop.get(n.id);
      tip.innerHTML = `<b>${esc(n.title)}</b><div class="mono">${esc(n.label)} · ${esc(t("{n} link(s)", { n: n.degree }))}`
        + `${hop != null ? " · " + esc(hop === 0 ? t("seed") : t("hop {n}", { n: hop })) : ""}</div>`;
      tip.style.display = "block";
      tip.style.left = Math.min(sx + 14, stage.clientWidth - 290) + "px"; tip.style.top = (sy + 14) + "px";
    } else tip.style.display = "none";
    return;
  }
  if (Math.hypot(sx - drag.sx, sy - drag.sy) > 3) drag.moved = true;
  if (drag.node) {
    const p = toWorld(sx, sy); drag.node.x = p.x; drag.node.y = p.y; drag.node.fixed = true; reheat(0.25);
  } else { view.x = drag.vx + sx - drag.sx; view.y = drag.vy + sy - drag.sy; draw(); }
});
stage.addEventListener("pointerup", () => {
  if (!drag) return;
  const d = drag; drag = null; stage.classList.remove("panning");
  if (d.node) d.node.fixed = false;
  if (!d.moved) { selected = d.node; renderInfo(); draw(); }
});
stage.addEventListener("pointerleave", () => { $("g-tip").style.display = "none"; if (hover) { hover = null; draw(); } });
stage.addEventListener("wheel", e => {
  if (!G) return;
  e.preventDefault();
  const [sx, sy] = local(e), before = toWorld(sx, sy);
  view.k = Math.max(0.05, Math.min(6, view.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
  view.x = sx - before.x * view.k; view.y = sy - before.y * view.k;
  draw();
}, { passive: false });
$("g-only").addEventListener("change", draw);
$("g-find").addEventListener("input", e => {
  const q = e.target.value.trim().toLowerCase();
  found = new Set(q && G ? G.nodes.filter(n => n.title.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)).map(n => n.id) : []);
  draw();
});
$("g-find").addEventListener("keydown", e => {
  if (e.key === "Enter" && found.size) focus(G.pool, [...found][0]);
});
// Center on a concept and select it (from the results' "via" chips).
function focus(pool, id) {
  if (!G || G.pool !== pool) { syncPools(pool); return; }
  const n = G.byId.get(id); if (!n) return;
  selected = n;
  const r = stage.getBoundingClientRect();
  view.k = Math.max(view.k, 1.2);
  view.x = r.width / 2 - n.x * view.k; view.y = r.height / 2 - n.y * view.k;
  renderInfo(); draw();
  stage.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function titleOf(pool, id) {
  const n = G && G.pool === pool && G.byId.get(id);
  return n ? n.title : id;
}

// ---- side panels ------------------------------------------------------------------
function renderLegend() {
  const el = $("g-legend");
  if (!G) { el.innerHTML = ""; return; }
  const parts = G.labels.slice(0, 6).map(l => `<span><i style="background:${colorOf(l)}"></i>${esc(l || "—")}</span>`);
  if (T) parts.unshift(
    `<span><i style="background:${HOP_COLORS[0]}"></i>${esc(t("seed"))}</span>`,
    `<span><i style="background:${HOP_COLORS[1]}"></i>${esc(t("hop {n}", { n: 1 }))}</span>`,
    `<span><i style="background:${HOP_COLORS[2]}"></i>${esc(t("hop {n}", { n: "2+" }))}</span>`,
    `<span><i class="ring"></i>${esc(t("in results"))}</span>`);
  if (G.nodes.some(n => n.origin === "both")) parts.push(`<span><i class="ring dashed" style="border-color:${OVERRIDE_COLOR}"></i>${esc(t("uploaded override"))}</span>`);
  parts.push(`<span>${esc(G.truncated ? t("{n} of {total} concepts", { n: G.nodes.length, total: G.total }) : t("{n} concepts", { n: G.nodes.length }))} · ${esc(t("{n} links", { n: G.edges.length }))}</span>`);
  el.innerHTML = parts.join("");
}
function renderInfo() {
  const el = $("g-info");
  if (!G) { el.innerHTML = ""; return; }
  if (!selected) {
    el.innerHTML = T
      ? `<span class="hint">${esc(t("Last retrieval: {s} seed(s), {r} concept(s) reached, {h} contributed result chunks. Click a node for details.", { s: T.seeds.size, r: T.hop.size, h: T.hits.size }))}</span>`
      : `<span class="hint">${esc(t("Run an RRF or Graph retrieval to highlight the concepts it walked. Click a node for details."))}</span>`;
    return;
  }
  const n = selected, hop = T && T.hop.get(n.id), hits = T && T.hits.get(n.id);
  const nbrs = G.adj.get(n.id);
  el.innerHTML = `<div><b>${esc(n.title)}</b> <span class="chip" style="color:${colorOf(n.label)}">${esc(n.label || "—")}</span>
      ${hop != null ? `<span class="chip warn">${esc(hop === 0 ? t("seed") : t("hop {n}", { n: hop }))}</span>` : ""}
      ${hits ? `<span class="chip ok">${esc(t("{n} result chunk(s)", { n: hits.length }))}</span>` : ""}
      ${ORIGINS[n.origin] ? `<span class="chip" ${n.origin === "both" ? `style="color:${OVERRIDE_COLOR}"` : ""}>${esc(t(ORIGINS[n.origin]))}</span>` : ""}</div>
    <div class="mono">${esc(n.id)}</div>
    <div class="nbrs">${nbrs.slice(0, 40).map(x => `<button class="ghost mini" data-g-node="${esc(x.id)}" title="${esc(x.relation)}">${esc(G.byId.get(x.id).title)}</button>`).join("")}
      ${nbrs.length > 40 ? `<span class="hint">+${nbrs.length - 40}</span>` : ""}</div>`;
}
$("g-info").addEventListener("click", e => {
  const b = e.target.closest("[data-g-node]"); if (b) focus(G.pool, b.dataset.gNode);
});

return { syncPools, noteStatuses, showTraces, clearTraces, focus, titleOf, redraw() { renderLegend(); renderInfo(); draw(); } };
})();
