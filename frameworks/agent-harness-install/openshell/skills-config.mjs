// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
// Image-build step for Hermes skill packs (--runtime openshell): registers every pack baked into
// /opt/harness/skills (see openshell/skill-packs/manifest.json, staged by scripts/lib/skill-packs.sh)
// in skills.external_dirs of the sandbox Hermes's config.yaml. The packs are read-only image content;
// Hermes's own skills directory is never written here.
import fs from "node:fs";
import path from "node:path";
import {execFileSync} from "node:child_process";

process.on("uncaughtException", error => {
  console.error(`Error: ${error.message}`);
  process.exit(1);
});

const skillsRoot = "/opt/harness/skills";
const helper = "/opt/harness/skill-packs.py";
const hermesBin = "/home/node/.local/bin/hermes";
const hermesHome = "/home/node/.hermes";
const idPattern = /^[a-z0-9][a-z0-9-]{0,31}$/;

const manifest = JSON.parse(fs.readFileSync(path.join(skillsRoot, "manifest.json"), "utf8"));
if (manifest.schema !== 1 || !Array.isArray(manifest.packs)) throw Error("Invalid skill pack manifest");
if (manifest.packs.length === 0) process.exit(0);

const dirs = manifest.packs.map(pack => {
  if (typeof pack.id !== "string" || !idPattern.test(pack.id)) throw Error("Invalid skill pack id in the manifest");
  const dir = path.join(skillsRoot, pack.id, "skills");
  if (!fs.statSync(dir).isDirectory()) throw Error(`Skill pack '${pack.id}' has no skills directory`);
  return dir;
});

// Same Python runtime (and YAML library) Hermes itself uses; it is installed in the image, not the sandbox HOME.
const runtimeOptions = {encoding: "utf8", env: {...process.env, HERMES_HOME: hermesHome}};
const runtime = JSON.parse(execFileSync(hermesBin, ["--print-runtime-command"], runtimeOptions));
if (!Array.isArray(runtime) || typeof runtime[0] !== "string" || !path.isAbsolute(runtime[0]))
  throw Error("Invalid Hermes Python runtime command");

const addArgs = dirs.flatMap(dir => ["--add", dir]);
const output = execFileSync(runtime[0], ["-I", helper, "merge-config", "--config", path.join(hermesHome, "config.yaml"),
  "--create", "--no-backup", ...addArgs], {...runtimeOptions, env: {...runtimeOptions.env, HARNESS_HERMES_AGENT_DIR: path.join(hermesHome, "hermes-agent")}});
console.log(`Skill packs registered: ${manifest.packs.map(pack => pack.id).join(", ")} (${output.trim()})`);
