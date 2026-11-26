// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {buildSummary, runStage, stages} from "./hosted-openshell-report.mjs";

function fixture(context) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "hosted-openshell-"));
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const write = (name, data) => fs.writeFileSync(path.join(directory, name), JSON.stringify(data));
  write("metadata.json", {repositoryVisibility: "public", runnerEnvironment: "github-hosted"});
  for (const stage of stages) write(`${stage}.json`, {stage, code: 0, signal: null, seconds: 60});
  fs.writeFileSync(path.join(directory, "integration.tap"), "TAP version 13\nok 1 - acceptance\n1..1\n");
  return {directory, write, outcomes: Object.fromEntries(stages.map(stage => [stage, "success"]))};
}

test("complete acceptance and successful stages produce a public-runner usage summary", context => {
  const {directory, outcomes} = fixture(context);
  const result = buildSummary(directory, outcomes);
  assert.equal(result.success, true);
  assert.match(result.markdown, /compute: \$0/);
  assert.match(result.markdown, /4-core \$0.05; 8-core \$0.09/);
  assert.match(result.markdown, /planning estimates, not billed usage/);
});

for (const stage of stages) {
  test(`missing or failed ${stage} cannot pass`, context => {
    const {directory, outcomes, write} = fixture(context);
    fs.unlinkSync(path.join(directory, `${stage}.json`));
    assert.equal(buildSummary(directory, outcomes).success, false);
    write(`${stage}.json`, {stage, code: 1, signal: null, seconds: 1});
    assert.equal(buildSummary(directory, outcomes).success, false);
    write(`${stage}.json`, {stage, code: 0, signal: null, seconds: 1});
    outcomes[stage] = "skipped";
    assert.equal(buildSummary(directory, outcomes).success, false);
  });
}

for (const tap of ["", "ok 1 - truncated\n", "not ok 1 - failure\n1..1\n", "ok 1 - optional # SKIP\n1..1\n"]) {
  test(`invalid acceptance fails closed: ${JSON.stringify(tap)}`, context => {
    const {directory, outcomes} = fixture(context);
    fs.writeFileSync(path.join(directory, "integration.tap"), tap);
    assert.equal(buildSummary(directory, outcomes).success, false);
  });
}

test("unknown visibility does not claim free compute", context => {
  const {directory, outcomes, write} = fixture(context);
  write("metadata.json", {});
  assert.match(buildSummary(directory, outcomes).markdown, /cost is not established/);
});

test("mismatched stage identity is rejected", context => {
  const {directory, outcomes, write} = fixture(context);
  write("prepare.json", {stage: "integration", code: 0, signal: null, seconds: 1});
  assert.throws(() => buildSummary(directory, outcomes), /Stage receipt mismatch/);
});

test("missing resource measurements are not reported as zero", context => {
  const {directory, outcomes} = fixture(context);
  assert.match(buildSummary(directory, outcomes).markdown, /RAM: unavailable/);
});

test("stage wrapper propagates command failure and records resources", async context => {
  const {directory} = fixture(context);
  assert.equal(await runStage("prepare", directory, process.execPath, ["-e", "process.exit(7)"]), 7);
  const record = JSON.parse(fs.readFileSync(path.join(directory, "prepare.json"), "utf8"));
  assert.equal(record.code, 7);
  assert.ok(record.seconds >= 0);
  assert.ok(record.usedDiskBytes > 0);
});

test("stage wrapper records launch failures", async context => {
  const {directory} = fixture(context);
  assert.notEqual(await runStage("prepare", directory, path.join(directory, "missing-command"), []), 0);
  assert.match(JSON.parse(fs.readFileSync(path.join(directory, "prepare.json"), "utf8")).spawnError, /ENOENT/);
});