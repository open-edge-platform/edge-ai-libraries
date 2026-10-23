// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {execFileSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import test from "node:test";

const helper = process.env.HARNESS_TEST_MODEL_CONFIG ??
  fileURLToPath(new URL("../openshell/model-config.mjs", import.meta.url));
const model = "Qwen3.5-9B-int8-ov";
const endpoint = "http://host.openshell.internal:8010/v1";
const hermes = "/home/node/.local/bin/hermes";
const python = fs.existsSync(hermes)
  ? JSON.parse(execFileSync(hermes, ["--print-runtime-command"], {encoding: "utf8"}))[0] : null;
if (process.env.HARNESS_TEST_REQUIRE_HERMES === "1" && python === null)
  throw Error("Hermes defaults validation requires the pinned Hermes image runtime");
const bootstrap = 'import sys; sys.path.insert(0, "/home/node/.hermes/hermes-agent"); ' +
  "import hermes_bootstrap; import hermes_yaml as yaml; ";

function fixture(t, agent = "openclaw") {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "harness-defaults-"));
  t.after(() => fs.rmSync(home, {recursive: true, force: true}));
  const file = path.join(home, agent === "openclaw" ? ".openclaw/openclaw.json" : "config.yaml");
  fs.mkdirSync(path.dirname(file), {recursive: true});
  const env = {...process.env, HOME: home, HERMES_HOME: home};
  function read() {
    if (agent === "openclaw") return JSON.parse(fs.readFileSync(file, "utf8"));
    return JSON.parse(execFileSync(python, ["-I", "-c", bootstrap +
      "import json; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))", file],
    {encoding: "utf8"}));
  }
  function write(config) {
    const json = JSON.stringify(config);
    fs.writeFileSync(file, agent === "openclaw" ? json : execFileSync(python, ["-I", "-c", bootstrap +
      "import json; print(yaml.safe_dump(json.load(sys.stdin)))"], {input: json}));
  }
  function apply(selected = model, mode = "apply") {
    execFileSync(process.execPath, [helper, agent, selected, endpoint, mode], {env, stdio: "pipe"});
    return read();
  }
  write(agent === "openclaw" ? {
    models: {providers: {ovms: {models: [{id: model, name: model}]}}},
    agents: {defaults: {model: {primary: `ovms/${model}`}}},
    gateway: {auth: {token: "preserved-token"}},
    userSetting: true
  } : {model: {provider: "custom", default: model, base_url: endpoint}, userSetting: true});
  return {read, write, apply, home};
}

test("Qwen OpenClaw defaults cover catalog, request parameters and lean prompt", t => {
  const f = fixture(t);
  const config = f.apply();
  assert.equal(config.models.providers.ovms.models[0].contextWindow, 65536);
  assert.equal(config.models.providers.ovms.models[0].maxTokens, 512);
  assert.equal(config.agents.defaults.experimental.localModelLean, true);
  assert.equal(config.agents.defaults.bootstrapMaxChars, 4000);
  assert.equal(config.agents.defaults.bootstrapTotalMaxChars, 12000);
  assert.equal(config.agents.defaults.thinkingDefault, "off");
  assert.equal(config.tools.profile, "coding");
  assert.deepEqual(config.agents.defaults.models[`ovms/${model}`].params, {
    maxTokens: 512, temperature: 0.2, chat_template_kwargs: {enable_thinking: false}
  });
  assert.equal(config.gateway.auth.token, "preserved-token");
  assert.equal(config.userSetting, true);
  assert.deepEqual(f.apply(), config);
});

test("explicit OpenClaw overrides survive initial application and restarts", t => {
  const f = fixture(t);
  const config = f.read();
  config.models.providers.ovms.models[0].contextWindow = 16384;
  config.models.providers.ovms.models[0].maxTokens = 2048;
  config.agents.defaults.bootstrapMaxChars = 8000;
  config.agents.defaults.experimental = {localModelLean: false};
  config.agents.defaults.models = {[`ovms/${model}`]: {params: {
    temperature: 0.7, chat_template_kwargs: {enable_thinking: true, other: "preserved"}
  }}};
  config.tools = {profile: "full"};
  f.write(config);
  const result = f.apply();
  assert.equal(result.models.providers.ovms.models[0].contextWindow, 16384);
  assert.equal(result.agents.defaults.models[`ovms/${model}`].params.maxTokens, 2048);
  assert.equal(result.agents.defaults.models[`ovms/${model}`].params.temperature, 0.7);
  assert.deepEqual(result.agents.defaults.models[`ovms/${model}`].params.chat_template_kwargs,
    {enable_thinking: true, other: "preserved"});
  assert.equal(result.agents.defaults.bootstrapMaxChars, 8000);
  assert.equal(result.agents.defaults.experimental.localModelLean, false);
  assert.equal(result.tools.profile, "full");
  assert.deepEqual(f.apply(), result);
});

test("user edits to generated defaults survive later restarts and model changes", t => {
  const f = fixture(t);
  const config = f.apply();
  config.tools.profile = "full";
  config.agents.defaults.models[`ovms/${model}`].params.temperature = 0.8;
  f.write(config);
  assert.equal(f.apply().tools.profile, "full");
  const switched = f.apply("other-model");
  assert.equal(switched.tools.profile, "full");
  assert.equal(switched.agents.defaults.models["ovms/other-model"].params.temperature, 0.8);
});

test("switching away removes managed Qwen tuning and restores generic catalog defaults", t => {
  const f = fixture(t);
  f.apply();
  const config = f.apply("other-model");
  assert.equal(config.models.providers.ovms.models[0].contextWindow, 32768);
  assert.equal(config.models.providers.ovms.models[0].maxTokens, 4096);
  assert.equal(config.agents.defaults.thinkingDefault, undefined);
  assert.equal(config.agents.defaults.experimental, undefined);
  assert.equal(config.agents.defaults.models, undefined);
  assert.equal(config.tools, undefined);
  assert.equal(f.apply().models.providers.ovms.models[0].maxTokens, 512);
});

test("non-Qwen models retain existing configuration", t => {
  const f = fixture(t);
  const config = f.read();
  config.models.providers.ovms.models[0].contextWindow = 8192;
  config.models.providers.ovms.models[0].maxTokens = 900;
  config.tools = {profile: "minimal"};
  f.write(config);
  const result = f.apply("other-model");
  assert.equal(result.models.providers.ovms.models[0].contextWindow, 8192);
  assert.equal(result.models.providers.ovms.models[0].maxTokens, 900);
  assert.equal(result.agents.defaults.thinkingDefault, undefined);
  assert.equal(result.tools.profile, "minimal");
});

test("selection-only updates do not modify agent defaults", t => {
  const f = fixture(t);
  const before = f.read();
  assert.deepEqual(f.apply(model, "select"), before);
  assert.equal(fs.existsSync(path.join(f.home, ".harness-local-defaults.json")), false);
});

test("pre-existing empty configuration sections retain their identity and ordering", t => {
  const f = fixture(t);
  const config = f.read();
  config.agents.defaults.experimental = {};
  config.agents.defaults.other = true;
  config.tools = {};
  f.write(config);
  const first = JSON.stringify(f.apply());
  assert.equal(JSON.stringify(f.apply()), first);
  const switched = f.apply("other-model");
  assert.deepEqual(switched.agents.defaults.experimental, {});
  assert.deepEqual(switched.tools, {});
});

test("Hermes Qwen defaults normalize into actual custom-provider request overrides",
  {skip: python === null}, t => {
    const f = fixture(t, "hermes");
    const config = f.apply();
    assert.equal(config.model.context_length, 65536);
    assert.equal(config.model.provider, "custom:harness-ovms-qwen");
    assert.equal(config.agent.reasoning_overrides[model], "none");
    const body = config.providers["harness-ovms-qwen"].extra_body;
    assert.deepEqual(body, {max_tokens: 512, temperature: 0.2,
      chat_template_kwargs: {enable_thinking: false}});
    execFileSync(python, ["-I", "-c", bootstrap + `
import json, sys
sys.path.insert(0, "/home/node/.hermes/hermes-agent")
from hermes_cli.config_providers import providers_dict_to_custom_providers
from agent.agent_init import _custom_provider_extra_body_for_agent
config = json.load(sys.stdin)
entries = providers_dict_to_custom_providers(config["providers"])
body = _custom_provider_extra_body_for_agent(provider=config["model"]["provider"],
    model=config["model"]["default"], base_url=config["model"]["base_url"], custom_providers=entries)
assert body == {"max_tokens": 512, "temperature": 0.2, "chat_template_kwargs": {"enable_thinking": False}}, body
`], {input: JSON.stringify(config)});
    assert.deepEqual(f.apply(), config);
    const switched = f.apply("other-model");
    assert.equal(switched.model.provider, "custom");
    assert.equal(switched.model.context_length, undefined);
    assert.equal(switched.providers, undefined);
    assert.equal(switched.agent, undefined);
    assert.equal(switched.userSetting, true);
  });

test("Hermes explicit overrides survive restart and switching away",
  {skip: python === null}, t => {
    const f = fixture(t, "hermes");
    const config = f.read();
    config.model.context_length = 16384;
    config.providers = {"harness-ovms-qwen": {extra_body: {
      max_tokens: 2048, temperature: 0.7, chat_template_kwargs: {enable_thinking: true}
    }}};
    config.agent = {reasoning_overrides: {[model]: "low"}};
    f.write(config);
    const result = f.apply();
    assert.equal(result.model.context_length, 16384);
    assert.equal(result.providers["harness-ovms-qwen"].extra_body.max_tokens, 2048);
    assert.equal(result.providers["harness-ovms-qwen"].extra_body.temperature, 0.7);
    assert.equal(result.providers["harness-ovms-qwen"].extra_body.chat_template_kwargs.enable_thinking, true);
    assert.equal(result.agent.reasoning_overrides[model], "low");
    assert.deepEqual(f.apply(), result);
    const switched = f.apply("other-model");
    assert.equal(switched.model.context_length, 16384);
    assert.deepEqual(switched.providers["harness-ovms-qwen"].extra_body,
      config.providers["harness-ovms-qwen"].extra_body);
  });
