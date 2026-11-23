<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Build Visual AI Agents with VSS

This tutorial sets up a local AI agent for
[Video Search and Summarization (VSS)](./index.md) on one Intel host. At the
end, you ask the agent in plain language to search your footage and to track
people across cameras. The agent model runs on the host. You do not need a
cloud model or an API key.

The tutorial uses these parts:

- **VSS** indexes and searches the video. Its **MCP server** gives the agent
  tools to call.
- **[agent-harness-install](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/frameworks/agent-harness-install)**
  is an installer. It serves the agent model with **OpenVINO™ Model Server**
  (OVMS) behind an **Inference Router**, and it installs the **Hermes** agent.
- **Hermes** is the agent. It talks to you, uses the model to decide what to
  do, and calls the VSS tools.

This page shows one recommended path with Hermes. To use another agent, see
[Other Harnesses](#other-harnesses). To learn how the agent works with VSS, and
for more use cases, see the reference page
[Agentic Video Analytics with VSS](./agentic-video-analytics.md).

## What You Get

When you finish, these parts run on the host:

| Part | Runs as | Address |
|---|---|---|
| VSS (search mode) and its MCP server | Docker containers that `setup.sh` starts | `http://<HOST_IP>:12345/` and `http://<HOST_IP>:12345/mcp` |
| OVMS with the agent model | Docker container that the installer starts | `127.0.0.1:8450` |
| Inference Router | Docker container that the installer starts | `http://127.0.0.1:8010/v1` |
| Hermes | Command-line tool on the host | Uses the router for the model and VSS for tools |

## Before You Start

You need:

- A host that meets the VSS [system requirements](./get-started/system-requirements.md)
  and has an Intel GPU. The GPU holds the agent model and the VSS search
  models at the same time. On an integrated GPU, this memory is system memory.
  See [Choose the agent model](#choose-the-agent-model).
- `git`, and a user account that can run `sudo`. The installer installs
  Docker, Node.js, and Python if they are missing. It also checks the Intel GPU
  driver.

If the host is behind a proxy, export the proxy settings in every terminal
that you use for these steps:

```bash
export HTTP_PROXY=<proxy-url> HTTPS_PROXY=<proxy-url>
export NO_PROXY=localhost,127.0.0.1,<HOST_IP>
export http_proxy=$HTTP_PROXY https_proxy=$HTTPS_PROXY no_proxy=$NO_PROXY
```

`NO_PROXY` and `no_proxy` must include `localhost`, `127.0.0.1`, and
`<HOST_IP>`.

> **Note:** The VSS MCP server has no authentication. Any user who can reach
> `http://<HOST_IP>:12345` can call its tools. Run VSS only on a trusted
> network.

## Step 1: Get the Sources

VSS and the installer are both in the `edge-ai-libraries` repository. Clone
the repository with only these two folders:

```bash
git clone --filter=blob:none --sparse --branch main https://github.com/open-edge-platform/edge-ai-libraries.git
git -C edge-ai-libraries sparse-checkout set \
  sample-applications/video-search-and-summarization \
  frameworks/agent-harness-install
```

Run the commands in the next steps from the directory where you ran
`git clone`.

## Step 2: Start VSS in Search Mode

Set the service credentials and the search models. Then start VSS:

```bash
cd edge-ai-libraries/sample-applications/video-search-and-summarization
export REGISTRY_URL=intel TAG=latest
export MINIO_ROOT_USER=<user> MINIO_ROOT_PASSWORD=<password>
export POSTGRES_USER=<user> POSTGRES_PASSWORD=<password>
export RABBITMQ_USER=<user> RABBITMQ_PASSWORD=<password>
export MULTIMODAL_EMBEDDING_MODEL="CLIP/clip-vit-b-32"
export DATAPREP_DETECTION_MODEL="OpenVINO/yolox_s-int8-ov"
source setup.sh --search
```

You must `source` `setup.sh`. Do not run it as `./setup.sh`.

Search mode supports these tasks:

- Review incidents with search.
- Find a person from a description or an image.
- Track a person across cameras.
- Search live cameras.

For other models, GPU embedding, and more options, see
[Get Started](./get-started.md).

> **Why search mode:** Summary mode and Dual UI mode also run a vision language
> model (VLM) for captions and summaries. The VLM uses the same GPU as the
> agent model. Use these modes only if the GPU has memory for both models, or
> choose a smaller agent model. For the features of each mode, see
> [Step 1: Start VSS](./agentic-video-analytics.md#step-1-start-vss) in the
> reference page.

## Step 3: Install Hermes and the Agent Model

### Choose the agent model

The agent must call tools correctly and follow workflows that have many steps.
This needs a capable model. This tutorial uses
`OpenVINO/Qwen3.6-35B-A3B-int4-ov`, for two reasons:

- It is a mixture-of-experts model with about 3B active parameters. It answers
  quickly and calls tools reliably.
- It is already in OpenVINO IR format. OVMS downloads it and does not convert
  it.

Other models have trade-offs:

- Smaller models, of about 8B parameters, use less memory. But they skip steps
  and use tools incorrectly more often.
- Dense models, such as `OpenVINO/Qwen3.8-27B-int4-ov`, are more accurate but
  much slower.

For each model, the GPU must hold the model weights, the KV cache, and the VSS
search models at the same time.

### Run the installer

From the directory where you ran `git clone`:

```bash
cd edge-ai-libraries/frameworks/agent-harness-install
export MODEL=OpenVINO/Qwen3.6-35B-A3B-int4-ov
export SERVED_MODEL="${MODEL##*/}"
export HARNESS_OVMS_REST_PORT=8450
./install.sh --harness hermes --model "$MODEL"
```

The installer asks two questions:

1. **Runtime [host/openshell]:** Press Enter to keep `host`.
2. **Host/IP to advertise in printed endpoint URLs:** Press Enter to keep
   `127.0.0.1`. Hermes runs on the same host, so OVMS and the router listen
   only on loopback. Other machines cannot reach them.

On the first run, the installer downloads the model. This can take a long
time. For all installer options, see the installer's
[Get Started](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/user-guide/get-started.md)
guide.

### Connect Hermes to the model

The installer starts the router, but it does not set the Hermes model. Set the
model, then check the installation:

```bash
hermes config set model.provider custom
hermes config set model.base_url http://127.0.0.1:8010/v1
hermes config set model.default "$SERVED_MODEL"
./install.sh status
```

## Step 4: Move the Bundled Hermes Skills Aside

Hermes includes a set of skills in `~/.hermes/skills/`. It loads all of them
in every session. With a local model, these skills compete with the VSS tools,
and the agent can use a skill when it should call VSS. Move the skills to a
different folder:

```bash
mv ~/.hermes/skills ~/.hermes/skills.bundled.$(date +%Y%m%d)
mkdir -p ~/.hermes/skills
hermes skills list    # shows no skills
```

This step does not delete the skills. To restore a skill, move its folder back
into `~/.hermes/skills/`.

`hermes update` can add the bundled skills again. Do this step again after each
update.

## Step 5: Connect Hermes to the VSS MCP Server

From the installer directory, register the VSS MCP server and test it:

```bash
./install.sh mcp register vss http://<HOST_IP>:12345/mcp hermes
hermes mcp test vss
```

The `register` command adds this entry to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  vss:
    url: http://<HOST_IP>:12345/mcp
    transport: streamable-http
    enabled: true
    connect_timeout: 15
    timeout: 120
```

`hermes mcp test vss` connects to the server and lists the VSS tools. If the
test fails behind a proxy, make sure that `NO_PROXY` and `no_proxy` include
`<HOST_IP>`.

## Step 6: Try It

1. Start Hermes:

   ```bash
   hermes
   ```

2. Ask what VSS can do:

   > *"What can VSS do in this deployment?"*

   The agent calls `vss_get_deployment_info`. It reports the enabled features
   and how many videos are indexed.

3. Add footage. Hermes can use its terminal tool to upload and index a video
   for you:

   > *"Upload `/path/to/loading-dock.mp4` to VSS with the tag `loading-dock`,
   > then index it for search."*

   To add live cameras, or to upload from the VSS UI, see
   [Step 2: Add Footage](./agentic-video-analytics.md#step-2-add-footage).

4. Search:

   > *"Find a person in a dark jacket carrying a backpack at the loading dock.
   > Show me the frame for the top three hits."*

If you change the Hermes configuration during a session, enter `/reload-mcp`
to load the change.

For incident review, image search, live tracking, and more prompts, see
[Step 5: Try the Use Cases](./agentic-video-analytics.md#step-5-try-the-use-cases)
and [Tips for Good Results](./agentic-video-analytics.md#tips-for-good-results).

> **Note:** The Hermes terminal tool runs shell commands on the host for the
> agent. Keep a person in the loop. Do not expose Hermes or VSS outside a
> trusted network.

## Other Harnesses

The installer can also install OpenClaw. Make these two changes:

- In Step 3, use `--harness openclaw`.
- In Step 5, use `openclaw` as the last argument of `./install.sh mcp register`.

For the OpenClaw request timeout, see
[OpenClaw](./agentic-video-analytics.md#openclaw) in the reference page. For
other agents, see the installer's
[Get Started](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/user-guide/get-started.md)
guide.

## Troubleshooting

| Symptom | What to do |
|---|---|
| Hermes answers with a model error or a `404` error | The `model.default` value does not match the served model name. Compare it with the output of `curl -s http://127.0.0.1:8010/v1/models`. Then set the correct name with `hermes config set model.default <name>`. |
| `hermes mcp test vss` fails | Run `curl -s http://<HOST_IP>:12345/manager/health`. Behind a proxy, add `<HOST_IP>` to `NO_PROXY` and `no_proxy`. Read the server log with `docker logs vss-mcp-server`. |
| The agent does not use the VSS tools | The bundled skills are back in `~/.hermes/skills/`, for example after `hermes update`. Do [Step 4](#step-4-move-the-bundled-hermes-skills-aside) again. |
| OVMS cannot load the model, or VSS services restart | The GPU does not have enough memory. Use a smaller agent model, or keep VSS in search mode. |
| The installer reports that a port is in use | Set `HARNESS_OVMS_REST_PORT` to a different free port and run the installer again. |
| `./install.sh status` shows a stopped service | Run `./install.sh --harness hermes --model "$MODEL"` again with the same `HARNESS_OVMS_REST_PORT`. |

For VSS problems, see
[Troubleshooting](./agentic-video-analytics.md#troubleshooting) in the
reference page and the [Troubleshooting](./troubleshooting.md) guide.

## Remove

From the VSS directory:

```bash
source setup.sh --stop          # stops VSS
source setup.sh --clean-data    # also deletes the VSS data volumes (indexed videos, database) and keeps the model caches
```

From the installer directory:

```bash
./uninstall.sh --harness hermes                  # also deletes the downloaded model
./uninstall.sh --harness hermes --keep-models    # keeps the model for a later install
```

`uninstall.sh` removes these items:

- Hermes and `~/.hermes`. To keep `~/.hermes`, add `--keep-agent-data`.
- OVMS and the router.
- The installer state in `~/.agent-harness-install`.

Docker, Node.js, and the GPU driver stay installed.
