// Copyright (C) 2025 Intel Corporation; SPDX-License-Identifier: Apache-2.0
// Canvas view: an inventory of the scoped library's assets, pools and sources
// on the left, a stage they are dragged onto in the middle, and an inspector for
// the selection on the right.
//
// Links are the library's relationships, not something the canvas owns:
//   asset ──▶ pool    the asset is a member of the pool
//   pool  ──▶ source  the pool indexes into the source
// Drawing one calls the API; the canvas then re-reads the library. Only node
// positions are canvas state, kept per library in localStorage. Drafts (a new
// pool, source or upload not yet created) live in memory until committed.

(() => {
const NODE_W = 210, PORT_Y = 21;
const STAGE_W = 3200, STAGE_H = 2200;
const COL_X = { asset: 60, pool: 500, source: 940 };
const ROW_H = { asset: 70, pool: 92, source: 84 };
const MAX_AUTO_ASSETS = 300;     // "Place all" stops here; the rest stay in the inventory
const INV_LIMIT = 200;

let scale = 1;
let LAYOUT = {};       // node key -> {x, y}
let DRAFTS = {};       // "draft:<n>" -> {kind: "pool"|"source"|"upload", ...fields}
let draftSeq = 0;
let SEL = null;        // {type: "node", key} | {type: "edge", from, to}
let layoutLib = null;  // id of the library LAYOUT belongs to

const wrap = $("cv-wrap"), stage = $("cv-stage"), nodesEl = $("cv-nodes"), edgesEl = $("cv-edges"), insp = $("insp");
const visible = () => document.querySelector('[data-panel="canvas"]').classList.contains("on");

// ---- model --------------------------------------------------------------------
const keyOf = (kind, id) => `${kind}:${id}`;
function splitKey(key) { const i = key.indexOf(":"); return [key.slice(0, i), key.slice(i + 1)]; }
// What a node key stands for: {kind, obj} where kind is asset|pool|source, or a
// draft ({kind, draft: true, obj: the draft}). Null when it no longer exists.
function entity(key) {
  const [kind, id] = splitKey(key), lib = scoped();
  if (kind === "draft") return DRAFTS[key] ? { kind: DRAFTS[key].kind, draft: true, obj: DRAFTS[key] } : null;
  if (!lib) return null;
  const obj = kind === "asset" ? ASSETS.find(a => a.id === id)
    : kind === "pool" ? lib.asset_pools.find(p => p.id === id)
    : kind === "source" ? lib.sources.find(s => s.id === id) : null;
  return obj ? { kind, draft: false, obj } : null;
}
const placed = (key) => key in LAYOUT;
const storeKey = (lib) => `die.canvas.${lib.id}`;

function loadLayout() {
  const lib = scoped();
  layoutLib = lib ? lib.id : null; DRAFTS = {}; SEL = null; LAYOUT = {};
  if (!lib) return;
  const saved = JSON.parse(localStorage.getItem(storeKey(lib)) || "null");
  if (saved) LAYOUT = saved;
  else {
    // First visit: pools and sources are few, so start with them on the stage;
    // assets too when there are not many.
    lib.asset_pools.forEach(p => (LAYOUT[keyOf("pool", p.id)] = { x: 0, y: 0 }));
    lib.sources.forEach(s => (LAYOUT[keyOf("source", s.id)] = { x: 0, y: 0 }));
    if (ASSETS.length <= 40) ASSETS.forEach(a => (LAYOUT[keyOf("asset", a.id)] = { x: 0, y: 0 }));
    autoLayout(false);
  }
}
function saveLayout() {
  const lib = scoped(); if (!lib) return;
  const keep = {};
  for (const k in LAYOUT) if (!k.startsWith("draft:")) keep[k] = LAYOUT[k];
  localStorage.setItem(storeKey(lib), JSON.stringify(keep));
}
// Drop positions for things that are gone (deleted elsewhere, or a draft committed).
function prune() {
  let changed = false;
  const lib = scoped(), known = new Set(attachableSources(lib).map(source => source.id));
  for (const draft of Object.values(DRAFTS)) {
    if (draft.kind === "pool") draft.sources = draft.sources.filter(id => known.has(id));
    if (draft.attachTo && !lib?.asset_pools.some(pool => pool.id === draft.attachTo)) draft.attachTo = null;
  }
  for (const k of Object.keys(LAYOUT)) {
    if (entity(k)) continue;
    const [kind, id] = splitKey(k);
    if (kind === "asset" && WATCHED.has(id)) continue;   // still being ingested
    delete LAYOUT[k]; changed = true;
  }
  if (SEL && SEL.type === "node" && !entity(SEL.key)) SEL = null;
  if (SEL && SEL.type === "edge" && !(entity(SEL.from) && entity(SEL.to))) SEL = null;
  if (changed) saveLayout();
}

// Every relationship between two placed nodes.
function edges() {
  const lib = scoped(); if (!lib) return [];
  const out = [];
  // Every pool keeps its content in the library's content source: a fixed link.
  const ck = lib.default_content_source_id && keyOf("source", lib.default_content_source_id);
  const contentLink = (pk) => ck && placed(ck) && out.push({ from: pk, to: ck, cls: "pool-source content", content: true });
  for (const p of lib.asset_pools) {
    const pk = keyOf("pool", p.id);
    if (!placed(pk)) continue;
    contentLink(pk);
    for (const id of p.asset_ids) { const ak = keyOf("asset", id); if (placed(ak)) out.push({ from: ak, to: pk, cls: "asset-pool" }); }
    for (const st of p.source_statuses) {
      const sk = keyOf("source", st.source_id);
      if (sk === ck) continue;
      const {cls} = SourceStatus.appearance(SourceStatus.source(st));
  const frozen = !SourceServing.polling(st);
  if (placed(sk)) out.push({ from: pk, to: sk, cls: "pool-source " + (frozen ? "frozen" : cls === "bad" ? "failed" : cls === "warn" ? "pending" : "") });
    }
  }
  for (const [dk, d] of Object.entries(DRAFTS)) {
    if (!placed(dk)) continue;
    if (d.kind === "pool") {
      contentLink(dk);
      d.assets.forEach(id => placed(keyOf("asset", id)) && out.push({ from: keyOf("asset", id), to: dk, cls: "asset-pool pending" }));
      d.sources.forEach(id => placed(keyOf("source", id)) && out.push({ from: dk, to: keyOf("source", id), cls: "pool-source pending" }));
    }
    if (d.kind === "upload") d.pools.forEach(id => placed(keyOf("pool", id)) && out.push({ from: dk, to: keyOf("pool", id), cls: "asset-pool pending" }));
  }
  return out;
}

// ---- layout helpers -----------------------------------------------------------
function freeSpot(x, y) {
  const taken = Object.values(LAYOUT);
  while (taken.some(p => Math.abs(p.x - x) < NODE_W - 20 && Math.abs(p.y - y) < 60)) y += 70;
  return { x: Math.max(10, Math.min(STAGE_W - NODE_W - 10, x)), y: Math.max(10, Math.min(STAGE_H - 80, y)) };
}
function place(key, x, y, exact = false) {
  LAYOUT[key] = exact ? { x: Math.max(0, x), y: Math.max(0, y) } : freeSpot(x, y);
  saveLayout();
}
// Put `key` beside `anchor`: assets to its left, sources to its right.
function placeNear(key, anchorKey) {
  if (placed(key)) return;
  const a = LAYOUT[anchorKey] || { x: COL_X.pool, y: 60 };
  const kind = (entity(key) || {}).kind;
  const dx = kind === "source" ? 440 : kind === "pool" ? (entity(anchorKey)?.kind === "source" ? -440 : 440) : -440;
  place(key, a.x + dx, a.y);
}
function kindOfKey(key) { const e = entity(key); return e ? (e.kind === "upload" ? "asset" : e.kind) : "asset"; }
// Columns by kind, ordered so links cross as little as is cheap to arrange:
// pools by id, then assets and sources in the order of the first pool using them.
function autoLayout(save = true) {
  const lib = scoped(); if (!lib) return;
  const cols = { asset: [], pool: [], source: [] };
  for (const k of Object.keys(LAYOUT)) cols[kindOfKey(k)].push(k);
  const poolOrder = new Map(lib.asset_pools.map((p, i) => [p.id, i]));
  const rank = (k) => {
    const [kind, id] = splitKey(k);
    if (kind === "pool") return poolOrder.get(id) ?? 1e6;
    let best = 1e6;
    for (const p of lib.asset_pools) {
      const hit = kind === "asset" ? p.asset_ids.includes(id) : p.source_statuses.some(s => s.source_id === id);
      if (hit) best = Math.min(best, poolOrder.get(p.id));
    }
    return kind === "draft" ? 2e6 : best;
  };
  for (const [kind, keys] of Object.entries(cols)) {
    keys.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
    // Center the shorter columns against the tallest one.
    const tallest = Math.max(...Object.entries(cols).map(([k, v]) => v.length * ROW_H[k]));
    const top = 50 + Math.max(0, (tallest - keys.length * ROW_H[kind]) / 2);
    keys.forEach((k, i) => (LAYOUT[k] = { x: COL_X[kind], y: top + i * ROW_H[kind] }));
  }
  if (save) saveLayout();
}

// ---- rendering ----------------------------------------------------------------
const GLYPH = { asset: "▤", pool: "◎", source: "⛁", upload: "⇪" };
function poolHealth(p) {
  return SourceStatus.appearance(SourceStatus.pool(p)).cls;
}
function nodeView(key, e) {
  const lib = scoped(), o = e.obj;
  if (e.draft) {
    if (e.kind === "pool") return { title: o.name || o.id || t("New asset pool"), sub: t("unsaved · edit on the right"), inP: true, outP: true };
    if (e.kind === "source") return { title: o.name || t("New source"), sub: t("unsaved · edit on the right"), inP: true };
    return { title: t("Upload assets"), sub: t("{n} file(s) staged", { n: o.uploader.items.length }) + (o.pools.length ? " · " + t("{n} pool(s)", { n: o.pools.length }) : ""), outP: true };
  }
  if (e.kind === "asset") {
    const phase = o.materialization || (WATCHED.has(o.id) ? "materializing" : "");
    const pools = lib.asset_pools.filter(p => p.asset_ids.includes(o.id)).length;
    return { title: assetName(o), outP: true,
      sub: `${esc(o.kind)} · ${esc(t("{n} pool(s)", { n: pools }))}${phase && phase !== "ready" ? ` <span class="phase ${esc(phase)}">${esc(phaseLabel(phase))}</span>` : ""}`, html: true };
  }
  if (e.kind === "pool") {
    const h = poolHealth(o);
    return { title: o.name || o.id, inP: true, outP: true, html: true,
      sub: `${h ? `<span class="dot ${h}"></span> ` : ""}${esc(t(SourceStatus.appearance(SourceStatus.pool(o)).label))} · ${esc(t("{n} asset(s)", { n: o.asset_ids.length }))} · ${esc(t("{n} source(s)", { n: o.source_statuses.length }))}` };
  }
  const isContent = o.id === lib.default_content_source_id;
  const bindings = lib.asset_pools.flatMap(pool => pool.source_statuses.filter(status => status.source_id === o.id));
  const readiness = bindings.length ? poolStatusChip({source_statuses: bindings}) : "";
  return { title: o.name || o.id, inP: true, html: true,
    sub: `<span class="chip">${esc(o.type)}</span>${readiness}${isContent ? `<span class="chip">${esc(t("content"))}</span>` : ""}${o.reconciled ? "" : `<span class="chip bad">${esc(t("unreconciled"))}</span>`}</div>`
      + `<div class="ln" title="${esc(o.database_id)}/${esc(o.collection_name)}">${esc(o.database_id)}/${esc(o.collection_name)}` };
}
function renderNodes() {
  const lib = scoped();
  if (lib && lib.id !== layoutLib) loadLayout();
  if (!lib && layoutLib) loadLayout();
  prune();
  const html = [];
  for (const [key, pos] of Object.entries(LAYOUT)) {
    const e = entity(key); if (!e) continue;
    const v = nodeView(key, e);
    const sel = SEL && SEL.type === "node" && SEL.key === key;
    html.push(`<div class="node ${e.kind === "upload" ? "asset" : e.kind}${e.draft ? " draft" : ""}${sel ? " sel" : ""}" data-key="${esc(key)}" style="left:${pos.x}px;top:${pos.y}px">
      ${v.inP ? '<span class="port in"></span>' : ""}${v.outP ? `<span class="port out" title="${esc(t("Drag to link"))}"></span>` : ""}
      <div class="nh"><span class="glyph ${e.kind === "upload" ? "asset" : e.kind}">${GLYPH[e.kind]}</span><span class="nt" title="${esc(v.title)}">${esc(v.title)}</span></div>
      <div class="ns"><div class="ln">${v.html ? v.sub : esc(v.sub)}</div></div></div>`);
  }
  nodesEl.innerHTML = html.join("");
  renderEdges();
  const empty = $("cv-empty");
  empty.textContent = !lib ? t("Create or select an asset library first")
    : Object.keys(LAYOUT).length ? "" : t("Drag assets, pools and sources from the inventory, or press Place all.");
  renderInventory();
  // A live refresh (ingest progress) should not wipe what the user is typing.
  if (!insp.contains(document.activeElement)) renderInspector();
}
function portPoint(key, side) {
  const p = LAYOUT[key]; return { x: p.x + (side === "out" ? NODE_W : 0), y: p.y + PORT_Y };
}
function curve(a, b) {
  const dx = Math.max(50, Math.abs(b.x - a.x) / 2);
  return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
}
function renderEdges() {
  edgesEl.innerHTML = edges().map(ed => {
    const d = curve(portPoint(ed.from, "out"), portPoint(ed.to, "in"));
    const sel = SEL && SEL.type === "edge" && SEL.from === ed.from && SEL.to === ed.to;
    return `<path d="${d}" class="${ed.cls}${sel ? " sel" : ""}"/><path d="${d}" class="hit" data-from="${esc(ed.from)}" data-to="${esc(ed.to)}"/>`;
  }).join("") + '<path class="temp" id="cv-temp" d=""/>';
}
function render() { renderNodes(); renderInspector(); }

// ---- inventory ----------------------------------------------------------------
function invItem(kind, id, label, title) {
  const k = keyOf(kind, id);
  return `<div class="inv-item" draggable="true" data-kind="${kind}" data-id="${esc(id)}" title="${esc(title || label)}">
    <span class="glyph ${kind}">${GLYPH[kind]}</span><span class="lbl">${esc(label)}</span>${placed(k) ? `<span class="placed" title="${esc(t("on canvas"))}"></span>` : ""}</div>`;
}
function renderInventory() {
  const lib = scoped(), q = $("inv-filter").value.trim().toLowerCase();
  const match = (...xs) => !q || xs.some(x => String(x || "").toLowerCase().includes(q));
  const assets = ASSETS.filter(a => match(a.name, a.id, a.origin));
  const pools = ((lib && lib.asset_pools) || []).filter(p => match(p.name, p.id));
  const sources = ((lib && lib.sources) || []).filter(s => match(s.name, s.id, s.collection_name, s.database_id));
  $("inv-assets").innerHTML = assets.slice(0, INV_LIMIT).map(a => invItem("asset", a.id, assetName(a), a.origin)).join("")
    + (assets.length > INV_LIMIT ? `<div class="hint">${esc(t("+{n} more; filter to find them", { n: assets.length - INV_LIMIT }))}</div>` : "")
    + (!assets.length ? `<div class="hint">${esc(t("none"))}</div>` : "");
  $("inv-pools").innerHTML = pools.map(p => invItem("pool", p.id, p.name || p.id, p.id)).join("") || `<div class="hint">${esc(t("none"))}</div>`;
  $("inv-sources").innerHTML = sources.map(s => invItem("source", s.id, s.name || s.id, `${s.type} · ${s.database_id}/${s.collection_name}`)).join("") || `<div class="hint">${esc(t("none"))}</div>`;
  $("inv-assets-n").textContent = ASSETS_TOTAL > ASSETS.length ? `${ASSETS.length}/${ASSETS_TOTAL}` : ASSETS.length;
  $("inv-pools-n").textContent = lib ? lib.asset_pools.length : 0;
  $("inv-sources-n").textContent = lib ? lib.sources.length : 0;
}
$("inv-filter").addEventListener("input", renderInventory);

// ---- actions: link / unlink -----------------------------------------------------
// Normalize a pair to (from, to) along the arrow direction, or null if the two
// kinds do not relate.
function orient(a, b) {
  const ka = entity(a)?.kind, kb = entity(b)?.kind;
  const ok = (x, y) => (x === "asset" && y === "pool") || (x === "upload" && y === "pool") || (x === "pool" && y === "source");
  return ok(ka, kb) ? [a, b] : ok(kb, ka) ? [b, a] : null;
}
async function link(a, b) {
  const pair = orient(a, b);
  if (!pair) { toast(t("Those two cannot be linked. Link an asset to a pool, or a pool to a source."), true); return; }
  const [from, to] = pair, f = entity(from), g = entity(to), lib = scoped();
  if (g.kind === "source" && isContentSource(g.obj)) { toast(t("Every pool already stores its content in the library's content source.")); return; }
  try {
    if (g.draft && f.kind !== "asset") throw new Error(t("Create the {kind} first", { kind: t(g.kind) }));
    if (f.kind === "asset") {
      if (g.draft) { if (!g.obj.assets.includes(f.obj.id)) g.obj.assets.push(f.obj.id); return render(); }
      if (g.obj.asset_ids.includes(f.obj.id)) return toast(t("Already in this pool"));
      await addAssetsToPool(lib, g.obj.id, [f.obj.id]);
    } else if (f.kind === "upload") {
      if (!f.obj.pools.includes(g.obj.id)) f.obj.pools.push(g.obj.id);
      return render();
    } else if (f.draft) {          // draft pool -> source
      if (!f.obj.sources.includes(g.obj.id)) f.obj.sources.push(g.obj.id);
      return render();
    } else {                       // pool -> source
      const cur = f.obj.source_statuses.map(s => s.source_id);
      if (cur.includes(g.obj.id)) return toast(t("Already attached"));
      await setPoolSources(lib, f.obj.id, [...cur, g.obj.id]);
    }
    await refresh();
  } catch (err) { toast(err.message, true); }
}
async function unlink(from, to) {
  const f = entity(from), g = entity(to), lib = scoped();
  if (!f || !g) return;
  if (f.kind === "pool" && g.kind === "source" && g.obj.id === lib.default_content_source_id) {
    toast(t("The content source serves every pool in the library; this link cannot be removed."), true); return;
  }
  try {
    if (f.kind === "upload") { f.obj.pools = f.obj.pools.filter(id => id !== g.obj.id); return render(); }
    if (g.draft && f.kind === "asset") { g.obj.assets = g.obj.assets.filter(id => id !== f.obj.id); return render(); }
    if (f.draft && f.kind === "pool") { f.obj.sources = f.obj.sources.filter(id => id !== g.obj.id); return render(); }
    if (f.kind === "asset") throw new Error(t("The engine API cannot take an asset out of a pool."));
    if (!confirm(t('Detach source "{source}" from pool "{pool}"?', { source: g.obj.name || g.obj.id, pool: f.obj.id }))) return;
    await setPoolSources(lib, f.obj.id, f.obj.source_statuses.map(s => s.source_id).filter(id => id !== g.obj.id));
    SEL = null;
    await refresh();
  } catch (err) { toast(err.message, true); }
}

// ---- drafts -------------------------------------------------------------------
function newDraft(kind, x, y, preset = {}) {
  const key = `draft:${++draftSeq}`;
  const base = kind === "pool" ? { id: "", name: "", metadata: "", sources: [], assets: [] }
    : kind === "source" ? { name: "", database_id: (DATABASES.find(d => d.type === "vector") || DATABASES[0] || {}).id || "", collection: "", optionState: SourceOptions.defaults(), attachTo: null }
    : { text: "", pools: [] };
  const d = DRAFTS[key] = { kind, ...base, ...preset };
  if (kind === "upload") {
    d.el = document.createElement("div");
    d.uploader = new Uploader(d.el, () => renderNodes());
  }
  place(key, x, y);
  SEL = { type: "node", key };
  render();
  return d;
}
function discard(key) { delete DRAFTS[key]; delete LAYOUT[key]; if (SEL && SEL.key === key) SEL = null; render(); }
// A committed draft becomes the real node, at the draft's position.
function replaceDraft(key, realKey) {
  const pos = LAYOUT[key]; delete DRAFTS[key]; delete LAYOUT[key];
  LAYOUT[realKey] = pos; SEL = { type: "node", key: realKey }; saveLayout();
}
async function commitPool(key) {
  const d = DRAFTS[key], lib = scoped();
  const id = d.id.trim();
  await createPool(lib, { id, name: d.name.trim(), sources: d.sources, metadata: parseJsonObject(d.metadata, t("Metadata")) });
  replaceDraft(key, keyOf("pool", id));
  if (d.assets.length) await addAssetsToPool(lib, id, d.assets);
  await refresh();
}
async function commitSource(key) {
  const d = DRAFTS[key], lib = scoped();
  const s = await createSource(lib, { name: d.name.trim(), database_id: d.database_id, collection_name: d.collection.trim(),
    operator_options: d.editor.read() });
  replaceDraft(key, keyOf("source", s.id));
  await refresh();
  if (d.attachTo) await link(keyOf("pool", d.attachTo), keyOf("source", s.id));
}
async function commitUpload(key) {
  const d = DRAFTS[key], lib = scoped();
  const r = await ingestAssets(lib.name, { uploader: d.uploader, text: d.text.trim(), poolIds: d.pools });
  toast(t("Added {n} asset(s): {status}", { n: r.asset_ids.length, status: t(r.status) }));
  // The new assets take the draft's spot, stacked downwards.
  const pos = LAYOUT[key];
  delete DRAFTS[key]; delete LAYOUT[key]; SEL = null;
  r.asset_ids.forEach((id, i) => { if (!placed(keyOf("asset", id))) LAYOUT[keyOf("asset", id)] = freeSpot(pos.x, pos.y + i * ROW_H.asset); });
  if (r.asset_ids.length === 1) SEL = { type: "node", key: keyOf("asset", r.asset_ids[0]) };
  saveLayout();
  await refresh();
}

// ---- inspector ----------------------------------------------------------------
function kv(rows) {
  return `<dl class="kv">${rows.filter(Boolean).map(([k, v]) => `<dt>${esc(t(k))}</dt><dd>${v}</dd>`).join("")}</dl>`;
}
function inspHead(kind, title, key) {
  return `<div class="insp-h"><span class="glyph ${kind === "upload" ? "asset" : kind}">${GLYPH[kind]}</span><h2 title="${esc(title)}">${esc(title)}</h2>
    ${key ? `<button class="ghost mini" data-a="deselect" title="${esc(t("Close"))}">×</button>` : ""}</div>`;
}
const btn = (a, label, cls = "ghost", extra = "") => `<button class="${cls} mini" data-a="${a}" ${extra}>${esc(t(label))}</button>`;
function renderInspector() {
  const lib = scoped();
  if (!lib) {
    insp.innerHTML = inspHead("pool", t("No library")) + `<div class="insp-b">
      <p class="hint">${esc(t("Create an asset library to start."))}</p>
      <label>${esc(t("Name"))}</label><input data-f="newlib" placeholder="my_library" />
      <div class="actions">${btn("create-lib", "Create", "")}</div></div>`;
    return;
  }
  if (SEL && SEL.type === "edge") return inspectEdge(lib);
  const e = SEL && entity(SEL.key);
  if (!e) return inspectLibrary(lib);
  const k = SEL.key;
  if (e.draft) return e.kind === "pool" ? inspectDraftPool(lib, k, e.obj) : e.kind === "source" ? inspectDraftSource(k, e.obj) : inspectUpload(lib, k, e.obj);
  return e.kind === "asset" ? inspectAsset(lib, k, e.obj) : e.kind === "pool" ? inspectPool(lib, k, e.obj) : inspectSource(lib, k, e.obj);
}
function inspectLibrary(lib) {
  insp.innerHTML = inspHead("pool", lib.name) + `<div class="insp-b">
    ${kv([["Description", esc(lib.description || "—")], ["Assets", lib.asset_count], ["Docs", lib.document_count], ["Chunks", lib.chunk_count],
          ["Pools", lib.asset_pools.length], ["Sources", lib.sources.length], ["Content database", esc(lib.content_database || "—")]])}
    <h4>${esc(t("How to"))}</h4>
    <ul class="hint" style="padding-left:18px;margin:0">
      <li>${esc(t("Drag Upload assets, New asset pool or New source onto the canvas, fill in the form here, then create it."))}</li>
      <li>${esc(t("Drag from a node's right-hand port to another node to link them."))}</li>
      <li>${esc(t("Drop files or folders from your computer onto the canvas, or onto a pool to index them there."))}</li>
      <li>${esc(t("Click a link to inspect or remove it. Delete removes the selected node from the canvas; Esc clears the selection."))}</li>
    </ul>
    <div class="actions">${btn("retrieve-lib", "Retrieve from all pools")}</div></div>`;
}
function inspectAsset(lib, k, a) {
  const pools = lib.asset_pools.filter(p => p.asset_ids.includes(a.id));
  const others = lib.asset_pools.filter(p => !p.asset_ids.includes(a.id));
  const src = lib.sources.find(s => s.id === a.content_source_id);
  const phase = a.materialization;
  insp.innerHTML = inspHead("asset", assetName(a), k) + `<div class="insp-b">
    ${kv([["ID", `<span class="mono">${esc(a.id)}</span>`], ["Kind", esc(a.kind)], a.media_type && ["Media type", esc(a.media_type)],
          ["Origin", `<span class="mono">${esc(a.origin)}</span>`], ["Content source", esc(src ? src.name || src.id : a.content_source_id || "—")],
          phase && ["Ingest", `<span class="phase ${esc(phase)}">${esc(phaseLabel(phase))}</span>`]])}
    <h4>${esc(t("In pools"))}</h4>
    <div>${pools.map(p => `<span class="chip">${esc(p.name || p.id)}</span>`).join("") || `<span class="hint">${esc(t("none"))}</span>`}</div>
    ${others.length ? `<label>${esc(t("Add to pool"))}</label>
      <div class="inline"><select data-f="pool">${others.map(p => `<option value="${esc(p.id)}">${esc(p.name || p.id)}</option>`).join("")}</select>
      ${btn("asset-add-pool", "Add", "")}</div>` : ""}
    <div class="actions">${btn("place-linked", "Show its pools")}${btn("unplace", "Remove from canvas")}${btn("delete-asset", "Delete asset", "danger")}</div></div>`;
}
function inspectPool(lib, k, p) {
  const attached = p.source_statuses.map(s => s.source_id);
  const free = attachableSources(lib).filter(s => !attached.includes(s.id));
  const members = new Set(p.asset_ids);
  const nonMembers = ASSETS.filter(a => !members.has(a.id));
  const meta = Object.keys(p.metadata || {}).length ? `<span class="mono">${esc(JSON.stringify(p.metadata))}</span>` : "—";
  insp.innerHTML = inspHead("pool", p.name || p.id, k) + `<div class="insp-b">
    ${kv([["ID", `<span class="mono">${esc(p.id)}</span>`], ["Name", esc(p.name)], ["Status", poolStatusChip(p)], ["Revision", p.revision], ["Assets", p.asset_ids.length], ["Metadata", meta]])}
    <div class="hint">${esc(t("The engine API cannot rename a pool or edit its metadata."))}</div>
    <h4>${esc(t("Sources"))}</h4>
    ${p.source_statuses.map(st => `<div class="ing-item"><span class="name">${esc(sourceName(lib, st.source_id))}
        ${st.error ? `<div class="err">${esc(st.error)}</div>` : ""}</span>
  ${sourceStatusChip(st)}${SourceServing.control(lib, p, st.source_id)}
        ${st.extraction ? `<button class="ghost mini" data-a="extract" data-id="${esc(st.source_id)}" title="${esc(t("Extract now"))}">⚙</button>` : ""}
        <button class="ghost mini" data-a="detach" data-id="${esc(st.source_id)}" title="${esc(t("Detach"))}">×</button></div>`).join("")
      || `<div class="hint">${esc(t("none"))}</div>`}
    ${free.length ? `<div class="inline"><select data-f="source">${free.map(s => `<option value="${esc(s.id)}">${esc(s.name || s.id)} (${esc(s.type)})</option>`).join("")}</select>
      ${btn("attach", "Attach", "")}</div>` : ""}
    <h4>${esc(t("Assets"))} (${p.asset_ids.length})</h4>
    <div class="checks" style="max-height:160px">${p.asset_ids.slice(0, 100).map(id => {
      const a = ASSETS.find(x => x.id === id); return `<div class="ing-item"><span class="name">${esc(a ? assetName(a) : id)}</span></div>`;
    }).join("") || `<div class="empty">${esc(t("none"))}</div>`}</div>
    ${nonMembers.length ? `<label>${esc(t("Add asset"))}</label>
      <div class="inline"><select data-f="asset">${nonMembers.slice(0, 500).map(a => `<option value="${esc(a.id)}">${esc(assetName(a))}</option>`).join("")}</select>
      ${btn("pool-add-asset", "Add", "")}</div>` : ""}
    <div class="actions">${btn("upload-here", "Upload into this pool")}${btn("place-linked", "Show linked")}${btn("retrieve-pool", "Retrieve")}
      ${btn("unplace", "Remove from canvas")}${btn("delete-pool", "Delete pool", "danger")}</div></div>`;
}
function inspectSource(lib, k, s) {
  const pools = s.id === lib.default_content_source_id ? lib.asset_pools
    : lib.asset_pools.filter(p => p.source_statuses.some(st => st.source_id === s.id));
  const opts = Object.keys(s.operator_options || {}).length ? `<span class="mono">${esc(JSON.stringify(s.operator_options, null, 1))}</span>` : "—";
  insp.innerHTML = inspHead("source", s.name || s.id, k) + `<div class="insp-b">
    ${kv([["ID", `<span class="mono">${esc(s.id)}</span>`], ["Type", esc(s.type)], ["Database", esc(s.database_id)], ["Collection", esc(s.collection_name)],
          ["Operator options", opts], ["Validation", s.reconciled ? esc(t("reconciled")) : `<span class="err">${esc(t("unreconciled"))}: ${esc(s.reconciliation_error || "")}</span>`],
          s.id === lib.default_content_source_id && ["Role", esc(t("default content"))]])}
    <div class="hint">${esc(t("Model and parameters are fixed at creation."))}</div>
    <h4>${esc(t("Used by pools"))}</h4>
    <div>${s.id === lib.default_content_source_id ? pools.map(p => `<span class="chip">${esc(p.name || p.id)}</span>`).join("")
      : SourceServing.sourceBindings(lib, s.id)}</div>
    <div class="actions">${btn("place-linked", "Show linked")}${btn("unplace", "Remove from canvas")}${btn("delete-source", "Delete source", "danger")}</div></div>`;
}
function inspectDraftPool(lib, k, d) {
  insp.innerHTML = inspHead("pool", d.name || d.id || t("New asset pool"), k) + `<div class="insp-b">
    <label>${esc(t("ID"))}</label><input data-d="id" value="${esc(d.id)}" placeholder="docs" />
    <label>${esc(t("Name"))}</label><input data-d="name" value="${esc(d.name)}" placeholder="Documents" />
    <label>${esc(t("Sources"))}</label><div class="checks" data-d-list="sources"></div>
    <label>${esc(t("Assets to add"))} (${d.assets.length})</label>
    <div class="checks" style="max-height:130px">${d.assets.map(id => { const a = ASSETS.find(x => x.id === id);
      return `<div class="ing-item"><span class="name">${esc(a ? assetName(a) : id)}</span><button class="ghost mini" data-a="draft-rm-asset" data-id="${esc(id)}">×</button></div>`; }).join("")
      || `<div class="empty">${esc(t("Link assets to this pool on the canvas."))}</div>`}</div>
    <label>${esc(t("Metadata (JSON, optional)"))}</label><textarea class="code" data-d="metadata" placeholder='{"owner": "team-a"}'>${esc(d.metadata)}</textarea>
    <div class="actions">${btn("commit-pool", "Create pool", "")}${btn("discard", "Discard")}</div></div>`;
  sourceChecks(insp.querySelector('[data-d-list="sources"]'), attachableSources(lib), d.sources);
}
function inspectDraftSource(k, d) {
  if (!DATABASES.some(database => database.id === d.database_id)) {
    d.database_id = (DATABASES.find(database => database.type === "vector") || DATABASES[0] || {}).id || "";
  }
  insp.innerHTML = inspHead("source", d.name || t("New source"), k) + `<div class="insp-b">
    <label>${esc(t("Name"))}</label><input data-d="name" value="${esc(d.name)}" placeholder="docs_vectors" />
    <label>${esc(t("Database"))}</label><select data-d="database_id">${databaseOptions().map(([v, l]) => `<option value="${esc(v)}" ${v === d.database_id ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
    <div class="hint">${esc(t("The source's type (vector / graph / object…) follows from the database."))}</div>
    <label>${esc(t("Collection name"))}</label><input data-d="collection" value="${esc(d.collection)}" placeholder="docs_vectors" />
    <div data-slot="source-options"></div>
    ${d.attachTo ? `<div class="hint">${esc(t("Will be attached to pool {pool} once created.", { pool: d.attachTo }))}</div>` : ""}
    <div class="actions">${btn("commit-source", "Create source", "")}${btn("discard", "Discard")}</div></div>`;
  mountDraftOptions(d);
}
function mountDraftOptions(d) {
  d.editor = SourceOptions.mount(insp.querySelector('[data-slot="source-options"]'), {
    type: DATABASES.find(database => database.id === d.database_id)?.type || "",
    state: d.optionState, models: SOURCE_MODELS,
  });
}
function inspectUpload(lib, k, d) {
  insp.innerHTML = inspHead("upload", t("Upload assets"), k) + `<div class="insp-b">
    <label>${esc(t("Files and folders"))}</label><div data-slot="uploader"></div>
    <label>${esc(t("Text (optional)"))}</label><textarea data-d="text" placeholder="${esc(t("Paste text to add…"))}">${esc(d.text)}</textarea>
    <label>${esc(t("Index in asset pools"))}</label><div class="checks" data-d-list="pools"></div>
    <div class="hint">${esc(t("None checked stores the assets without indexing them; add them to a pool later."))}</div>
    <div class="actions">${btn("commit-upload", "Upload", "")}${btn("discard", "Discard")}</div></div>`;
  insp.querySelector('[data-slot="uploader"]').replaceWith(d.el);
  d.uploader.render();
  poolChecks(insp.querySelector('[data-d-list="pools"]'), lib.asset_pools, d.pools);
}
function inspectEdge(lib) {
  const f = entity(SEL.from), g = entity(SEL.to);
  const name = (e) => e.draft ? (e.obj.name || e.obj.id || t("draft")) : (e.kind === "asset" ? assetName(e.obj) : e.obj.name || e.obj.id);
  const assetPool = f.kind === "asset" || f.kind === "upload";
  const content = !assetPool && g.obj.id === lib.default_content_source_id;
  const st = !assetPool && !f.draft && !content ? f.obj.source_statuses.find(s => s.source_id === g.obj.id) : null;
  const removable = !(f.kind === "asset" && !g.draft) && !content;
  insp.innerHTML = inspHead(assetPool ? "asset" : "source", assetPool ? t("Pool membership") : t("Pool source")) + `<div class="insp-b">
    ${kv([["From", esc(name(f))], ["To", esc(name(g))], st && ["Status", sourceStatusChip(st)],
          st && ["serving_state", SourceServing.control(lib, f.obj, g.obj.id)],
          st && ["Indexed revision", st.indexed_revision], st && st.error && ["Error", `<span class="err">${esc(st.error)}</span>`],
          st && st.extraction && ["OKF extraction", extractionChip(st) + `<div class="hint" style="white-space:pre-line">${esc(extractionTitle(st.extraction))}</div>`]])}
    ${st && st.extraction ? `<div class="actions">${btn("extract-edge", "Extract now", "")}</div>` : ""}
    ${content ? `<div class="hint">${esc(t("Every pool in the library stores its asset content in this source. The link is fixed."))}</div>`
      : st ? `<div class="hint">${esc(t("Removing this link detaches the source immediately; it does not set DEPRECATED. Indexed data is kept."))}</div>`
      : removable ? "" : `<div class="hint">${esc(t("The engine API cannot take an asset out of a pool."))}</div>`}
    <div class="actions">${removable ? btn("unlink", "Remove link", "danger") : ""}${btn("deselect", "Close")}</div></div>`;
}
// Draft forms write straight into their draft, so a re-render never loses input.
insp.addEventListener("input", e => {
  const f = e.target.dataset.d, d = SEL && DRAFTS[SEL.key];
  if (f && d) { d[f] = e.target.value; if (f === "name" || f === "id") renderNodes(); }
});
insp.addEventListener("change", e => {
  const list = e.target.closest("[data-d-list]"), d = SEL && DRAFTS[SEL.key];
  if (list && d) { d[list.dataset.dList] = [...list.querySelectorAll("input:checked")].map(i => i.value); renderNodes(); }
  if (e.target.dataset.d && d) {
    d[e.target.dataset.d] = e.target.value;
    if (e.target.dataset.d === "database_id" && d.kind === "source") mountDraftOptions(d);
  }
});
insp.addEventListener("click", e => {
  const b = e.target.closest("button[data-a]"); if (!b) return;
  const a = b.dataset.a, lib = scoped(), key = SEL && SEL.key, ent = key && entity(key);
  const field = (n) => insp.querySelector(`[data-f="${n}"]`)?.value;
  const run = (label, fn) => busy(b, t(label), fn);
  switch (a) {
    case "deselect": SEL = null; return render();
    case "extract": return run("Starting…", () => extractNow(lib, ent.obj.id, b.dataset.id));
    case "extract-edge": return run("Starting…", () => extractNow(lib, entity(SEL.from).obj.id, entity(SEL.to).obj.id));
    case "create-lib": return run("Creating…", async () => {
      const name = (field("newlib") || "").trim(); if (!name) throw new Error(t("Name is required"));
      await api("POST", "/v1/libraries", { name }); toast(t("Created {name}", { name })); await refresh(); selectLibrary(name);
    });
    case "retrieve-lib": return retrieveFrom(lib.name);
    case "retrieve-pool": return retrieveFrom(lib.name, ent.obj.id);
    case "unplace": delete LAYOUT[key]; SEL = null; saveLayout(); return render();
    case "discard": return discard(key);
    case "unlink": return unlink(SEL.from, SEL.to);
    case "place-linked": return showLinked(key);
    case "upload-here": { const p = LAYOUT[key]; return newDraft("upload", p.x - 440, p.y, { pools: [ent.obj.id] }); }
    case "asset-add-pool": return run("Adding…", async () => { await addAssetsToPool(lib, field("pool"), [ent.obj.id]); await refresh(); });
    case "pool-add-asset": return run("Adding…", async () => {
      const id = field("asset"); await addAssetsToPool(lib, ent.obj.id, [id]); placeNear(keyOf("asset", id), key); await refresh();
    });
    case "attach": { const sk = keyOf("source", field("source")); placeNear(sk, key); return link(key, sk); }
    case "detach": SEL = { type: "edge", from: key, to: keyOf("source", b.dataset.id) }; return unlink(key, keyOf("source", b.dataset.id));
    case "draft-rm-asset": DRAFTS[key].assets = DRAFTS[key].assets.filter(id => id !== b.dataset.id); return render();
    case "commit-pool": return run("Creating…", () => commitPool(key));
    case "commit-source": return run("Creating…", () => commitSource(key));
    case "commit-upload": return run("Uploading…", () => commitUpload(key));
    case "delete-pool": return run("Deleting…", async () => { if (await deletePool(lib, ent.obj.id)) await refresh(); });
    case "delete-source": return run("Deleting…", async () => { if (await deleteSource(lib, ent.obj.id, ent.obj.name || ent.obj.id)) await refresh(); });
    case "delete-asset": return run("Deleting…", async () => {
      if (await deleteAssets(lib, [ent.obj.id])) await refresh();
    });
  }
});
// Bring everything linked to a node onto the stage beside it.
function showLinked(key) {
  const lib = scoped(), [kind, id] = splitKey(key);
  const keys = kind === "asset" ? lib.asset_pools.filter(p => p.asset_ids.includes(id)).map(p => keyOf("pool", p.id))
    : kind === "source" ? lib.asset_pools.filter(p => id === lib.default_content_source_id || p.source_statuses.some(s => s.source_id === id)).map(p => keyOf("pool", p.id))
    : (() => { const p = entity(key).obj; return [...p.source_statuses.map(s => keyOf("source", s.source_id)),
        ...(lib.default_content_source_id ? [keyOf("source", lib.default_content_source_id)] : []), ...p.asset_ids.slice(0, 100).map(a => keyOf("asset", a))]; })();
  const fresh = keys.filter(k => entity(k) && !placed(k));
  fresh.forEach(k => placeNear(k, key));
  toast(fresh.length ? t("Placed {n} linked item(s)", { n: fresh.length }) : t("Everything linked is already on the canvas"));
  render();
}

// ---- stage interaction --------------------------------------------------------
function toStage(cx, cy) { const r = stage.getBoundingClientRect(); return { x: (cx - r.left) / scale, y: (cy - r.top) / scale }; }
function nodeAt(cx, cy) { const el = document.elementFromPoint(cx, cy); return el && el.closest(".node"); }
let drag = null;   // {mode: "move"|"link", key, ...}
stage.addEventListener("pointerdown", e => {
  if (e.button !== 0) return;
  // preventDefault below keeps focus where it was; drop it out of any form
  // field so keyboard shortcuts (Delete, Esc) reach the canvas.
  if (document.activeElement && document.activeElement.matches("input, textarea, select")) document.activeElement.blur();
  const port = e.target.closest(".port.out"), node = e.target.closest(".node");
  if (port && node) {
    drag = { mode: "link", key: node.dataset.key };
  } else if (node) {
    const p = toStage(e.clientX, e.clientY), pos = LAYOUT[node.dataset.key];
    drag = { mode: "move", key: node.dataset.key, el: node, dx: p.x - pos.x, dy: p.y - pos.y, sx: e.clientX, sy: e.clientY, moved: false };
  } else if (!e.target.closest("path.hit")) {
    if (SEL) { SEL = null; render(); }
    return;
  } else return;
  stage.setPointerCapture(e.pointerId);
  e.preventDefault();
});
let lastTarget = null;
function markTarget(el) { if (lastTarget && lastTarget !== el) lastTarget.classList.remove("target"); if (el) el.classList.add("target"); lastTarget = el; }
stage.addEventListener("pointermove", e => {
  if (!drag) return;
  const p = toStage(e.clientX, e.clientY);
  if (drag.mode === "move") {
    if (!drag.moved && Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < 4) return;
    drag.moved = true; drag.el.classList.add("moving");
    LAYOUT[drag.key] = { x: Math.max(0, Math.min(STAGE_W - NODE_W, p.x - drag.dx)), y: Math.max(0, Math.min(STAGE_H - 60, p.y - drag.dy)) };
    drag.el.style.left = LAYOUT[drag.key].x + "px"; drag.el.style.top = LAYOUT[drag.key].y + "px";
    renderEdges();
  } else {
    const a = portPoint(drag.key, "out");
    $("cv-temp").setAttribute("d", curve(a, p));
    const over = nodeAt(e.clientX, e.clientY);
    markTarget(over && over.dataset.key !== drag.key && orient(drag.key, over.dataset.key) ? over : null);
  }
});
stage.addEventListener("pointerup", e => {
  if (!drag) return;
  const d = drag; drag = null; markTarget(null);
  if (d.mode === "move") {
    d.el.classList.remove("moving");
    if (d.moved) { saveLayout(); return; }
    SEL = { type: "node", key: d.key }; return render();
  }
  $("cv-temp").setAttribute("d", "");
  const over = nodeAt(e.clientX, e.clientY);
  if (over && over.dataset.key !== d.key) link(d.key, over.dataset.key);
});
edgesEl.addEventListener("click", e => {
  const hit = e.target.closest("path.hit"); if (!hit) return;
  SEL = { type: "edge", from: hit.dataset.from, to: hit.dataset.to }; render();
});
edgesEl.style.pointerEvents = "none";   // only the .hit paths take events (see CSS)

// Inventory -> stage (HTML5 drag and drop), and files from the desktop.
const DND = "application/x-die";
document.querySelector(".inventory").addEventListener("dragstart", e => {
  const it = e.target.closest(".inv-item"); if (!it) return;
  e.dataTransfer.setData(DND, JSON.stringify({ kind: it.dataset.kind, id: it.dataset.id || null }));
  e.dataTransfer.effectAllowed = "copyMove";
  it.classList.add("dragging");
});
document.querySelector(".inventory").addEventListener("dragend", e => e.target.closest(".inv-item")?.classList.remove("dragging"));
wrap.addEventListener("dragover", e => {
  const types = [...e.dataTransfer.types];
  if (!types.includes(DND) && !types.includes("Files")) return;
  e.preventDefault();
  wrap.classList.toggle("files-over", types.includes("Files"));
  markTarget(e.target.closest(".node"));
});
wrap.addEventListener("dragleave", e => { if (!wrap.contains(e.relatedTarget)) { wrap.classList.remove("files-over"); markTarget(null); } });
wrap.addEventListener("drop", async e => {
  e.preventDefault(); wrap.classList.remove("files-over"); markTarget(null);
  const lib = scoped();
  if (!lib) return toast(t("Create or select an asset library first"), true);
  const p = toStage(e.clientX, e.clientY), x = p.x - NODE_W / 2, y = p.y - 20;
  const target = e.target.closest(".node"), tkey = target && target.dataset.key, tent = tkey && entity(tkey);
  const targetPool = tent && tent.kind === "pool" && !tent.draft ? tent.obj.id : null;
  if (hasFiles(e)) {
    const staged = stagedFromDrop(e.dataTransfer);   // grabs the entries synchronously
    const d = newDraft("upload", targetPool ? LAYOUT[tkey].x - 440 : x, targetPool ? LAYOUT[tkey].y : y, { pools: targetPool ? [targetPool] : [] });
    d.uploader.add(await staged);
    return;
  }
  let payload; try { payload = JSON.parse(e.dataTransfer.getData(DND) || "null"); } catch { payload = null; }
  if (!payload) return;
  const { kind, id } = payload;
  if (kind === "new-upload") return newDraft("upload", x, y, { pools: targetPool ? [targetPool] : [] });
  if (kind === "new-pool") return newDraft("pool", x, y);
  if (kind === "new-source") return newDraft("source", targetPool ? LAYOUT[tkey].x + 440 : x, targetPool ? LAYOUT[tkey].y : y, { attachTo: targetPool });
  const key = keyOf(kind, id);
  if (tkey && tkey !== key && orient(key, tkey)) {
    placeNear(key, tkey); render();
    return link(key, tkey);
  }
  place(key, x, y, true);
  SEL = { type: "node", key };
  render();
  nodesEl.querySelector(`.node[data-key="${CSS.escape(key)}"]`)?.classList.add("flash");
});

// Keyboard: Delete removes the selection from the canvas (or unlinks a link).
document.addEventListener("keydown", e => {
  if (!visible() || e.target.closest("input, textarea, select")) return;
  if (e.key === "Escape" && SEL) { SEL = null; render(); }
  if ((e.key === "Delete" || e.key === "Backspace") && SEL) {
    e.preventDefault();
    if (SEL.type === "edge") return unlink(SEL.from, SEL.to);
    if (DRAFTS[SEL.key]) return discard(SEL.key);
    delete LAYOUT[SEL.key]; SEL = null; saveLayout(); render();
  }
});

// ---- toolbar: zoom / place / layout ---------------------------------------------
function setScale(s, cx, cy) {
  const before = cx != null ? toStage(cx, cy) : null;
  scale = Math.max(0.3, Math.min(2, s));
  stage.style.transform = `scale(${scale})`;
  $("cv-sizer").style.width = STAGE_W * scale + "px"; $("cv-sizer").style.height = STAGE_H * scale + "px";
  $("cv-zoom").textContent = Math.round(scale * 100) + "%";
  if (before) {   // keep the point under the cursor fixed
    const after = toStage(cx, cy);
    wrap.scrollLeft += (before.x - after.x) * scale; wrap.scrollTop += (before.y - after.y) * scale;
  }
}
$("cv-zoom-in").addEventListener("click", () => setScale(scale * 1.2));
$("cv-zoom-out").addEventListener("click", () => setScale(scale / 1.2));
wrap.addEventListener("wheel", e => {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault(); setScale(scale * (e.deltaY < 0 ? 1.1 : 1 / 1.1), e.clientX, e.clientY);
}, { passive: false });
function fit() {
  const ps = Object.values(LAYOUT); if (!ps.length) { setScale(1); wrap.scrollTo(0, 0); return; }
  const minX = Math.min(...ps.map(p => p.x)) - 40, minY = Math.min(...ps.map(p => p.y)) - 40;
  const maxX = Math.max(...ps.map(p => p.x)) + NODE_W + 40, maxY = Math.max(...ps.map(p => p.y)) + 110;
  setScale(Math.min(wrap.clientWidth / (maxX - minX), wrap.clientHeight / (maxY - minY), 1.2));
  wrap.scrollTo(minX * scale, minY * scale);
}
$("cv-fit").addEventListener("click", fit);
$("cv-layout").addEventListener("click", () => { autoLayout(); render(); fit(); });
$("cv-place-all").addEventListener("click", () => {
  const lib = scoped(); if (!lib) return;
  lib.asset_pools.forEach(p => (LAYOUT[keyOf("pool", p.id)] ||= { x: 0, y: 0 }));
  lib.sources.forEach(s => (LAYOUT[keyOf("source", s.id)] ||= { x: 0, y: 0 }));
  ASSETS.slice(0, MAX_AUTO_ASSETS).forEach(a => (LAYOUT[keyOf("asset", a.id)] ||= { x: 0, y: 0 }));
  if (ASSETS_TOTAL > MAX_AUTO_ASSETS) toast(t("Placed the first {n} assets; drag others from the inventory", { n: MAX_AUTO_ASSETS }));
  autoLayout(); render(); fit();
});
$("cv-clear").addEventListener("click", () => {
  for (const k of Object.keys(LAYOUT)) if (!k.startsWith("draft:")) delete LAYOUT[k];
  SEL = null; saveLayout(); render();
});
setScale(1);

window.Canvas = {
  render,
  renderNodes,
  // Status-only update: nodes and edges, plus the inspector of a saved item
  // (draft forms are left alone while they are being filled in).
  renderStatus() { renderNodes(); if (SEL && !(SEL.type === "node" && entity(SEL.key)?.draft)) renderInspector(); },
  libraryChanged() { loadLayout(); render(); },
};
})();

initConsole();
