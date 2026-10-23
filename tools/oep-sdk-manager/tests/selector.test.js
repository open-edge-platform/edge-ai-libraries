// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const assets = join(__dirname, "../docs/oep-sdk-manager-files");
const selectorSource = readFileSync(join(assets, "config.js"), "utf8");
const resizerSource = readFileSync(join(assets, "iframe-resizer.js"), "utf8");

function selectorContext() {
  const context = vm.createContext({
    URLSearchParams,
    document: { addEventListener() {} },
  });
  vm.runInContext(selectorSource, context);
  return context;
}

test("all SDK/version combinations retain their install and tutorial rules", () => {
  const context = selectorContext();
  const result = vm.runInContext(`(() => {
    let combinations = 0;
    for (const sdk of CONFIG.categories.find(cat => cat.key === "SDK").options) {
      const versions = sdk.supports?.VERSION ??
        CONFIG.categories.find(cat => cat.key === "VERSION").options.map(opt => opt.value);
      for (const version of versions) {
        const state = { SDK: sdk.value, OP_SYSTEM: "UBUNTU", VERSION: version };
        repairState(state);
        if (state.SDK !== sdk.value || state.VERSION !== version) return false;
        for (const output of CONFIG.outputs) {
          const rule = firstMatch(output.rules, state);
          if (!rule) return false;
          if (output.id === "install") {
            const latestNames = {
              OEP_VISION: "metro-vision-ai-sdk.sh",
              OEP_GENAI: "metro-gen-ai-sdk.sh",
              VISUAL_AI_DEMO: "metro-visual-ai-demo-kit.sh",
              UAV_MISSION_COMPUTE: "uav-mission-compute-sdk.sh",
            };
            const releaseNames = {
              OEP_VISION: "oep-vision-ai-sdk.sh",
              OEP_GENAI: "oep-gen-ai-sdk.sh",
              VISUAL_AI_DEMO: "visual-ai-demo-kit.sh",
              UAV_MISSION_COMPUTE: "uav-mission-compute-sdk.sh",
            };
            const path = version === "latest"
              ? "edge-ai-libraries/refs/heads/main/tools/oep-sdk-manager/scripts/" + latestNames[sdk.value]
              : "edge-ai-suites/refs/heads/release-" + version + ".0/metro-ai-suite/metro-sdk-manager/scripts/" + releaseNames[sdk.value];
            if (rule.text !== "curl -fsS https://raw.githubusercontent.com/open-edge-platform/" + path + " | bash") return false;
          }
        }
        combinations++;
      }
    }
    return combinations;
  })()`, context);
  assert.equal(result, 11);
});

test("incompatible versions stay disabled and invalid shared selections are repaired", () => {
  const context = selectorContext();
  assert.equal(vm.runInContext(`isOptionAvailable(
    CONFIG.categories.find(cat => cat.key === "VERSION"),
    { value: "2026.1" },
    { SDK: "UAV_MISSION_COMPUTE", OP_SYSTEM: "UBUNTU", VERSION: "latest" }
  )`, context), false);
  assert.equal(vm.runInContext(`(() => {
    const state = { SDK: "invalid", OP_SYSTEM: "invalid", VERSION: "invalid" };
    repairState(state);
    return CONFIG.categories.every(cat =>
      cat.options.some(opt => opt.value === state[cat.key] && isOptionAvailable(cat, opt, state))
    );
  })()`, context), true);
});

test("2026.0 is removed and old shared selections fall back to latest", () => {
  const context = selectorContext();
  assert.equal(vm.runInContext(`(() => {
    const versions = CONFIG.categories.find(cat => cat.key === "VERSION").options;
    if (versions.some(opt => opt.value === "2026.0")) return false;
    if (CONFIG.outputs.some(output => output.rules.some(rule => rule.when.VERSION === "2026.0"))) return false;
    const state = { SDK: "OEP_VISION", OP_SYSTEM: "UBUNTU", VERSION: "2026.0" };
    repairState(state);
    return state.VERSION === "latest";
  })()`, context), true);
  const html = readFileSync(join(assets, "selector.html"), "utf8");
  assert.doesNotMatch(html, /All install commands currently use the main branch/);
});

test("unavailable categories do not keep stale state", () => {
  const context = selectorContext();
  assert.equal(vm.runInContext(`(() => {
    CONFIG.categories.push({ key: "EMPTY", options: [] });
    const state = { EMPTY: "stale" };
    repairState(state);
    return Object.hasOwn(state, "EMPTY");
  })()`, context), false);
});

test("copy is disabled when no installation rule matches", () => {
  const context = selectorContext();
  vm.runInContext(`
    const copy = { disabled: false };
    const install = { textContent: "" };
    document.querySelector = selector => selector === "#copyCmd" ? copy : install;
    history = { replaceState() {} };
    location = { origin: "https://example.test", pathname: "/selector.html" };
    CONFIG.outputs = [{ id: "install", fallback: "No command", rules: [] }];
    updateOutputsAndUrl();
  `, context);
  assert.equal(vm.runInContext("copy.disabled", context), true);
  assert.equal(vm.runInContext("install.textContent", context), "No command");
});

test("iframe sizing follows content, shrinks, stabilizes and caps large content", () => {
  const content = { offsetTop: 0, scrollHeight: 1500 };
  const frame = {
    style: {},
    contentWindow: {},
    contentDocument: { querySelector: () => content },
  };
  const context = vm.createContext({
    document: {
      getElementById: () => frame,
      addEventListener() {},
    },
    window: { addEventListener() {} },
  });
  vm.runInContext(resizerSource, context);
  vm.runInContext("resizeIframe()", context);
  assert.equal(frame.style.height, "1520px");
  content.scrollHeight = 600;
  vm.runInContext("resizeIframe()", context);
  assert.equal(frame.style.height, "620px");
  vm.runInContext("resizeIframe()", context);
  assert.equal(frame.style.height, "620px");
  content.scrollHeight = 3000;
  vm.runInContext("resizeIframe()", context);
  assert.equal(frame.style.height, "2020px");
});

test("the documentation loads its own resizer without a fixed minimum height", () => {
  const index = readFileSync(join(__dirname, "../docs/user-guide/index.md"), "utf8");
  assert.match(index, /src="\.\.\/\.\.\/_static\/oep-sdk-manager-files\/iframe-resizer\.js"/);
  assert.doesNotMatch(index, /min-height:/);
  const css = readFileSync(join(assets, "style.css"), "utf8");
  assert.match(css, /\.app-wrap \.st-section\{border-bottom:/);
  assert.match(css, /\.option-button-group \.spark-button\{border:/);
  assert.match(css, /\.option-button-group\{gap:/);
});
