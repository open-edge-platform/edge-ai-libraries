// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import test from "node:test";

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "local-validation-"));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  for (const dir of ["test", "scripts", "openshell", "bin"]) fs.mkdirSync(path.join(root, dir));
  fs.copyFileSync(new URL("./validate-local-openshell.sh", import.meta.url),
    path.join(root, "test/validate-local-openshell.sh"));
  const write = (name, text) => fs.writeFileSync(path.join(root, name), text, {mode: 0o755});
  write("test/openshell-test.sh", 'echo offline >>"$TRACE"; exit "${OFFLINE_RC:-0}"\n');
  write("test/tap-summary-test.mjs", "");
  write("test/openshell-integration-test.sh", 'echo live >>"$TRACE"; exit "${LIVE_RC:-0}"\n');
  write("scripts/install.sh", `
HARNESS_IR_CONTAINER=ir
HARNESS_OPENSHELL_VERSION=0.1.5
error() { echo "$*" >&2; exit 1; }
resolve_bind_host() { echo 127.0.0.1; }
harness_state_root() { echo "$FIXTURE/state"; }
openshell_validate_shared_inference() { echo validate >>"$TRACE"; [[ "\${CONFLICT:-0}" == 0 ]] || error conflict; }
with_deployment_lock() { "$@"; }
ensure_openshell_cli() { echo cli-prepare >>"$TRACE"; }
`);
  write("startup.sh", 'echo prerequisites >>"$TRACE"\n');
  write("install.sh", 'echo "inference-prepare:${HARNESS_LLM_MODEL-unset}:$*" >>"$TRACE"\n');
  write("uninstall.sh", "");
  write("bin/docker", '#!/bin/bash\nif [[ "$1" == container && "\${FRESH:-0}" == 0 ]]; then echo ir; fi\n');
  write("bin/openshell", '#!/bin/bash\nif [[ "$1" == --version ]]; then echo "openshell \${VERSION:-0.1.5}"; else echo gateway >>"$TRACE"; fi\n');
  function run(args = [], changes = {}) {
    const env = {...process.env, FIXTURE: root, TRACE: path.join(root, "trace"),
      PATH: `${root}/bin:${process.env.PATH}`, ...changes};
    delete env.HARNESS_HF_MODEL;
    Object.assign(env, changes);
    const result = spawnSync("bash", [path.join(root, "test/validate-local-openshell.sh"),
      "--report-dir", path.join(root, "reports"), ...args], {env, encoding: "utf8"});
    const trace = fs.existsSync(env.TRACE) ? fs.readFileSync(env.TRACE, "utf8") : "";
    return {...result, trace};
  }
  return {run};
}

test("default validates existing services and runs live tests without preparation", t => {
  const r = fixture(t).run();
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.trace, /offline\nvalidate\ngateway\nlive/);
  assert.doesNotMatch(r.trace, /prepare|prerequisites/);
});
test("offline failure stops before shared environment changes", t => {
  const r = fixture(t).run(["--prepare"], {OFFLINE_RC: "1"});
  assert.notEqual(r.status, 0);
  assert.equal(r.trace, "offline\n");
});
test("prepare provisions fresh default without explicitly requesting a model", t => {
  const r = fixture(t).run(["--prepare"], {FRESH: "1"});
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.trace, /prerequisites\ninference-prepare:unset:inference --runtime openshell --non-interactive\nvalidate\ncli-prepare\ngateway\nlive/);
});
test("missing inference without consent fails before live testing", t => {
  const r = fixture(t).run([], {FRESH: "1"});
  assert.notEqual(r.status, 0);
  assert.doesNotMatch(r.trace, /live|prepare/);
});
test("conflicting existing inference is never repaired by prepare", t => {
  const r = fixture(t).run(["--prepare"], {CONFLICT: "1"});
  assert.notEqual(r.status, 0);
  assert.doesNotMatch(r.trace, /inference-prepare|cli-prepare|live/);
});
test("incompatible OpenShell fails before preparation", t => {
  const r = fixture(t).run(["--prepare"], {VERSION: "0.1.4"});
  assert.notEqual(r.status, 0);
  assert.doesNotMatch(r.trace, /prerequisites|prepare|live/);
});
test("custom fresh model requires explicit external preparation", t => {
  const r = fixture(t).run(["--prepare", "--model", "custom"], {FRESH: "1"});
  assert.notEqual(r.status, 0);
  assert.doesNotMatch(r.trace, /inference-prepare|live/);
});
test("live test failures propagate rather than print success", t => {
  const r = fixture(t).run([], {LIVE_RC: "1"});
  assert.notEqual(r.status, 0);
  assert.doesNotMatch(r.stdout, /Stage 5: validation passed/);
});
test("missing option values fail before tests or provisioning", t => {
  const r = fixture(t).run(["--model"]);
  assert.equal(r.status, 2);
  assert.equal(r.trace, "");
});
