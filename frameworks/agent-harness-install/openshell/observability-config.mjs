// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
// Sandbox-side half of `./install.sh observability` for --runtime openshell.
// Run inside the sandbox, either piped to `node --input-type=module -` by the
// installer or from /opt/harness (agent-start.sh applies staged OpenClaw settings).
import fs from "node:fs";
import path from "node:path";
import {randomUUID} from "node:crypto";
import {spawnSync} from "node:child_process";

process.on("uncaughtException", error => {
  console.error(`Error: ${error.message}`);
  process.exit(1);
});

const [command, ...args] = process.argv.slice(2);
const home = process.env.HOME;
const stateFile = path.join(home, ".harness-observability.json");
const openclawConfig = path.join(home, ".openclaw", "openclaw.json");
const baseUrl = /^https?:\/\/[A-Za-z0-9._-]+(:[1-9][0-9]{0,4})?(\/[A-Za-z0-9._~%\/-]*[A-Za-z0-9._~%-])?$/;
// The host's own services; any other collector must be reached over https.
const localHttp = /^http:\/\/host\.openshell\.internal(:\d+)?(\/|$)/;
const pluginDir = "/home/node/.openclaw/npm/projects";
const script = "/opt/harness/observability-config.mjs";
// Hermes: the hermes-otel plugin is installed and enabled in the image (enabling downloads
// dependencies, which the default sandbox policy does not allow); its exporter is switched through this file only.
const hermesHome = process.env.HERMES_HOME || "/home/node/.hermes";
const hermesConfig = path.join(hermesHome, "hermes_otel.yaml");
const hermesPlugin = path.join(hermesHome, "plugins", "hermes_otel", "plugin.yaml");
// The sandbox user's HOME is /sandbox, but the image installs Hermes under /home/node.
const hermesBin = process.env.HERMES_BIN || "/home/node/.local/bin/hermes";
const hermesMarker = "# Managed by agent-harness-install (metrics)";

function writeFile(file, content) {
  fs.mkdirSync(path.dirname(file), {recursive: true, mode: 0o700});
  const tmp = `${file}.${randomUUID()}.tmp`;
  fs.writeFileSync(tmp, content, {mode: 0o600, flag: "wx"});
  try {
    fs.renameSync(tmp, file);
  } finally {
    if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
  }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function validBase(value) {
  if (!baseUrl.test(value ?? "") || Number(/^https?:\/\/[^/:]+:(\d+)/.exec(value)?.[1] ?? 1) > 65535)
    throw Error("Invalid sandbox telemetry endpoint");
  if (value.startsWith("http://") && !localHttp.test(value))
    throw Error("Invalid sandbox telemetry endpoint: plain http is only allowed to the host's own services");
  return value;
}

function validContent(value) {
  if (!["off", "preview", "full"].includes(value)) throw Error("Invalid content mode");
  return value;
}

function stagedState() {
  return fs.existsSync(stateFile) ? readJson(stateFile) : null;
}

function currentOpenclawConfig() {
  return fs.existsSync(openclawConfig) ? readJson(openclawConfig) : {};
}

function pluginInstalled() {
  return fs.existsSync(pluginDir) && fs.readdirSync(pluginDir).some(name => name.includes("diagnostics-otel"));
}

function assertNoForeignOpenclawExporter() {
  const staged = stagedState();
  if (currentOpenclawConfig().diagnostics?.otel?.enabled === true && staged?.enabled !== true)
    throw Error("OpenClaw already has diagnostics.otel enabled that this installer did not set up; it is not overwritten");
}

function openclawApply() {
  const staged = stagedState();
  if (!staged) return;
  const config = currentOpenclawConfig();
  config.diagnostics ??= {};
  config.diagnostics.otel ??= {};
  if (staged.enabled) {
    validBase(staged.endpoint);
    config.plugins ??= {};
    config.plugins.entries ??= {};
    config.plugins.entries["diagnostics-otel"] = {...config.plugins.entries["diagnostics-otel"], enabled: true};
    config.diagnostics.enabled = true;
    Object.assign(config.diagnostics.otel, {
      enabled: true, endpoint: staged.endpoint, protocol: "http/protobuf", serviceName: "openclaw",
      traces: true, metrics: false, logs: false, captureContent: staged.content !== "off", flushIntervalMs: 1000
    });
  } else {
    Object.assign(config.diagnostics.otel, {enabled: false, captureContent: false});
    if (config.plugins?.entries?.["diagnostics-otel"]) config.plugins.entries["diagnostics-otel"].enabled = false;
  }
  writeFile(openclawConfig, JSON.stringify(config, null, 2));
}

// A hermes_otel.yaml this installer did not write is never replaced.
function hermesConfigState() {
  if (!fs.existsSync(hermesConfig)) return "absent";
  return fs.readFileSync(hermesConfig, "utf8").split("\n")[0] === hermesMarker ? "managed" : "foreign";
}

function assertHermesConfigWritable() {
  if (hermesConfigState() === "foreign")
    throw Error(`${hermesConfig} exists and is not managed by this installer; move it aside and retry`);
}

function hermesPluginInstalled() {
  return fs.existsSync(hermesPlugin);
}

// Plugin versions before the capture_tool_* settings export command lines and paths whatever content_capture says.
function hermesPluginOmitsToolText() {
  const walk = dir => fs.readdirSync(dir, {withFileTypes: true}).some(entry => entry.isDirectory()
    ? walk(path.join(dir, entry.name))
    : entry.name.endsWith(".py") && fs.readFileSync(path.join(dir, entry.name), "utf8").includes("capture_tool_command"));
  return walk(path.dirname(hermesPlugin));
}

// `hermes -z` leaves a gateway process running that holds the loaded plugin
// configuration; the next turn starts a new one with the settings just written.
function restartHermesGateway() {
  // 'gateway stop' exits 0 when no gateway is running, so any failure here is real.
  const result = spawnSync(hermesBin, ["gateway", "stop"], {
    env: {...process.env, HERMES_HOME: hermesHome, PATH: `/home/node/.local/bin:${process.env.PATH ?? "/usr/bin:/bin"}`},
    encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 60000
  });
  if (result.error || result.status !== 0) {
    const why = result.error?.message ?? `exit ${result.status}: ${`${result.stderr}${result.stdout}`.trim().slice(-300)}`;
    throw Error(`Could not stop the running Hermes gateway (${why}); it may keep exporting with the previous settings`);
  }
}

function hermesInert() {
  writeFile(hermesConfig, `${hermesMarker}\nenabled: false\n`);
}

function openclawMatches(expect, endpoint) {
  const otel = currentOpenclawConfig().diagnostics?.otel;
  return expect === "on"
    ? otel?.enabled === true && otel.endpoint === endpoint
    : !otel || otel.enabled !== true;
}

switch (command) {
  case "check": {
    const [agent] = args;
    if (agent === "openclaw") {
      if (!fs.existsSync(script) || !pluginInstalled())
        throw Error("This sandbox image predates telemetry support (no diagnostics-otel plugin); remove the sandbox and install it again");
      assertNoForeignOpenclawExporter();
    } else if (agent === "hermes") {
      if (!fs.existsSync(script) || !hermesPluginInstalled() || hermesConfigState() === "absent")
        throw Error("This sandbox image predates telemetry support (no hermes-otel plugin); remove the sandbox and install it again");
      assertHermesConfigWritable();
    } else {
      throw Error("Unsupported sandbox agent");
    }
    break;
  }
  case "openclaw-stage": {
    const [mode, base, content] = args;
    assertNoForeignOpenclawExporter();
    if (mode === "on") writeFile(stateFile, JSON.stringify({enabled: true, endpoint: validBase(base), content: validContent(content)}));
    else if (mode === "off") writeFile(stateFile, JSON.stringify({enabled: false}));
    else throw Error("Invalid staging mode");
    break;
  }
  case "openclaw-apply":
    openclawApply();
    break;
  case "openclaw-verify": {
    const [mode, base] = args;
    if (!openclawMatches(mode, base)) process.exitCode = 1;
    break;
  }
  case "hermes-enable": {
    // "filtered" means the receiver on the other end drops tool text itself.
    const [tracesUrl, content, receiver] = args;
    validBase(tracesUrl);
    validContent(content);
    assertHermesConfigWritable();
    const omitToolText = content === "off";
    if (omitToolText && receiver !== "filtered" && !hermesPluginOmitsToolText())
      throw Error("The hermes-otel plugin in this sandbox image predates capture_tool_command, so --content off would still export tool commands and paths; use --backend sqlite, or rebuild the sandbox with a newer plugin (HARNESS_HERMES_OTEL_REF)");
    // "off" must stay quoted: bare off is a YAML 1.1 boolean.
    writeFile(hermesConfig, [hermesMarker, `content_capture: "${content}"`,
      ...(omitToolText ? ["capture_tool_command: false", "capture_tool_target: false", "capture_error_message: false"] : []),
      "backends:", "  - type: otlp",
      `    endpoint: "${tracesUrl}"`, "    metrics: false", "    logs: false", ""].join("\n"));
    restartHermesGateway();
    break;
  }
  case "hermes-disable":
    if (hermesConfigState() === "foreign") break;
    hermesInert();
    // Image build: no gateway exists yet.
    if (args[0] !== "no-restart") restartHermesGateway();
    break;
  case "status": {
    const [agent] = args;
    if (agent === "hermes") {
      const state = hermesConfigState();
      console.log(`hermes-otel plugin ${hermesPluginInstalled() ? "installed" : "not installed"}`);
      if (state === "foreign") console.log(`${hermesConfig} is not managed by this installer`);
      else if (state === "absent") console.log(`No exporter settings in ${hermesConfig}`);
      else {
        const text = fs.readFileSync(hermesConfig, "utf8");
        const endpoint = text.match(/^\s+endpoint: "([^"]+)"/m)?.[1];
        console.log(`Exporter settings: ${hermesConfig} (${/^enabled: false$/m.test(text) ? "off" : `on${endpoint ? `, ${endpoint}` : ""}`})`);
      }
    } else if (agent === "openclaw") {
      const otel = currentOpenclawConfig().diagnostics?.otel;
      console.log(`diagnostics-otel plugin ${pluginInstalled() ? "installed" : "not installed"}`);
      console.log(`diagnostics.otel.enabled: ${otel?.enabled === true}${otel?.endpoint ? ` (${otel.endpoint})` : ""}`);
    } else {
      throw Error("Unsupported sandbox agent");
    }
    break;
  }
  default:
    throw Error("Invalid observability command");
}
