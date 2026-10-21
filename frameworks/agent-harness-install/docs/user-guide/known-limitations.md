<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Known Limitations

- OpenClaw onboarding registers the inference endpoint as a custom model
  provider (`openclaw config set models.providers.ovms ...`, OpenClaw's own
  documented `models.providers` mechanism — see
  docs/gateway/config-tools/custom-providers.md in
  github.com/openclaw/openclaw), selects it with `openclaw models set`, and
  smoke-tests it with `openclaw infer model run` — the same shape as the
  dcode/Hermes onboarding paths. This requires OpenClaw's local Gateway
  daemon to be stopped (its own `config set` refuses to write otherwise);
  on a fresh install there is no daemon running yet, so this only matters
  when re-running `./install.sh onboard` after `openclaw gateway run`/
  `openclaw onboard --install-daemon` has started one — stop it first, or
  configure the provider manually with the command the warning prints.
  OpenClaw is installed via `npm install -g openclaw` rather than its own
  `curl | bash` installer intentionally — that installer exists for people
  who don't want to manage Node.js themselves, but agent-harness-install
  deliberately manages Node.js (via nvm) itself, consistently across all
  three agents; using OpenClaw's own
  installer too would mean two separate, possibly-conflicting Node.js
  runtimes. `npm install -g` is OpenClaw's own documented path for
  environments that already manage Node.js.
- "Hermes" installs via its own official installer (curl | bash), not npm —
  this installer downloads and runs it unattended (`--skip-setup --non-interactive`).
  Nous Research doesn't publish a checksum for it, and the
  `hermes-agent.nousresearch.com` URL always serves the latest script, so
  this installer instead fetches `scripts/install.sh` from a pinned
  `NousResearch/hermes-agent` commit (the `v0.22.2` tag), verifies its
  SHA-256, and passes the same commit via `--commit`. No flags are needed.
  To use a different installer, set `HERMES_INSTALL_URL` together with
  `HERMES_INSTALL_SHA256` (or `HERMES_ALLOW_UNVERIFIED_INSTALL=1`, not
  recommended); `HERMES_INSTALL_SHA256` alone overrides the built-in digest.
- "deepagents-code" installs LangChain's official `dcode` CLI via its own
  installer. As with Hermes, this installer fetches `libs/code/scripts/install.sh`
  from a pinned `langchain-ai/deepagents` commit (the `deepagents-code==0.1.86`
  tag, byte-identical to what `https://langch.in/dcode` served for that
  release), verifies its SHA-256 and installs that exact dcode version.
  Override with `DEEPAGENTS_CODE_VERSION`, or use a different installer via
  `DCODE_INSTALL_URL` plus `DCODE_INSTALL_SHA256` (or
  `HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL=1`). It's wired to OVMS by writing
  a `[models.providers.openai]` block into `~/.deepagents/config.toml`
  (dcode's own "Compatible APIs" mechanism) inside `BEGIN`/`END` markers, so
  a re-run replaces only that block and leaves any other provider config
  alone — but a config.toml a user already hand-edited to use a *different*
  `openai` provider block (outside those markers) would end up with two.
  The managed block reads its API key from `HARNESS_DCODE_API_KEY`, which
  only the installer's own smoke test sets; running `dcode` yourself needs
  `export HARNESS_DCODE_API_KEY=not-needed` (any non-empty value; the local
  endpoint ignores it) or it fails with `MissingCredentialsError`. Behind a
  corporate proxy, dcode's local LangGraph health check is also sent through
  the proxy and rejected (`Server did not become healthy within 60s (last
  status: 403)`), because many HTTP clients ignore `localhost` and CIDR
  entries in `no_proxy` for `127.0.0.1`. Run it without the proxy variables:
  `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY dcode ...`.
- Intel's Core Ultra iGPU/Arc lineup has no fixed appliance concept, so
  there's no dual-node pairing/reboot-resume receipt handling.
- Model export (`optimum-cli export openvino`) is CPU/host-bound and can be
  slow for large models.
- `mcp register` has Hermes's config shape and OpenClaw's `mcp set` command
  built in; other agents need `HARNESS_MCP_REGISTER_CMD` set to a real
  registration script.
- `HARNESS_OVMS_EXPORTER` defaults to `docker-pull`, which runs OVMS's own
  "-py" Docker image (bundles `optimum-cli`) in `--pull` mode to download,
  convert, and quantize a `--model` entirely via Docker — no host Python
  venv, no separate GitHub-fetched script. Three alternatives remain for
  hosts that need them:
  - `export-model-py` — the original host-venv-based exporter: fetches and
    pins OVMS's `export_model.py`/`requirements.txt` from GitHub, runs them
    in a Python venv. Kept for hosts that can't/won't run the conversion
    step inside Docker.
  - `model-download` — runs edge-ai-libraries' Model Download microservice
    as a one-shot ephemeral container (`get_model.sh`) instead. Newer and
    less battle-tested than the other two. Its Docker image also defaults
    to the floating `latest` tag unless `HARNESS_MODEL_DOWNLOAD_IMAGE_TAG`
    is pinned, and its `get_model.sh` is fetched from a pinned commit and
    verified against a built-in SHA-256 (a different
    `HARNESS_MODEL_DOWNLOAD_SCRIPT_REF` needs its own
    `HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256`, or
    `HARNESS_ALLOW_UNVERIFIED_MODEL_DOWNLOAD_SCRIPT=1`). `get_model.sh`
    converts with its own OVMS release (default `v2025.4.1`), which may
    differ from the OVMS image served here; set
    `HARNESS_MODEL_DOWNLOAD_OVMS_RELEASE_TAG` to pass `--ovms-release-tag`.
    For gated Hugging Face models, export `HF_TOKEN`. It is also what
    `--model-hub` selects: any hub other than the default `openvino` chooses
    this exporter automatically (unless `HARNESS_OVMS_EXPORTER` is set to
    something else, which is then rejected as a conflict). The hubs are the
    microservice's own: `openvino` (Hugging Face + conversion, the default),
    `huggingface` (raw download), `ollama`, `remote-url`, `ultralytics`,
    `geti`, `pipeline-zoo-models`, `omz` and `hls`. A download is registered
    with OVMS, and wired to the Inference Router, only when it contains a
    `graph.pbtxt` — the `openvino` hub always produces one, a pre-converted
    `huggingface` repo or a `remote-url` tarball may, and the other hubs
    never can (Ollama-format models are not loadable by OVMS yet; Ultralytics,
    Geti, the zoos and HLS are vision/other-runtime models, not something an
    agent can use). Whatever is not served is still downloaded and tracked
    (`<models-dir>/unregistered-downloads.json`), so it shows up under
    `./install.sh models list` (labeled "not served by OVMS") and can be
    removed with `./install.sh models remove <name>` even though
    `config.json` never gets an entry for it. Which hubs can be served is
    decided in one place, `model_hub_unserved_reason` in
    `scripts/lib/openvino.sh`, so Ollama can be enabled there once OVMS
    supports it. `--model` is validated per hub before anything is
    installed (for example `org/name` for Hugging Face, `name[:tag]` for
    Ollama, a URL in `--model-config` for `remote-url`, `GETI_*` for
    Geti). `--model-type` (default `llm` for `openvino`/`huggingface`),
    `--model-revision`, `--model-precision` (default `int8`),
    `--model-device` (default `CPU`), `--model-config` and
    `HARNESS_MODEL_PLUGINS` mirror `get_model.sh`'s own
    `--type`/`--revision`/`--precision`/`--device`/`--config-json`/`--plugins`
    flags (the matching `HARNESS_MODEL_*` environment variables work too) —
    see microservices/model-download/docs/user-guide/get-started.md in
    edge-ai-libraries for the full parameter reference per hub. Other
    exporters ignore the options that don't apply to them and say so
    (`--model-precision` also applies to the default `docker-pull`
    exporter; `--model-revision` also to `hf-snapshot`).
  - `hf-snapshot` — a plain `huggingface_hub.snapshot_download` in a host
    Python venv, no `optimum-cli` conversion step at all. For HF repos
    already published as ready-to-serve OpenVINO IR + an OVMS MediaPipe
    `graph.pbtxt`. Set `HARNESS_HF_MODEL_REVISION` to pin an exact
    commit/tag; fails fast if the downloaded repo has no `graph.pbtxt` (it
    only supports already-converted repos, not raw/un-exported ones). As of
    this writing, no verified Intel/OpenVINO-owned public HF repo of this
    exact shape is known to exist (checked the OpenVINO org's own
    published repos — they ship plain OpenVINO IR, no `graph.pbtxt`); only
    unverified third-party community uploads do. Bring your own
    already-verified repo via `HARNESS_HF_MODEL` rather than relying on a
    public example for this exporter specifically.

  All four register the resulting model into `config.json` the same way (a
  `model_config_list` entry — confirmed by comparing exporters' output side
  by side; OVMS itself auto-detects the `graph.pbtxt` sitting in
  `base_path`) whenever they produce one. `model-download` registers a
  download only if it contains a `graph.pbtxt` (see above).
- The **Inference Router** (IR) always sits in front of the model backend and
  is what agents are actually wired to (`harness_llm_endpoint`) — not
  optional, including when `HARNESS_LLM_ROUTER_ENDPOINT` points at an
  external endpoint (IR's provider is then that endpoint instead of OVMS;
  `HARNESS_LLM_ROUTER_API_KEY` is sent as a bearer token, and a
  `localhost`/`127.0.0.1` endpoint is unreachable from inside the IR
  container, so use the host's LAN address or `host.docker.internal`). This
  installer pulls the published `intel/inference-router` image
  (`HARNESS_IR_IMAGE`, default tag `2026.2.0`). That image is a release
  build and may not match the pinned source commit below exactly; set
  `HARNESS_IR_BUILD_FROM_SOURCE=1` to build it locally from a pinned commit
  SHA of `microservices/inference-router` in `open-edge-platform/edge-ai-libraries`
  instead (`HARNESS_IR_SOURCE_REPO`/`HARNESS_IR_SOURCE_REF`; a full
  40-character SHA is required unless `HARNESS_ALLOW_UNVERIFIED_IR_SOURCE=1`).
  IR limits
  concurrent requests (3 by default) and answers `429` above that. IR's `providers[].type` is passed
  straight through to LiteLLM as a `type/model` prefix with no allowlist
  enforced by IR's own config loader; `HARNESS_IR_PROVIDER_TYPE` defaults
  to `hosted_vllm` (the type IR's own examples use for a self-hosted
  OpenAI-compatible backend). `openai` does not work here: LiteLLM's
  `openai` provider requires an API key, so every request to the keyless
  OVMS fails with "Missing credentials".
- IR's routing policy defaults to `Balanced` (single provider, no extra
  GPU-resident classifier model) — confirmed against IR's own
  `RouterOrchestrator`/`DecisionEngine.from_config`/bundled `policy.yaml`
  that `Balanced` only instantiates its own strategies
  (`Planning`/`ContextLengthQuality`), never the classifier-backed
  `IntelligentRouting` strategy. `HARNESS_IR_ROUTING_POLICY=Intelligent` is
  **not actually usable with this installer today**: that policy needs an
  OpenVINO classifier model mounted at `/models/ov-classifier` (IR's own
  `IR_OV_MODEL` env var/volume), which this installer never prepares,
  downloads, or mounts — selecting `Intelligent` as-is will very likely
  make IR fail at startup. Treat this override as a placeholder for future
  work, not a supported option, until the classifier model is wired up.
  Shares the GPU with OVMS (confirmed acceptable); `HARNESS_IR_PORT`
  defaults to `8010` to avoid colliding with OVMS's own `8000`.
- OVMS and the Inference Router are joined to a dedicated Docker network
  (`HARNESS_BACKEND_NETWORK`, default `agent-harness-install-backend`) so
  IR can reach OVMS by container name on OVMS's internal port — IR runs in
  its own container and cannot reach OVMS via the install host's
  loopback/advertised address or a host-published port that's bound
  loopback-only by default (`resolve_bind_host`). Both containers are
  recreated (not just restarted) on every `./install.sh` run when they
  already exist, so a container from an older version of this installer
  (before this network existed) picks it up automatically, along with any
  other changed GPU/proxy/port configuration, on the next run.
- Published ports of OVMS (`8000`) and the Inference Router (`8010`) bind to
  `127.0.0.1` by default. `HARNESS_ADVERTISED_HOST=<ip>` binds them to that
  address and prints it in endpoint URLs; `HARNESS_BIND_HOST=0.0.0.0` binds
  all interfaces but does not change the printed URLs, so set
  `HARNESS_ADVERTISED_HOST` as well (or use the machine's real address).
  Neither service authenticates inbound requests, and Docker-published ports
  bypass `ufw`; restrict access with the `DOCKER-USER` iptables chain or bind
  to a specific interface. Only the advertised host is persisted
  (`~/.agent-harness-install/advertised-host`); `HARNESS_BIND_HOST` must be
  set again on every run. Binding a specific address requires it to exist on
  the host: an address that is not assigned yet (for example a DHCP lease
  that arrives after Docker starts at boot) stops the container from
  starting.
- Switching from a locally-managed OVMS install to
  `HARNESS_LLM_ROUTER_ENDPOINT` does not stop/remove the previously-managed
  OVMS container: re-running `ensure_inference_backend` with the router
  endpoint set only updates the `ovms-managed` marker and restarts the
  Inference Router against the new provider; it never calls
  `remove_openvino_model_server`. The Router is always removed by
  `./uninstall.sh`, but OVMS is skipped once the marker says the last install
  routed externally, so that earlier OVMS container (and its image) must be
  removed manually: `docker rm -f agent-harness-install-ovms`, or re-run
  `./install.sh` without the router endpoint and then `./uninstall.sh`.
- `HARNESS_OVMS_IMAGE` (the serving image, default `2026.4.1-gpu`) and
  `HARNESS_OVMS_EXPORT_IMAGE` (the "-py" image the default `docker-pull`
  exporter converts models with, default `2026.1-py`) are pinned separately
  because OVMS has not published a newer "-py" tag. The export is therefore
  produced by an older OVMS than the one that serves it; this pairing is
  only exercised by `test/full-flow-test.sh` on real hardware.
- There is no default model: a full install needs `--model` (or
  `HARNESS_HF_MODEL`), prompted for on a terminal and an error otherwise,
  unless a model is already exported from an earlier run. With
  `HARNESS_LLM_ROUTER_ENDPOINT`, `--model`/`HARNESS_LLM_MODEL` names the model
  the external endpoint serves.
- Docker, Node.js/npm, and Python (venv + PyYAML) are installed/verified by
  `./startup.sh`, which `./install.sh` now runs automatically as its first
  step (see [Get Started](get-started.md)) -- there's still only one
  script to run. `test/full-flow-test.sh` and `test/smoke-test.sh` also
  call it explicitly up front (so an early prerequisite failure is
  reported before the long per-agent install loop, not buried inside it);
  running either test script directly still assumes a host that can reach
  the package repositories/URLs `./startup.sh` itself downloads from.
