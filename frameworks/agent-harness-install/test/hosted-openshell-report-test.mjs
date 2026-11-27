// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {buildSummary, candidatePins, discoverOpenShellRelease, publishOpenShellUpgrade, retryAcceptanceCleanup, runStage, stages} from "./hosted-openshell-report.mjs";

test("release discovery selects a newer stable version and hashes its immutable installer", async () => {
  const source = 'HARNESS_OPENSHELL_VERSION="0.1.5"\nHARNESS_OPENSHELL_INSTALL_SHA256="old"\n';
  const calls = [];
  const result = await discoverOpenShellRelease(source, {
    getJson: async url => {
      calls.push(url);
      return url.endsWith("/latest") ? {tag_name: "v0.1.10", draft: false, prerelease: false} : {sha: "a".repeat(40)};
    },
    getBytes: async url => { calls.push(url); return Buffer.from("installer"); }
  });
  assert.equal(result.available, true);
  assert.equal(result.version, "0.1.10");
  assert.equal(result.releaseCommit, "a".repeat(40));
  assert.match(result.checksum, /^[a-f0-9]{64}$/);
  assert.match(calls[2], new RegExp(`${"a".repeat(40)}/install\\.sh$`));
});

test("release discovery skips current and older versions and rejects unsafe releases", async () => {
  const source = 'HARNESS_OPENSHELL_VERSION="0.1.5"\nHARNESS_OPENSHELL_INSTALL_SHA256="old"\n';
  const run = release => discoverOpenShellRelease(source, {
    getJson: async () => release,
    getBytes: async () => assert.fail("Installer must not be fetched")
  });
  for (const tag_name of ["v0.1.5", "v0.1.4"]) assert.equal((await run({tag_name, draft: false, prerelease: false})).available, false);
  for (const release of [
    {tag_name: "v0.2.0-rc.1", draft: false, prerelease: false},
    {tag_name: "v0.2.0", draft: false, prerelease: true},
    {tag_name: "v0.2.0\nINJECTED=1", draft: false, prerelease: false}
  ]) await assert.rejects(run(release));
});

test("selected reliability candidates are validated even when older than the current pin", async () => {
  const source = 'HARNESS_OPENSHELL_VERSION="0.1.10"\nHARNESS_OPENSHELL_INSTALL_SHA256="old"\n';
  const clients = {
    getJson: async url => url.includes("/releases/") ? {tag_name: "v0.1.6", draft: false, prerelease: false} : {sha: "a".repeat(40)},
    getBytes: async () => Buffer.from("installer")
  };
  assert.equal((await discoverOpenShellRelease(source, clients, "0.1.6", true)).version, "0.1.6");
  await assert.rejects(discoverOpenShellRelease(source, clients, "0.1.7", true), /requested stable/);
});

function upgradeFixture() {
  return {repository: "example/repo", baseCommit: "a".repeat(40), releaseCommit: "b".repeat(40),
    source: 'HARNESS_OPENSHELL_VERSION="0.1.5"\nHARNESS_OPENSHELL_INSTALL_SHA256="old"\n',
    version: "0.1.10", checksum: "c".repeat(64), runId: "123"};
}

test("upgrade publisher creates a pin commit and PR with acceptance evidence", async () => {
  const input = upgradeFixture();
  const calls = [];
  const result = await publishOpenShellUpgrade(input, async (method, resource, body) => {
    calls.push({method, resource, body});
    if (resource.includes("/pulls?")) return [];
    if (resource.endsWith("/git/ref/heads/main")) return {object: {sha: input.baseCommit}};
    if (resource.includes("/git/ref/heads/automation/")) return null;
    if (resource.endsWith("/pulls")) return {html_url: "https://github.com/example/repo/pull/1"};
    return {};
  });
  assert.equal(result.existing, false);
  const commit = calls.find(call => call.method === "PUT");
  assert.equal(Buffer.from(commit.body.content, "base64").toString(), candidatePins(input.source, input.version, input.checksum));
  const pr = calls.find(call => call.method === "POST" && call.resource.endsWith("/pulls"));
  assert.match(pr.body.body, /actions\/runs\/123/);
  assert.match(pr.body.body, /not independently authenticated/);
  assert.equal(pr.body.head, "automation/openshell-0.1.10");
});

test("upgrade publisher does not overwrite existing PRs or stale branches", async () => {
  const input = upgradeFixture();
  let calls = 0;
  const existing = await publishOpenShellUpgrade(input, async () => { calls++; return [{html_url: "https://example.test/pr"}]; });
  assert.equal(existing.existing, true);
  assert.equal(calls, 1);
  await assert.rejects(publishOpenShellUpgrade(input, async (method, resource) => {
    if (resource.includes("/pulls?")) return [];
    return {object: {sha: "d".repeat(40)}};
  }), /Main changed/);
  await assert.rejects(publishOpenShellUpgrade(input, async (method, resource) => {
    if (resource.includes("/pulls?")) return [];
    if (resource.endsWith("/main")) return {object: {sha: input.baseCommit}};
    return {object: {sha: input.baseCommit}};
  }), /branch already exists/);
});

test("candidate pins replace only the exact version and checksum assignments", () => {
  const source = 'HARNESS_OPENSHELL_VERSION="0.1.5"\r\nHARNESS_OPENSHELL_INSTALL_SHA256="old"\r\nother=value\r\n';
  assert.equal(candidatePins(source, "0.2.0-rc.1", "a".repeat(64)),
    `HARNESS_OPENSHELL_VERSION="0.2.0-rc.1"\r\nHARNESS_OPENSHELL_INSTALL_SHA256="${"a".repeat(64)}"\r\nother=value\r\n`);
});

test("candidate pins reject unsafe inputs and missing or duplicate assignments", () => {
  const source = 'HARNESS_OPENSHELL_VERSION="0.1.5"\nHARNESS_OPENSHELL_INSTALL_SHA256="old"\n';
  for (const version of ["", "v0.2.0", "0.2.0\nINJECTED=1", "../0.2.0", "01.2.3", "0.2.0+build"])
    assert.throws(() => candidatePins(source, version, "a".repeat(64)), /Invalid candidate/);
  for (const checksum of ["", "a".repeat(63), "A".repeat(64), "g".repeat(64)])
    assert.throws(() => candidatePins(source, "0.2.0", checksum), /SHA-256/);
  assert.throws(() => candidatePins("", "0.2.0", "a".repeat(64)), /exactly one/);
  assert.throws(() => candidatePins(source + source, "0.2.0", "a".repeat(64)), /exactly one/);
});

test("candidate CLI updates only valid disposable pin files", context => {
  const {directory} = fixture(context);
  const file = path.join(directory, "pins.sh");
  const source = 'HARNESS_OPENSHELL_VERSION="0.1.5"\nHARNESS_OPENSHELL_INSTALL_SHA256="old"\n';
  fs.writeFileSync(file, source);
  const cli = fileURLToPath(new URL("./hosted-openshell-report.mjs", import.meta.url));
  const invalid = spawnSync(process.execPath, [cli, "candidate", "0.2.0", "bad", file]);
  assert.notEqual(invalid.status, 0);
  assert.equal(fs.readFileSync(file, "utf8"), source);
  const valid = spawnSync(process.execPath, [cli, "candidate", "0.2.0", "b".repeat(64), file]);
  assert.equal(valid.status, 0);
  assert.equal(fs.readFileSync(file, "utf8"), candidatePins(source, "0.2.0", "b".repeat(64)));
});

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

test("candidate evidence requires the requested version and installer checksum", context => {
  const {directory, outcomes, write} = fixture(context);
  const metadata = {candidateVersion: "0.2.0-rc.1", candidateInstallerSha256: "a".repeat(64), openshellVersion: "openshell 0.2.0-rc.1"};
  write("metadata.json", metadata);
  const result = buildSummary(directory, outcomes);
  assert.equal(result.success, true);
  assert.match(result.markdown, /Requested candidate: 0\.2\.0-rc\.1; installer SHA-256:/);
  write("metadata.json", {...metadata, openshellVersion: "openshell 0.1.5"});
  assert.equal(buildSummary(directory, outcomes).success, false);
  write("metadata.json", {...metadata, candidateInstallerSha256: ""});
  assert.equal(buildSummary(directory, outcomes).success, false);
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