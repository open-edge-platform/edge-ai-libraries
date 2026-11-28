// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import {spawn, spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import test from "node:test";

const helper = process.env.HARNESS_TEST_HERMES_API_CONFIG ??
  fileURLToPath(new URL("../scripts/lib/hermes-api-config.mjs", import.meta.url));

function fixture(t, env = "") {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "harness-hermes-api-"));
  t.after(() => fs.rmSync(home, {recursive: true, force: true}));
  const file = path.join(home, ".env");
  if (env) fs.writeFileSync(file, env);
  const run = (...args) => spawnSync(process.execPath, [helper, ...args], {
    env: {...process.env, HERMES_HOME: home}, encoding: "utf8"
  });
  return {home, file, run};
}

const settings = (file) => Object.fromEntries(fs.readFileSync(file, "utf8").split("\n")
  .filter((line) => /^API_SERVER_[A-Z]+=/.test(line)).map((line) => line.split("=")));

test("enable writes a loopback-only 0600 block with a generated key", (t) => {
  const {file, run} = fixture(t, "OPENAI_API_KEY=abc\n");
  const result = run("enable");
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {enabled: true, host: "127.0.0.1", port: 8642});
  assert.equal(result.stdout.includes(settings(file).API_SERVER_KEY), false);
  assert.match(settings(file).API_SERVER_KEY, /^[0-9a-f]{64}$/);
  assert.equal(settings(file).API_SERVER_HOST, "127.0.0.1");
  if (process.platform !== "win32") assert.equal(fs.statSync(file).mode & 0o777, 0o600);
  assert.match(fs.readFileSync(file, "utf8"), /^OPENAI_API_KEY=abc\n/);
});

test("re-enable keeps the key and port unless a new port is given", (t) => {
  const {file, run} = fixture(t);
  run("enable", "--port", "9000");
  const key = settings(file).API_SERVER_KEY;
  assert.equal(run("enable").status, 0);
  assert.equal(settings(file).API_SERVER_KEY, key);
  assert.equal(settings(file).API_SERVER_PORT, "9000");
  assert.equal(run("enable", "--port", "9100").status, 0);
  assert.equal(settings(file).API_SERVER_PORT, "9100");
  assert.equal(settings(file).API_SERVER_KEY, key);
  assert.equal(fs.readFileSync(file, "utf8").split("\n").filter((line) => line.startsWith("# BEGIN")).length, 1);
});

test("disable removes only the managed block", (t) => {
  const {file, run} = fixture(t, "A=1\n# note\n");
  run("enable");
  assert.equal(run("disable").status, 0);
  assert.equal(fs.readFileSync(file, "utf8"), "A=1\n# note\n");
  assert.equal(run("enabled").status, 1);
  assert.equal(run("disable").status, 0);
});

test("enabled, port and key verbs follow the state", (t) => {
  const {file, run} = fixture(t);
  assert.equal(run("enabled").status, 1);
  assert.equal(run("key").status, 1);
  run("enable", "--port", "8700");
  assert.equal(run("enabled").status, 0);
  assert.equal(run("port").stdout.trim(), "8700");
  assert.equal(run("key").stdout.trim(), settings(file).API_SERVER_KEY);
});

test("API server settings outside the managed block are refused", (t) => {
  const {file, run} = fixture(t, "API_SERVER_KEY=mine\n");
  const result = run("enable");
  assert.equal(result.status, 2);
  assert.match(result.stderr, /outside the installer-managed block/);
  assert.equal(fs.readFileSync(file, "utf8"), "API_SERVER_KEY=mine\n");
  assert.equal(run("enabled").status, 2);
});

test("any other API_SERVER_* setting outside the managed block is refused", (t) => {
  for (const line of ["API_SERVER_MODEL_NAME=x", "export API_SERVER_CORS_ORIGINS=*"]) {
    const {file, run} = fixture(t, `${line}\n`);
    const result = run("enable");
    assert.equal(result.status, 2, line);
    assert.match(result.stderr, /outside the installer-managed block/);
    assert.equal(fs.readFileSync(file, "utf8"), `${line}\n`);
  }
});

test("a commented-out API server key is left alone", (t) => {
  const {run} = fixture(t, "# API_SERVER_KEY=example\n");
  assert.equal(run("enable").status, 0);
});

test("invalid ports and options are rejected", (t) => {
  const {file, run} = fixture(t);
  for (const port of ["0", "65536", "80a", "-1"]) assert.equal(run("enable", "--port", port).status, 2, port);
  assert.equal(run("enable", "--bogus", "1").status, 2);
  assert.equal(fs.existsSync(file), false);
});

test("a symlinked .env is refused", (t) => {
  const {home, file, run} = fixture(t);
  const target = path.join(home, "elsewhere");
  fs.writeFileSync(target, "X=1\n");
  try {
    fs.symlinkSync(target, file);
  } catch {
    t.skip("symlinks unavailable");
    return;
  }
  assert.equal(run("enable").status, 2);
  assert.equal(fs.readFileSync(target, "utf8"), "X=1\n");
});

test("a damaged managed block is refused", (t) => {
  const {run} = fixture(t, "# BEGIN agent-harness-install hermes-api -- do not edit between markers\nA=1\n");
  assert.equal(run("enable").status, 2);
});

test("probe authenticates /v1/models with the generated key, ignoring proxy settings", async (t) => {
  const {file, run, home} = fixture(t);
  const server = http.createServer((req, res) => {
    const key = settings(file).API_SERVER_KEY;
    if (req.url === "/health") return res.end("{}");
    if (req.headers.authorization !== `Bearer ${key}`) {
      res.statusCode = 401;
      return res.end("{}");
    }
    res.end(JSON.stringify({data: [{id: "hermes-agent"}]}));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  run("enable", "--port", String(server.address().port));
  const child = spawn(process.execPath, [helper, "probe"], {
    env: {...process.env, HERMES_HOME: home, NODE_USE_ENV_PROXY: "1", HTTP_PROXY: "http://127.0.0.1:9",
      http_proxy: "http://127.0.0.1:9", NO_PROXY: "", no_proxy: ""}
  });
  let out = "";
  child.stdout.on("data", (chunk) => { out += chunk; });
  const code = await new Promise((resolve) => child.on("close", resolve));
  assert.equal(code, 0);
  assert.match(out, /models: hermes-agent/);
});

test("probe reports an unreachable server after the wait", (t) => {
  const {run} = fixture(t);
  run("enable", "--port", "1");
  const result = run("probe");
  assert.equal(result.status, 2);
  assert.match(result.stderr, /not ready/);
});
