// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {parseTap, summarize} from "./tap-summary.mjs";

test("counts passing, failing and skipped cases without counting diagnostics", () => {
  const result = parseTap("TAP version 13\nok 1 - works\nnot ok 2 - fails\nok 3 - Hermes # SKIP Requires image\n# tests 3\n1..3\n");
  assert.equal(result.executed, 2);
  assert.equal(result.passed, 1);
  assert.equal(result.failed, 1);
  assert.equal(result.skipped.length, 1);
  assert.equal(result.skipped[0].reason, "Requires image");
  assert.equal(result.complete, true);
});

test("rejects empty, truncated, bailed out and inconsistent reports", () => {
  for (const text of ["", "ok 1 - partial\n", "ok 1 - one\n1..2\n",
    "ok 2 - wrong number\n1..1\n", "1..0\n", "ok 1 - one\n1..1\nBail out! broken\n",
    "ok 1 - one\n1..1\n1..1\n"])
    assert.equal(parseTap(text).complete, false, text);
});

test("ignores indented subtests and treats TODO as unfinished validation", () => {
  const result = parseTap("    ok 1 - child\n    1..1\nnot ok 1 - unfinished # TODO implement\n1..1\n");
  assert.equal(result.executed, 1);
  assert.equal(result.failed, 1);
});

test("provides a reason for an unspecified skip", () => {
  assert.equal(parseTap("ok 1 - optional # SKIP\n1..1\n").skipped[0].reason, "No reason supplied");
});

test("summary reports skips, missing files and failed process outcomes", t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "tap-summary-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const ids = ["core", "inference", "lifecycle", "metrics", "defaults", "reporting"];
  const outcomes = Object.fromEntries(ids.map(id => [id, "success"]));
  for (const id of ids) fs.writeFileSync(path.join(dir, `${id}.tap`), "ok 1 - works\n1..1\n");
  fs.writeFileSync(path.join(dir, "defaults.tap"), "ok 1 - Hermes # SKIP Requires image\n1..1\n");
  const passing = summarize(dir, outcomes);
  assert.equal(passing.success, true);
  assert.match(passing.markdown, /Hermes: Requires image/);
  assert.match(passing.markdown, /\*\*5\*\* \| \*\*5\*\* \| \*\*0\*\* \| \*\*1\*\*/);
  assert.equal(summarize(dir, {...outcomes, core: "failure"}).success, false);
  fs.unlinkSync(path.join(dir, "core.tap"));
  const missing = summarize(dir, outcomes);
  assert.equal(missing.success, false);
  assert.match(missing.markdown, /Missing; not a pass/);
  assert.equal(summarize(dir, {}).success, false);
});
