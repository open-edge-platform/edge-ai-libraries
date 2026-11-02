// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
/*
 * Shared, framework-free source operator-options editor (classic script).
 *
 * SourceOptions.defaults() returns a new mutable, flat, JSON-serializable object.
 * Every value is a string. Its exact keys are:
 *   graph_mode: "okf" (safe default) | "documents"
 *   graph_url, graph_api_key, graph_timeout, graph_trigger,
 *   graph_debounce_seconds, graph_cron, graph_timezone, graph_language, graph_goal
 *   graph_advanced: "false" | "true" (disclosure only; never disables overrides)
 *   graph_instruction_<NAME>, for TYPE_HINTS, DOMAIN, GRANULARITY, TITLE_RULES,
 *     MERGE_STANCE, RELATION_RULES, ESCALATION_RULES
 *   vector_mode: "documents" | "images" | "video" | "audio"
 *   vector_asset_types: JSON array of selected content, or blank for the mode default
 *   vector_<MODE>_<FIELD>, with these common fields for each mode:
 *     embedding_backend, embedding_model, embedding_device,
 *     asset_types (JSON array)
 *   graph_asset_types is a JSON array, or blank to follow the graph preset.
 *   Additional fields: documents: embedding_api_base, chunk_size, chunk_overlap,
 *     figure_context_chars, max_image_tokens; images/audio: max_image_tokens;
 *     video: frames_per_clip.
 *
 * Blank vector fields inherit engine/model defaults; nothing is copied out of
 * the model catalog into state. Separate banks preserve edits without leaking
 * document overrides into the media registry. Remote document embeddings omit
 * local device/image-token settings, retaining them in state.
 *
 * mount(container, {type, state = defaults(), models, onChange}) owns the
 * container's children and fills missing known state keys in place. It returns
 * {state, read()}. onChange(state) receives that SAME object after each actual
 * input/select/disclosure change, including invalid intermediate text. read()
 * validates and returns operator_options, or throws an Error with a safe message
 * and a `field` state-key property, displaying/focusing the invalid field.
 * Call mount again to refresh external state, translations, or model suggestions;
 * an existing mount with the same container/type/state keeps its DOM and focus.
 * models accepts a ModelOptions object, an array of ModelInfo/string entries, or
 * {embedding, multimodal} values containing ModelOptions (also {opt: ...}).
 *
 * serialize(type, state) is pure, accepts partial state, ignores inactive fields,
 * and never includes UI-only keys. Types are graph/vector/object/sql; an empty
 * type is a neutral unselected-database form. Unknown types are rejected.
 * No DOM, translation helper, or URL constructor is needed at script load.
 */
(function (root) {
  "use strict";

  const MODES = ["documents", "images", "video", "audio"];
  const BACKENDS = ["llamaindex_openvino", "openvino_genai", "openai_compatible", "native_openvino_gme"];
  const DEVICES = ["", "CPU", "GPU", "GPU.0", "AUTO"];
  const COMMON_VECTOR_FIELDS = ["embedding_backend", "embedding_model", "embedding_device", "asset_types"];
  const DEFAULT_ASSETS = { documents: ["document"], images: ["image"], video: ["video"], audio: ["audio"] };
  const EXTRA_VECTOR_FIELDS = {
    documents: ["embedding_api_base", "chunk_size", "chunk_overlap", "figure_context_chars", "max_image_tokens"],
    images: ["max_image_tokens"],
    video: ["frames_per_clip"],
    audio: ["max_image_tokens"],
  };
  const INSTRUCTIONS = [
    ["TYPE_HINTS", "Suggested concept types", "Optional type guidance; these are suggestions, not a fixed vocabulary."],
    ["DOMAIN", "Domain", "Describe the subject area and the intended extraction role."],
    ["GRANULARITY", "Granularity", "Describe what should count as one concept and the desired level of detail."],
    ["TITLE_RULES", "Title rules", "Explain how to name concepts consistently across documents."],
    ["MERGE_STANCE", "Merge stance", "Explain when concepts should be merged or kept separate."],
    ["RELATION_RULES", "Relation rules", "Guide relationship naming, evidence, and direction."],
    ["ESCALATION_RULES", "Escalation rules", "Describe ambiguities that should be escalated rather than guessed."],
  ];
  const INITIAL = {
    graph_mode: "okf",
    graph_asset_types: "",
    graph_url: "http://okf-extractor:8080",
    graph_api_key: "",
    graph_timeout: "3600",
    graph_trigger: "auto",
    graph_debounce_seconds: "15",
    graph_cron: "",
    graph_timezone: "UTC",
    graph_language: "",
    graph_goal: "",
    graph_advanced: "false",
    vector_mode: "documents",
    vector_asset_types: "",
  };
  for (const [name] of INSTRUCTIONS) INITIAL[`graph_instruction_${name}`] = "";
  for (const mode of MODES) {
    for (const field of [...COMMON_VECTOR_FIELDS, ...EXTRA_VECTOR_FIELDS[mode]]) INITIAL[vectorKey(mode, field)] = "";
    INITIAL[vectorKey(mode, "asset_types")] = JSON.stringify(DEFAULT_ASSETS[mode]);
  }
  Object.freeze(INITIAL);
  const mounts = new WeakMap();
  const dismissDocuments = new WeakSet();
  let nextId = 0;

  function defaults() { return { ...INITIAL }; }
  function vectorKey(mode, field) { return `vector_${mode}_${field}`; }
  function tr(message) { return typeof root.t === "function" ? root.t(message) : message; }
  function fail(field, message) {
    // Only fixed labels/messages reach errors; never echo URLs, tokens or input.
    const error = new Error(tr(message));
    error.field = field;
    throw error;
  }
  function stateObject(state) {
    if (state == null) return {};
    if (Object.prototype.toString.call(state) !== "[object Object]") fail("", "Source options state must be a flat object of strings.");
    return state;
  }
  function value(state, key) {
    const raw = Object.prototype.hasOwnProperty.call(state, key) && state[key] !== undefined ? state[key] : INITIAL[key];
    if (typeof raw !== "string") fail(key, "Source option field values must be strings.");
    return raw.trim();
  }
  function databaseType(type) {
    const kind = type == null ? "" : typeof type === "string" ? type.trim().toLowerCase() : "invalid";
    if (!["", "graph", "vector", "object", "sql"].includes(kind)) fail("", "Choose a supported database type: graph, vector, object, or sql.");
    return kind;
  }
  function choice(state, key, allowed, message) {
    const selected = value(state, key);
    if (!allowed.includes(selected)) fail(key, message);
    return selected;
  }
  function number(state, key, { label, min = 0, positive = false, max = Infinity, integer = false, optional = false }) {
    const text = value(state, key);
    if (optional && !text) return undefined;
    const parsed = Number(text);
    const valid = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(text)
      && Number.isFinite(parsed) && (positive ? parsed > 0 : parsed >= min)
      && parsed <= max && (!integer || Number.isSafeInteger(parsed));
    if (!valid) {
      const range = positive ? "greater than 0" : max === Infinity ? "0 or greater" : `between ${min} and ${max}`;
      fail(key, `${label} must be a finite ${integer ? "whole number" : "number"} ${range}.`);
    }
    return parsed;
  }

  // URL is a browser global, but not supplied by every Node vm sandbox. Keep a
  // strict structural fallback for pure serialization in those environments.
  function fallbackHost(host) {
    if (host.startsWith("[")) {
      const address = host.slice(1, -1), halves = address.split("::");
      if (halves.length > 2) return false;
      const parts = halves.flatMap(part => part ? part.split(":") : []);
      let count = 0;
      for (let i = 0; i < parts.length; i++) {
        if (/^\d+(?:\.\d+){3}$/.test(parts[i]) && i === parts.length - 1) {
          if (!parts[i].split(".").every(n => Number(n) <= 255)) return false;
          count += 2;
        } else if (/^[a-f\d]{1,4}$/i.test(parts[i])) count++;
        else return false;
      }
      return halves.length === 2 ? count < 8 : count === 8;
    }
    if (/^[\d.]+$/.test(host)) return /^\d+(?:\.\d+){3}$/.test(host) && host.split(".").every(n => Number(n) <= 255);
    return host.length <= 254 && host.replace(/\.$/, "").split(".")
      .every(part => /^[a-z\d](?:[a-z\d_-]{0,61}[a-z\d])?$/i.test(part));
  }
  function httpUrl(state, key, label) {
    const text = value(state, key);
    const match = /^https?:\/\/(\[[a-f\d:.]+\]|[a-z\d](?:[a-z\d._-]*[a-z\d])?\.?)(?::(\d{1,5}))?(?:\/[^\s\\?#]*)?$/i.exec(text);
    let valid = !!match && (!match[2] || (Number(match[2]) > 0 && Number(match[2]) <= 65535));
    if (valid && typeof root.URL === "function") {
      try {
        const parsed = new root.URL(text);
        valid = ["http:", "https:"].includes(parsed.protocol) && !!parsed.hostname
          && !parsed.username && !parsed.password && !parsed.search && !parsed.hash && parsed.port !== "0";
      } catch { valid = false; }
    } else if (valid) valid = fallbackHost(match[1]);
    if (!valid) fail(key, `${label} must be an HTTP(S) URL with a host and no credentials, query, or fragment.`);
    return text.replace(/\/+$/, "");
  }
  function cron(state) {
    const key = "graph_cron", parts = value(state, key).split(/\s+/);
    if (parts.length !== 5) fail(key, "Schedule cron must have five fields: minute, hour, day of month, month, day of week.");
    const fields = [["minute", 0, 59], ["hour", 0, 23], ["day of month", 1, 31], ["month", 1, 12], ["day of week", 0, 7]];
    for (let i = 0; i < fields.length; i++) {
      const [label, low, high] = fields[i];
      for (const part of parts[i].split(",")) {
        const match = /^(\*|\d+(?:-\d+)?)(?:\/(\d+))?$/.exec(part);
        let valid = !!match;
        if (match) {
          const step = match[2] === undefined ? 1 : Number(match[2]);
          const bounds = match[1] === "*" ? [low, high] : match[1].split("-").map(Number);
          const start = bounds[0], end = bounds[1] ?? (match[2] === undefined ? start : high);
          valid = Number.isSafeInteger(step) && step > 0 && low <= start && start <= end && end <= high;
        }
        if (!valid) fail(key, `Cron ${label} must use values ${low}–${high}, ordered ranges, lists, and positive steps.`);
      }
    }
    return parts.join(" ");
  }
  function timezone(state) {
    const key = "graph_timezone", zone = value(state, key);
    const message = "Schedule timezone must be a known IANA timezone, for example UTC or Asia/Shanghai.";
    if (!/^[a-z][a-z\d._+-]*(?:\/[a-z\d._+-]+)*$/i.test(zone) || zone.split("/").some(part => part === "." || part === "..")) fail(key, message);
    if (root.Intl && typeof root.Intl.DateTimeFormat === "function") {
      try {
        // Canonical casing also avoids accepting a name Intl knows but Python's
        // case-sensitive zoneinfo lookup would not (for example asia/shanghai).
        return new root.Intl.DateTimeFormat("en", { timeZone: zone }).resolvedOptions().timeZone;
      } catch { fail(key, message); }
    }
    // No timezone database in this environment: require a recognized region or
    // a UTC/GMT name, not just any non-empty string or numeric UTC offset.
    if (!/^(?:UTC|GMT|Etc\/UTC|Etc\/GMT(?:[+-](?:\d|1[0-4]))?)$/.test(zone)
        && !/^(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific)\/[a-z_+-]+(?:\/[a-z_+-]+)?$/i.test(zone)) fail(key, message);
    return zone;
  }
  function putText(target, state, key, outputKey) {
    const text = value(state, key);
    if (text) target[outputKey] = text;
  }
  function putInteger(target, state, key, outputKey, label, positive = false) {
    const parsed = number(state, key, { label, positive, integer: true, optional: true });
    if (parsed !== undefined) target[outputKey] = parsed;
  }

  function assets(type, state, key, fallback) {
    let selected;
    try { selected = JSON.parse(value(state, key) || JSON.stringify(fallback)); }
    catch { fail(key, "Invalid content type for this database"); }
    try { return SourceAssetTypes.options(type, selected, {}).asset_types; }
    catch (error) { fail(key, error.message); }
  }

  function vectorContent(state) {
    const preset = choice(state, "vector_mode", MODES, "Choose documents, images, video, or audio for vector content.");
    if (!value(state, "vector_asset_types")) {
      return { mode: preset, selected: assets("vector", state, vectorKey(preset, "asset_types"), DEFAULT_ASSETS[preset]) };
    }
    const selected = assets("vector", state, "vector_asset_types", DEFAULT_ASSETS[preset]);
    const mode = MODES.find(name => selected.includes(DEFAULT_ASSETS[name][0])) || "documents";
    return { mode, selected };
  }

  function contentError(type, selected) {
    if (type === "graph") return selected.includes("document") && !selected.includes("okf")
      ? "Document extraction requires OKF. Select OKF together with Documents → OKF." : null;
    const media = selected.filter(item => ["image", "video", "audio"].includes(item));
    if (media.length && media.length !== selected.length) {
      return "Documents and media need separate sources. Select documents alone, or select compatible media.";
    }
    if (selected.includes("video") && selected.length > 1) {
      return "Video needs its own source. Images and audio can share a source.";
    }
    return null;
  }

  function serialize(type, input) {
    const kind = databaseType(type);
    if (!kind || kind === "object" || kind === "sql") return {};
    const state = stateObject(input);
    if (kind === "graph") {
      const mode = choice(state, "graph_mode", ["okf", "documents"], "Choose OKF bundles only or Documents → OKF.");
      const selected = assets(kind, state, "graph_asset_types", mode === "documents" ? ["okf", "document"] : ["okf"]);
      const error = contentError(kind, selected);
      if (error) fail("graph_asset_types", error);
      if (!selected.includes("document")) return { asset_types: selected };
      const extractor = {
        url: httpUrl(state, "graph_url", "Extractor service URL"),
        timeout: number(state, "graph_timeout", { label: "HTTP timeout", positive: true }),
      };
      putText(extractor, state, "graph_api_key", "api_key");
      const trigger = choice(state, "graph_trigger", ["auto", "manual", "schedule"], "Extraction trigger must be auto, manual, or schedule.");
      if (trigger === "auto") extractor.trigger = {
        mode: "auto",
        debounce_seconds: number(state, "graph_debounce_seconds", { label: "Quiet seconds", max: 86400 }),
      };
      else if (trigger === "schedule") extractor.trigger = { mode: "schedule", cron: cron(state), timezone: timezone(state) };
      else extractor.trigger = "manual";
      const options = {};
      putText(options, state, "graph_language", "language");
      putText(options, state, "graph_goal", "goal");
      if (options.language && [...options.language].length > 100) fail("graph_language", "Summary language must be at most 100 characters.");
      if (options.goal && [...options.goal].length > 8000) fail("graph_goal", "Task goal must be at most 8000 characters.");
      const instructions = {};
      for (const [name] of INSTRUCTIONS) putText(instructions, state, `graph_instruction_${name}`, name);
      if (Object.keys(instructions).length) options.instructions = instructions;
      if (Object.keys(options).length) extractor.options = options;
      return { asset_types: selected, external_extractor: extractor };
    }

    const { mode, selected } = vectorContent(state);
    const error = contentError(kind, selected);
    if (error) fail("vector_asset_types", error);
    const key = field => vectorKey(mode, field);
    const backend = choice(state, key("embedding_backend"), ["", ...BACKENDS], "Embedding backend must be inherited or a supported canonical backend.");
    if (mode !== "documents" && backend && backend !== "llamaindex_openvino") {
      fail(key("embedding_backend"), "Image, video, and audio sources support only llamaindex_openvino or the inherited media default.");
    }
    const options = { asset_types: selected };
    if (backend) options.embedding_backend = backend;
    putText(options, state, key("embedding_model"), "embedding_model");
    const remote = backend === "openai_compatible";
    if (remote) {
      if (value(state, key("embedding_api_base"))) options.embedding_api_base = httpUrl(state, key("embedding_api_base"), "Remote API base");
    } else {
      const device = choice(state, key("embedding_device"), DEVICES, "Embedding device must be inherited, CPU, GPU, GPU.0, or AUTO.");
      if (device) options.embedding_device = device;
      if (mode !== "video") putInteger(options, state, key("max_image_tokens"), "max_image_tokens", "Maximum image tokens", true);
    }
    if (mode === "documents") {
      putInteger(options, state, key("chunk_size"), "chunk_size", "Chunk size", true);
      putInteger(options, state, key("chunk_overlap"), "chunk_overlap", "Chunk overlap");
      putInteger(options, state, key("figure_context_chars"), "figure_context_chars", "Figure context characters");
      if (options.chunk_size !== undefined && options.chunk_overlap !== undefined && options.chunk_overlap >= options.chunk_size) {
        fail(key("chunk_overlap"), "Chunk overlap must be smaller than chunk size when both are set.");
      }
    }
    if (mode === "video") putInteger(options, state, key("frames_per_clip"), "frames_per_clip", "Frames per clip", true);
    return options;
  }

  function catalog(models, mode) {
    let group = models;
    if (group && !Array.isArray(group) && !group.models && !group.opt) group = group[mode === "documents" ? "embedding" : "multimodal"];
    if (group && group.opt) group = group.opt;
    const entries = Array.isArray(group) ? group : group && Array.isArray(group.models) ? group.models : [];
    const result = new Map();
    for (const item of entries) {
      const name = typeof item === "string" ? item : item && (item.name || item.model_id);
      if (typeof name !== "string" || !name.trim()) continue;
      if (item && typeof item === "object" && item.model_type && item.model_type !== (mode === "documents" ? "embedding" : "multimodal")) continue;
      if (item && Array.isArray(item.supported_kinds) && mode !== "documents"
          && !item.supported_kinds.includes({ images: "image", video: "video", audio: "audio" }[mode])) continue;
      result.set(name, { name, path: typeof item.path === "string" ? item.path : "", ready: item.ready !== false });
    }
    if (group && typeof group.model_id === "string" && group.model_id.trim() && !result.has(group.model_id)) {
      result.set(group.model_id, { name: group.model_id, path: "", ready: true });
    }
    return [...result.values()];
  }

  function mount(container, { type, state = defaults(), models, onChange } = {}) {
    const kind = databaseType(type), current = stateObject(state);
    if (!container || !container.ownerDocument || typeof container.replaceChildren !== "function") {
      fail("", "Source options need a DOM container.");
    }
    if (Object.isFrozen(current)) fail("", "Source options state must be mutable.");
    for (const [key, initial] of Object.entries(INITIAL)) {
      if (!Object.prototype.hasOwnProperty.call(current, key) || current[key] === undefined) current[key] = initial;
      else if (typeof current[key] !== "string") fail(key, "Source option field values must be strings.");
    }
    if (onChange !== undefined && typeof onChange !== "function") fail("", "Source options onChange must be a function.");
    const previous = mounts.get(container);
    if (previous && previous.type === kind && previous.state === current && previous.element.parentNode === container) {
      previous.refresh(models, onChange);
      return previous.api;
    }

    const doc = container.ownerDocument, prefix = `source-options-${++nextId}`;
    const controls = new Map(), translations = [], placeholders = [], lists = [];
    let callback = onChange, modelCatalog = models, lastError = null;
    const element = doc.createElement("div");
    element.className = "source-options";
    element.dataset.sourceType = kind;
    element.setAttribute("role", "group");
    const alert = doc.createElement("p");
    alert.className = "so-alert"; alert.setAttribute("role", "alert"); alert.hidden = true;
    element.appendChild(alert);

    function node(parent, tag, className, text) {
      const el = doc.createElement(tag);
      if (className) el.className = className;
      if (text) { translations.push([el, text]); el.textContent = tr(text); }
      parent.appendChild(el);
      return el;
    }
    function section(parent, title, hint) {
      const box = node(parent, "fieldset", "so-section");
      node(box, "legend", "so-title", title);
      if (hint) node(box, "p", "so-hint", hint);
      return box;
    }
    function field(parent, key, label, spec = {}) {
      const wrap = node(parent, "div", "so-field");
      const title = node(wrap, "label", "so-label", label);
      const el = node(wrap, spec.options ? "select" : spec.multiline ? "textarea" : "input", "so-control");
      el.id = `${prefix}-${key}`; el.name = key; el.dataset.sourceOption = key; title.htmlFor = el.id;
      if (!spec.options && !spec.multiline) el.type = spec.type || "text";
      if (spec.multiline) el.rows = 3;
      if (spec.options) {
        for (const [optionValue, optionLabel] of spec.options) {
          const option = node(el, "option", "", optionLabel); option.value = optionValue;
        }
      }
      if (spec.placeholder) { placeholders.push([el, spec.placeholder]); el.placeholder = tr(spec.placeholder); }
      for (const attr of ["min", "max", "step", "maxLength", "inputMode", "autoComplete", "spellcheck"]) {
        if (spec[attr] !== undefined) el[attr] = spec[attr];
      }
      const descriptionIds = [];
      if (spec.hint) {
        const hint = node(wrap, "p", "so-hint", spec.hint);
        hint.id = `${el.id}-hint`; descriptionIds.push(hint.id);
      }
      const error = node(wrap, "p", "so-error");
      error.id = `${el.id}-error`; error.hidden = true; descriptionIds.push(error.id);
      el.setAttribute("aria-describedby", descriptionIds.join(" "));
      controls.set(key, { el, error });
      el.value = current[key];
      return el;
    }
    function shown(el, visible) {
      if (!el) return;
      el.hidden = !visible;
      for (const control of el.querySelectorAll("input, select, textarea")) control.disabled = !visible;
    }
    function clearErrors() {
      lastError = null; alert.hidden = true; alert.textContent = "";
      for (const { el, error } of controls.values()) {
        el.removeAttribute("aria-invalid"); error.textContent = ""; error.hidden = true;
      }
    }
    function notify(key, text) {
      if (current[key] === text) return;
      current[key] = text;
      if (lastError && (lastError.field === key || ["graph_mode", "graph_trigger", "vector_mode"].includes(key) || key.endsWith("_embedding_backend"))) clearErrors();
      updateVisibility();
      if (callback) callback(current);
    }

    let graph = null, advanced = null;
    const banks = [];
    const inherited = [["", "Inherit engine default"]];
    let scope = null;
    if (kind === "graph" || kind === "vector") {
      const contentLabel = kind === "graph" ? "Graph source content" : "Vector content";
      const group = section(element, contentLabel);
      node(group, "p", "so-hint", kind === "graph"
        ? "OKF bundles are indexed directly. Select Documents → OKF together with OKF to enable document extraction."
        : "Documents and video each need a separate source. Images and audio can be selected together. Selecting an incompatible category switches the selection.");
      scope = node(group, "details", "asset-types-dropdown");
      const summary = node(scope, "summary");
      summary.id = `${prefix}-content`;
      const scopeKey = kind === "graph" ? "graph_asset_types" : "vector_asset_types";
      summary.dataset.sourceOption = scopeKey;
      const display = node(summary, "span", "asset-types-value");
      const arrow = node(summary, "span", "asset-types-arrow");
      arrow.textContent = "▾"; arrow.setAttribute("aria-hidden", "true");
      const menu = node(scope, "div", "asset-types-menu");
      const tools = node(menu, "div", "asset-types-tools");
      const checks = node(menu, "div", "asset-types-checks");
      checks.setAttribute("role", "group");
      const scopeError = node(group, "p", "so-error"); scopeError.hidden = true;
      scopeError.id = `${summary.id}-error`; summary.setAttribute("aria-describedby", scopeError.id);
      const inputs = [];
      const choices = kind === "graph" ? [["okf", "OKF"], ["document", "Documents → OKF"]]
        : [["document", "Documents"], ["image", "Images"], ["video", "Video"], ["audio", "Audio"]];
      function selectedAssets() {
        try { return kind === "vector" ? vectorContent(current).selected
          : assets(kind, current, scopeKey, current.graph_mode === "documents" ? ["okf", "document"] : ["okf"]); }
        catch { return []; }
      }
      function changedAssets(selected) {
        const text = JSON.stringify(selected);
        if (current[scopeKey] === text) return;
        current[scopeKey] = text;
        if (selected.length) {
          if (kind === "graph") current.graph_mode = selected.includes("document") ? "documents" : "okf";
          else current.vector_mode = vectorContent(current).mode;
        }
        clearErrors(); updateVisibility();
        if (callback) callback(current);
      }
      for (const [action, label] of [["all", kind === "vector" ? "Select images and audio" : "Select all"], ["none", "Clear selection"]]) {
        const button = node(tools, "button", "ghost mini", label); button.type = "button";
        button.addEventListener("click", () => changedAssets(action === "all"
          ? kind === "vector" ? ["image", "audio"] : choices.map(([value]) => value) : []));
      }
      for (const [item, title] of choices) {
        const label = node(checks, "label"), input = node(label, "input");
        input.type = "checkbox"; input.value = item;
        input.id = `${prefix}-content-${item}`; label.htmlFor = input.id;
        node(label, "span", "", title); inputs.push(input);
        input.addEventListener("change", () => {
          if (kind === "vector" && input.checked) {
            // A source owns one encoder; do not combine document/media paths or
            // X-CLIP video with the image/audio GME path.
            for (const other of inputs) {
              if (other !== input && (item === "document" || item === "video" || ["document", "video"].includes(other.value))) other.checked = false;
            }
          } else if (kind === "graph") {
            if (item === "document" && input.checked) inputs.find(el => el.value === "okf").checked = true;
            if (item === "okf" && !input.checked) inputs.find(el => el.value === "document").checked = false;
          }
          changedAssets(inputs.filter(el => el.checked).map(el => el.value));
        });
      }
      scope.addEventListener("keydown", event => {
        if (event.key === "Escape" && scope.open) { event.preventDefault(); event.stopPropagation(); scope.open = false; summary.focus(); }
      });
      scope.addEventListener("focusout", event => { if (event.relatedTarget && !scope.contains(event.relatedTarget)) scope.open = false; });
      if (typeof doc.addEventListener === "function" && !dismissDocuments.has(doc)) {
        doc.addEventListener("click", event => {
          doc.querySelectorAll(".asset-types-dropdown[open]").forEach(dropdown => {
            if (!dropdown.contains(event.target)) dropdown.open = false;
          });
        });
        dismissDocuments.add(doc);
      }
      scope.update = () => {
        const selected = selectedAssets();
        summary.setAttribute("aria-label", tr(contentLabel));
        checks.setAttribute("aria-label", tr(contentLabel));
        for (const input of inputs) input.checked = selected.includes(input.value);
        display.textContent = selected.length ? selected.map(item => tr(choices.find(([value]) => value === item)?.[1] || item)).join(", ") : tr("Select content…");
        display.title = display.textContent;
        summary.setAttribute("aria-invalid", String(!selected.length || !!contentError(kind, selected)));
        controls.set(scopeKey, { el: summary, error: scopeError });
      };
    }
    if (kind === "graph") {
      const documents = node(element, "div", "so-stack");
      const service = section(documents, "Extraction service", "The engine calls this service; the address must be reachable from the engine, not just this browser.");
      field(service, "graph_url", "Service URL", { type: "url", autoComplete: "off", spellcheck: false, placeholder: "http://okf-extractor:8080" });
      field(service, "graph_api_key", "API key (optional)", {
        type: "password", autoComplete: "new-password", spellcheck: false,
        hint: "Optional bearer token for the extraction service. Leave blank when authentication is not required.",
      });
      field(service, "graph_timeout", "HTTP timeout (seconds)", {
        type: "number", min: "0", step: "any", inputMode: "decimal",
        hint: "Positive request timeout. This is not the automatic extraction delay; large tasks can take an hour or more.",
      });
      const trigger = section(documents, "When to extract");
      field(trigger, "graph_trigger", "Extraction trigger", {
        options: [["auto", "Automatic · after changes settle"], ["manual", "Manual · Extract now"], ["schedule", "Scheduled · cron"]],
      });
      const auto = node(trigger, "div", "so-stack");
      field(auto, "graph_debounce_seconds", "Quiet seconds", {
        type: "number", min: "0", max: "86400", step: "any", inputMode: "decimal",
        hint: "Wait after the last document change before extracting the corpus. Use 0–86400 seconds; 15 is the default.",
      });
      const schedule = node(trigger, "div", "so-stack");
      field(schedule, "graph_cron", "Cron schedule", {
        placeholder: "0 2 * * *", spellcheck: false, autoComplete: "off",
        hint: "Five numeric fields: minute hour day-of-month month day-of-week. Supports *, ranges, lists, and steps; no names or seconds.",
      });
      field(schedule, "graph_timezone", "Schedule timezone", {
        placeholder: "UTC", spellcheck: false, autoComplete: "off",
        hint: "IANA timezone, for example UTC or Asia/Shanghai. Daylight saving follows this zone.",
      });
      const task = section(documents, "Extraction task", "Blank task options and instructions use the extractor's defaults. Entered overrides still apply when Advanced is collapsed.");
      field(task, "graph_language", "Summary language (optional)", { maxLength: 100, placeholder: "For example: en, zh, English" });
      field(task, "graph_goal", "Task goal (optional)", { maxLength: 8000, placeholder: "What should this document corpus help explain?" });
      advanced = node(task, "details", "so-advanced");
      node(advanced, "summary", "", "Advanced extraction instructions");
      const instructions = node(advanced, "div", "so-instructions");
      for (const [name, label, hint] of INSTRUCTIONS) {
        field(instructions, `graph_instruction_${name}`, `${label} (${name})`, { multiline: true, hint });
      }
      advanced.open = current.graph_advanced === "true";
      advanced.addEventListener("toggle", () => notify("graph_advanced", advanced.open ? "true" : "false"));
      graph = { documents, auto, schedule };
    } else if (kind === "vector") {
      const hints = {
        documents: "Uses document embedding defaults without a block filter, so fused models can include document figures.",
        images: "Indexes image representations using the image-category embedding defaults.",
        video: "Indexes video representations using the video-category embedding defaults. Frames per clip must match the prepared checkpoint.",
        audio: "Indexes audio through its speech transcript, not raw sound, using the image-category embedding defaults. Transcription is configured by the engine.",
      };
      for (const mode of MODES) {
        const key = name => vectorKey(mode, name);
        const wrapper = node(element, "div", "so-stack");
        const model = section(wrapper, "Embedding model", hints[mode]);
        field(model, key("embedding_backend"), "Backend override (optional)", {
          options: [...inherited, ...(mode === "documents" ? BACKENDS : ["llamaindex_openvino"]).map(name => [name, name])],
          hint: mode === "documents" ? "Leave blank to inherit the document runtime. Overrides use canonical backend names."
            : "The media registry supports llamaindex_openvino only. Leave blank to inherit this content type's engine default.",
        });
        const picker = field(model, key("embedding_model"), "Model override (optional)", {
          placeholder: "Inherit engine default", spellcheck: false, autoComplete: "off",
          hint: "Choose a suggested model or enter a model ID. Local models must already be prepared; the engine does not download them.",
        });
        const list = node(model, "datalist"); list.id = `${picker.id}-models`; picker.setAttribute("list", list.id); lists.push({ list, mode });
        const local = node(model, "div", "so-stack");
        field(local, key("embedding_device"), "Device override (optional)", { options: [...inherited, ...DEVICES.filter(Boolean).map(name => [name, name])] });
        let remote = null;
        if (mode === "documents") {
          remote = node(model, "div", "so-stack");
          field(remote, key("embedding_api_base"), "Remote API base (optional)", {
            type: "url", placeholder: "https://embeddings.example/v1", autoComplete: "off", spellcheck: false,
            hint: "Leave blank to inherit the engine endpoint. Credentials are configured by the engine; the source API cannot store a per-source embedding API key.",
          });
        }
        if (mode === "documents") {
          const chunks = section(wrapper, "Text chunks", "Leave blank to inherit engine defaults. Chunk overlap must be smaller than chunk size when both are set.");
          field(chunks, key("chunk_size"), "Chunk size (tokens, optional)", { type: "number", min: "1", step: "1", inputMode: "numeric", placeholder: "Inherit engine default" });
          field(chunks, key("chunk_overlap"), "Chunk overlap (tokens, optional)", { type: "number", min: "0", step: "1", inputMode: "numeric", placeholder: "Inherit engine default" });
          field(chunks, key("figure_context_chars"), "Figure context (characters per side, optional)", {
            type: "number", min: "0", step: "1", inputMode: "numeric", placeholder: "Inherit engine default",
            hint: "Neighbouring text included with a figure caption; 0 is an explicit override, not an empty value.",
          });
        }
        const tuning = section(wrapper, "Prepared-model settings", "Optional settings for models that support them. Leave blank to retain the prepared model's defaults.");
        if (mode === "video") {
          field(tuning, key("frames_per_clip"), "Frames per clip (optional)", { type: "number", min: "1", step: "1", inputMode: "numeric", placeholder: "Prepared-model default" });
        } else {
          field(tuning, key("max_image_tokens"), "Maximum image tokens (optional)", {
            type: "number", min: "1", step: "1", inputMode: "numeric", placeholder: "Prepared-model default",
            hint: "Positive visual-token budget for supported GME models, including figures in fused document embeddings.",
          });
        }
        banks.push({ mode, wrapper, local, remote, tuning });
      }
    } else {
      node(element, "p", "so-neutral", kind ? "This database type needs no model or extraction options." : "Choose a database to configure its source options.");
    }

    function updateVisibility() {
      if (graph) {
        let documents = false;
        try { documents = assets("graph", current, "graph_asset_types", current.graph_mode === "documents" ? ["okf", "document"] : ["okf"]).includes("document"); }
        catch { /* An empty selection stays editable; read() reports it. */ }
        shown(graph.documents, documents);
        shown(graph.auto, documents && current.graph_trigger === "auto");
        shown(graph.schedule, documents && current.graph_trigger === "schedule");
      }
      let vectorMode = null;
      if (kind === "vector") {
        try { vectorMode = vectorContent(current).mode; }
        catch { /* Invalid/empty selections remain editable; read() reports them. */ }
      }
      for (const bank of banks) {
        const active = vectorMode === bank.mode;
        const remote = bank.mode === "documents" && current[vectorKey(bank.mode, "embedding_backend")] === "openai_compatible";
        shown(bank.wrapper, active); shown(bank.local, active && !remote);
        shown(bank.remote, active && remote); shown(bank.tuning, active && !remote);
      }
      for (const [key, { el }] of controls) if (el.tagName === "SELECT" && el.value !== current[key]) el.value = current[key];
      if (scope) scope.update();
    }
    function refresh(newModels, newCallback) {
      modelCatalog = newModels; callback = newCallback;
      element.setAttribute("aria-label", tr("Source operator options"));
      for (const [el, message] of translations) el.textContent = tr(message);
      for (const [el, message] of placeholders) el.placeholder = tr(message);
      for (const [key, { el }] of controls) {
        // Assigning even the same value resets text selection in some browsers.
        if (el.tagName !== "SUMMARY" && el.value !== current[key]) el.value = current[key];
      }
      if (advanced && advanced.open !== (current.graph_advanced === "true")) advanced.open = current.graph_advanced === "true";
      for (const { list, mode } of lists) {
        const options = catalog(modelCatalog, mode).map(model => {
          const option = doc.createElement("option"); option.value = model.name;
          option.label = [model.name, model.ready ? tr("prepared") : tr("not prepared"), model.path].filter(Boolean).join(" · ");
          return option;
        });
        list.replaceChildren(...options);
      }
      updateVisibility();
    }
    function changed(event) {
      const key = event.target && event.target.dataset && event.target.dataset.sourceOption;
      if (key && controls.get(key)?.el === event.target && !event.target.disabled) notify(key, event.target.value);
    }
    element.addEventListener("input", changed);
    element.addEventListener("change", changed);
    const api = {
      state: current,
      read() {
        try {
          const options = serialize(kind, current); clearErrors(); return options;
        } catch (error) {
          clearErrors(); lastError = error;
          alert.textContent = error.message; alert.hidden = false;
          const invalid = controls.get(error.field);
          if (invalid) {
            invalid.error.textContent = error.message; invalid.error.hidden = false;
            invalid.el.setAttribute("aria-invalid", "true"); invalid.el.focus();
          }
          throw error;
        }
      },
    };
    refresh(models, onChange);
    container.replaceChildren(element);
    mounts.set(container, { type: kind, state: current, element, api, refresh });
    return api;
  }

  root.SourceOptions = { defaults, mount, serialize };
})(globalThis);

// Asset scope shared by the source CRUD form and the canvas inspector.
const SourceAssetTypes = (() => {
  // Document extensions mirror core.loader.SUPPORTED_EXTS. Media families cover
  // the MIME-recognized image/video/audio inputs without listing every suffix.
  const choices = {
    vector: ["pdf", "txt", "docx", "pptx", "xlsx", "csv", "md", "html", "htm", "rst", "document", "image", "video", "audio"],
    graph: ["okf", "document"],
  };
  const supported = type => [...(choices[type] || [])];
  const defaults = type => type === "vector" ? ["document"] : type === "graph" ? ["okf"] : [];
  let dismissBound = false;
  const translate = (message, vars = {}) => typeof globalThis.t === "function" ? globalThis.t(message, vars)
    : message.replace(/\{(\w+)\}/g, (match, key) => vars[key] ?? match);

  function options(type, values, extra) {
    for (const option of type === "vector" ? ["embedding_model_path", "precision"] : ["embedding_model_path"]) {
      if (Object.hasOwn(extra, option)) {
        throw new Error(translate("Invalid model option: {option}. Select a prepared package with embedding_model", {option}));
      }
    }
    if (!choices[type]) return extra;
    if (!Array.isArray(values) || !values.length) throw new Error(translate("Select at least one content type"));
    if (values.some(value => !choices[type].includes(value))) throw new Error(translate("Invalid content type for this database"));
    if (Object.hasOwn(extra, "asset_types")) throw new Error(translate("Choose content above, not in the JSON options"));
    return { ...extra, asset_types: [...new Set(values)] };
  }

  function mount(host, type, values, onChange) {
    host.hidden = !choices[type];
    if (host.hidden) { host.replaceChildren(); return; }
    if (!dismissBound) {
      document.addEventListener("click", event => {
        document.querySelectorAll(".asset-types-dropdown[open]").forEach(dropdown => {
          if (!dropdown.contains(event.target)) dropdown.open = false;
        });
      });
      dismissBound = true;
    }
    const id = host.id;
    host.innerHTML = `<label id="${esc(id)}-label">${esc(t(type === "vector" ? "Vector content" : "Graph source content"))}</label>
      <details class="asset-types-dropdown">
        <summary aria-labelledby="${esc(id)}-label ${esc(id)}-value"><span id="${esc(id)}-value" class="asset-types-value"></span><span class="asset-types-arrow" aria-hidden="true">▾</span></summary>
        <div class="asset-types-menu">
          <div class="asset-types-tools">
            <button type="button" class="ghost mini" data-select="all">${esc(t("Select all"))}</button>
            <button type="button" class="ghost mini" data-select="none">${esc(t("Clear selection"))}</button>
          </div>
          <div class="asset-types-checks" role="group" aria-labelledby="${esc(id)}-label">
            ${supported(type).map(value => `<label><input type="checkbox" value="${esc(value)}" ${values.includes(value) ? "checked" : ""} />${esc(value)}</label>`).join("")}
          </div>
        </div>
      </details>
      ${type === "graph" ? `<div class="hint" data-extractor-hint>${esc(t("Document extraction requires external_extractor.url and a vector source in the pool."))}</div>` : ""}`;
    const dropdown = host.querySelector("details"), summary = host.querySelector("summary");
    const inputs = [...host.querySelectorAll('input[type="checkbox"]')];
    const update = () => {
      const text = values.length ? values.join(", ") : t("Select content…");
      const display = host.querySelector(".asset-types-value");
      display.textContent = text; display.title = text;
      summary.setAttribute("aria-invalid", String(!values.length));
      const hint = host.querySelector("[data-extractor-hint]");
      if (hint) hint.hidden = !values.includes("document");
    };
    const changed = () => {
      values = inputs.filter(input => input.checked).map(input => input.value);
      update(); onChange([...values]);
    };
    inputs.forEach(input => input.addEventListener("change", changed));
    host.querySelectorAll("[data-select]").forEach(button => button.addEventListener("click", () => {
      inputs.forEach(input => (input.checked = button.dataset.select === "all"));
      changed();
    }));
    dropdown.addEventListener("keydown", event => {
      if (event.key === "Escape" && dropdown.open) {
        event.preventDefault(); event.stopPropagation();
        dropdown.open = false; summary.focus();
      }
    });
    dropdown.addEventListener("focusout", event => {
      if (event.relatedTarget && !dropdown.contains(event.relatedTarget)) dropdown.open = false;
    });
    update();
  }
  return { supported, defaults, options, mount };
})();
