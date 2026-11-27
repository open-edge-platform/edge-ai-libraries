// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {createHash} from "node:crypto";
import {execFileSync, spawn, spawnSync} from "node:child_process";
import {fileURLToPath, pathToFileURL} from "node:url";
import {validateRuntimeTap} from "./tap-summary.mjs";

export const stages = ["preflight", "prepare", "integration", "uninstall"];

export function candidatePins(source, version, checksum) {
  if (typeof version !== "string" || version.length > 128 ||
      !/^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/.test(version))
    throw Error("Invalid candidate OpenShell version");
  if (typeof checksum !== "string" || !/^[a-f0-9]{64}$/.test(checksum))
    throw Error("Invalid candidate installer SHA-256");
  for (const [name, value] of [["HARNESS_OPENSHELL_VERSION", version], ["HARNESS_OPENSHELL_INSTALL_SHA256", checksum]]) {
    const pattern = new RegExp(`^${name}="[^"\\r\\n]*"$`, "gm");
    if ([...source.matchAll(pattern)].length !== 1) throw Error(`Expected exactly one ${name} pin`);
    source = source.replace(pattern, `${name}="${value}"`);
  }
  return source;
}

export async function discoverOpenShellRelease(source, {getJson, getBytes}, selectedVersion, allowOlder = false) {
  const pins = [...source.matchAll(/^HARNESS_OPENSHELL_VERSION="([^"\r\n]+)"$/gm)];
  if (pins.length !== 1) throw Error("Expected exactly one OpenShell version pin");
  const parseVersion = version => {
    const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/.exec(version);
    if (!match || version.length > 128) throw Error("Invalid OpenShell version");
    return {numbers: match.slice(1, 4).map(BigInt), prerelease: match[4]};
  };
  const current = parseVersion(pins[0][1]);
  if (selectedVersion) parseVersion(selectedVersion);
  const release = await getJson(selectedVersion ? `/repos/ai-openshell/openshell/releases/tags/v${selectedVersion}` : "/repos/ai-openshell/openshell/releases/latest");
  if (release.draft !== false || release.prerelease !== false || typeof release.tag_name !== "string" || !release.tag_name.startsWith("v"))
    throw Error("Expected a published stable OpenShell release tag");
  const version = release.tag_name.slice(1);
  const candidate = parseVersion(version);
  if (candidate.prerelease || (selectedVersion && version !== selectedVersion)) throw Error("Expected the requested stable OpenShell release");
  const order = candidate.numbers.findIndex((number, index) => number !== current.numbers[index]);
  if (!allowOlder && (order < 0 ? !current.prerelease : candidate.numbers[order] < current.numbers[order]))
    return {available: false, version};
  const commit = await getJson(`/repos/ai-openshell/openshell/commits/${release.tag_name}`);
  if (typeof commit.sha !== "string" || !/^[a-f0-9]{40}$/.test(commit.sha)) throw Error("Invalid release commit");
  const installer = await getBytes(`https://raw.githubusercontent.com/ai-openshell/openshell/${commit.sha}/install.sh`);
  if (!Buffer.isBuffer(installer) || installer.length === 0 || installer.length > 2 * 1024 * 1024)
    throw Error("Invalid OpenShell installer content");
  const checksum = createHash("sha256").update(installer).digest("hex");
  candidatePins(source, version, checksum);
  return {available: true, version, checksum, releaseCommit: commit.sha};
}

export async function publishOpenShellUpgrade({repository, baseCommit, source, version, checksum, releaseCommit, runId}, request) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository) || !/^[a-f0-9]{40}$/.test(baseCommit) ||
      !/^[a-f0-9]{40}$/.test(releaseCommit) || !/^[0-9]+$/.test(runId)) throw Error("Invalid upgrade metadata");
  const updated = candidatePins(source, version, checksum);
  const [owner] = repository.split("/");
  const repo = `/repos/${repository}`;
  const branch = `automation/openshell-${version}`;
  const query = new URLSearchParams({state: "open", head: `${owner}:${branch}`, base: "main"});
  const existing = await request("GET", `${repo}/pulls?${query}`);
  if (!Array.isArray(existing)) throw Error("Invalid pull request response");
  if (existing.length) return {existing: true, url: existing[0].html_url};
  const base = await request("GET", `${repo}/git/ref/heads/main`);
  if (base?.object?.sha !== baseCommit) throw Error("Main changed after acceptance; rerun validation");
  if (await request("GET", `${repo}/git/ref/heads/${branch}`, undefined, true))
    throw Error("Upgrade branch already exists without an open PR; manual review required");
  await request("POST", `${repo}/git/refs`, {ref: `refs/heads/${branch}`, sha: baseCommit});
  const file = "frameworks/agent-harness-install/scripts/lib/openshell.sh";
  const bytes = Buffer.from(source);
  const blob = createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
  await request("PUT", `${repo}/contents/${file}`, {
    message: `chore(agent-harness): upgrade OpenShell to ${version}`,
    content: Buffer.from(updated).toString("base64"), sha: blob, branch
  });
  const current = await request("GET", `${repo}/git/ref/heads/main`);
  if (current?.object?.sha !== baseCommit) throw Error("Main changed after acceptance; review the generated branch and rerun validation");
  const body = [
    `Updates the OpenShell version and installer SHA-256 to ${version}.`, "",
    `- Validated AHI commit: ${baseCommit}`,
    `- OpenShell release commit: ${releaseCommit}`,
    `- Installer SHA-256: ${checksum}`,
    `- Passing live acceptance and artifacts: https://github.com/${repository}/actions/runs/${runId}`, "",
    "The installer checksum is derived from the upstream release commit, not independently authenticated.",
    "Review upstream provenance, release notes, compatibility and version-specific documentation before merging.",
    "GitHub Actions PR checks and repository review requirements still apply."
  ].join("\n");
  const pr = await request("POST", `${repo}/pulls`, {title: `chore(agent-harness): upgrade OpenShell to ${version}`, head: branch, base: "main", body});
  if (!pr?.html_url) throw Error("Pull request creation did not return a URL");
  return {existing: false, url: pr.html_url};
}

async function githubRequest(method, resource, body, allowMissing = false) {
  const response = await fetch(`https://api.github.com${resource}`, {
    method,
    headers: {"Accept": "application/vnd.github+json", "Authorization": `Bearer ${process.env.GH_TOKEN}`, "User-Agent": "agent-harness-openshell-upgrade", "X-GitHub-Api-Version": "2022-11-28"},
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30000)
  });
  if (allowMissing && response.status === 404) return null;
  if (!response.ok) throw Error(`GitHub API ${method} ${resource.split("?")[0]} failed: ${response.status}`);
  return response.json();
}

async function installerBytes(url) {
  const response = await fetch(url, {signal: AbortSignal.timeout(30000)});
  if (!response.ok) throw Error(`OpenShell installer download failed: ${response.status}`);
  const length = Number(response.headers.get("content-length"));
  if (length > 2 * 1024 * 1024) throw Error("OpenShell installer is too large");
  return Buffer.from(await response.arrayBuffer());
}

export function retryAcceptanceCleanup(stateDirectory, {
  home = process.env.HOME,
  uninstaller = fileURLToPath(new URL("../uninstall.sh", import.meta.url)),
  execute = spawnSync
} = {}) {
  if (!/^\.agent-harness-ci-[a-f0-9]{16}$/.test(stateDirectory) ||
      typeof home !== "string" || !path.isAbsolute(home))
    throw Error("Invalid acceptance ownership root");
  const inspect = (file, directory) => {
    let stat;
    try { stat = fs.lstatSync(file); }
    catch (error) { if (error.code === "ENOENT") return; throw error; }
    if (stat.isSymbolicLink() || (directory ? !stat.isDirectory() : !stat.isFile()) ||
        (process.getuid && stat.uid !== process.getuid()))
      throw Error(`Unsafe acceptance ownership path: ${file}`);
    return stat;
  };
  const root = path.join(home, stateDirectory);
  if (!inspect(root, true) || !inspect(path.join(root, "openshell"), true)) return 0;
  const agents = ["openclaw", "deepagents-code", "hermes"].filter(agent => {
    const directory = path.join(root, "openshell", agent);
    return inspect(directory, true) && inspect(path.join(directory, "profile.json"), false);
  });
  let result = 0;
  for (const agent of agents) {
    const child = execute("timeout", ["180", "bash", uninstaller,
      "--runtime", "openshell", "--sandbox-only", "--harness", agent, "--yes"], {
      env: {...process.env, HOME: home, HARNESS_STATE_DIRNAME: stateDirectory},
      stdio: "inherit"
    });
    if (child.status !== 0 || child.error || child.signal) result = 1;
  }
  return result;
}

export function sampleResources(directory) {
  let usedMemoryBytes = null;
  if (process.platform === "linux") {
    const memory = fs.readFileSync("/proc/meminfo", "utf8");
    const total = /^MemTotal:\s+(\d+) kB$/m.exec(memory);
    const available = /^MemAvailable:\s+(\d+) kB$/m.exec(memory);
    if (total && available) usedMemoryBytes = (Number(total[1]) - Number(available[1])) * 1024;
  }
  const disk = fs.statfsSync(directory);
  return {usedMemoryBytes, usedDiskBytes: (disk.blocks - disk.bfree) * disk.bsize};
}

export async function runStage(stage, directory, command, args) {
  if (!stages.includes(stage) || !command) throw Error("A known stage and executable are required");
  fs.mkdirSync(directory, {recursive: true});
  const started = Date.now();
  const peaks = sampleResources(directory);
  const sample = () => {
    const current = sampleResources(directory);
    for (const key of Object.keys(peaks))
      if (current[key] !== null) peaks[key] = Math.max(peaks[key] ?? 0, current[key]);
  };
  const child = spawn(command, args, {stdio: "inherit"});
  const forward = signal => child.kill(signal);
  const interrupt = () => forward("SIGINT");
  const terminate = () => forward("SIGTERM");
  process.on("SIGINT", interrupt);
  process.on("SIGTERM", terminate);
  const timer = setInterval(sample, 5000);
  let spawnError;
  child.on("error", error => { spawnError = error.message; });
  const result = await new Promise(resolve => child.on("close", (code, signal) => resolve({code, signal})));
  clearInterval(timer);
  process.off("SIGINT", interrupt);
  process.off("SIGTERM", terminate);
  sample();
  const record = {stage, ...result, spawnError, seconds: (Date.now() - started) / 1000, ...peaks};
  fs.writeFileSync(path.join(directory, `${stage}.json`), JSON.stringify(record, null, 2));
  return Number.isInteger(result.code) && result.code >= 0 ? result.code : 1;
}

export function buildSummary(directory, outcomes) {
  const metadata = JSON.parse(fs.readFileSync(path.join(directory, "metadata.json"), "utf8"));
  const records = stages.map(stage => {
    const file = path.join(directory, `${stage}.json`);
    const record = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {stage};
    if (record.stage !== stage) throw Error(`Stage receipt mismatch: ${stage}`);
    return record;
  });
  let success = records.every(record => outcomes[record.stage] === "success" && record.code === 0 &&
    record.signal === null && Number.isFinite(record.seconds) && record.seconds >= 0);
  if (metadata.candidateVersion || metadata.candidateInstallerSha256)
    success &&= /^[a-f0-9]{64}$/.test(metadata.candidateInstallerSha256 ?? "") &&
      metadata.openshellVersion === `openshell ${metadata.candidateVersion}`;
  let acceptance;
  try {
    const result = validateRuntimeTap(fs.readFileSync(path.join(directory, "integration.tap"), "utf8"));
    acceptance = `${result.passed} passed, zero failed, zero skipped`;
  } catch {
    success = false;
    acceptance = "Missing, incomplete, failing or skipped acceptance evidence";
  }
  const minutes = records.reduce((total, record) => total + Math.ceil((record.seconds ?? 0) / 60), 0);
  const measured = records.reduce((total, record) => total + (record.seconds ?? 0), 0);
  const gib = bytes => Number.isFinite(bytes) ? (bytes / 1024 ** 3).toFixed(2) : "unavailable";
  const peak = key => {
    const values = records.map(record => record[key]).filter(Number.isFinite);
    return values.length ? Math.max(...values) : null;
  };
  const escape = value => String(value ?? "unavailable").replace(/[\r\n|`<>]/g, " ");
  const freeCompute = metadata.repositoryVisibility === "public" && metadata.runnerEnvironment === "github-hosted";
  const lines = [
    "## GitHub-hosted OpenShell live validation", "",
    `**Result: ${success ? "passed" : "failed or incomplete"}.** ${acceptance}.`, "",
    `Commit: ${escape(metadata.commit)}; OpenShell: ${escape(metadata.openshellVersion)}.`,
    ...(metadata.candidateVersion || metadata.candidateInstallerSha256 ? [
      `Requested candidate: ${escape(metadata.candidateVersion)}; installer SHA-256: ${escape(metadata.candidateInstallerSha256)}.`
    ] : []),
    `Runner: ${escape(metadata.imageOS)} ${escape(metadata.imageVersion)}; kernel: ${escape(metadata.kernel)}.`,
    `CPU model: ${escape(metadata.model)} @ ${escape(metadata.modelRevision)}.`, "",
    "| Stage | Outcome | Seconds |", "|---|---|---:|",
    ...records.map(record => `| ${record.stage} | ${escape(outcomes[record.stage])} | ${record.seconds?.toFixed(1) ?? "missing"} |`),
    "",
    `Measured stage time: ${(measured / 60).toFixed(1)} minutes.`,
    `Sampled peak whole-VM used RAM: ${gib(peak("usedMemoryBytes"))} GiB; filesystem used: ${gib(peak("usedDiskBytes"))} GiB.`,
    "Samples include other VM processes and filesystem contents, not just this job; brief peaks may be missed.", "",
    freeCompute ? "Standard public-repository hosted compute: $0 under GitHub's published pricing." :
      "Compute cost is not established for this repository; consult its billing plan.",
    `Illustrative larger x64 Linux runner cost for measured stages: 4-core $${(minutes * 0.012).toFixed(2)}; 8-core $${(minutes * 0.022).toFixed(2)}.`,
    `At five runs/month: $${(minutes * 0.012 * 5).toFixed(2)} / $${(minutes * 0.022 * 5).toFixed(2)}; at thirty: $${(minutes * 0.012 * 30).toFixed(2)} / $${(minutes * 0.022 * 30).toFixed(2)}.`,
    "These are planning estimates, not billed usage. Stage minutes are conservatively rounded separately; checkout, tool setup, offline jobs, uploads, retries and storage are excluded.",
    "Rates assumed: $0.012/min (4-core), $0.022/min (8-core); recheck GitHub pricing before selecting paid runners.",
    "No external inference API is used. This small CPU fixture does not qualify the default 9B model or Intel GPU behavior.", ""
  ];
  return {success, markdown: lines.join("\n")};
}

function writeMetadata(directory) {
  fs.mkdirSync(directory, {recursive: true});
  const file = path.join(directory, "metadata.json");
  const previous = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
  let openshellVersion = previous.openshellVersion;
  try { openshellVersion = execFileSync("openshell", ["--version"], {encoding: "utf8", stdio: ["ignore", "pipe", "ignore"]}).trim(); }
  catch { openshellVersion = previous.openshellVersion; }
  fs.writeFileSync(file, JSON.stringify({
    commit: process.env.GITHUB_SHA,
    repositoryVisibility: process.env.HOSTED_REPOSITORY_VISIBILITY,
    runnerEnvironment: process.env.RUNNER_ENVIRONMENT,
    imageOS: process.env.ImageOS,
    imageVersion: process.env.ImageVersion,
    kernel: os.release(),
    model: process.env.HOSTED_MODEL_REPO,
    modelRevision: process.env.HARNESS_HF_MODEL_REVISION,
    candidateVersion: process.env.HOSTED_CANDIDATE_VERSION,
    candidateInstallerSha256: process.env.HOSTED_CANDIDATE_INSTALLER_SHA256,
    openshellVersion
  }, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [operation, ...args] = process.argv.slice(2);
  if (operation === "metadata" && args.length === 1) writeMetadata(args[0]);
  else if (operation === "discover" && args.length === 1) {
    const source = fs.readFileSync(args[0], "utf8");
    const clients = {
      getJson: resource => githubRequest("GET", resource), getBytes: installerBytes
    };
    const reliability = process.env.DISCOVERY_MODE === "reliability";
    const releases = reliability ? await Promise.all(["0.1.6", "0.1.7", "0.1.8", "0.1.9", "0.1.10"].map(version =>
      discoverOpenShellRelease(source, clients, version, true))) : [await discoverOpenShellRelease(source, clients)];
    const candidates = releases.filter(release => release.available);
    const outputs = {available: candidates.length > 0, matrix: JSON.stringify({include: candidates})};
    if (!reliability && candidates.length) Object.assign(outputs, candidates[0]);
    for (const [name, value] of Object.entries(outputs)) fs.appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${value}\n`);
    console.log(candidates.length ? `Candidate OpenShell releases: ${candidates.map(release => release.version).join(", ")}` : "No newer stable OpenShell release");
  } else if (operation === "open-pr" && args.length === 1) {
    const result = await publishOpenShellUpgrade({
      repository: process.env.GITHUB_REPOSITORY, baseCommit: process.env.GITHUB_SHA,
      source: fs.readFileSync(args[0], "utf8"), version: process.env.CANDIDATE_VERSION,
      checksum: process.env.CANDIDATE_CHECKSUM, releaseCommit: process.env.CANDIDATE_RELEASE_COMMIT,
      runId: process.env.GITHUB_RUN_ID
    }, githubRequest);
    console.log(`${result.existing ? "Existing" : "Created"} upgrade PR: ${result.url}`);
  }
  else if (operation === "candidate" && args.length === 3)
    fs.writeFileSync(args[2], candidatePins(fs.readFileSync(args[2], "utf8"), args[0], args[1]));
  else if (operation === "cleanup" && args.length === 1)
    process.exitCode = retryAcceptanceCleanup(args[0]);
  else if (operation === "run" && args[2] === "--")
    process.exitCode = await runStage(args[0], args[1], args[3], args.slice(4));
  else if (operation === "summary" && args.length === 1) {
    const {success, markdown} = buildSummary(args[0], JSON.parse(process.env.HOSTED_STEP_OUTCOMES ?? "{}"));
    console.log(markdown);
    if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, markdown);
    process.exitCode = success ? 0 : 1;
  } else throw Error("Usage: hosted-openshell-report.mjs metadata|summary <directory> OR cleanup <acceptance-state-name> OR run <stage> <directory> -- <executable> [args]");
}