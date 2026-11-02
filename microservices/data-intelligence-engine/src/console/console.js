// Copyright (C) 2025 Intel Corporation; SPDX-License-Identifier: Apache-2.0
// Data Intelligence Engine console: shared state, API helpers, the tabbed views,
// and the browser uploader. The canvas view lives in canvas.js and reads the
// globals defined here (classic scripts share one global scope).

const API = ""; // same origin
const $ = (id) => document.getElementById(id);
const enc = encodeURIComponent;

function toast(msg, isErr = false) {
  const el = $("toast");
  el.textContent = msg; el.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(el._t); el._t = setTimeout(() => (el.className = "toast"), isErr ? 6000 : 3200);
}
function errorDetail(data, fallback) {
  let detail = data && (data.detail || data.message);
  // FastAPI validation errors arrive as a list of {loc, msg}.
  if (Array.isArray(detail)) detail = detail.map(d => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
  return detail || fallback;
}
async function api(method, path, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const res = await fetch(API + path, opt);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) throw new Error(errorDetail(data, res.status + " " + res.statusText));
  return data;
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
// Optional JSON object field: empty means {}, anything else must parse to an object.
function parseJsonObject(raw, label) {
  raw = raw.trim();
  if (!raw) return {};
  let v;
  try { v = JSON.parse(raw); } catch (e) { throw new Error(t("{label} is not valid JSON: {error}", { label, error: e.message })); }
  if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error(t("{label} must be a JSON object", { label }));
  return v;
}
// Run an async action with its button disabled, toasting any error.
async function busy(btn, label, fn) {
  const orig = btn.textContent; btn.disabled = true; btn.textContent = label;
  try { await fn(); } catch (err) { toast(err.message, true); }
  finally { btn.disabled = false; btn.textContent = orig; }
}
function fillSelect(sel, options, keep = true) {
  const cur = sel.value;
  sel.innerHTML = options.map(([v, label]) => `<option value="${esc(v)}">${esc(label)}</option>`).join("");
  if (keep && options.some(([v]) => v === cur)) sel.value = cur;
}
function checkedValues(box) { return [...box.querySelectorAll("input[type=checkbox]:checked:not(:disabled)")].map(i => i.value); }
function fmtBytes(n) {
  if (n < 1024) return n + " B";
  const u = ["KB", "MB", "GB"]; let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return n.toFixed(n < 10 ? 1 : 0) + " " + u[i];
}

// ---- theme + language ---------------------------------------------------------
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("die.theme", theme);
  $("theme-toggle").textContent = theme === "dark" ? "☀" : "☾";
}
$("theme-toggle").addEventListener("click", () =>
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
setTheme(document.documentElement.dataset.theme);

$("lang-toggle").addEventListener("click", () => { setLang(LANG === "zh" ? "en" : "zh"); renderAll(); });
// Every view re-renders from state, so switching language is just a redraw.
function renderAll() {
  applyI18n();
  $("lang-toggle").textContent = LANG === "zh" ? "EN" : "中文";
  renderLibraries(); renderScoped(); renderRetrievePools(); renderDatabases(); resetDbFormLabels();
  renderModels(); renderModalities(); ingestUploader.render(); renderResults();
  if (window.Canvas) Canvas.render();
  if (window.Chat) Chat.render();
  GraphView.redraw();
  health();
}

// ---- tabs -----------------------------------------------------------------
// Three tabs; the Library tab holds five sections picked from its left panel.
// The hash is "tab" or "library/section"; the old per-section tab names
// ("#pools", "#databases", ...) still land on their section.
const SECTIONS = ["libraries", "assets", "pools", "sources", "databases", "models"];
const SECTION_LOADERS = { databases: loadDatabases, models: loadModels };
let SECTION = "libraries";
function showTab(name) {
  let [tab, section] = (name || "").split("/");
  if (SECTIONS.includes(tab)) { section = tab; tab = "library"; }
  if (!document.querySelector(`[data-panel="${tab}"]`)) tab = "canvas";
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll("[data-panel]").forEach(p => p.classList.toggle("on", p.dataset.panel === tab));
  if (tab === "library") showSection(section || SECTION, false);
  const hash = "#" + (tab === "library" ? `library/${SECTION}` : tab);
  if (location.hash !== hash) history.replaceState(null, "", hash);
  if (tab === "canvas" && window.Canvas) Canvas.render();
  if (tab === "retrieve") GraphView.redraw();
}
function showSection(section, updateHash = true) {
  if (!SECTIONS.includes(section)) section = "libraries";
  SECTION = section;
  document.querySelectorAll("#lib-nav button").forEach(b => b.classList.toggle("on", b.dataset.sec === section));
  document.querySelectorAll("[data-section]").forEach(p => p.classList.toggle("on", p.dataset.section === section));
  if (SECTION_LOADERS[section]) SECTION_LOADERS[section]().catch(e => toast(e.message, true));
  if (updateHash) history.replaceState(null, "", `#library/${section}`);
}
$("tabs").addEventListener("click", e => { const b = e.target.closest("button"); if (b) showTab(b.dataset.tab); });
$("lib-nav").addEventListener("click", e => { const b = e.target.closest("button[data-sec]"); if (b) showSection(b.dataset.sec); });
function renderNavCounts() {
  const lib = scoped();
  $("nav-n-libraries").textContent = LIBRARIES.length;
  $("nav-n-assets").textContent = lib ? ASSETS_TOTAL : "";
  $("nav-n-pools").textContent = lib ? lib.asset_pools.length : "";
  $("nav-n-sources").textContent = lib ? lib.sources.length : "";
  $("nav-n-databases").textContent = DATABASES.length;
  const ok = ["embedding", "reranker"].filter(type => MODELS[type] && MODELS[type].opt && modelStatus(MODELS[type].opt)[0] !== "bad").length;
  $("nav-n-models").textContent = MODELS.embedding || MODELS.reranker ? `${ok}/2` : "";
}

// ---- health -----------------------------------------------------------------
let HEALTH = null;
async function health() {
  try { HEALTH = await api("GET", "/health"); } catch { HEALTH = null; }
  $("health-dot").className = "dot " + (HEALTH ? "ok" : "bad");
  $("health-text").textContent = HEALTH
    ? t("{status} · {libs} libraries · {dbs} databases", { status: t(HEALTH.status), libs: HEALTH.asset_libraries, dbs: HEALTH.databases })
    : t("offline");
}

// ---- shared state -----------------------------------------------------------
// Libraries carry their sources and pools, so one GET refreshes every library-
// scoped view. Assets are paged, so the scoped library's are fetched separately.
let LIBRARIES = [];
let DATABASES = [];
let ASSETS = [];          // scoped library's assets (first page)
let ASSETS_TOTAL = 0;
let RERANKERS = null;     // reranker ModelOptions, for the retrieve picker
let SOURCE_MODELS = {};
let SOURCE_OPTIONS = SourceOptions.defaults();
let SOURCE_EDITOR = null;
const ASSET_PAGE = 1000;
const scoped = () => LIBRARIES.find(l => l.name === $("scope-library").value);
const assetName = (a) => a.name || a.id;

async function loadAssets() {
  const lib = scoped();
  if (!lib) { ASSETS = []; ASSETS_TOTAL = 0; return; }
  const page = await api("GET", `/v1/libraries/${enc(lib.name)}/assets?page_size=${ASSET_PAGE}`);
  if (scoped() !== lib && scoped()?.name !== lib.name) return;   // scope changed meanwhile
  ASSETS = page.assets || []; ASSETS_TOTAL = page.total || ASSETS.length;
}
async function refresh() {
  [LIBRARIES, DATABASES, SOURCE_MODELS] = await Promise.all([
    api("GET", "/v1/libraries"), api("GET", "/v1/databases"),
    api("GET", "/v1/models").catch(() => SOURCE_MODELS),
  ]);
  const opts = LIBRARIES.map(l => [l.name, l.name]);
  fillSelect($("scope-library"), opts);
  fillSelect($("q-library"), opts);
  await loadAssets().catch(e => toast(e.message, true));
  renderLibraries(); renderScoped(); renderRetrievePools(); renderDatabases();
  if (window.Canvas) Canvas.render();
  GraphView.noteStatuses();
  health();
  scheduleStatusPoll();
}
// Source syncs finish in the background (an OKF extraction takes minutes), so
// while any pool's source is pending or indexing, statuses are re-fetched and
// only status-bearing views re-render; forms and checkboxes keep their input.
const SYNCING = new Set(["pending", "indexing", "queued", "running"]);
const STATUS_POLL_MS = 3000;
let statusTimer = null;
const shapeOf = (libs) => JSON.stringify(libs.map(l => [l.name, l.sources.map(s => s.id), l.asset_pools.map(p => [p.id, p.source_statuses.map(st => st.source_id)])]));
function scheduleStatusPoll() {
  clearTimeout(statusTimer); statusTimer = null;
  const syncing = LIBRARIES.some(l => l.asset_pools.some(p => p.source_statuses.some(st =>
    SourceServing.polling(st) && (SYNCING.has(st.status) || (st.extraction && SYNCING.has(st.extraction.state))))));
  if (syncing) statusTimer = setTimeout(pollStatuses, STATUS_POLL_MS);
}
async function pollStatuses() {
  statusTimer = null;
  let libs;
  try { libs = await api("GET", "/v1/libraries"); } catch { return scheduleStatusPoll(); }
  if (shapeOf(libs) !== shapeOf(LIBRARIES)) return refresh().catch(() => scheduleStatusPoll());
  LIBRARIES = libs;
  renderLibraries(); renderPools(); renderSources(); renderNavCounts();
  if (window.Canvas) Canvas.renderStatus();
  GraphView.noteStatuses();
  scheduleStatusPoll();
}
function renderScoped() {
  const lib = scoped();
  for (const id of ["ing-scope", "pool-scope", "src-scope", "as-scope"]) $(id).textContent = lib ? lib.name : t("no library");
  renderIngestPools(); renderPoolCreateSources(); renderPools(); renderSources(); renderSourceDbOptions(); renderAssets(); renderNavCounts();
  if (PM_POOL && !(lib && lib.asset_pools.some(p => p.id === PM_POOL))) closePoolManager();
  else if (PM_POOL) { renderPoolManagerSources(); renderPoolManagerAssets(); }
}
$("scope-library").addEventListener("change", async () => {
  stopIngPoll(); closePoolManager();
  // One current library: Retrieve and its concept graph follow the header.
  if ($("q-library").value !== $("scope-library").value) {
    $("q-library").value = $("scope-library").value; GraphView.clearTraces(); renderRetrievePools();
  }
  await loadAssets().catch(e => toast(e.message, true));
  renderLibraries(); renderScoped();
  if (window.Canvas) Canvas.libraryChanged();
});
function selectLibrary(name) {
  $("scope-library").value = name; $("scope-library").dispatchEvent(new Event("change"));
}

// Watch assets until they are fully materialized, refreshing ASSETS so every
// view (ingest status, canvas nodes) can show text_ready before ready. An asset
// is listed only once the background ingest registers it, so a watched id may
// be missing from ASSETS for a while; the canvas keeps its spot meanwhile.
const WATCHED = new Map();   // asset id -> when watching started
const WATCH_LIMIT_MS = 10 * 60 * 1000;
let watchTimer = null;
function watchAssets(ids) {
  ids.forEach(id => WATCHED.set(id, Date.now()));
  if (!watchTimer) watchTimer = setTimeout(watchTick, 1200);
}
async function watchTick() {
  watchTimer = null;
  try { await loadAssets(); } catch { /* transient; retry */ }
  const byId = new Map(ASSETS.map(a => [a.id, a]));
  for (const [id, since] of [...WATCHED]) {
    const a = byId.get(id);
    if ((a && (a.materialization === "ready" || a.materialization == null)) || Date.now() - since > WATCH_LIMIT_MS) WATCHED.delete(id);
  }
  renderIngestStatus(); renderAssets();
  if (window.Canvas) Canvas.renderNodes();
  if (WATCHED.size) watchTimer = setTimeout(watchTick, 1500);
  else refresh().catch(() => {});
}

// ---- libraries ----------------------------------------------------------------
function renderLibraries() {
  const tb = $("library-table").querySelector("tbody"); tb.innerHTML = "";
  $("library-empty").hidden = LIBRARIES.length > 0;
  for (const library of LIBRARIES) {
    const tr = document.createElement("tr");
    if (library.name === $("scope-library").value) tr.className = "sel";
    tr.innerHTML = `
      <td><b>${esc(library.name)}</b>
          <div class="hint">${esc(library.description || "")}</div>
          ${library.content_database ? `<div class="mono">${esc(t("content"))}: ${esc(library.content_database)}</div>` : ""}</td>
      <td>${library.asset_count}</td>
      <td>${library.document_count}</td>
      <td>${library.chunk_count}</td>
      <td>${library.asset_pools.length}</td>
      <td>${library.sources.length}</td>
      <td><div class="actions">
        <button class="ghost mini" data-act="use" data-library="${esc(library.name)}">${esc(t("Select"))}</button>
        <button class="danger mini" data-act="delete" data-library="${esc(library.name)}">${esc(t("Delete"))}</button>
      </div></td>`;
    tb.appendChild(tr);
  }
}
$("library-table").addEventListener("click", async (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  const library = btn.dataset.library;
  try {
    if (btn.dataset.act === "use") return selectLibrary(library);
    if (!confirm(t('Delete asset library "{name}"?', { name: library }))) return;
    await api("DELETE", `/v1/libraries/${enc(library)}`);
    toast(t("Deleted {name}", { name: library }));
    await refresh();
  } catch (err) { toast(err.message, true); }
});
$("library-create").addEventListener("click", (e) => busy(e.target, t("Creating…"), async () => {
  const name = $("library-name").value.trim();
  if (!name) throw new Error(t("Name is required"));
  await api("POST", "/v1/libraries", { name, description: $("library-desc").value.trim() || null });
  toast(t("Created {name}", { name })); $("library-name").value = ""; $("library-desc").value = "";
  await refresh();
  selectLibrary(name);
}));

// ---- browser uploads ----------------------------------------------------------
// Files go to PUT /v1/libraries/{lib}/uploads/{path} as raw bodies, keeping
// their folder path, then POST /assets names them. A loose file is one asset; a
// dropped folder is named as a whole and the engine either ingests it as an OKF
// bundle or expands it into its supported files.
const isHidden = (path) => path.split("/").some(seg => seg.startsWith("."));
function stagedFromInput(input) {
  return [...input.files].map(f => ({ file: f, path: f.webkitRelativePath || f.name })).filter(s => !isHidden(s.path));
}
// Read files (and folders, recursively) out of a drop. Entries must be taken
// synchronously inside the drop event; the walk itself can be async.
async function stagedFromDrop(dt) {
  const entries = [...(dt.items || [])].filter(i => i.kind === "file")
    .map(i => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null)).filter(Boolean);
  if (!entries.length) return [...(dt.files || [])].map(f => ({ file: f, path: f.name }));
  const out = [];
  async function walk(entry) {
    if (entry.isFile) {
      const file = await new Promise((res, rej) => entry.file(res, rej));
      out.push({ file, path: entry.fullPath.replace(/^\/+/, "") });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do {
        batch = await new Promise((res, rej) => reader.readEntries(res, rej));
        for (const child of batch) await walk(child);
      } while (batch.length);
    }
  }
  for (const entry of entries) await walk(entry);
  return out.filter(s => !isHidden(s.path));
}
function putFile(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = e => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let data; try { data = JSON.parse(xhr.responseText); } catch { data = { detail: xhr.responseText }; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(errorDetail(data, xhr.status + " " + xhr.statusText)));
    };
    xhr.onerror = () => reject(new Error(t("Network error")));
    xhr.send(file);
  });
}

// A drop zone + file/folder pickers + staged list. `items` is [{file, path,
// progress, state, error}]; the owner reads it when the user commits.
class Uploader {
  constructor(el, onChange = () => {}) {
    this.el = el; this.items = []; this.onChange = onChange; this.locked = false;
    el.classList.add("uploader");
    el.addEventListener("dragover", e => { if (hasFiles(e)) { e.preventDefault(); e.stopPropagation(); this.zone()?.classList.add("over"); } });
    el.addEventListener("dragleave", () => this.zone()?.classList.remove("over"));
    el.addEventListener("drop", async e => {
      if (!hasFiles(e)) return;
      e.preventDefault(); e.stopPropagation(); this.zone()?.classList.remove("over");
      this.add(await stagedFromDrop(e.dataTransfer));
    });
    el.addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b || this.locked) return;
      if (b.dataset.pick) el.querySelector(`input[data-pick="${b.dataset.pick}"]`).click();
      if (b.dataset.rm != null) { this.items.splice(+b.dataset.rm, 1); this.render(); this.onChange(); }
      if (b.dataset.clear != null) this.clear();
    });
    el.addEventListener("change", e => {
      const input = e.target.closest("input[type=file]"); if (!input) return;
      this.add(stagedFromInput(input)); input.value = "";
    });
    this.render();
  }
  zone() { return this.el.querySelector(".drop"); }
  add(staged) {
    if (this.locked) return;
    const seen = new Set(this.items.map(i => i.path));
    for (const s of staged) if (!seen.has(s.path)) { this.items.push({ ...s, progress: 0, state: "queued" }); seen.add(s.path); }
    this.render(); this.onChange();
  }
  clear() { this.items = []; this.render(); this.onChange(); }
  render() {
    const total = this.items.reduce((n, i) => n + i.file.size, 0);
    const label = { queued: t("queued"), uploading: t("uploading…"), done: t("uploaded"), error: t("failed") };
    this.el.innerHTML = `
      <div class="drop">${esc(t("Drop files or folders here"))}
        <div class="btns">
          <button class="ghost mini" data-pick="files" type="button">${esc(t("Choose files"))}</button>
          <button class="ghost mini" data-pick="folder" type="button">${esc(t("Choose folder"))}</button>
        </div></div>
      <input type="file" multiple data-pick="files" />
      <input type="file" multiple webkitdirectory data-pick="folder" />
      ${this.items.length ? `<div class="staged">${this.items.map((it, i) => `
        <div class="ing-item"><span class="name">${esc(it.path)}<div class="bar"><i style="width:${Math.round(it.progress * 100)}%"></i></div>
          ${it.error ? `<div class="err">${esc(it.error)}</div>` : ""}</span>
          <span class="phase ${it.state === "done" ? "ready" : ""}">${esc(fmtBytes(it.file.size))} · ${esc(label[it.state])}</span>
          ${this.locked ? "" : `<button class="x" data-rm="${i}" type="button" title="${esc(t("Remove"))}">×</button>`}</div>`).join("")}</div>
        <div class="sum"><span>${esc(t("{n} file(s) · {size}", { n: this.items.length, size: fmtBytes(total) }))}</span>
          ${this.locked ? "" : `<button class="x" data-clear type="button">${esc(t("Clear"))}</button>`}</div>` : ""}`;
  }
  // Upload every staged file (3 at a time), then work out what to ingest.
  async upload(library) {
    this.locked = true; this.render();
    const results = new Array(this.items.length);
    let next = 0;
    const worker = async () => {
      while (next < this.items.length) {
        const i = next++, it = this.items[i];
        it.state = "uploading"; it.error = null; this.render();
        try {
          const url = `/v1/libraries/${enc(library)}/uploads/${it.path.split("/").map(enc).join("/")}`;
          results[i] = await putFile(url, it.file, p => {
            it.progress = p;
            const bar = this.el.querySelectorAll(".staged .bar i")[i]; if (bar) bar.style.width = Math.round(p * 100) + "%";
          });
          it.state = "done"; it.progress = 1;
        } catch (err) { it.state = "error"; it.error = err.message; }
        this.render();
      }
    };
    try { await Promise.all([worker(), worker(), worker()]); }
    finally { this.locked = false; this.render(); }
    const failed = this.items.filter(i => i.state === "error");
    if (failed.length) throw new Error(t("{n} upload(s) failed", { n: failed.length }));
    // Loose files are named one by one; a folder is named once, by its root.
    const names = [], skipped = [], roots = new Map();
    results.forEach((r, i) => {
      const path = this.items[i].path, slash = path.indexOf("/");
      if (slash < 0) { (r.supported ? names : skipped).push(r.supported ? r.name : path); return; }
      const root = r.name.slice(0, r.name.length - path.length) + path.slice(0, slash);
      roots.set(root, roots.get(root) || r.supported);
    });
    for (const [root, anySupported] of roots) (anySupported ? names : skipped).push(anySupported ? root : root.split("/").pop() + "/");
    return { names, skipped };
  }
}
function hasFiles(e) { return [...(e.dataTransfer?.types || [])].includes("Files"); }

// Upload (if any), then create the assets. Returns the AssetCreateResult.
async function ingestAssets(library, { uploader = null, filePaths = [], text = "", poolIds = [] }) {
  let names = [], skipped = [];
  if (uploader && uploader.items.length) ({ names, skipped } = await uploader.upload(library));
  if (skipped.length) toast(t("Skipped unsupported: {list}", { list: skipped.join(", ") }), true);
  const file_paths = [...filePaths, ...names];
  if (!file_paths.length && !text) throw new Error(t("Provide files, a folder, text or server paths"));
  const r = await api("POST", `/v1/libraries/${enc(library)}/assets`, { asset_pool_ids: poolIds, file_paths, text: text || null });
  if (uploader) uploader.clear();
  watchAssets(r.asset_ids);
  return r;
}

// ---- add assets (Libraries tab) -------------------------------------------------
function poolChecks(box, pools, checked = []) {
  box.innerHTML = pools.length
    ? pools.map(p => `<label><input type="checkbox" value="${esc(p.id)}" ${checked.includes(p.id) ? "checked" : ""} />
        ${esc(p.name || p.id)} <span class="mono">${esc(p.id)}</span></label>`).join("")
    : `<div class="empty">${esc(t("No asset pools in this library."))}</div>`;
}
function renderIngestPools() {
  const lib = scoped(); const box = $("ing-pools");
  poolChecks(box, (lib && lib.asset_pools) || [], checkedValues(box));
}
const ingestUploader = new Uploader($("ing-uploader"));
let ING_TRACKED = [];
$("ing-run").addEventListener("click", (e) => busy(e.target, t("Adding…"), async () => {
  const lib = scoped();
  if (!lib) throw new Error(t("Create or select an asset library first"));
  const text = $("ing-text").value.trim();
  const filePaths = $("ing-files").value.split(",").map(s => s.trim()).filter(Boolean);
  const r = await ingestAssets(lib.name, { uploader: ingestUploader, filePaths, text, poolIds: checkedValues($("ing-pools")) });
  toast(t("Added {n} asset(s): {status}", { n: r.asset_ids.length, status: t(r.status) }));
  $("ing-text").value = ""; $("ing-files").value = "";
  ING_TRACKED = r.asset_ids; renderIngestStatus();
  await refresh();
}));

// Show each just-added asset's ingest phase, so the user sees text become
// searchable (text_ready) before figures/graph finish (ready).
const PHASE_LABEL = {
  materializing: "materializing…",
  text_ready: "text-ready · searchable",
  ready: "ready",
};
const phaseLabel = (p) => t(PHASE_LABEL[p] || p);
function stopIngPoll() { ING_TRACKED = []; $("ing-status").innerHTML = ""; }
function renderIngestStatus() {
  const byId = new Map(ASSETS.map(a => [a.id, a]));
  $("ing-status").innerHTML = ING_TRACKED.map(id => {
    const a = byId.get(id);
    const phase = (a && a.materialization) || (WATCHED.has(id) ? "materializing" : "ready");
    return `<div class="ing-item"><span class="name">${esc(a ? assetName(a) : id)}</span>`
      + `<span class="phase ${esc(phase)}">${esc(phaseLabel(phase))}</span></div>`;
  }).join("");
}

// ---- assets -------------------------------------------------------------------
// Deleting takes everything the asset left behind: its stored content, its
// chunks, its graph vertices (or an OKF bundle's concepts), and citations of its
// chunks by remaining concepts. The engine refuses before changing anything if
// any of that cannot be done.
async function deleteAssets(lib, ids) {
  const names = ids.map(id => { const a = ASSETS.find(x => x.id === id); return a ? assetName(a) : id; });
  const what = ids.length === 1 ? `"${names[0]}"` : t("{n} assets", { n: ids.length });
  if (!confirm(t("Delete {what} from {lib}? Its content and everything indexed from it (chunks, OKF concepts) are removed. This cannot be undone.", { what, lib: lib.name }))) return false;
  const r = await api("DELETE", `/v1/libraries/${enc(lib.name)}/assets`, { asset_ids: ids });
  toast(t("Deleted {n} asset(s); removed {m} indexed record(s)", { n: r.removed.length, m: r.materializations_removed }));
  ids.forEach(id => AS_SELECTED.delete(id));
  return true;
}
const AS_SELECTED = new Set();
function assetRows() {
  const q = $("as-filter").value.trim().toLowerCase();
  return ASSETS.filter(a => !q || [a.name, a.id, a.origin].some(x => String(x || "").toLowerCase().includes(q)));
}
function renderAssets() {
  const lib = scoped(), rows = assetRows(), tb = $("as-table").querySelector("tbody");
  for (const id of [...AS_SELECTED]) if (!ASSETS.some(a => a.id === id)) AS_SELECTED.delete(id);
  $("as-empty").hidden = ASSETS.length > 0;
  $("as-count").textContent = ASSETS_TOTAL > ASSETS.length
    ? t("Showing {n} of {total}.", { n: ASSETS.length, total: ASSETS_TOTAL }) : t("{n} asset(s)", { n: ASSETS.length });
  const poolName = (id) => { const p = lib && lib.asset_pools.find(x => x.id === id); return p ? p.name || p.id : id; };
  tb.innerHTML = rows.map(a => {
    const phase = a.materialization || (WATCHED.has(a.id) ? "materializing" : "");
    return `<tr${AS_SELECTED.has(a.id) ? ' class="sel"' : ""}>
      <td><input type="checkbox" data-as="${esc(a.id)}" ${AS_SELECTED.has(a.id) ? "checked" : ""} /></td>
      <td><b>${esc(assetName(a))}</b><div class="mono" title="${esc(a.origin)}">${esc(a.origin)}</div></td>
      <td><span class="chip">${esc(a.kind)}</span>${a.media_type ? `<div class="mono">${esc(a.media_type)}</div>` : ""}</td>
      <td>${a.asset_pool_ids.map(id => `<span class="chip">${esc(poolName(id))}</span>`).join("") || '<span class="hint">—</span>'}</td>
      <td>${phase ? `<span class="phase ${esc(phase)}">${esc(phaseLabel(phase))}</span>` : '<span class="hint">—</span>'}</td>
      <td><div class="actions"><button class="danger mini" data-as-del="${esc(a.id)}">${esc(t("Delete"))}</button></div></td></tr>`;
  }).join("");
  $("as-all").checked = rows.length > 0 && rows.every(a => AS_SELECTED.has(a.id));
  $("as-delete").disabled = !AS_SELECTED.size;
  $("as-delete").textContent = t("Delete selected ({n})", { n: AS_SELECTED.size });
  renderNavCounts();
}
$("as-filter").addEventListener("input", renderAssets);
$("as-refresh").addEventListener("click", () => loadAssets().then(renderAssets).catch(e => toast(e.message, true)));
$("as-all").addEventListener("change", e => { assetRows().forEach(a => (e.target.checked ? AS_SELECTED.add(a.id) : AS_SELECTED.delete(a.id))); renderAssets(); });
$("as-table").addEventListener("change", e => {
  const box = e.target.closest("[data-as]"); if (!box) return;
  box.checked ? AS_SELECTED.add(box.dataset.as) : AS_SELECTED.delete(box.dataset.as);
  renderAssets();
});
$("as-table").addEventListener("click", e => {
  const b = e.target.closest("[data-as-del]"); if (!b) return;
  busy(b, t("Deleting…"), async () => { if (await deleteAssets(scoped(), [b.dataset.asDel])) await refresh(); });
});
$("as-delete").addEventListener("click", e => busy(e.target, t("Deleting…"), async () => {
  if (await deleteAssets(scoped(), [...AS_SELECTED])) await refresh();
}));

// ---- asset pools ------------------------------------------------------------
// Object sources store asset content for the whole library. They have no
// projection, so every pool uses the content source and none attaches it.
const isContentSource = (s) => !!s && s.type === "object";
const attachableSources = (lib) => ((lib && lib.sources) || []).filter(s => !isContentSource(s));
function sourceName(lib, id) { const s = lib.sources.find(s => s.id === id); return s ? (s.name || s.id) : id; }
const STATUS_CLASS = { ready: "ok", failed: "bad", pending: "warn" };
function sourceStatusChip(st) {
  const {label, cls} = SourceStatus.appearance(SourceStatus.source(st));
  const title = st.error || (st.extraction ? extractionTitle(st.extraction) : t(st.status));
  return `<span class="chip ${cls}" title="${esc(title)}">${esc(t(label))}</span>`;
}
function poolStatusChip(pool) {
  const {label, cls} = SourceStatus.appearance(SourceStatus.pool(pool));
  return `<span class="chip ${cls}">${esc(t(label))}</span>`;
}
function sourceChecks(box, sources, checked = []) {
  box.innerHTML = sources.length
    ? sources.map(s => `<label><input type="checkbox" value="${esc(s.id)}" ${checked.includes(s.id) ? "checked" : ""} />
        ${esc(s.name || s.id)} <span class="mono">${esc(s.database_id)}/${esc(s.collection_name)}</span>
        <span class="chip">${esc(s.type)}</span></label>`).join("")
    : `<div class="empty">${esc(t("No sources in this library. Create one under Sources."))}</div>`;
}
function renderPoolCreateSources() {
  const lib = scoped(); const box = $("pool-sources");
  sourceChecks(box, attachableSources(lib), checkedValues(box));
}
function sourceStatusChips(lib, pool) {
  return pool.source_statuses.map(st =>
  `<span class="source-status"><b>${esc(sourceName(lib, st.source_id))}</b> ${sourceStatusChip(st)} ${SourceServing.chip(st)}</span>`).join("") || `<span class="hint">${esc(t("none"))}</span>`;
}
// A graph source extracting documents into OKF: where its extraction stands.
function extractionState(x) {
  if (x.state === "running") return ["Extracting…", "warn"];
  if (x.state === "queued") return [x.active && x.active.not_before ? "Extraction waiting" : "Extraction queued", "warn"];
  if (x.last && x.last.state === "failed" && x.outdated) return ["Extraction failed", "bad"];
  if (x.outdated) return ["Extraction outdated", "warn"];
  return x.bundle_asset_id ? ["Extracted", "ok"] : ["Not extracted", ""];
}
function extractionTitle(x) {
  const lines = [t("Trigger") + ": " + t(x.trigger)];
  if (x.trigger_options && x.trigger_options.cron) lines.push(`cron: ${x.trigger_options.cron} (${x.trigger_options.timezone})`);
  if (x.next_run) lines.push(t("Next run") + ": " + new Date(x.next_run).toLocaleString());
  if (x.active && x.active.not_before) lines.push(t("Starts after") + ": " + new Date(x.active.not_before).toLocaleTimeString());
  if (x.last) lines.push(t("Last") + `: ${t(x.last.state)}` + (x.last.finished_at ? " · " + new Date(x.last.finished_at).toLocaleString() : "")
    + (x.last.result && x.last.result.concepts != null ? " · " + t("{n} concepts", { n: x.last.result.concepts }) : ""));
  if (x.last && x.last.error) lines.push(x.last.error);
  return lines.join("\n");
}
function extractionChip(st) {
  const x = st.extraction; if (!x) return "";
  const [label, cls] = extractionState(x);
  return `<span class="chip ${cls}" title="${esc(extractionTitle(x))}">⚙ ${esc(t(label))}</span>`;
}
const extractingStatuses = (pool) => pool.source_statuses.filter(st => st.extraction);
async function extractNow(lib, poolId, sourceId) {
  const res = await fetch(API + `/v1/libraries/${enc(lib.name)}/asset_pools/${enc(poolId)}/extractions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_id: sourceId }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(errorDetail(data, res.status + " " + res.statusText));
  toast(res.status === 202 ? t("Extraction started") : t("An extraction is already {state}; it will cover the latest documents", { state: t(data.state) }));
  await refresh();
}
function renderPools() {
  const lib = scoped();
  const pools = (lib && lib.asset_pools) || [];
  const tb = $("pool-table").querySelector("tbody"); tb.innerHTML = "";
  $("pool-empty").hidden = pools.length > 0;
  for (const p of pools) {
    const tr = document.createElement("tr");
    if (p.id === PM_POOL) tr.className = "sel";
    tr.innerHTML = `
      <td><b>${esc(p.name || p.id)}</b><div class="mono">${esc(p.id)}</div>${poolStatusChip(p)}</td>
      <td>${p.asset_ids.length}</td>
      <td>${sourceStatusChips(lib, p)}</td>
      <td>${p.revision}</td>
      <td><div class="actions">
        ${extractingStatuses(p).map(st => `<button class="ghost mini" data-act="extract" data-pool="${esc(p.id)}" data-source="${esc(st.source_id)}"
          title="${esc(sourceName(lib, st.source_id))}">${esc(t("Extract now"))}</button>`).join("")}
        <button class="ghost mini" data-act="manage" data-pool="${esc(p.id)}">${esc(t("Manage"))}</button>
        <button class="danger mini" data-act="delete" data-pool="${esc(p.id)}">${esc(t("Delete"))}</button>
      </div></td>`;
    tb.appendChild(tr);
  }
}
async function deletePool(lib, pool) {
  if (!confirm(t('Delete asset pool "{pool}" from {lib}? Assets stay in the library.', { pool, lib: lib.name }))) return false;
  await api("DELETE", `/v1/libraries/${enc(lib.name)}/asset_pools/${enc(pool)}`);
  toast(t("Deleted pool {pool}", { pool }));
  return true;
}
$("pool-table").addEventListener("click", async (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  const lib = scoped(), pool = btn.dataset.pool;
  try {
    if (btn.dataset.act === "manage") return openPoolManager(pool);
    if (btn.dataset.act === "extract") return await busy(btn, t("Starting…"), () => extractNow(lib, pool, btn.dataset.source));
    if (!(await deletePool(lib, pool))) return;
    if (PM_POOL === pool) closePoolManager();
    await refresh();
  } catch (err) { toast(err.message, true); }
});
async function createPool(lib, { id, name, sources, metadata }) {
  if (!id) throw new Error(t("Pool ID is required"));
  await api("POST", `/v1/libraries/${enc(lib.name)}/asset_pools`, { id, name: name || id, sources, metadata });
  toast(t("Created pool {pool}", { pool: id }));
}
$("pool-create").addEventListener("click", (e) => busy(e.target, t("Creating…"), async () => {
  const lib = scoped();
  if (!lib) throw new Error(t("Create or select an asset library first"));
  await createPool(lib, {
    id: $("pool-id").value.trim(), name: $("pool-name").value.trim(),
    sources: checkedValues($("pool-sources")), metadata: parseJsonObject($("pool-meta").value, t("Metadata")),
  });
  $("pool-id").value = ""; $("pool-name").value = ""; $("pool-meta").value = "";
  $("pool-sources").querySelectorAll("input").forEach(i => (i.checked = false));
  await refresh();
}));
// Shared with the canvas: replace a pool's sources / add assets to a pool.
async function setPoolSources(lib, poolId, sources) {
  if (!sources.length) throw new Error(t("A pool needs at least one source; delete the pool instead"));
  const current = LIBRARIES.find(item => item.id === lib.id) || lib;
  const known = new Set(attachableSources(current).map(source => source.id));
  if (sources.some(source => !known.has(typeof source === "string" ? source : source.source_id))) {
    await refresh();
    throw new Error(t("Sources changed. Review the current source selection and try again."));
  }
  await api("PUT", `/v1/libraries/${enc(lib.name)}/asset_pools/${enc(poolId)}/sources`, { sources });
  toast(t("Updated sources of {pool}; re-indexing in the background", { pool: poolId }));
}
// Dedicated binding update: no attachment changes and no replacement workflow.
async function setSourceServingState(lib, poolId, sourceId, state) {
  return api("PATCH", `/v1/libraries/${enc(lib.name)}/asset_pools/${enc(poolId)}/sources/${enc(sourceId)}`,
    {serving_state: state});
}
document.addEventListener("change", async e => {
  const select = e.target.closest("select[data-serving-source]"); if (!select) return;
  const lib = LIBRARIES.find(item => item.name === select.dataset.servingLibrary);
  const source = lib?.sources.find(item => item.id === select.dataset.servingSource);
  const pool = lib?.asset_pools.find(item => item.id === select.dataset.servingPool);
  const previous = select.dataset.servingState, next = select.value;
  if (!lib || !source || !pool || next === previous) { select.value = previous; return; }
  if (next === "DEPRECATED" && !confirm(t('Set "{source}" to DEPRECATED in "{pool}"? Retrieval and syncing stop for this binding; indexed data is kept.',
    {source: source.name || source.id, pool: pool.name || pool.id}))) { select.value = previous; return; }
  select.disabled = true;
  try {
    await setSourceServingState(lib, pool.id, source.id, next);
    await refresh();
  } catch (err) { select.value = previous; toast(err.message, true); }
  finally { if (select.isConnected) select.disabled = false; }
});
async function addAssetsToPool(lib, poolId, assetIds) {
  if (!assetIds.length) throw new Error(t("Select assets to add"));
  await api("POST", `/v1/libraries/${enc(lib.name)}/asset_pools/${enc(poolId)}/assets`, { asset_ids: assetIds });
  toast(t("Added {n} asset(s) to {pool}; indexing in the background", { n: assetIds.length, pool: poolId }));
}

// Manage panel: one pool's sources (add/remove) and its assets (add).
let PM_POOL = null;
function managedPool() { const lib = scoped(); return lib && lib.asset_pools.find(p => p.id === PM_POOL); }
function openPoolManager(poolId) {
  PM_POOL = poolId;
  $("pm-card").hidden = false; $("pm-title").textContent = poolId;
  renderPools(); renderPoolManagerSources(); renderPoolManagerAssets();
  $("pm-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function closePoolManager() { PM_POOL = null; $("pm-card").hidden = true; renderPools(); }
$("pm-close").addEventListener("click", closePoolManager);
function renderPoolManagerSources() {
  const lib = scoped(), pool = managedPool(); if (!pool) return;
  sourceChecks($("pm-sources"), attachableSources(lib), pool.source_statuses.map(s => s.source_id));
}
function renderPoolManagerAssets() {
  const pool = managedPool(), box = $("pm-assets"); if (!pool) return;
  const members = new Set(pool.asset_ids);
  box.innerHTML = ASSETS.length
    ? ASSETS.map(a => {
        const inPool = members.has(a.id);
        return `<label title="${esc(a.origin)}"><input type="checkbox" value="${esc(a.id)}" ${inPool ? "checked disabled" : ""} />
          ${esc(assetName(a))} <span class="chip ${inPool ? "ok" : ""}">${inPool ? esc(t("in pool")) : esc(a.kind)}</span></label>`;
      }).join("")
      + (ASSETS_TOTAL > ASSETS.length ? `<div class="hint">${esc(t("Showing {n} of {total}.", { n: ASSETS.length, total: ASSETS_TOTAL }))}</div>` : "")
    : `<div class="empty">${esc(t("This library has no assets yet. Add some under Libraries."))}</div>`;
}
$("pm-sources-save").addEventListener("click", (e) => busy(e.target, t("Saving…"), async () => {
  const lib = scoped(), pool = managedPool(); if (!pool) return;
  await setPoolSources(lib, pool.id, [...$("pm-sources").querySelectorAll("input:checked")].map(i => i.value));
  await refresh();
}));
$("pm-assets-add").addEventListener("click", (e) => busy(e.target, t("Adding…"), async () => {
  const lib = scoped(), pool = managedPool(); if (!pool) return;
  await addAssetsToPool(lib, pool.id, checkedValues($("pm-assets")));
  await refresh();
}));

// ---- sources ------------------------------------------------------------------
function databaseOptions() { return DATABASES.map(d => [d.id, `${d.id} (${d.type}/${d.backend})`]); }
function renderSourceDbOptions() {
  fillSelect($("src-db"), databaseOptions());
  SOURCE_EDITOR = SourceOptions.mount($("src-options"), {
    type: DATABASES.find(database => database.id === $("src-db").value)?.type || "",
    state: SOURCE_OPTIONS, models: SOURCE_MODELS,
  });
}
$("src-db").addEventListener("change", renderSourceDbOptions);
function renderSources() {
  const lib = scoped();
  const sources = (lib && lib.sources) || [];
  const tb = $("src-table").querySelector("tbody"); tb.innerHTML = "";
  $("src-empty").hidden = sources.length > 0;
  for (const s of sources) {
    const isContent = s.id === lib.default_content_source_id;
    const opts = Object.keys(s.operator_options || {}).length ? `<div class="mono">${esc(JSON.stringify(s.operator_options))}</div>` : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${esc(s.name || s.id)}</b> ${isContent ? `<span class="chip">${esc(t("default content"))}</span>` : ""}
          <div class="mono">${esc(s.id)}</div>${opts}</td>
      <td><span class="chip">${esc(s.type)}</span></td>
      <td>${esc(s.database_id)}<div class="mono">${esc(s.collection_name)}</div></td>
      <td>${SourceServing.sourceBindings(lib, s.id)}</td>
      <td>${s.reconciled ? `<span class="chip ok">${esc(t("reconciled"))}</span>`
            : `<span class="chip bad" title="${esc(s.reconciliation_error || "")}">${esc(t("unreconciled"))}</span>`}</td>
      <td><div class="actions"><button class="danger mini" data-src="${esc(s.id)}" data-name="${esc(s.name || s.id)}">${esc(t("Delete"))}</button></div></td>`;
    tb.appendChild(tr);
  }
}
async function deleteSource(lib, id, name) {
  if (!confirm(t('Detach source "{name}" from {lib}? The external collection is left untouched.', { name, lib: lib.name }))) return false;
  await api("DELETE", `/v1/libraries/${enc(lib.name)}/sources/${enc(id)}`);
  toast(t("Removed source {name}", { name }));
  return true;
}
$("src-table").addEventListener("click", async (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  try { if (await deleteSource(scoped(), btn.dataset.src, btn.dataset.name)) await refresh(); }
  catch (err) { toast(err.message, true); }
});
async function createSource(lib, { name, database_id, collection_name, operator_options }) {
  if (!name) throw new Error(t("Name is required"));
  if (!database_id) throw new Error(t("Register a database first"));
  const s = await api("POST", `/v1/libraries/${enc(lib.name)}/sources`, { name, database_id, collection_name, operator_options });
  toast(t("Created source {name}", { name }));
  return s;
}
$("src-create").addEventListener("click", (e) => busy(e.target, t("Creating…"), async () => {
  const lib = scoped();
  if (!lib) throw new Error(t("Create or select an asset library first"));
  await createSource(lib, {
    name: $("src-name").value.trim(), database_id: $("src-db").value, collection_name: $("src-collection").value.trim(),
    operator_options: SOURCE_EDITOR.read(),
  });
  $("src-name").value = ""; $("src-collection").value = "";
  SOURCE_OPTIONS = SourceOptions.defaults();
  await refresh();
}));

// ---- databases ----------------------------------------------------------------
let BACKENDS = [];           // [{database_type, backends}]
let DB_EDITING = null;       // id being edited, or null when registering
const DB_CHECKS = {};        // id -> DatabaseCheck | "checking"
async function loadDatabases() {
  if (!BACKENDS.length) {
    BACKENDS = await api("GET", "/v1/databases/backends");
    fillSelect($("db-type"), BACKENDS.map(b => [b.database_type, b.database_type]));
    renderDbBackends();
  }
  DATABASES = await api("GET", "/v1/databases");
  renderDatabases(); renderSourceDbOptions(); renderNavCounts();
}
function renderDbBackends() {
  const tp = BACKENDS.find(b => b.database_type === $("db-type").value);
  fillSelect($("db-backend"), ((tp && tp.backends) || []).map(b => [b, b]));
}
$("db-type").addEventListener("change", renderDbBackends);
function renderDatabases() {
  const tb = $("db-table").querySelector("tbody"); tb.innerHTML = "";
  $("db-empty").hidden = DATABASES.length > 0;
  for (const d of DATABASES) {
    const c = DB_CHECKS[d.id];
    const st = c === "checking" ? `<span class="chip warn">${esc(t("checking…"))}</span>`
      : !c ? `<span class="hint">${esc(t("unchecked"))}</span>`
      : c.reachable ? `<span class="chip ok">${esc(t("reachable"))}</span>`
      : `<span class="chip bad" title="${esc(c.error || "")}">${esc(t("unreachable"))}</span>${c.error ? `<div class="mono">${esc(c.error).slice(0, 160)}</div>` : ""}`;
    const tr = document.createElement("tr");
    if (d.id === DB_EDITING) tr.className = "sel";
    tr.innerHTML = `
      <td><b>${esc(d.id)}</b><div><span class="chip">${esc(d.type)}</span><span class="chip">${esc(d.backend)}</span></div>
          <div class="hint">${esc(d.description || "")}</div></td>
      <td><div class="mono">${esc(JSON.stringify(d.options))}</div></td>
      <td>${d.in_use_by.map(u => `<span class="chip">${esc(u)}</span>`).join("") || '<span class="hint">—</span>'}</td>
      <td>${st}</td>
      <td><div class="actions">
        <button class="ghost mini" data-act="check" data-db="${esc(d.id)}">${esc(t("Check"))}</button>
        <button class="ghost mini" data-act="edit" data-db="${esc(d.id)}">${esc(t("Edit"))}</button>
        <button class="danger mini" data-act="delete" data-db="${esc(d.id)}">${esc(t("Delete"))}</button>
      </div></td>`;
    tb.appendChild(tr);
  }
}
async function checkDatabase(id) {
  DB_CHECKS[id] = "checking"; renderDatabases();
  try { DB_CHECKS[id] = await api("POST", `/v1/databases/${enc(id)}/check`); }
  catch (err) { DB_CHECKS[id] = { reachable: false, error: err.message }; }
  renderDatabases();
}
$("db-check-all").addEventListener("click", () => Promise.all(DATABASES.map(d => checkDatabase(d.id))));
function resetDbFormLabels() {
  $("db-form-title").textContent = DB_EDITING ? t("Edit database {id}", { id: DB_EDITING }) : t("Register database");
  $("db-save").textContent = DB_EDITING ? t("Save changes") : t("Register");
}
function resetDbForm() {
  DB_EDITING = null; resetDbFormLabels();
  $("db-cancel").hidden = true; $("db-id").disabled = false; $("db-type").disabled = false;
  $("db-id").value = ""; $("db-options").value = ""; $("db-desc").value = "";
  renderDatabases();
}
$("db-cancel").addEventListener("click", resetDbForm);
$("db-table").addEventListener("click", async (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  const id = btn.dataset.db, d = DATABASES.find(x => x.id === id);
  try {
    if (btn.dataset.act === "check") return checkDatabase(id);
    if (btn.dataset.act === "edit") {
      DB_EDITING = id; resetDbFormLabels();
      $("db-cancel").hidden = false;
      $("db-id").value = id; $("db-id").disabled = true;
      $("db-type").value = d.type; $("db-type").disabled = true;   // the type cannot change
      renderDbBackends(); $("db-backend").value = d.backend;
      $("db-options").value = JSON.stringify(d.options, null, 2);
      $("db-desc").value = d.description || "";
      renderDatabases(); return;
    }
    if (!confirm(t('Unregister database "{id}"?', { id }))) return;
    await api("DELETE", `/v1/databases/${enc(id)}`);
    delete DB_CHECKS[id];
    if (DB_EDITING === id) resetDbForm();
    toast(t("Removed database {id}", { id }));
    await loadDatabases();
  } catch (err) { toast(err.message, true); }
});
$("db-save").addEventListener("click", (e) => busy(e.target, t("Saving…"), async () => {
  const options = parseJsonObject($("db-options").value, t("Options"));
  const backend = $("db-backend").value, description = $("db-desc").value.trim();
  if (DB_EDITING) {
    const id = DB_EDITING;
    await api("PATCH", `/v1/databases/${enc(id)}`, { backend, options, description });
    delete DB_CHECKS[id];
    toast(t("Updated {id}", { id })); resetDbForm();
  } else {
    const id = $("db-id").value.trim();
    if (!id) throw new Error(t("ID is required"));
    await api("POST", "/v1/databases", { id, type: $("db-type").value, backend, options, description });
    toast(t("Registered {id}", { id })); resetDbForm();
  }
  await loadDatabases();
}));

// ---- models -------------------------------------------------------------------
// "Available" means the configured model is something the engine can run: for a
// local backend, a prepared workspace model of that kind; missing artifacts must
// be exported beforehand. Remote endpoints are configured but not dialed here.
// Mirrors config.LOCAL_MODEL_BACKENDS: providers that load a workspace model directory.
const LOCAL_MODEL_BACKENDS = ["llamaindex_openvino", "openvino_genai", "native_openvino_gme"];
const isLocal = (opt) => LOCAL_MODEL_BACKENDS.includes(opt.backend);
const MODELS = {};   // type -> {opt} | {err}
function findConfigured(opt) {
  const id = opt.model_id || "", base = id.split("/").pop();
  return opt.models.find(m => m.name === id)
    || opt.models.find(m => m.name.split("/").pop() === base || (m.path || "").split("/").pop() === base);
}
function modelStatus(opt) {
  if (!isLocal(opt)) return opt.api_base ? ["ok", t("remote endpoint configured ({url}); not probed", { url: opt.api_base })]
                                         : ["bad", t("remote backend with no API base")];
  const m = findConfigured(opt);
  if (!m) return ["bad", t('configured model "{model}" not found in {dir}', { model: opt.model_id, dir: opt.workspace })];
  return m.ready ? ["ok", t("available · exported")] : ["bad", t("not prepared · export before use")];
}
function renderModel(cardId, entry) {
  const body = $(cardId).querySelector(".body");
  if (!entry) return;
  if (entry.err) { body.innerHTML = `<div class="status-line"><span class="dot bad"></span>${esc(t("unavailable"))}</div><div class="mono">${esc(entry.err)}</div>`; return; }
  const opt = entry.opt;
  const [cls, msg] = modelStatus(opt);
  const conf = findConfigured(opt);
  body.innerHTML = `
    <div class="status-line"><span class="dot ${cls}"></span>${esc(msg)}</div>
    <dl class="kv">
      <dt>${esc(t("Model"))}</dt><dd>${esc(opt.model_id || "—")}</dd>
      <dt>${esc(t("Backend"))}</dt><dd>${esc(opt.backend)} <span class="hint">(${esc(opt.backends.join(", "))})</span></dd>
      <dt>${esc(t("Device"))}</dt><dd>${esc(opt.device || "—")}</dd>
      ${opt.api_base ? `<dt>${esc(t("API base"))}</dt><dd>${esc(opt.api_base)}</dd>` : ""}
      <dt>${esc(t("Workspace"))}</dt><dd>${esc(opt.workspace || "—")}</dd>
    </dl>
    <label>${esc(t("Models the engine can run ({n})", { n: opt.models.length }))}</label>
    <table><thead><tr><th>${esc(t("Name"))}</th><th>${esc(t("State"))}</th></tr></thead><tbody>
      ${opt.models.map(m => `<tr ${m === conf ? 'class="sel"' : ""}><td>${esc(m.name)}${m === conf ? ` <span class="chip">${esc(t("configured"))}</span>` : ""}
        <div class="mono">${esc(m.path || "")}</div></td>
        <td>${m.ready ? `<span class="chip ok">${esc(t("exported"))}</span>` : `<span class="chip warn">${esc(t("not exported"))}</span>`}</td></tr>`).join("")
        || `<tr><td colspan="2" class="empty">${esc(t("None found."))}</td></tr>`}
    </tbody></table>
    <button class="ghost mini" style="margin-top:12px" data-refresh-models>${esc(t("Re-check"))}</button>`;
}
function renderModels() { renderModel("model-embedding", MODELS.embedding); renderModel("model-reranker", MODELS.reranker); renderNavCounts(); }
async function loadModels() {
  await Promise.all(["embedding", "reranker"].map(async type => {
    try {
      MODELS[type] = { opt: await api("GET", `/v1/models/${type}`) };
      if (type === "reranker") { RERANKERS = MODELS[type].opt; renderRerankerOptions(); }
    } catch (err) { MODELS[type] = { err: err.message }; }
  }));
  renderModels();
}
document.querySelector('[data-section="models"]').addEventListener("click", e => {
  if (e.target.closest("[data-refresh-models]")) loadModels().catch(err => toast(err.message, true));
});

// ---- retrieve -------------------------------------------------------------------
const ALL_POOLS = "";
function renderRetrievePools() {
  const lib = LIBRARIES.find(l => l.name === $("q-library").value);
  const pools = (lib && lib.asset_pools) || [];
  fillSelect($("q-pool"), [[ALL_POOLS, t("All pools ({n})", { n: pools.length })],
    ...pools.map(p => [p.id, `${p.name || p.id} (${p.id})`])]);
  GraphView.syncPools($("q-pool").value || undefined);
}
$("q-library").addEventListener("change", () => {
  GraphView.clearTraces(); renderRetrievePools();
  if ($("scope-library").value !== $("q-library").value) selectLibrary($("q-library").value);
});
$("q-pool").addEventListener("change", () => { if ($("q-pool").value) GraphView.syncPools($("q-pool").value); });
// What each retrieval type does, shown under the picker.
const TYPE_HINTS = {
  rrf: "Fuses vector, BM25 and graph results by reciprocal rank. A pool without a graph source falls back to vector similarity.",
  vectorsimilarity: "Dense embedding similarity over the pool's chunks.",
  bm25: "Keyword (BM25) match over the pool's chunks.",
  graph: "Seeds OKF concepts from the query and walks the concept graph to their source chunks. Needs a graph and a vector source.",
};
const TRACED_TYPES = ["rrf", "graph"];
const MODALITY_LABELS = { document: "Document", video: "Video", image: "Image", audio: "Audio" };
const selectedModalities = () => checkedValues($("q-modalities"));
const mediaSearch = () => selectedModalities().some(target => target !== "document");
function renderModalities() {
  const targets = selectedModalities();
  $("q-modalities-value").textContent = targets.map(target => t(MODALITY_LABELS[target])).join(", ");
  $("q-type").disabled = !targets.includes("document");
  $("q-topk-label").textContent = t("Retrieve top-k (per source)");
  renderRerankerOptions();
  renderTypeHint();
}
$("q-modalities").addEventListener("change", e => {
  const changed = e.target;
  if (changed.type !== "checkbox") return;
  if (!selectedModalities().length) changed.checked = true;
  renderModalities();
});
function renderTypeHint() {
  $("q-type-hint").textContent = t(selectedModalities().includes("document")
    ? TYPE_HINTS[$("q-type").value] || ""
    : "Media search uses a vector projection for each selected modality, optionally narrowed to the selected pool. Top-k applies to each source.");
  if (typeof renderFlow === "function") renderFlow();
}
$("q-type").addEventListener("change", renderTypeHint);
// Open the Retrieve tab aimed at one library (and optionally one pool).
function retrieveFrom(library, pool = ALL_POOLS) {
  $("q-library").value = library; renderRetrievePools(); $("q-pool").value = pool;
  if (pool) GraphView.syncPools(pool);
  showTab("retrieve"); $("q-text").focus();
}
// Post-processing: rerank (engine default or a local model), the sentence
// window (`metadata_replace`: each chunk's text becomes its stored window), or none.
const NO_RERANK = "__none__", WINDOW = "__window__";
function renderRerankerOptions() {
  const media = mediaSearch();
  const mediaId = RERANKERS && RERANKERS.media_model_id ? ` (${RERANKERS.media_model_id})` : "";
  const textId = RERANKERS && RERANKERS.model_id ? ` (${RERANKERS.model_id})` : "";
  const opts = [["", (media ? t("Media default") + mediaId : t("Engine default") + textId)]];
  // VL reranker packages are all served by the media default above; listing
  // each exported variant (fp16, int8, ...) would only duplicate that entry.
  const local = RERANKERS && isLocal(RERANKERS)
    ? RERANKERS.models.filter(m => m.backend !== "openvino_vl") : [];
  fillSelect($("q-reranker"), opts.concat(local.map(m => [m.name, m.name]),
    [[WINDOW, t("Sentence window (no reranking)")], [NO_RERANK, t("No reranking")]]));
  fillSelect($("q-rerank-backend"), [["", t("Engine default") + (RERANKERS && RERANKERS.backend ? ` (${RERANKERS.backend})` : "")],
    ...((RERANKERS && RERANKERS.backends) || []).map(b => [b, b])]);
}
const reranking = () => ![NO_RERANK, WINDOW].includes($("q-reranker").value);

// Build the /v1/blob URL for an image chunk from its retrieved metadata.
// Note: a chunk's metadata.source_id is the asset_pool_id, but /v1/blob's
// source_id means a content-source UUID -- passing it 404s. Blobs are
// content-addressed, so omitting it lets the reader resolve by media_key.
function blobUrl(m) {
  const p = new URLSearchParams({ library: m.library, media_key: m.media_key });
  return "/v1/blob?" + p.toString();
}

$("q-results").addEventListener("click", e => {
  const chip = e.target.closest("[data-via]"); if (chip) GraphView.focus(chip.dataset.viaPool, chip.dataset.via);
  const exclude = e.target.closest("[data-exclude]");
  if (exclude) {
    const ids = $("q-exclude").value.split(/[\s,]+/).filter(Boolean);
    if (!ids.includes(exclude.dataset.exclude)) $("q-exclude").value = [...ids, exclude.dataset.exclude].join("\n");
    $("q-advanced").open = true;
    toast(t("Excluded {id} from the next retrievals", { id: exclude.dataset.exclude }));
  }
});
$("q-topk").addEventListener("input", e => ($("q-topk-v").textContent = e.target.value));
$("q-topn").addEventListener("input", e => ($("q-topn-v").textContent = e.target.value));

// The last result is kept so a language switch can redraw it.
let LAST_RESULT = null;
const TYPE_LABEL = { rrf: "RRF (vector + BM25 + graph)", vectorsimilarity: "Vector similarity", bm25: "BM25", graph: "Graph" };
function renderResults() {
  const box = $("q-results");
  if (!LAST_RESULT) return "";
  const { r, pool, type, targets } = LAST_RESULT;
  const media = targets.some(target => target !== "document");
  const scope = media
    ? `${r.libraries.join(", ")} · ${pool === ALL_POOLS ? t("all pools") : pool} · ${targets.map(target => t(MODALITY_LABELS[target])).join(", ")}`
    : `${r.libraries.join(", ")} · ${pool === ALL_POOLS ? t("all pools") : pool} · ${t(TYPE_LABEL[type] || type)}`;
  // chunk id -> [[pool, concept id]] that brought it in through the graph.
  const via = new Map();
  for (const tr of r.graph_traces || [])
    for (const c of tr.concepts) for (const cid of c.hit_chunk_ids)
      (via.get(cid) || via.set(cid, []).get(cid)).push([tr.asset_pool_id, c.id]);
  $("q-summary").textContent = t("{n} of {total} · {scope}", { n: r.chunks.length, total: r.retrieved_chunks.length, scope });
  box.innerHTML = r.chunks.length ? "" : `<div class="empty">${esc(t("No results."))}</div>`;
  r.chunks.forEach((c, i) => {
    const el = document.createElement("div"); el.className = "result";
    const m = c.metadata || {};
    const src = m.file_name || m.library || c.id;
    const isImg = m.kind === "image" && m.media_key && m.library;
    const isVid = m.kind === "video" && m.media_key && m.library;
    const pageInfo = (m.page != null) ? ` · p.${esc(m.page)}` : "";
    const poolInfo = m.source_id ? ` · <span class="chip">${esc(m.source_id)}</span>` : "";
    let bodyHtml;
    if (isImg) {
      const url = blobUrl(m);
      const cap = c.text ? `<div class="cap">${esc(c.text)}</div>` : "";
      bodyHtml = `<div class="fig"><a href="${esc(url)}" target="_blank" rel="noopener">`
        + `<img src="${esc(url)}" alt="${esc(c.text || "figure")}" loading="lazy" /></a></div>${cap}`;
    } else if (isVid) {
      // A segment result carries t_start_ms/t_end_ms; a media fragment starts
      // playback at the segment instead of the top of the recording.
      const t0 = m.t_start_ms != null ? m.t_start_ms / 1000 : null;
      const t1 = m.t_end_ms != null ? m.t_end_ms / 1000 : null;
      const frag = t0 != null ? `#t=${t0}${t1 != null ? "," + t1 : ""}` : "";
      const url = blobUrl(m) + frag;
      const cap = c.text ? `<div class="cap">${esc(c.text)}</div>` : "";
      bodyHtml = `<div class="fig"><video controls preload="metadata" src="${esc(url)}"></video></div>${cap}`;
    } else {
      bodyHtml = `<div class="txt">${esc(c.text)}</div>`;
    }
    const concepts = via.get(c.id) || [];
    const viaHtml = concepts.length ? `<div class="via">${esc(t("via concepts"))}: ${concepts.slice(0, 8).map(([p, id]) =>
      `<span class="chip" data-via-pool="${esc(p)}" data-via="${esc(id)}">${esc(GraphView.titleOf(p, id))}</span>`).join("")}</div>` : "";
    const rank = media ? (m.rank || i + 1) : i + 1;
    const modality = media && m.target_media ? ` · ${esc(t(MODALITY_LABELS[m.target_media] || m.target_media))}` : "";
    const kindChip = (isImg || isVid) ? ` · <span class="kind">${esc(t(m.kind))}</span>` : "";
    el.innerHTML = `<div class="top"><span>#${rank} · ${esc(src)}${modality}`
      + `${kindChip}${pageInfo}${poolInfo}</span>`
      + `<span class="score">${(c.score ?? 0).toFixed(5)}`
      + ` <button class="ghost mini" data-exclude="${esc(c.id)}" title="${esc(t("Exclude this chunk from the next retrievals"))}">⊘</button></span></div>${bodyHtml}${viaHtml}`;
    box.appendChild(el);
  });
  return scope;
}
// The pipeline line above the form, for the selected type and reranker.
const FLOW = { rrf: ["vector", "+", "BM25", "+", "graph", "→", "RRF"], vectorsimilarity: ["vector"], bm25: ["BM25"], graph: ["seed concepts", "→", "walk graph", "→", "source chunks"] };
function renderFlow() {
  const steps = selectedModalities().includes("document")
    ? [...(FLOW[$("q-type").value] || [])] : ["vector"];
  if (selectedModalities().includes("document") && mediaSearch()) steps.push("+", "vector");
  if (reranking()) steps.push("→", "rerank");
  if ($("q-reranker").value === WINDOW) steps.push("→", "sentence window");
  $("q-flow").innerHTML = steps.map(s => ["+", "→"].includes(s) ? esc(s) : `<span class="step">${esc(t(s))}</span>`).join("");
}
$("q-reranker").addEventListener("change", renderFlow);

// Retrieve and rerank with the form's settings; show the results and graph
// trace and return the response. The chat (chat.js) sends its chunks as context.
async function runRetrieval(query) {
  const library = $("q-library").value, pool = $("q-pool").value;
  if (!library) throw new Error(t("Create or select an asset library first"));
  if (!query) throw new Error(t("Enter a query"));
  const reranker = $("q-reranker").value, type = $("q-type").value;
  const targets = selectedModalities();
  const field = (id) => $(id).value.trim();
  const body = {
    query, libraries: [library],
    asset_pool_ids: pool === ALL_POOLS ? [] : [pool],   // empty = every pool in the library
    top_k: +$("q-topk").value,
    exclude_chunk_ids: field("q-exclude").split(/[\s,]+/).filter(Boolean),
  };
  if (targets.length !== 4) body.target_media = targets;
  if (targets.includes("document")) {
    body.retriever_type = type;
    body.include_graph_trace = TRACED_TYPES.includes(type);   // drives the concept graph highlights
  }
  if (reranker === WINDOW) body.postprocess = { processor_type: "metadata_replace" };
  else if (reranker !== NO_RERANK) {
    body.postprocess = { processor_type: "reranker", top_n: +$("q-topn").value };
    if (field("q-rerank-query")) body.postprocess.query = field("q-rerank-query");
    // Unset fields fall back to the engine's reranker configuration.
    const model = Object.fromEntries(Object.entries({
      model_id: field("q-rerank-model") || reranker, backend: field("q-rerank-backend"),
      api_base: field("q-rerank-api"), device: field("q-rerank-device"), model_path: field("q-rerank-path"),
    }).filter(([, value]) => value));
    if (Object.keys(model).length) {
      const picked = (RERANKERS?.models || []).find(m => m.name === model.model_id);
      if (!model.backend && (picked?.backend === "openvino_vl"
          || model.model_id === RERANKERS?.media_model_id
          || (!model.model_id && mediaSearch()))) {
        model.backend = "openvino_vl";
      }
      body.postprocess.reranker_model = model;
    }
  }
  const r = await api("POST", "/v1/retrieve", body);
  if (r.postprocess_error) toast(`${t("Reranking failed; showing the recall order")}: ${r.postprocess_error}`, true);
  LAST_RESULT = { r, pool, type, targets };
  if (targets.includes("document") && TRACED_TYPES.includes(type)) GraphView.showTraces(r.graph_traces, pool || undefined); else GraphView.clearTraces();
  return { r, scope: renderResults() };
}
$("q-run").addEventListener("click", async () => {
  const btn = $("q-run"); btn.disabled = true; btn.textContent = t("Retrieving…");
  const box = $("q-results"); box.innerHTML = ""; $("q-summary").textContent = "";
  try {
    const { r, scope } = await runRetrieval($("q-text").value.trim());
    toast(t("Retrieved {n} chunk(s) from {scope}", { n: r.chunks.length, scope }));
  } catch (err) { box.innerHTML = `<div class="empty">${esc(err.message)}</div>`; toast(err.message, true); }
  finally { btn.disabled = false; btn.textContent = t("Retrieve"); }
});

// ---- init -------------------------------------------------------------------------
// Runs after canvas.js has loaded (see the bottom of that file).
function initConsole() {
  applyI18n();
  $("lang-toggle").textContent = LANG === "zh" ? "EN" : "中文";
  resetDbFormLabels(); renderModalities();
  showTab(location.hash.slice(1));
  refresh().catch(e => toast(e.message, true));
  loadDatabases().catch(() => {});
  loadModels().catch(() => {});
  setInterval(health, 15000);
}
