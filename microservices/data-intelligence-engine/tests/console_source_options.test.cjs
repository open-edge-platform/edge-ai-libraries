// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
// No npm dependencies or Python setup: node --test this file.
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const filename = resolve(__dirname, "../src/console/source-options.js");
const script = new vm.Script(readFileSync(filename, "utf8"), { filename });
function load(globals = {}) {
  const context = vm.createContext(globals);
  script.runInContext(context);
  return { api: context.SourceOptions, context };
}
const { api } = load({ URL });
const plain = value => JSON.parse(JSON.stringify(value));
const MODES = ["documents", "images", "video", "audio"];
const NAMES = ["TYPE_HINTS", "DOMAIN", "GRANULARITY", "TITLE_RULES", "MERGE_STANCE", "RELATION_RULES", "ESCALATION_RULES"];
const COMMON = ["embedding_backend", "embedding_model", "embedding_device", "asset_types"];
const ASSETS = { documents: ["document"], images: ["image"], video: ["video"], audio: ["audio"] };
const EXTRA = {
  documents: ["embedding_api_base", "chunk_size", "chunk_overlap", "figure_context_chars", "max_image_tokens"],
  images: ["max_image_tokens"], video: ["frames_per_clip"], audio: ["max_image_tokens"],
};
function graph(fields = {}) { return Object.assign(api.defaults(), { graph_mode: "documents" }, fields); }
function vector(mode = "documents", fields = {}) {
  const state = api.defaults(); state.vector_mode = mode;
  for (const [key, value] of Object.entries(fields)) state[`vector_${mode}_${key}`] = value;
  return state;
}
function serialized(type, state, implementation = api) { return plain(implementation.serialize(type, state)); }
function invalid(type, state, field, message, implementation = api) {
  const before = JSON.stringify(state);
  assert.throws(() => implementation.serialize(type, state), error => {
    assert.equal(error.field, field);
    assert.match(error.message, message);
    return true;
  });
  assert.equal(JSON.stringify(state), before, "validation must not rewrite state");
}

test("classic script loads without touching DOM, helpers, URL, or other console globals", () => {
  const globals = { URL: undefined, Intl: undefined };
  for (const name of ["document", "window", "esc", "t"]) {
    Object.defineProperty(globals, name, { get() { throw new Error(`Unexpected load-time ${name} access`); } });
  }
  const isolated = load(globals).api;
  assert.deepEqual(Object.keys(isolated).sort(), ["defaults", "mount", "serialize"]);
  assert.deepEqual(serialized("graph", isolated.defaults(), isolated), { asset_types: ["okf"] });
});

test("defaults are fresh, mutable, flat strings with exactly the documented keys", () => {
  const a = api.defaults(), b = api.defaults();
  const expected = [
    "graph_mode", "graph_asset_types", "graph_url", "graph_api_key", "graph_timeout", "graph_trigger", "graph_debounce_seconds",
    "graph_cron", "graph_timezone", "graph_language", "graph_goal", "graph_advanced", "vector_mode", "vector_asset_types",
    ...NAMES.map(name => `graph_instruction_${name}`),
    ...MODES.flatMap(mode => [...COMMON, ...EXTRA[mode]].map(field => `vector_${mode}_${field}`)),
  ];
  assert.deepEqual(Object.keys(a).sort(), expected.sort());
  assert.ok(Object.values(a).every(value => typeof value === "string"));
  assert.deepEqual(plain(a), plain(b));
  assert.equal(a.graph_mode, "okf"); assert.equal(a.vector_mode, "documents");
  assert.equal(a.graph_timeout, "3600"); assert.equal(a.graph_debounce_seconds, "15");
  assert.equal(a.graph_url, "http://okf-extractor:8080"); assert.equal(a.graph_timezone, "UTC");
  a.graph_url = "changed"; a.vector_images_embedding_model = "changed";
  assert.notEqual(a.graph_url, b.graph_url); assert.equal(b.vector_images_embedding_model, "");
  assert.deepEqual(JSON.parse(JSON.stringify(b)), plain(b));
});

test("OKF-only is explicit and ignores all extraction and vector fields", () => {
  const state = Object.assign(api.defaults(), {
    graph_url: "invalid", graph_timeout: "NaN", graph_trigger: "unknown", graph_api_key: "secret",
    vector_documents_embedding_model: "unrelated",
  });
  assert.deepEqual(serialized("graph", state), { asset_types: ["okf"] });
  assert.deepEqual(serialized("graph", {}), { asset_types: ["okf"] });
  assert.deepEqual(serialized("graph"), { asset_types: ["okf"] });
});

test("graph documents use the exact nested auto shape and defaults", () => {
  assert.deepEqual(serialized("graph", graph()), {
    asset_types: ["okf", "document"],
    external_extractor: {
      url: "http://okf-extractor:8080", timeout: 3600,
      trigger: { mode: "auto", debounce_seconds: 15 },
    },
  });
  const options = serialized("graph", graph());
  assert.deepEqual(Object.keys(options).sort(), ["asset_types", "external_extractor"]);
  assert.ok(!("options" in options.external_extractor));
});

test("graph credentials, language, goal and all seven instructions are nested correctly", () => {
  const state = graph({ graph_api_key: "  bearer-token  ", graph_language: " zh ", graph_goal: " Map systems ", graph_advanced: "false" });
  const instructions = {};
  for (const name of NAMES) { state[`graph_instruction_${name}`] = `  ${name}\nKeep evidence.  `; instructions[name] = `${name}\nKeep evidence.`; }
  state.graph_instruction_UNKNOWN = "must not leak";
  state.url = "misplaced"; state.options = "not an input";
  state.vector_documents_embedding_model = "must not leak";
  assert.deepEqual(serialized("graph", state), {
    asset_types: ["okf", "document"], external_extractor: {
      url: "http://okf-extractor:8080", timeout: 3600, api_key: "bearer-token",
      trigger: { mode: "auto", debounce_seconds: 15 },
      options: { language: "zh", goal: "Map systems", instructions },
    },
  });
});

test("blank graph optionals are omitted, including an empty instructions object", () => {
  const state = graph({ graph_api_key: " \n ", graph_language: " ", graph_goal: "\n" });
  for (const name of NAMES) state[`graph_instruction_${name}`] = " \n ";
  const options = serialized("graph", state).external_extractor;
  assert.ok(!("api_key" in options)); assert.ok(!("options" in options));
  state.graph_instruction_DOMAIN = "medicine";
  assert.deepEqual(serialized("graph", state).external_extractor.options, { instructions: { DOMAIN: "medicine" } });
});

test("manual trigger is the string manual and never leaks auto or schedule fields", () => {
  const state = graph({ graph_trigger: "manual", graph_debounce_seconds: "invalid", graph_cron: "invalid", graph_timezone: "invalid" });
  assert.deepEqual(serialized("graph", state).external_extractor, {
    url: "http://okf-extractor:8080", timeout: 3600, trigger: "manual",
  });
});

test("schedule trigger has exactly mode, five-field cron, and timezone", () => {
  const state = graph({ graph_trigger: "schedule", graph_cron: "  0  2\t* * 1-5 ", graph_timezone: " Asia/Shanghai ", graph_debounce_seconds: "invalid" });
  assert.deepEqual(serialized("graph", state).external_extractor.trigger, {
    mode: "schedule", cron: "0 2 * * 1-5", timezone: "Asia/Shanghai",
  });
  state.graph_timezone = "asia/shanghai";
  assert.equal(serialized("graph", state).external_extractor.trigger.timezone, "Asia/Shanghai");
});

test("auto ignores stale cron/timezone while preserving explicit zero debounce", () => {
  const state = graph({ graph_debounce_seconds: "0", graph_cron: "invalid", graph_timezone: "invalid" });
  assert.deepEqual(serialized("graph", state).external_extractor.trigger, { mode: "auto", debounce_seconds: 0 });
});

test("graph modes and trigger modes are validated without coercion or echoed values", () => {
  invalid("graph", graph({ graph_mode: "secret-mode" }), "graph_mode", /OKF/);
  for (const trigger of ["", "AUTO", "automatic", "secret-trigger"]) {
    invalid("graph", graph({ graph_trigger: trigger }), "graph_trigger", /auto, manual, or schedule/);
  }
});

test("timeout requires a positive finite decimal number", () => {
  for (const timeout of ["", " ", "0", "-1", "NaN", "Infinity", "1e999", "0x10", "15seconds", "1_000"]) {
    invalid("graph", graph({ graph_timeout: timeout }), "graph_timeout", /HTTP timeout.*finite.*greater than 0/);
  }
  for (const [text, number] of [[".5", 0.5], [" 3600.25 ", 3600.25], ["1e3", 1000]]) {
    assert.equal(serialized("graph", graph({ graph_timeout: text })).external_extractor.timeout, number);
  }
  invalid("graph", graph({ graph_timeout: 3600 }), "graph_timeout", /strings/);
});

test("quiet seconds accepts finite values from 0 through 86400 only", () => {
  for (const debounce of ["", "-0.1", "86400.1", "NaN", "Infinity", "1e999", "0x10"]) {
    invalid("graph", graph({ graph_debounce_seconds: debounce }), "graph_debounce_seconds", /Quiet seconds.*between 0 and 86400/);
  }
  for (const text of ["0", "0.25", "15", "86400"]) {
    assert.equal(serialized("graph", graph({ graph_debounce_seconds: text })).external_extractor.trigger.debounce_seconds, Number(text));
  }
});

test("extractor URL validation accepts service names, HTTPS, paths and IPv6", () => {
  for (const url of ["http://okf-extractor:8080", "https://example.com/service/", "http://localhost:8080/v1", "http://[::1]:8080/service", "https://example.com:443/"]) {
    assert.equal(serialized("graph", graph({ graph_url: ` ${url} ` })).external_extractor.url, url.replace(/\/+$/, ""));
  }
});

test("extractor URL validation rejects malformed URLs, credentials, query, fragment and invalid ports", () => {
  for (const url of [
    "", "okf-extractor:8080", "/relative", "ftp://host/path", "javascript:alert(1)", "http://", "https:///host",
    "http://host:0", "http://host:65536", "http://host:notaport", "http://999.999.999.999", "http://[:::1]",
    "http://user:secret@host", "http://secret@host", "http://host?api_key=secret", "http://host/#secret", "http://host/path with space", "http://host\\path",
  ]) invalid("graph", graph({ graph_url: url, graph_api_key: "secret" }), "graph_url", /HTTP\(S\) URL/);
});

test("URL fallback permits serialization in a vm without URL or DOM globals", () => {
  const isolated = load({ URL: undefined }).api;
  assert.deepEqual(serialized("graph", graph(), isolated).external_extractor.trigger, { mode: "auto", debounce_seconds: 15 });
  for (const url of ["http://[::1]:8080", "http://[2001:db8::1]", "http://[::ffff:192.0.2.1]", "http://127.0.0.1:8080", "https://okf-extractor/service"]) {
    assert.equal(serialized("graph", graph({ graph_url: url }), isolated).external_extractor.url, url);
  }
  for (const url of ["http://999.999.999.999", "http://[:::1]", "http://[1:2:3]", "http://bad..host", "http://host:0", "http://secret@host"]) {
    invalid("graph", graph({ graph_url: url }), "graph_url", /HTTP\(S\) URL/, isolated);
  }
});

test("cron validation matches the numeric five-field engine grammar", () => {
  for (const expression of ["* * * * *", "*/15 0-23/2 1,15 * 0,7", "0 2 * 1-12 1-5", "5/10 * * * *", "59 23 31 12 7"]) {
    assert.equal(serialized("graph", graph({ graph_trigger: "schedule", graph_cron: expression })).external_extractor.trigger.cron, expression);
  }
  for (const expression of [
    "", "* * * *", "* * * * * *", "@daily", "0 2 * * MON", "60 * * * *", "0 24 * * *", "0 2 0 * *", "0 2 * 13 *", "0 2 * * 8",
    "*/0 * * * *", "0 20-10 * * *", "0,,1 * * * *", "0/ * * * *", "*/1/2 * * * *", "0 2.5 * * *", "-1 * * * *", "*/999999999999999999999 * * * *",
  ]) invalid("graph", graph({ graph_trigger: "schedule", graph_cron: expression }), "graph_cron", /cron/i);
});

test("scheduled timezone is checked with Intl and has a meaningful fallback", () => {
  for (const zone of ["", "Not_A_Timezone", "Mars/Olympus", "Asia/Not_A_Zone", "+01:00", "../UTC"]) {
    invalid("graph", graph({ graph_trigger: "schedule", graph_cron: "0 2 * * *", graph_timezone: zone }), "graph_timezone", /IANA timezone/);
  }
  const isolated = load({ Intl: undefined, URL: undefined }).api;
  for (const zone of ["UTC", "Asia/Shanghai", "America/New_York", "Etc/GMT+8"]) {
    assert.equal(serialized("graph", graph({ graph_trigger: "schedule", graph_cron: "0 2 * * *", graph_timezone: zone }), isolated).external_extractor.trigger.timezone, zone);
  }
  for (const zone of ["arbitrary", "Mars/Olympus", "+08:00"]) {
    invalid("graph", graph({ graph_trigger: "schedule", graph_cron: "0 2 * * *", graph_timezone: zone }), "graph_timezone", /IANA timezone/, isolated);
  }
});

test("task text limits match the extractor request schema", () => {
  invalid("graph", graph({ graph_language: "x".repeat(101) }), "graph_language", /100 characters/);
  invalid("graph", graph({ graph_goal: "x".repeat(8001) }), "graph_goal", /8000 characters/);
  assert.equal(serialized("graph", graph({ graph_language: "x".repeat(100) })).external_extractor.options.language.length, 100);
});

test("every vector mode declares asset scope without stamping model or device defaults", () => {
  for (const mode of MODES) {
    const result = serialized("vector", vector(mode));
    assert.deepEqual(result, { asset_types: ASSETS[mode] });
    for (const key of ["embedding_backend", "embedding_model", "embedding_model_path", "embedding_device"]) assert.ok(!(key in result));
  }
  assert.deepEqual(serialized("vector", {}), { asset_types: ["document"] });
});

test("document vector overrides use backend field names, numeric types and no block filter", () => {
  const state = vector("documents", {
    embedding_backend: "native_openvino_gme", embedding_model: " vendor/gme ", embedding_device: "GPU.0",
    chunk_size: "512", chunk_overlap: "0", figure_context_chars: "0", max_image_tokens: "1024",
  });
  assert.deepEqual(serialized("vector", state), {
    asset_types: ["document"], embedding_backend: "native_openvino_gme", embedding_model: "vendor/gme", embedding_device: "GPU.0",
    chunk_size: 512, chunk_overlap: 0, figure_context_chars: 0, max_image_tokens: 1024,
  });
});

test("media overrides remain in their own bank with explicit asset scope", () => {
  for (const mode of ["images", "video", "audio"]) {
    const state = vector(mode, { embedding_backend: "llamaindex_openvino", embedding_model: "model-id", embedding_device: "AUTO" });
    const number = mode === "video" ? "frames_per_clip" : "max_image_tokens";
    state[`vector_${mode}_${number}`] = "32";
    assert.deepEqual(serialized("vector", state), {
      asset_types: ASSETS[mode],
      embedding_backend: "llamaindex_openvino", embedding_model: "model-id", embedding_device: "AUTO", [number]: 32,
    });
  }
});

test("mode switching preserves document overrides but never applies them to media", () => {
  const state = vector("documents", { embedding_backend: "native_openvino_gme", embedding_model: "document-model", embedding_device: "GPU", chunk_size: "512", max_image_tokens: "1024" });
  const documents = serialized("vector", state);
  for (const mode of ["images", "video", "audio"]) {
    state.vector_mode = mode;
    assert.deepEqual(serialized("vector", state), { asset_types: ASSETS[mode] });
  }
  state.vector_images_embedding_model = "image-model";
  state.vector_images_embedding_backend = "llamaindex_openvino";
  state.vector_mode = "images";
  assert.equal(serialized("vector", state).embedding_model, "image-model");
  state.vector_mode = "documents";
  assert.deepEqual(serialized("vector", state), documents);
});

test("graph, vector, object, and SQL options cannot leak into each other", () => {
  const state = graph({ graph_api_key: "extractor-secret", graph_language: "zh", vector_images_embedding_model: "image-model", vector_documents_embedding_model: "text-model" });
  assert.deepEqual(serialized("vector", state), { asset_types: ["document"], embedding_model: "text-model" });
  assert.ok(!JSON.stringify(serialized("graph", state)).includes("text-model"));
  assert.deepEqual(serialized("object", state), {}); assert.deepEqual(serialized("sql", state), {});
  assert.deepEqual(serialized("", state), {}); assert.deepEqual(serialized(undefined, state), {});
  invalid("unknown-secret-type", state, "", /database type/);
});

test("all canonical document backends and listed devices are accepted", () => {
  for (const backend of ["", "llamaindex_openvino", "openvino_genai", "openai_compatible", "native_openvino_gme"]) {
    const result = serialized("vector", vector("documents", { embedding_backend: backend }));
    assert.equal(result.embedding_backend, backend || undefined);
  }
  for (const device of ["", "CPU", "GPU", "GPU.0", "AUTO"]) {
    assert.equal(serialized("vector", vector("documents", { embedding_device: device })).embedding_device, device || undefined);
  }
});

test("unknown vector modes, backend aliases and devices are rejected", () => {
  invalid("vector", Object.assign(api.defaults(), { vector_mode: "image" }), "vector_mode", /documents, images, video, or audio/);
  for (const backend of ["openai", "openvino", "gme", "other"]) invalid("vector", vector("documents", { embedding_backend: backend }), "vector_documents_embedding_backend", /canonical backend/);
  invalid("vector", vector("documents", { embedding_device: "GPU.1" }), "vector_documents_embedding_device", /Embedding device/);
});

test("media registry rejects native GME, OpenAI-compatible and GenAI runtimes", () => {
  for (const mode of ["images", "video", "audio"]) {
    for (const backend of ["native_openvino_gme", "openai_compatible", "openvino_genai"]) {
      invalid("vector", vector(mode, { embedding_backend: backend }), `vector_${mode}_embedding_backend`, /only llamaindex_openvino/);
    }
  }
});

test("remote base is optional and scoped to remote documents; per-source vector API keys never serialize", () => {
  const state = vector("documents", {
    embedding_backend: "openai_compatible", embedding_model: " remote-model ", embedding_api_base: " https://embeddings.example/v1/ ",
    embedding_device: "invalid-but-hidden", max_image_tokens: "invalid-but-hidden", chunk_size: "512",
  });
  state.vector_documents_embedding_api_key = "must-not-serialize";
  state.embedding_api_key = "must-not-serialize";
  state.graph_api_key = "must-not-serialize";
  assert.deepEqual(serialized("vector", state), {
    asset_types: ["document"], embedding_backend: "openai_compatible", embedding_model: "remote-model", embedding_api_base: "https://embeddings.example/v1", chunk_size: 512,
  });
  state.vector_documents_embedding_api_base = " ";
  assert.ok(!("embedding_api_base" in serialized("vector", state)));
  state.vector_documents_embedding_api_base = "http://user:secret@host";
  invalid("vector", state, "vector_documents_embedding_api_base", /Remote API base/);
  state.vector_documents_embedding_backend = "llamaindex_openvino";
  state.vector_documents_embedding_device = "CPU"; state.vector_documents_max_image_tokens = "";
  const local = serialized("vector", state);
  assert.ok(!("embedding_api_base" in local)); assert.equal(local.embedding_device, "CPU");
});

test("blank optional vector values are omitted, including whitespace-only values", () => {
  const state = vector("documents");
  for (const field of [...COMMON, ...EXTRA.documents].filter(field => field !== "asset_types")) state[`vector_documents_${field}`] = " \t ";
  assert.deepEqual(serialized("vector", state), { asset_types: ["document"] });
});

test("vector counts must be finite safe whole numbers with the correct zero policy", () => {
  const cases = [
    ["documents", "chunk_size", true], ["documents", "chunk_overlap", false], ["documents", "figure_context_chars", false],
    ["documents", "max_image_tokens", true], ["images", "max_image_tokens", true], ["audio", "max_image_tokens", true], ["video", "frames_per_clip", true],
  ];
  for (const [mode, field, positive] of cases) {
    for (const raw of ["-1", "1.5", "NaN", "Infinity", "1e999", "9007199254740992", "0x10", ...(positive ? ["0"] : [])]) {
      invalid("vector", vector(mode, { [field]: raw }), `vector_${mode}_${field}`, /finite whole number/);
    }
    assert.equal(serialized("vector", vector(mode, { [field]: positive ? "1" : "0" }))[field], positive ? 1 : 0);
  }
});

test("chunk overlap must be smaller only when both chunk fields are explicitly set", () => {
  for (const overlap of ["512", "513"]) invalid("vector", vector("documents", { chunk_size: "512", chunk_overlap: overlap }), "vector_documents_chunk_overlap", /smaller than chunk size/);
  assert.deepEqual(serialized("vector", vector("documents", { chunk_size: "1", chunk_overlap: "0" })), { asset_types: ["document"], chunk_size: 1, chunk_overlap: 0 });
  assert.deepEqual(serialized("vector", vector("documents", { chunk_overlap: "1024" })), { asset_types: ["document"], chunk_overlap: 1024 });
  assert.deepEqual(serialized("vector", vector("documents", { chunk_size: "1" })), { asset_types: ["document"], chunk_size: 1 });
});

test("unsupported tuning fields from inactive modes are neither validated nor serialized", () => {
  const state = vector("video", { frames_per_clip: "32" });
  state.vector_video_chunk_size = "not-a-number"; state.vector_video_max_image_tokens = "not-a-number";
  state.vector_documents_chunk_size = "not-a-number"; state.graph_url = "not-a-url";
  assert.deepEqual(serialized("vector", state), { asset_types: ["video"], frames_per_clip: 32 });
});

test("validation messages and error objects never contain credentials or raw failing values", () => {
  const secret = "sensitive-token-very-private";
  const cases = [
    ["graph", graph({ graph_api_key: secret, graph_url: `http://user:${secret}@host` })],
    ["graph", graph({ graph_api_key: secret, graph_timeout: secret })],
    ["graph", graph({ graph_api_key: secret, graph_trigger: secret })],
    ["graph", graph({ graph_api_key: secret, graph_trigger: "schedule", graph_cron: secret })],
    ["graph", graph({ graph_api_key: secret, graph_trigger: "schedule", graph_cron: "0 2 * * *", graph_timezone: secret })],
    ["vector", vector("documents", { embedding_backend: "openai_compatible", embedding_api_base: `http://user:${secret}@host` })],
    ["vector", vector("documents", { embedding_backend: secret })],
  ];
  for (const [type, state] of cases) {
    assert.throws(() => api.serialize(type, state), error => {
      for (const text of [String(error), error.stack, JSON.stringify(error)]) assert.ok(!text.includes(secret));
      return true;
    });
  }
});

test("serialization does not mutate frozen, partial, valid or invalid state", () => {
  const states = [
    ["graph", graph()], ["graph", graph({ graph_trigger: "manual" })],
    ["graph", graph({ graph_trigger: "schedule", graph_cron: "0 2 * * *" })],
    ...MODES.map(mode => ["vector", vector(mode)]), ["graph", { graph_mode: "documents" }],
  ];
  for (const [type, state] of states) {
    const before = JSON.stringify(state);
    Object.freeze(state); api.serialize(type, state);
    assert.equal(JSON.stringify(state), before);
  }
  const invalidState = Object.freeze(graph({ graph_timeout: "bad" }));
  invalid("graph", invalidState, "graph_timeout", /HTTP timeout/);
  const result = api.serialize("graph", graph({ graph_language: "en" }));
  result.asset_types.push("changed"); result.external_extractor.options.language = "changed";
  assert.equal(serialized("graph", graph({ graph_language: "en" })).external_extractor.options.language, "en");
});

// Minimal standards-shaped fixture for DOM-independent mount/event regression
// tests. Browser layout/focus is additionally checked in an actual browser.
class Element {
  constructor(tag, document) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = document;
    this.children = []; this.parentNode = null; this.dataset = {};
    this.attributes = new Map(); this.listeners = new Map();
    this.hidden = false; this.disabled = false; this._text = "";
    this.selectionStart = 0; this.selectionEnd = 0;
  }
  appendChild(child) {
    if (child.parentNode) child.parentNode.children.splice(child.parentNode.children.indexOf(child), 1);
    this.children.push(child); child.parentNode = this; return child;
  }
  replaceChildren(...children) {
    for (const child of this.children) child.parentNode = null;
    this.children = []; this._text = "";
    for (const child of children) this.appendChild(child);
  }
  set textContent(value) { this.replaceChildren(); this._text = String(value); }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set value(value) {
    const text = String(value);
    this._value = this.tagName === "SELECT" && !this.children.some(child => child.value === text) ? "" : text;
    this.selectionStart = this.selectionEnd = this._value.length;
  }
  get value() { return this._value ?? (this.tagName === "SELECT" ? this.children[0]?.value || "" : ""); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }
  dispatchEvent(event) {
    if (!event.target) event.target = this;
    for (const listener of this.listeners.get(event.type) || []) listener(event);
    if (event.bubbles && this.parentNode) this.parentNode.dispatchEvent(event);
    return true;
  }
  querySelectorAll(selector) {
    const tags = selector.split(",").map(tag => tag.trim().toUpperCase());
    return descendants(this).filter(child => tags.includes(child.tagName));
  }
  focus() { this.ownerDocument.activeElement = this; }
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
}
class Document {
  constructor() { this.activeElement = null; }
  createElement(tag) { return new Element(tag, this); }
}
function descendants(parent) { return parent.children.flatMap(child => [child, ...descendants(child)]); }
function control(container, key) {
  const el = descendants(container).find(el => el.dataset.sourceOption === key);
  assert.ok(el, `Missing control ${key}`); return el;
}
function change(el, value, type = "input") {
  el.focus(); el.value = value; el.dispatchEvent({ type, bubbles: true });
}
function fixture(type, state, options = {}) {
  const document = new Document(), container = document.createElement("div");
  const loaded = load({ URL });
  const supplied = state || loaded.api.defaults();
  const mounted = loaded.api.mount(container, { type, state: supplied, ...options });
  return { ...loaded, document, container, mounted, state: supplied };
}

test("mount keeps the supplied state identity and fills partial state with string defaults", () => {
  const state = { graph_mode: "documents" };
  const f = fixture("graph", state);
  assert.equal(f.mounted.state, state);
  assert.equal(state.graph_timeout, "3600"); assert.equal(state.vector_images_embedding_model, "");
  assert.deepEqual(plain(f.mounted.read()), serialized("graph", state));
  assert.equal(f.container.children.length, 1);
});

test("graph mount has labeled structured controls, masked credentials and only named instruction textareas", () => {
  const f = fixture("graph");
  const all = descendants(f.container), fields = all.filter(el => el.dataset.sourceOption);
  for (const el of fields) {
    if (el.tagName === "SUMMARY") assert.equal(el.getAttribute("aria-label"), "Graph source content");
    else assert.ok(all.some(label => label.tagName === "LABEL" && label.htmlFor === el.id));
    const ids = el.getAttribute("aria-describedby").split(" ");
    assert.ok(ids.every(id => all.some(description => description.id === id)));
  }
  const password = control(f.container, "graph_api_key");
  assert.equal(password.type, "password"); assert.equal(password.autoComplete, "new-password");
  assert.equal(password.disabled, true, "OKF-only must disable hidden extraction controls");
  assert.equal(control(f.container, "graph_timeout").type, "number");
  assert.deepEqual(fields.filter(el => el.tagName === "TEXTAREA").map(el => el.dataset.sourceOption).sort(), NAMES.map(name => `graph_instruction_${name}`).sort());
  assert.ok(fields.every(el => !/json/i.test(el.name)));
});

test("conditional graph fields keep their DOM, values and the active selector's focus", () => {
  const f = fixture("graph"), documents = assetCheckbox(f.container, "document"), url = control(f.container, "graph_url");
  checkAsset(f.container, "document", true); assert.equal(url.disabled, false);
  change(url, "https://extractor.example/service");
  const trigger = control(f.container, "graph_trigger"), quiet = control(f.container, "graph_debounce_seconds"), cron = control(f.container, "graph_cron");
  change(quiet, "25"); change(trigger, "schedule", "change");
  assert.equal(f.document.activeElement, trigger); assert.equal(quiet.disabled, true); assert.equal(cron.disabled, false);
  change(cron, "0 3 * * *"); change(trigger, "manual", "change");
  assert.equal(f.document.activeElement, trigger); assert.equal(cron.value, "0 3 * * *"); assert.equal(cron.disabled, true);
  assert.equal(f.mounted.read().external_extractor.trigger, "manual");
  checkAsset(f.container, "document", false);
  assert.equal(f.document.activeElement, documents); assert.equal(url.disabled, true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["okf"] });
  checkAsset(f.container, "document", true); change(trigger, "auto", "change");
  assert.equal(control(f.container, "graph_url"), url); assert.equal(url.value, "https://extractor.example/service");
  assert.equal(quiet.value, "25"); assert.equal(f.document.activeElement, trigger);
});

test("input and select events mutate in place and notify once per actual change without validating partial text", () => {
  const calls = [], f = fixture("graph", graph(), { onChange: state => calls.push(state) });
  const timeout = control(f.container, "graph_timeout");
  change(timeout, ""); timeout.dispatchEvent({ type: "change", bubbles: true });
  assert.equal(f.state.graph_timeout, ""); assert.equal(calls.length, 1); assert.equal(calls[0], f.state);
  assert.equal(f.document.activeElement, timeout);
  checkAsset(f.container, "document", false);
  assert.equal(f.state.graph_mode, "okf"); assert.equal(calls.length, 2);
});

test("read displays safe validation errors, focuses the field, and clears errors on correction", () => {
  const secret = "never-show-this-token", f = fixture("graph", graph({ graph_api_key: secret }));
  const url = control(f.container, "graph_url"); change(url, `http://user:${secret}@host`);
  assert.throws(() => f.mounted.read(), /HTTP\(S\) URL/);
  assert.equal(f.document.activeElement, url); assert.equal(url.getAttribute("aria-invalid"), "true");
  const alert = descendants(f.container).find(el => el.getAttribute("role") === "alert");
  assert.equal(alert.hidden, false); assert.ok(!alert.textContent.includes(secret));
  change(url, "https://extractor.example");
  assert.equal(alert.hidden, true); assert.equal(url.getAttribute("aria-invalid"), null);
  assert.equal(f.mounted.read().external_extractor.url, "https://extractor.example");
});

test("advanced disclosure is string state, preserves values and does not disable entered overrides", () => {
  const f = fixture("graph", graph());
  const advanced = descendants(f.container).find(el => el.className === "so-advanced");
  assert.equal(advanced.open, false);
  advanced.open = true; advanced.dispatchEvent({ type: "toggle" });
  assert.equal(f.state.graph_advanced, "true");
  const domain = control(f.container, "graph_instruction_DOMAIN"); change(domain, "Clinical terms");
  advanced.open = false; advanced.dispatchEvent({ type: "toggle" });
  assert.equal(f.state.graph_advanced, "false"); assert.equal(domain.value, "Clinical terms");
  assert.deepEqual(plain(f.mounted.read().external_extractor.options), { instructions: { DOMAIN: "Clinical terms" } });
});

test("same-state remount keeps DOM, focus and selection, refreshes model catalogs and uses late global t", () => {
  const models = { embedding: { models: [{ name: "embedding-a", path: "/models/a", ready: true, model_type: "embedding" }] } };
  const f = fixture("vector", undefined, { models });
  const picker = control(f.container, "vector_documents_embedding_model");
  change(picker, "custom-model"); picker.setSelectionRange(2, 6);
  f.context.t = text => `<translated>${text}`;
  const refreshed = f.api.mount(f.container, { type: "vector", state: f.state, models: { embedding: { opt: { models: [{ name: "embedding-b", ready: false }] } } } });
  assert.equal(refreshed, f.mounted); assert.equal(control(f.container, "vector_documents_embedding_model"), picker);
  assert.equal(f.document.activeElement, picker); assert.equal(picker.selectionStart, 2); assert.equal(picker.selectionEnd, 6);
  const list = descendants(f.container).find(el => el.id === picker.getAttribute("list"));
  assert.deepEqual(list.children.map(option => option.value), ["embedding-b"]);
  assert.match(list.children[0].label, /<translated>not prepared/);
  assert.ok(descendants(f.container).some(el => el.tagName === "LABEL" && el.textContent === "<translated>Model override (optional)"));
  assert.ok(descendants(f.container).some(el => el.tagName === "LEGEND" && el.textContent === "<translated>Vector content"));
  assert.deepEqual(plain(refreshed.read()), { asset_types: ["document"], embedding_model: "custom-model" });
});

test("model catalogs are suggestions only and support raw, wrapped and embedding/multimodal dictionaries", () => {
  const catalogs = [
    ["manual-id", "manual-id"],
    { model_id: "configured-id", models: [{ name: "prepared-id", path: "/model" }] },
    { embedding: { opt: { model_id: "configured-id", models: [{ name: "prepared-id" }] } }, multimodal: { models: [{ name: "media-id" }] } },
  ];
  for (const models of catalogs) {
    const f = fixture("vector", undefined, { models });
    assert.deepEqual(plain(f.mounted.read()), { asset_types: ["document"] });
    assert.equal(f.state.vector_documents_embedding_backend, ""); assert.equal(f.state.vector_documents_embedding_model, "");
    const picker = control(f.container, "vector_documents_embedding_model");
    const list = descendants(f.container).find(el => el.id === picker.getAttribute("list"));
    assert.ok(list.children.length > 0); assert.equal(new Set(list.children.map(el => el.value)).size, list.children.length);
  }
  const f = fixture("vector", undefined, { models: { embedding: { models: [{ name: "text-only" }] }, multimodal: { models: [
    { name: "image-model", model_type: "multimodal", supported_kinds: ["image", "audio"] },
    { name: "video-model", model_type: "multimodal", supported_kinds: ["video"] },
  ] } } });
  const imagePicker = control(f.container, "vector_images_embedding_model"), videoPicker = control(f.container, "vector_video_embedding_model");
  const imageList = descendants(f.container).find(el => el.id === imagePicker.getAttribute("list"));
  const videoList = descendants(f.container).find(el => el.id === videoPicker.getAttribute("list"));
  assert.deepEqual(imageList.children.map(el => el.value), ["image-model"]);
  assert.deepEqual(videoList.children.map(el => el.value), ["video-model"]);
});

test("vector content selection constrains media backends and preserves document overrides", () => {
  const f = fixture("vector");
  const backend = control(f.container, "vector_documents_embedding_backend");
  change(backend, "native_openvino_gme", "change");
  change(control(f.container, "vector_documents_embedding_model"), "document-model");
  for (const name of ["images", "video", "audio"]) {
    selectAssets(f.container, ASSETS[name]);
    assert.equal(f.state.vector_mode, name);
    assert.equal(f.document.activeElement.type, "checkbox");
    const mediaBackend = control(f.container, `vector_${name}_embedding_backend`);
    assert.deepEqual(mediaBackend.children.map(el => el.value), ["", "llamaindex_openvino"]);
    assert.equal(mediaBackend.disabled, false); assert.equal(backend.disabled, true);
    assert.deepEqual(plain(f.mounted.read()), { asset_types: ASSETS[name] });
  }
  selectAssets(f.container, ["document"]);
  assert.equal(backend.value, "native_openvino_gme");
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["document"], embedding_backend: "native_openvino_gme", embedding_model: "document-model" });
});

test("remote backend hides and preserves local fields and never renders a vector API-key control", () => {
  const f = fixture("vector"), backend = control(f.container, "vector_documents_embedding_backend");
  const device = control(f.container, "vector_documents_embedding_device"), endpoint = control(f.container, "vector_documents_embedding_api_base");
  change(device, "GPU", "change"); change(backend, "openai_compatible", "change");
  assert.equal(f.document.activeElement, backend); assert.equal(device.disabled, true); assert.equal(endpoint.disabled, false);
  change(endpoint, "https://embeddings.example/v1");
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["document"], embedding_backend: "openai_compatible", embedding_api_base: "https://embeddings.example/v1" });
  change(backend, "llamaindex_openvino", "change");
  assert.equal(device.value, "GPU"); assert.equal(endpoint.value, "https://embeddings.example/v1");
  assert.equal(endpoint.disabled, true); assert.equal(device.disabled, false);
  assert.ok(descendants(f.container).filter(el => el.dataset.sourceOption).every(el => !el.dataset.sourceOption.includes("api_key")));
});

test("multiple mounts have unique accessible IDs and object/sql mounts need no controls", () => {
  const f = fixture("graph"), second = f.document.createElement("div");
  f.api.mount(second, { type: "graph", state: f.api.defaults() });
  const firstIds = new Set(descendants(f.container).map(el => el.id).filter(Boolean));
  assert.ok(descendants(second).filter(el => el.id).every(el => !firstIds.has(el.id)));
  for (const type of ["object", "sql", ""]) {
    const neutral = fixture(type);
    assert.equal(descendants(neutral.container).filter(el => el.dataset.sourceOption).length, 0);
    assert.deepEqual(plain(neutral.mounted.read()), {});
  }
});

test("mount reports caller contract mistakes without touching the DOM at load time", () => {
  assert.throws(() => api.mount(null, { type: "graph" }), /DOM container/);
  const document = new Document(), container = document.createElement("div");
  assert.throws(() => api.mount(container, { type: "graph", state: Object.freeze(api.defaults()) }), /mutable/);
  assert.throws(() => api.mount(container, { type: "graph", state: { graph_mode: 1 } }), /strings/);
  assert.throws(() => api.mount(container, { type: "graph", onChange: "not-a-function" }), /onChange/);
  assert.throws(() => api.serialize("graph", []), /flat object/);
});

test("asset scopes are required, exact and deduplicated", () => {
  for (const raw of ["[]", "null", '"video"', '["okf"]', "not-json"]) {
    invalid("vector", vector("video", { asset_types: raw }), "vector_video_asset_types", /content type/);
  }
  assert.deepEqual(serialized("vector", vector("documents", { asset_types: '["pdf","md","pdf"]' })), { asset_types: ["pdf", "md"] });
  const docs = graph({ graph_asset_types: '["document"]' });
  invalid("graph", docs, "graph_asset_types", /requires OKF/);
  invalid("graph", graph({ graph_asset_types: "[]" }), "graph_asset_types", /Select at least one/);
  invalid("graph", graph({ graph_asset_types: '["video"]' }), "graph_asset_types", /Invalid content type/);
});

test("representation filters are absent from UI, defaults and submissions", () => {
  const f = fixture("vector");
  const all = descendants(f.container);
  assert.ok(!all.some(el => /Representation filters|Block roles|Block kinds|block_roles|block_kinds/.test(el.textContent)));
  assert.ok(!all.some(el => /block_roles|block_kinds/.test(el.dataset.sourceOption || "")));
  assert.ok(Object.keys(f.api.defaults()).every(key => !/block_roles|block_kinds/.test(key)));
  for (const mode of MODES) {
    selectAssets(f.container, ASSETS[mode]);
    assert.deepEqual(plain(f.mounted.read()), { asset_types: ASSETS[mode] });
    const state = vector(mode, { block_roles: "l2_caption", block_kinds: "text" });
    assert.deepEqual(serialized("vector", state), { asset_types: ASSETS[mode] });
  }
});

test("public path and precision have no controls, defaults or serialized fields", () => {
  const f = fixture("vector");
  const names = descendants(f.container).filter(el => el.dataset.sourceOption).map(el => el.dataset.sourceOption);
  assert.ok(names.every(name => !/embedding_model_path|precision/.test(name)));
  assert.ok(Object.keys(f.api.defaults()).every(name => !/embedding_model_path|precision/.test(name)));
  for (const mode of MODES) {
    const options = serialized("vector", vector(mode, { embedding_model_path: "/stale", precision: "fp16" }));
    assert.ok(!("embedding_model_path" in options)); assert.ok(!("precision" in options));
    assert.deepEqual(options.asset_types, ASSETS[mode]);
  }
});

function assetCheckbox(container, value) {
  return descendants(container).find(el => el.tagName === "INPUT" && el.type === "checkbox" && el.value === value);
}
function checkAsset(container, value, checked) {
  const input = assetCheckbox(container, value);
  assert.ok(input, `Missing asset checkbox ${value}`);
  input.focus();
  input.checked = checked; input.dispatchEvent({ type: "change", bubbles: true });
}

function selectAssets(container, values) {
  const inputs = descendants(container).filter(el => el.tagName === "INPUT" && el.type === "checkbox");
  for (const input of inputs) {
    if (input.checked !== values.includes(input.value)) checkAsset(container, input.value, values.includes(input.value));
  }
}

test("vector content uses one checkbox dropdown with the original four categories and document default", () => {
  const f = fixture("vector");
  const all = descendants(f.container);
  assert.equal(all.filter(el => el.tagName === "LEGEND" && el.textContent === "Vector content").length, 1);
  assert.ok(!all.some(el => /Asset types/.test(el.textContent)));
  assert.equal(all.filter(el => el.className === "asset-types-dropdown").length, 1);
  assert.ok(!all.some(el => el.dataset.sourceOption === "vector_mode"));
  const inputs = all.filter(el => el.type === "checkbox");
  assert.deepEqual(inputs.map(el => [el.value, el.parentNode.textContent]), [
    ["document", "Documents"], ["image", "Images"], ["video", "Video"], ["audio", "Audio"],
  ]);
  assert.deepEqual(inputs.filter(el => el.checked).map(el => el.value), ["document"]);
  assert.equal(control(f.container, "vector_asset_types").textContent, "Documents▾");
  for (const mode of MODES) {
    selectAssets(f.container, ASSETS[mode]);
    assert.deepEqual(plain(f.mounted.read()), { asset_types: ASSETS[mode] });
  }
  assert.ok(!("asset_type" in f.mounted.read()), "keep the existing plural API parameter");
  const graphForm = fixture("graph");
  assert.equal(descendants(graphForm.container).filter(el => el.tagName === "LEGEND" && el.textContent === "Graph source content").length, 1);
  assert.ok(!descendants(graphForm.container).some(el => el.dataset.sourceOption === "graph_mode" || el.textContent === "Graph content" || el.textContent === "Knowledge input"));
  assert.ok(!descendants(graphForm.container).some(el => /Asset types/.test(el.textContent)));
  assert.equal(assetCheckbox(graphForm.container, "okf").checked, true);
  assert.equal(assetCheckbox(graphForm.container, "document").checked, false);
  assert.equal(control(graphForm.container, "graph_asset_types").textContent, "OKF▾");
  assert.deepEqual(plain(graphForm.mounted.read()), { asset_types: ["okf"] });
});

test("category selection and refresh keep separate model banks", () => {
  const calls = [], f = fixture("vector", undefined, { onChange: state => calls.push(state) });
  const picker = control(f.container, "vector_asset_types");
  change(control(f.container, "vector_documents_embedding_model"), "document-model");
  f.api.mount(f.container, { type: "vector", state: f.state, onChange: state => calls.push(state) });
  assert.equal(control(f.container, "vector_asset_types"), picker);
  selectAssets(f.container, ["video"]);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["video"] });
  change(control(f.container, "vector_video_embedding_model"), "custom-video-fp16");
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["video"], embedding_model: "custom-video-fp16" });
  selectAssets(f.container, ["document"]);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["document"], embedding_model: "document-model" });
  selectAssets(f.container, ["video"]);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["video"], embedding_model: "custom-video-fp16" });
  assert.ok(calls.length > 0 && calls.every(state => state === f.state));
});

test("graph checkbox controls extraction visibility and cannot silently restore a cleared selection", () => {
  const f = fixture("graph"), url = control(f.container, "graph_url");
  assert.equal(url.disabled, true);
  checkAsset(f.container, "document", true);
  assert.equal(url.disabled, false);
  assert.equal(f.state.graph_mode, "documents");
  checkAsset(f.container, "okf", false);
  assert.equal(assetCheckbox(f.container, "document").checked, false);
  assert.equal(url.disabled, true);
  assert.throws(() => f.mounted.read(), /Select at least one/);
  checkAsset(f.container, "okf", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["okf"] });
});

test("vector checkboxes retain multiple selections, emit exact scopes and preserve dropdown focus on refresh", () => {
  const calls = [], f = fixture("vector", undefined, { onChange: state => calls.push(state) });
  const dropdown = descendants(f.container).find(el => el.className === "asset-types-dropdown");
  dropdown.open = true;
  checkAsset(f.container, "image", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["image"] });
  assert.equal(dropdown.open, true);
  assert.equal(assetCheckbox(f.container, "document").checked, false);
  selectAssets(f.container, ["image", "audio"]);
  change(control(f.container, "vector_images_embedding_model"), "shared-gme-model");
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["image", "audio"], embedding_model: "shared-gme-model" });
  f.context.t = text => `translated:${text}`;
  const focused = f.document.activeElement;
  f.api.mount(f.container, { type: "vector", state: f.state, onChange: state => calls.push(state) });
  assert.equal(f.document.activeElement, focused);
  assert.equal(dropdown.open, true);
  assert.equal(control(f.container, "vector_asset_types").textContent, "translated:Images, translated:Audio▾");
  assert.ok(calls.every(state => state === f.state));
});

test("content dropdown bulk actions select only compatible content, clear and restore validation focus", () => {
  for (const kind of ["vector", "graph"]) {
    const f = fixture(kind);
    const dropdown = descendants(f.container).find(el => el.className === "asset-types-dropdown");
    const summary = control(f.container, `${kind}_asset_types`);
    const buttons = descendants(dropdown).filter(el => el.tagName === "BUTTON");
    buttons.find(el => el.textContent === (kind === "vector" ? "Select images and audio" : "Select all")).dispatchEvent({ type: "click" });
    assert.deepEqual(plain(f.mounted.read()).asset_types, kind === "vector" ? ["image", "audio"] : ["okf", "document"]);
    buttons.find(el => el.textContent === "Clear selection").dispatchEvent({ type: "click" });
    assert.throws(() => f.mounted.read(), /Select at least one/);
    assert.equal(f.document.activeElement, summary);
    assert.equal(summary.getAttribute("aria-invalid"), "true");
    checkAsset(f.container, kind === "vector" ? "document" : "okf", true);
    assert.equal(descendants(f.container).find(el => el.getAttribute("role") === "alert").hidden, true);
    assert.deepEqual(plain(f.mounted.read()), { asset_types: kind === "vector" ? ["document"] : ["okf"] });
    dropdown.open = true;
    dropdown.dispatchEvent({ type: "keydown", key: "Escape", preventDefault() {}, stopPropagation() {} });
    assert.equal(dropdown.open, false);
    assert.equal(f.document.activeElement, summary);
  }
});

test("explicit vector multi-selection drives its model bank without mutating state or leaking other banks", () => {
  const state = Object.assign(vector("video", { embedding_model: "unused-video-model" }), {
    vector_asset_types: '["image","audio","image"]',
    vector_images_embedding_model: "shared-gme",
    vector_documents_embedding_model: "unused-text-model",
  });
  Object.freeze(state);
  assert.deepEqual(serialized("vector", state), { asset_types: ["image", "audio"], embedding_model: "shared-gme" });
  for (const raw of ["[]", "null", '"video"', '["okf"]', "not-json"]) {
    invalid("vector", { vector_asset_types: raw }, "vector_asset_types", /content type/);
  }
});

test("vector category clicks switch incompatible groups in either direction without losing model overrides", () => {
  const f = fixture("vector");
  change(control(f.container, "vector_documents_embedding_model"), "doc-model");
  checkAsset(f.container, "audio", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["audio"] });
  checkAsset(f.container, "image", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["image", "audio"] });
  checkAsset(f.container, "video", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["video"] });
  change(control(f.container, "vector_video_embedding_model"), "video-model");
  checkAsset(f.container, "image", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["image"] });
  checkAsset(f.container, "document", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["document"], embedding_model: "doc-model" });
  checkAsset(f.container, "video", true);
  assert.deepEqual(plain(f.mounted.read()), { asset_types: ["video"], embedding_model: "video-model" });
});

test("restored incompatible vector combinations are rejected locally with the content field focused", () => {
  for (const selected of [["document", "image"], ["document", "audio"], ["document", "video"],
    ["image", "video"], ["video", "audio"], ["document", "image", "video", "audio"]]) {
    const state = { vector_asset_types: JSON.stringify(selected) };
    invalid("vector", state, "vector_asset_types", /separate source|own source/);
    const f = fixture("vector", state);
    const summary = control(f.container, "vector_asset_types");
    assert.equal(summary.getAttribute("aria-invalid"), "true");
    assert.throws(() => f.mounted.read(), /separate source|own source/);
    assert.equal(f.document.activeElement, summary);
    checkAsset(f.container, "document", true);
    assert.deepEqual(plain(f.mounted.read()), { asset_types: ["document"] });
  }
});

test("graph document checkbox always adds OKF and unchecking OKF clears its dependent document", () => {
  const f = fixture("graph");
  checkAsset(f.container, "okf", false);
  checkAsset(f.container, "document", true);
  assert.equal(assetCheckbox(f.container, "okf").checked, true);
  assert.deepEqual(plain(f.mounted.read()).asset_types, ["okf", "document"]);
  checkAsset(f.container, "okf", false);
  assert.equal(assetCheckbox(f.container, "document").checked, false);
  assert.throws(() => f.mounted.read(), /Select at least one/);
});

// Used by the Python contract test: these payloads come from real checkbox
// events and read(), then pass through FileAssetLibrary.create_source offline.
if (process.env.CONSOLE_SOURCE_OPTIONS_CONTRACT === "1") {
  const cases = [];
  const contents = ["document", "image", "video", "audio"];
  for (let mask = 1; mask < 16; mask++) {
    for (const order of [contents, [...contents].reverse()]) {
      const f = fixture("vector");
      for (const item of order) if (mask & (1 << contents.indexOf(item))) checkAsset(f.container, item, true);
      cases.push({ type: "vector", options: plain(f.mounted.read()) });
    }
  }
  for (const kind of ["vector", "graph"]) {
    const f = fixture(kind);
    cases.push({ type: kind, options: plain(f.mounted.read()) });
    const button = descendants(f.container).find(el => el.tagName === "BUTTON" && el.textContent === (kind === "vector" ? "Select images and audio" : "Select all"));
    button.dispatchEvent({ type: "click" });
    cases.push({ type: kind, options: plain(f.mounted.read()) });
  }
  console.log(`SOURCE_OPTIONS_CONTRACT=${JSON.stringify(cases)}`);
}
