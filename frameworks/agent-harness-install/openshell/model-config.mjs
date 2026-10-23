// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import fs from "node:fs";
import path from "node:path";
import {randomUUID} from "node:crypto";

const [agent, model, endpoint, mode = "apply"] = process.argv.slice(2);
const home = process.env.HOME;
if (!["openclaw", "hermes"].includes(agent) || !model || /[\x00-\x1f]/.test(model))
  throw Error("Invalid agent or model selection");
if (!["apply", "select"].includes(mode)) throw Error("Invalid model configuration mode");
const url = new URL(endpoint);
if (url.protocol !== "http:" || url.hostname !== "host.openshell.internal" ||
    url.pathname !== "/v1" || url.username || url.password || url.search || url.hash)
  throw Error("Invalid sandbox inference endpoint");

function writeJson(file, data) {
  const tmp = `${file}.${randomUUID()}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), {mode: 0o600, flag: "wx"});
  try {
    fs.renameSync(tmp, file);
  } finally {
    if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
  }
}

if (agent === "openclaw" && mode === "apply") {
  const file = path.join(home, ".openclaw", "openclaw.json");
  const config = JSON.parse(fs.readFileSync(file, "utf8"));
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
  writeJson(file, config);
}
// The creation environment is immutable. This workspace record takes precedence
// on every later startup, including Hermes's startup configuration commands.
writeJson(path.join(home, ".harness-model.json"), {model, endpoint, applied: mode === "apply"});
