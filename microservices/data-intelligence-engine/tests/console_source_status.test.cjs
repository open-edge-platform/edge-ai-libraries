// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/console/source-status.js"), "utf8"), context);
const status = context.SourceStatus;

for (const [extraction, expected] of [
  [null, "ready"],
  [{state: "queued", active: {not_before: "later"}, outdated: true}, "extraction_waiting"],
  [{state: "queued", active: {}, outdated: true}, "extraction_queued"],
  [{state: "running", outdated: true}, "extracting"],
  [{state: "idle", outdated: true}, "extraction_pending"],
  [{state: "idle", outdated: true, last: {state: "failed"}}, "extraction_failed"],
  [{state: "idle", outdated: false}, "ready"],
]) {
  test(`graph display ${expected}`, () => {
    const graph = {status: "ready", extraction};
    assert.equal(status.source(graph), expected);
    assert.equal(status.pool({source_statuses: [{status: "ready"}, graph]}), expected);
    assert.equal(status.appearance(expected).cls, expected === "ready" ? "ok" : expected === "extraction_failed" ? "bad" : "warn");
  });
}
test("sync failures win and empty pools are unconfigured", () => {
  assert.equal(status.source({status: "failed", extraction: {state: "running"}}), "failed");
  assert.equal(status.pool({source_statuses: []}), "unconfigured");
});