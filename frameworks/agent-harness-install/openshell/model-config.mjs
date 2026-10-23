// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import fs from "node:fs";
import path from "node:path";
import {randomUUID} from "node:crypto";
import {execFileSync} from "node:child_process";

const [agent, model, endpoint, mode = "apply"] = process.argv.slice(2);
const home = process.env.HOME;
if (!["openclaw", "hermes"].includes(agent) || !model || /[\x00-\x1f]/.test(model))
  throw Error("Invalid agent or model selection");
if (!["apply", "select"].includes(mode)) throw Error("Invalid model configuration mode");
const url = new URL(endpoint);
if (url.protocol !== "http:" || url.hostname !== "host.openshell.internal" ||
    url.pathname !== "/v1" || url.username || url.password || url.search || url.hash)
  throw Error("Invalid sandbox inference endpoint");

function writeFile(file, content) {
  const tmp = `${file}.${randomUUID()}.tmp`;
  fs.writeFileSync(tmp, content, {mode: 0o600, flag: "wx"});
  try {
    fs.renameSync(tmp, file);
  } finally {
    if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
  }
}

function writeJson(file, data) {
  writeFile(file, JSON.stringify(data, null, 2));
}

const qwen = model === "Qwen3.5-9B-int8-ov";
const defaultsFile = path.join(home, ".harness-local-defaults.json");
const installedDefaults = [];
const createdContainers = [];

function parentAt(config, keys, create) {
  let parent = config;
  for (const [index, key] of keys.entries()) {
    if (!Object.hasOwn(parent, key)) {
      if (!create) return;
      parent[key] = {};
      createdContainers.push(keys.slice(0, index + 1));
    }
    parent = parent[key];
    if (typeof parent !== "object" || parent === null) return;
  }
  return parent;
}

function removePreviousDefaults(config) {
  if (!fs.existsSync(defaultsFile)) return;
  const saved = JSON.parse(fs.readFileSync(defaultsFile, "utf8"));
  if (saved.agent !== agent || !Array.isArray(saved.entries) || !Array.isArray(saved.containers))
    throw Error("Invalid installer local-model defaults record");
  for (const {keys, value} of saved.entries) {
    if (!Array.isArray(keys) || !keys.length ||
        keys.some(k => typeof k !== "string" || ["__proto__", "prototype", "constructor"].includes(k)))
      throw Error("Invalid installer local-model default path");
    const parent = parentAt(config, keys.slice(0, -1), false);
    if (parent && Object.hasOwn(parent, keys.at(-1)) &&
        JSON.stringify(parent[keys.at(-1)]) === JSON.stringify(value)) {
      delete parent[keys.at(-1)];
    }
  }
  for (const keys of saved.containers.toReversed()) {
    if (!Array.isArray(keys) || !keys.length ||
        keys.some(k => typeof k !== "string" || ["__proto__", "prototype", "constructor"].includes(k)))
      throw Error("Invalid installer local-model container path");
    const parent = parentAt(config, keys.slice(0, -1), false);
    const child = parent?.[keys.at(-1)];
    if (child && typeof child === "object" && !Object.keys(child).length)
      delete parent[keys.at(-1)];
  }
}

function defaultAt(config, keys, value) {
  const parent = parentAt(config, keys.slice(0, -1), true);
  if (parent && !Object.hasOwn(parent, keys.at(-1))) {
    parent[keys.at(-1)] = value;
    installedDefaults.push({keys, value});
  }
}

if (agent === "openclaw" && mode === "apply") {
  const file = path.join(home, ".openclaw", "openclaw.json");
  const config = JSON.parse(fs.readFileSync(file, "utf8"));
  removePreviousDefaults(config);
  const provider = config.models?.providers?.ovms;
  if (!provider || !Array.isArray(provider.models) || !provider.models.length)
    throw Error("Missing installer-managed OpenClaw provider");
  const previous = provider.models;
  provider.baseUrl = endpoint;
  provider.models = [{...previous[0], id: model, name: model}];
  config.agents ??= {};
  config.agents.defaults ??= {};
  const selected = config.agents.defaults.model;
  config.agents.defaults.model = typeof selected === "object" && selected !== null
    ? {...selected, primary: `ovms/${model}`} : {primary: `ovms/${model}`};
  if (Array.isArray(config.agents.defaults.model.fallbacks))
    config.agents.defaults.model.fallbacks = config.agents.defaults.model.fallbacks.filter(x => !x.startsWith("ovms/"));
  for (const agentConfig of config.agents.list ?? []) {
    if (typeof agentConfig.model === "string" && agentConfig.model.startsWith("ovms/"))
      agentConfig.model = `ovms/${model}`;
    else if (agentConfig.model?.primary?.startsWith("ovms/")) {
      agentConfig.model.primary = `ovms/${model}`;
      if (Array.isArray(agentConfig.model.fallbacks))
        agentConfig.model.fallbacks = agentConfig.model.fallbacks.filter(x => !x.startsWith("ovms/"));
    }
  }
  if (config.agents.defaults.models) {
    for (const old of previous) {
      const key = `ovms/${old.id}`;
      if (key !== `ovms/${model}` && Object.hasOwn(config.agents.defaults.models, key)) {
        config.agents.defaults.models[`ovms/${model}`] ??= config.agents.defaults.models[key];
        delete config.agents.defaults.models[key];
      }
    }
  }
  const catalogDefaults = {contextWindow: qwen ? 65536 : 32768, maxTokens: qwen ? 512 : 4096};
  for (const [key, value] of Object.entries(catalogDefaults))
    defaultAt(config, ["models", "providers", "ovms", "models", "0", key], value);
  if (qwen) {
    defaultAt(config, ["agents", "defaults", "experimental", "localModelLean"], true);
    defaultAt(config, ["agents", "defaults", "bootstrapMaxChars"], 4000);
    defaultAt(config, ["agents", "defaults", "bootstrapTotalMaxChars"], 12000);
    defaultAt(config, ["agents", "defaults", "thinkingDefault"], "off");
    defaultAt(config, ["tools", "profile"], "coding");
    const params = ["agents", "defaults", "models", `ovms/${model}`, "params"];
    defaultAt(config, [...params, "maxTokens"], provider.models[0].maxTokens);
    defaultAt(config, [...params, "temperature"], 0.2);
    defaultAt(config, [...params, "chat_template_kwargs", "enable_thinking"], false);
  }
  writeJson(file, config);
  writeJson(defaultsFile, {agent, entries: installedDefaults, containers: createdContainers});
}
if (agent === "hermes" && mode === "apply") {
  const hermesHome = process.env.HERMES_HOME ?? "/home/node/.hermes";
  // Dependencies belong to the image installation, not the sandbox HOME.
  const runtimeOptions = {encoding: "utf8", env: {...process.env, HERMES_HOME: "/home/node/.hermes"}};
  const runtime = JSON.parse(execFileSync("/home/node/.local/bin/hermes",
    ["--print-runtime-command"], runtimeOptions));
  if (!Array.isArray(runtime) || typeof runtime[0] !== "string" || !path.isAbsolute(runtime[0]))
    throw Error("Invalid Hermes Python runtime command");
  const python = runtime[0];
  const bootstrap = 'import sys; sys.path.insert(0, "/home/node/.hermes/hermes-agent"); ' +
    "import hermes_bootstrap; import hermes_yaml as yaml; ";
  const file = path.join(hermesHome, "config.yaml");
  const config = JSON.parse(execFileSync(python, ["-I", "-c", bootstrap +
    "import json; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))", file],
  runtimeOptions));
  removePreviousDefaults(config);
  if (!config.model || typeof config.model !== "object")
    throw Error("Missing installer-managed Hermes model configuration");
  config.model.default = model;
  config.model.base_url = endpoint;
  config.model.provider = "custom";
  if (qwen) {
    const provider = "harness-ovms-qwen";
    defaultAt(config, ["model", "context_length"], 65536);
    defaultAt(config, ["agent", "reasoning_overrides", model], "none");
    defaultAt(config, ["providers", provider, "base_url"], endpoint);
    defaultAt(config, ["providers", provider, "default_model"], model);
    defaultAt(config, ["providers", provider, "api_key"], "not-needed");
    defaultAt(config, ["providers", provider, "extra_body", "max_tokens"], 512);
    defaultAt(config, ["providers", provider, "extra_body", "temperature"], 0.2);
    defaultAt(config, ["providers", provider, "extra_body", "chat_template_kwargs", "enable_thinking"], false);
    config.model.provider = `custom:${provider}`;
  }
  const yaml = execFileSync(python, ["-I", "-c", bootstrap +
    "import json; print(yaml.safe_dump(json.load(sys.stdin), sort_keys=False), end='')"],
  {...runtimeOptions, input: JSON.stringify(config)});
  writeFile(file, yaml);
  writeJson(defaultsFile, {agent, entries: installedDefaults, containers: createdContainers});
}
// The creation environment is immutable. This workspace record takes precedence
// on every later startup, including Hermes's startup configuration commands.
writeJson(path.join(home, ".harness-model.json"), {model, endpoint, applied: mode === "apply"});
