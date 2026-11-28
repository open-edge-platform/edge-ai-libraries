// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {buildSummary, retryAcceptanceCleanup, runStage, stages} from "./hosted-openshell-report.mjs";

function fixture(context) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "hosted-openshell-"));
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const write = (name, data) => fs.writeFileSync(path.join(directory, name), JSON.stringify(data));
  write("metadata.json", {repositoryVisibility: "public", runnerEnvironment: "github-hosted"});
  for (const stage of stages) write(`${stage}.json`, {stage, code: 0, signal: null, seconds: 60});
  fs.writeFileSync(path.join(directory, "integration.tap"), "TAP version 13\nok 1 - acceptance\n1..1\n");
  return {directory, write, outcomes: Object.fromEntries(stages.map(stage => [stage, "success"]))};
}

test("public hosted usage summary states standard compute is free without paid runner estimates", context => {
  const {directory, outcomes} = fixture(context);
  const result = buildSummary(directory, outcomes);
  assert.equal(result.success, true);
  assert.match(result.markdown, /Standard public-repository hosted compute: \$0/);
  assert.match(result.markdown, /no paid larger-runner estimate applies/);
  assert.doesNotMatch(result.markdown, /4-core|8-core|runner cost|monthly projections/);
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

function cleanupFixture(context) {
  const {directory: home} = fixture(context);
  const stateDirectory = ".agent-harness-ci-0123456789abcdef";
  const root = path.join(home, stateDirectory);
  const agents = ["openclaw", "deepagents-code", "hermes"];
  for (const agent of agents) {
    const directory = path.join(root, "openshell", agent);
    fs.mkdirSync(directory, {recursive: true});
    fs.writeFileSync(path.join(directory, "profile.json"), "{}");
  }
  return {home, stateDirectory, root, agents};
}

test("cleanup retries all acceptance profiles with the recorded root, not the default deployment", context => {
  const {home, stateDirectory, root, agents} = cleanupFixture(context);
  const deployment = path.join(home, ".agent-harness-install");
  fs.mkdirSync(deployment);
  fs.writeFileSync(path.join(deployment, "sentinel"), "preserve");
  const calls = [];
  const result = retryAcceptanceCleanup(stateDirectory, {home, uninstaller: "fixture-uninstall", execute(command, args, options) {
    assert.equal(command, "timeout");
    const agent = args[args.indexOf("--harness") + 1];
    assert.deepEqual(args, ["180", "bash", "fixture-uninstall", "--runtime", "openshell", "--sandbox-only", "--harness", agent, "--yes"]);
    assert.equal(options.env.HARNESS_STATE_DIRNAME, stateDirectory);
    assert.equal(options.env.HOME, home);
    calls.push(agent);
    const directory = path.join(root, "openshell", agent);
    fs.renameSync(path.join(directory, "profile.json"), path.join(directory, "removed-profile.json"));
    return {status: 0};
  }});
  assert.equal(result, 0);
  assert.deepEqual(calls, agents);
  assert.equal(fs.readFileSync(path.join(deployment, "sentinel"), "utf8"), "preserve");
});

test("cleanup failure remains failed while other acceptance profiles are attempted", context => {
  const {home, stateDirectory, agents} = cleanupFixture(context);
  const calls = [];
  const result = retryAcceptanceCleanup(stateDirectory, {home, execute(command, args) {
    const agent = args[args.indexOf("--harness") + 1];
    calls.push(agent);
    return {status: agent === "openclaw" ? 1 : 0};
  }});
  assert.equal(result, 1);
  assert.deepEqual(calls, agents);
});

test("cleanup skips absent and already archived acceptance profiles", context => {
  const {home, stateDirectory, root, agents} = cleanupFixture(context);
  for (const agent of agents) fs.unlinkSync(path.join(root, "openshell", agent, "profile.json"));
  const execute = () => assert.fail("No active acceptance profile should be uninstalled");
  assert.equal(retryAcceptanceCleanup(stateDirectory, {home, execute}), 0);
  fs.rmSync(root, {recursive: true});
  assert.equal(retryAcceptanceCleanup(stateDirectory, {home, execute}), 0);
});

test("cleanup rejects invalid roots before invoking uninstall", context => {
  const {home} = cleanupFixture(context);
  for (const stateDirectory of ["", "../outside", ".agent-harness-install", ".agent-harness-ci-not-a-token"])
    assert.throws(() => retryAcceptanceCleanup(stateDirectory, {home, execute: () => assert.fail("Unsafe uninstall")}), /Invalid acceptance ownership root/);
});

test("cleanup rejects a symlinked ownership root before invoking uninstall", context => {
  const {home, stateDirectory, root} = cleanupFixture(context);
  const target = path.join(home, "foreign-root");
  fs.renameSync(root, target);
  fs.symlinkSync(target, root, "junction");
  assert.throws(() => retryAcceptanceCleanup(stateDirectory, {home, execute: () => assert.fail("Unsafe uninstall")}), /Unsafe acceptance ownership path/);
});