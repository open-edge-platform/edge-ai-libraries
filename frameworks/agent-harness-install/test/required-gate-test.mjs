// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {fileURLToPath} from "node:url";
import test from "node:test";
import {evaluateGate} from "../../../.github/scripts/agent-harness-required-gate.mjs";

function outcomes(relevant = "true") {
  const result = relevant === "true" ? "success" : "skipped";
  return {CHANGE_RESULT: "success", RELEVANT: relevant, STATIC_RESULT: result};
}

test("relevant changes require successful static analysis", () => {
  assert.match(evaluateGate(outcomes()), /^Passed:/);
});

test("unrelated changes pass with static analysis skipped", () => {
  assert.match(evaluateGate(outcomes("false")), /^Not applicable:/);
});

for (const result of ["failure", "cancelled", "skipped", "", undefined]) {
  test(`change detection rejects ${String(result)} even on unrelated changes`, () => {
    assert.throws(() => evaluateGate({...outcomes("false"), CHANGE_RESULT: result}),
      /Change detection did not succeed/);
  });
}

for (const relevant of ["", "invalid", "TRUE", undefined]) {
  test(`invalid change decision ${String(relevant)} fails closed`, () => {
    assert.throws(() => evaluateGate({...outcomes(), RELEVANT: relevant}),
      /Missing or invalid change decision/);
  });
}

for (const relevant of ["true", "false"]) {
  const invalid = relevant === "true"
    ? ["failure", "cancelled", "skipped", "", undefined]
    : ["failure", "cancelled", "success", "", undefined];
  for (const result of invalid) {
    test(`${relevant} change decision rejects STATIC_RESULT=${String(result)}`, () => {
      assert.throws(() => evaluateGate({...outcomes(relevant), STATIC_RESULT: result}), /expected/);
    });
  }
}

test("CLI publishes successful summary and exits nonzero on rejected outcomes", t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "harness-required-gate-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const summary = path.join(dir, "summary.md");
  const script = fileURLToPath(new URL("../../../.github/scripts/agent-harness-required-gate.mjs", import.meta.url));
  const env = {...process.env, ...outcomes(), GITHUB_STEP_SUMMARY: summary};
  const passed = spawnSync(process.execPath, [script], {env, encoding: "utf8"});
  assert.equal(passed.status, 0, passed.stderr);
  assert.match(fs.readFileSync(summary, "utf8"), /Agent Harness static analysis succeeded/);
  const failed = spawnSync(process.execPath, [script],
    {env: {...env, STATIC_RESULT: "cancelled"}, encoding: "utf8"});
  assert.equal(failed.status, 1);
  assert.match(failed.stderr, /expected success, received cancelled/);
});

test("symlinked CLI executes validation with default and preserved main paths", t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "harness-gate-symlink-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const script = fileURLToPath(new URL("../../../.github/scripts/agent-harness-required-gate.mjs", import.meta.url));
  const link = path.join(dir, "gate.mjs");
  fs.symlinkSync(script, link);
  for (const flags of [[], ["--preserve-symlinks-main"]]) {
    const env = {...process.env, ...outcomes(), GITHUB_STEP_SUMMARY: ""};
    const passed = spawnSync(process.execPath, [...flags, link], {env, encoding: "utf8"});
    assert.equal(passed.status, 0, passed.stderr);
    assert.match(passed.stdout, /Agent Harness static analysis succeeded/);
    const failed = spawnSync(process.execPath, [...flags, link],
      {env: {...env, STATIC_RESULT: "failure"}, encoding: "utf8"});
    assert.equal(failed.status, 1, failed.stderr);
    assert.match(failed.stderr, /expected success, received failure/);
  }
});
