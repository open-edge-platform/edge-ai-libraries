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
  Nous Research doesn't publish a static checksum for it, so this installer
  refuses to run it unverified: set `HERMES_INSTALL_SHA256` (once you've
  reviewed a known-good copy) or `HERMES_ALLOW_UNVERIFIED_INSTALL=1` before
  installing the `hermes` agent, or it will fail with guidance.
- "deepagents-code" installs LangChain's official `dcode` CLI via its own
  installer (`https://langch.in/dcode`, no static checksum published either
  — same fail-closed stance: set `DCODE_INSTALL_SHA256` or
  `HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL=1`). It's wired to OVMS by writing
  a `[models.providers.openai]` block into `~/.deepagents/config.toml`
  (dcode's own "Compatible APIs" mechanism) inside `BEGIN`/`END` markers, so
  a re-run replaces only that block and leaves any other provider config
  alone — but a config.toml a user already hand-edited to use a *different*
  `openai` provider block (outside those markers) would end up with two.
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
    For gated Hugging Face models, export `HF_TOKEN`. This is the one exporter
    that can pull from sources other than Hugging Face — set
    `HARNESS_MODEL_HUB` (default `openvino`, i.e. today's HF+convert
    behavior) to any hub the microservice itself supports: `huggingface`
    (raw download, no conversion), `ollama`, `ultralytics`, `geti`,
    `pipeline-zoo-models`, `omz`, `remote-url`, or `hls`. Only the
    `openvino` hub produces an artifact OVMS can actually serve as a
    chat-completion endpoint (it's still HF-sourced under the hood — "pull
    from Hugging Face and convert to OpenVINO IR", not a separate source);
    the other hubs download models in their own native formats for their
    own runtimes (Ollama's server, vision pipelines, etc.), so this
    installer downloads them without attempting to register anything with
    OVMS. These are tracked separately (`<models-dir>/unregistered-downloads.json`)
    so they still show up under `./install.sh models list` (labeled "not
    served by OVMS") and can be removed with `./install.sh models remove
    <name>` even though `config.json` never gets an entry for them.
    `HARNESS_MODEL_TYPE` (default `llm`), `HARNESS_MODEL_DOWNLOAD_REVISION`,
    `HARNESS_MODEL_PRECISION` (default `int8`), `HARNESS_MODEL_DEVICE`
    (default `CPU`), `HARNESS_MODEL_CONFIG_JSON`, and `HARNESS_MODEL_PLUGINS`
    mirror `get_model.sh`'s own `--type`/`--revision`/`--precision`/`--device`/
    `--config-json`/`--plugins` flags — see
    microservices/model-download/docs/user-guide/get-started.md in
    edge-ai-libraries for the full parameter reference per hub.
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
  `base_path`) whenever they produce one; `model-download` with a non-`openvino`
  `HARNESS_MODEL_HUB` deliberately doesn't (see above).
- The **Inference Router** (IR) always sits in front of OVMS and is what
  agents are actually wired to (`harness_llm_endpoint`) — not optional. This
  installer builds it locally from a pinned commit SHA of
  `microservices/inference-router` in `open-edge-platform/edge-ai-libraries`
  (`HARNESS_IR_SOURCE_REPO`/`HARNESS_IR_SOURCE_REF`; a full 40-character SHA
  is required unless `HARNESS_ALLOW_UNVERIFIED_IR_SOURCE=1`). IR also
  publishes a prebuilt `intel/inference-router` image, which this installer
  does not use so that the exact reviewed commit is what runs. IR limits
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
- Switching from a locally-managed OVMS+IR install to
  `HARNESS_LLM_ROUTER_ENDPOINT` (or back) does not stop/remove the
  previously-managed containers — re-running `ensure_inference_backend`
  with the router endpoint set only updates the `ovms-managed` marker and
  returns; it never calls `remove_openvino_model_server`/
  `remove_inference_router`. A prior OVMS and/or IR container is left
  running, orphaned, until an explicit `./uninstall.sh` (which still
  checks the marker correctly) or a manual `docker rm -f`. This limitation
  pre-dates IR (OVMS alone already had it); IR's addition just means a
  second orphaned container in the same scenario.
- Docker, Node.js/npm, and Python (venv + PyYAML) are installed/verified by
  `./startup.sh`, which `./install.sh` now runs automatically as its first
  step (see [Get Started](get-started.md)) -- there's still only one
  script to run. `test/full-flow-test.sh` and `test/smoke-test.sh` also
  call it explicitly up front (so an early prerequisite failure is
  reported before the long per-agent install loop, not buried inside it);
  running either test script directly still assumes a host that can reach
  the package repositories/URLs `./startup.sh` itself downloads from.
