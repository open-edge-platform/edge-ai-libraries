// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const selectorPath = path.join(__dirname, "../docs/oep-cli-installer-files/selector.js");
const selector = fs.readFileSync(selectorPath, "utf8");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.style = {};
    this.textContent = "";
    this.disabled = false;
    this._innerHTML = "";
  }

  set innerHTML(value) {
    this._innerHTML = value;
    this.children = [];
  }

  get innerHTML() {
    return this._innerHTML;
  }

  get childElementCount() {
    return this.children.length;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener() {}

  setAttribute() {}
}

function renderSelection(modules, selected, { installAll = false } = {}) {
  const elements = new Map([
    ["#installText", new Element("pre")],
    ["#copyCmd", new Element("button")],
    ["#nextStepsSection", new Element("section")],
    ["#nextStepsText", new Element("div")],
    ["#selectionStatus", new Element("p")],
    ["#getStartedText", new Element("div")],
    ["#resourcesText", new Element("div")],
  ]);
  const document = {
    currentScript: { src: "https://example.test/selector.js" },
    querySelector: (selector) => elements.get(selector) || null,
    createElement: (tag) => new Element(tag),
    addEventListener() {},
  };
  const context = vm.createContext({
    document,
    URL,
    URLSearchParams,
    location: { search: "", origin: "https://example.test", pathname: "/" },
    history: { replaceState() {} },
  });
  vm.runInContext(selector, context, { filename: selectorPath });

  const profile = {
    label: "Test Suite",
    value: "test_suite",
    ...(installAll ? { installAll: true, remove: true } : {}),
  };
  const config = {
    shareKeys: [],
    categories: [
      { key: "PROFILE", type: "single", options: [profile] },
      {
        key: "MODULE",
        type: "multiple",
        options: modules.map((module) => ({
          ...module,
          supports: { PROFILE: ["test_suite"] },
        })),
      },
    ],
    outputs: [
      {
        id: "install",
        rules: [installAll
          ? {
            when: { PROFILE: "test_suite" },
            text: "openedge-cli install test_suite",
          }
          : {
            when: { PROFILE: "test_suite" },
            text: "openedge-cli install {{MODULE}}",
          }],
      },
      {
        id: "nextsteps",
        startStop: {
          start: "openedge-cli start {{MODULE}}",
          stop: "openedge-cli stop {{MODULE}}",
        },
        remove: "openedge-cli remove {{MODULE}}",
      },
      { id: "getstarted", fallback: "" },
      { id: "resources", fallback: "" },
    ],
  };

  vm.runInContext(
    `CONFIG = ${JSON.stringify(config)}; STATE = ${JSON.stringify({
      PROFILE: "test_suite",
      MODULE: selected.join(","),
    })}; updateOutputsAndUrl();`,
    context,
  );
  const commands = elements.get("#nextStepsText").children
    .filter((child) => child.children?.length)
    .map((child) => child.children.at(-1).textContent);

  return {
    install: elements.get("#installText").textContent,
    nextSteps: commands,
  };
}

test("single startable module is started after install and named in lifecycle commands", () => {
  const result = renderSelection(
    [{ value: "service", startStop: true, remove: true, options: ["--gpu"] }],
    ["service"],
  );

  assert.equal(result.install, "openedge-cli install service --gpu start");
  assert.deepEqual(result.nextSteps, [
    "openedge-cli start service",
    "openedge-cli stop service",
    "openedge-cli remove service",
  ]);
});

test("single install-only module is not started automatically", () => {
  const result = renderSelection(
    [{ value: "library", remove: true }],
    ["library"],
  );

  assert.equal(result.install, "openedge-cli install library");
  assert.deepEqual(result.nextSteps, ["openedge-cli remove library"]);
});

test("multi-module install omits automatic start and lifecycle commands use the module placeholder", () => {
  const result = renderSelection(
    [
      { value: "service_a", startStop: true, remove: true },
      { value: "service_b", startStop: true },
      { value: "installer_only", remove: true },
    ],
    ["service_a", "service_b", "installer_only"],
  );

  assert.equal(result.install, "openedge-cli install service_a service_b installer_only");
  assert.deepEqual(result.nextSteps, [
    "openedge-cli start <module_name>",
    "openedge-cli stop <module_name>",
    "openedge-cli remove <module_name>",
  ]);
});

test("install-all removal continues to target the selected profile", () => {
  const result = renderSelection(
    [{ value: "service", startStop: true, remove: true }],
    [],
    { installAll: true },
  );

  assert.equal(result.install, "openedge-cli install test_suite");
  assert.deepEqual(result.nextSteps, ["openedge-cli remove test_suite"]);
});
