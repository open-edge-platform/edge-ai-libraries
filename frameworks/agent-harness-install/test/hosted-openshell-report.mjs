// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {execFileSync, spawn, spawnSync} from "node:child_process";
import {fileURLToPath, pathToFileURL} from "node:url";
import {validateRuntimeTap} from "./tap-summary.mjs";

export const stages = ["preflight", "prepare", "integration", "uninstall"];

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
    "This workflow uses standard GitHub-hosted runners; no paid larger-runner estimate applies.",
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
    openshellVersion
  }, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [operation, ...args] = process.argv.slice(2);
  if (operation === "metadata" && args.length === 1) writeMetadata(args[0]);
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