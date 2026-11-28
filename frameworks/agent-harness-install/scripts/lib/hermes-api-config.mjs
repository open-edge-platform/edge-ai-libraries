#!/usr/bin/env node
// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Owns the installer-managed Hermes API server block in $HERMES_HOME/.env.
// Runs on the host and, copied into the image, inside the OpenShell sandbox.
//
//   enable [--port N]   write the block (loopback only, generated key reused on re-run)
//   disable             remove the block
//   status              print {"enabled","host","port"} as JSON (never the key)
//   enabled             exit 0 when enabled, 1 when not, 2 on error
//   port                print the configured port (exit 1 when not enabled)
//   key                 print the API key (exit 1 when not enabled)
//   probe [--wait S]    wait for /health, then check /v1/models with the key
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const BEGIN = "# BEGIN agent-harness-install hermes-api -- do not edit between markers";
const END = "# END agent-harness-install hermes-api";
const HOST = "127.0.0.1";
const DEFAULT_PORT = 8642;
const hermesHome = process.env.HERMES_HOME || path.join(process.env.HOME ?? "", ".hermes");
const envFile = path.join(hermesHome, ".env");
const OWNED = /^\s*(?:export\s+)?API_SERVER_(?:ENABLED|HOST|PORT|KEY)\s*=/;

class Fail extends Error {}

function validPort(value) {
  return /^[1-9][0-9]{0,4}$/.test(String(value)) && Number(value) <= 65535;
}

function readEnv() {
  let stat;
  try {
    stat = fs.lstatSync(envFile);
  } catch (error) {
    if (error.code === "ENOENT") return "";
    throw error;
  }
  if (!stat.isFile()) throw new Fail(`${envFile} is not a regular file`);
  return fs.readFileSync(envFile, "utf8");
}

function parse(text) {
  const lines = text.split("\n");
  const begin = lines.indexOf(BEGIN);
  const end = lines.indexOf(END);
  if (begin < 0 && end < 0) return {rest: lines, block: []};
  if (begin < 0 || end < begin || lines.indexOf(BEGIN, begin + 1) >= 0 || lines.indexOf(END, end + 1) >= 0)
    throw new Fail(`${envFile} has a damaged installer-managed API server block; repair or remove it by hand`);
  return {rest: [...lines.slice(0, begin), ...lines.slice(end + 1)], block: lines.slice(begin + 1, end)};
}

function current() {
  const text = readEnv();
  const {rest, block} = parse(text);
  const foreign = rest.find((line) => OWNED.test(line));
  if (foreign)
    throw new Fail(`${envFile} sets ${foreign.split("=")[0].trim()} outside the installer-managed block; ` +
      "remove it or manage the Hermes API server by hand");
  const values = {};
  for (const line of block) {
    const match = /^([A-Z_]+)=(.*)$/.exec(line);
    if (match) values[match[1]] = match[2];
  }
  const key = /^[0-9a-f]{64}$/.test(values.API_SERVER_KEY ?? "") ? values.API_SERVER_KEY : undefined;
  const port = validPort(values.API_SERVER_PORT) ? Number(values.API_SERVER_PORT) : undefined;
  const enabled = values.API_SERVER_ENABLED === "true" && values.API_SERVER_HOST === HOST &&
    key !== undefined && port !== undefined;
  return {text, rest, enabled, key, port};
}

function writeEnv(text, before) {
  fs.mkdirSync(hermesHome, {recursive: true, mode: 0o700});
  const tmp = path.join(hermesHome, `.env.harness-${process.pid}.tmp`);
  try {
    const fd = fs.openSync(tmp, "wx", 0o600);
    try {
      fs.writeFileSync(fd, text);
    } finally {
      fs.closeSync(fd);
    }
    // Hermes edits .env too; refuse to replace a file that changed since it was read.
    if (readEnv() !== before) throw new Fail(`${envFile} changed while it was being updated; run the command again`);
    fs.renameSync(tmp, envFile);
  } catch (error) {
    fs.rmSync(tmp, {force: true});
    throw error;
  }
  fs.chmodSync(envFile, 0o600);
}

function compose(rest, block) {
  const body = rest.join("\n").replace(/\n+$/, "");
  if (!block) return body ? `${body}\n` : "";
  return `${body ? `${body}\n\n` : ""}${block.join("\n")}\n`;
}

function status() {
  const {enabled, port} = current();
  return {enabled, host: HOST, port: enabled ? port : null};
}

function options(args) {
  const out = {};
  for (let i = 0; i < args.length; i += 2) {
    const name = args[i];
    const value = args[i + 1];
    if ((name !== "--port" && name !== "--wait") || value === undefined)
      throw new Fail(`unknown or incomplete option: ${name}`);
    if (name === "--port") {
      if (!validPort(value)) throw new Fail(`invalid port: ${value}`);
      out.port = Number(value);
    } else {
      if (!/^[0-9]{1,4}$/.test(value)) throw new Fail(`invalid wait: ${value}`);
      out.wait = Number(value);
    }
  }
  return out;
}

function enable(opts) {
  const state = current();
  const port = opts.port ?? state.port ?? DEFAULT_PORT;
  const key = state.key ?? crypto.randomBytes(32).toString("hex");
  writeEnv(compose(state.rest, [
    BEGIN, "API_SERVER_ENABLED=true", `API_SERVER_HOST=${HOST}`, `API_SERVER_PORT=${port}`,
    `API_SERVER_KEY=${key}`, END
  ]), state.text);
  console.log(JSON.stringify(status()));
}

function disable() {
  const state = current();
  if (fs.existsSync(envFile)) writeEnv(compose(state.rest, null), state.text);
  console.log(JSON.stringify(status()));
}

// A fresh agent never uses HTTP_PROXY (NODE_USE_ENV_PROXY applies only to the global agent and fetch).
function get(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, {headers, agent: new http.Agent(), timeout: 5000}, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => resolve({status: response.statusCode, body}));
    });
    request.on("timeout", () => request.destroy(Object.assign(new Error("timed out"), {code: "ETIMEDOUT"})));
    request.on("error", reject);
  });
}

async function probe(opts) {
  const state = current();
  if (!state.enabled) throw new Fail("the Hermes API server is not enabled");
  const base = `http://${HOST}:${state.port}`;
  const deadline = Date.now() + (opts.wait ?? 0) * 1000;
  let last = "";
  for (;;) {
    try {
      const health = await get(`${base}/health`);
      if (health.status >= 200 && health.status < 300) {
        const models = await get(`${base}/v1/models`, {Authorization: `Bearer ${state.key}`});
        if (models.status === 401 || models.status === 403)
          throw new Fail(`${base} rejected the API key; restart the Hermes gateway so it reloads ${envFile}, or another program owns that port`);
        if (models.status >= 200 && models.status < 300) {
          const body = JSON.parse(models.body);
          console.log(`${base}/v1 ready; models: ${(body.data ?? []).map((model) => model.id).join(", ")}`);
          return;
        }
        last = `/v1/models answered HTTP ${models.status}`;
      } else {
        last = `/health answered HTTP ${health.status}`;
      }
    } catch (error) {
      if (error instanceof Fail) throw error;
      last = error.code ?? error.message;
    }
    if (Date.now() >= deadline) throw new Fail(`the Hermes API server at ${base} is not ready (${last})`);
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

async function main() {
  const [verb, ...args] = process.argv.slice(2);
  switch (verb) {
    case "enable": enable(options(args)); break;
    case "disable": disable(); break;
    case "status": console.log(JSON.stringify(status())); break;
    case "enabled": process.exitCode = current().enabled ? 0 : 1; break;
    case "port": {
      const {enabled, port} = current();
      if (!enabled) process.exitCode = 1; else console.log(port);
      break;
    }
    case "key": {
      const {enabled, key} = current();
      if (!enabled) process.exitCode = 1; else console.log(key);
      break;
    }
    case "probe": await probe(options(args)); break;
    default: throw new Fail("usage: hermes-api-config.mjs <enable|disable|status|enabled|port|key|probe>");
  }
}

main().catch((error) => {
  if (!(error instanceof Fail)) throw error;
  console.error(`error: ${error.message}`);
  process.exitCode = 2;
});
