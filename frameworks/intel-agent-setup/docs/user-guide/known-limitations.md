# Known Limitations

- OpenClaw's own provider/config CLI surface isn't reproduced here. Its npm
  package is confirmed real and installable, but its runtime configuration
  commands aren't modeled, so onboarding reports the endpoint to configure
  (the OVMS endpoint) rather than fabricating flags. OpenClaw is installed
  via `npm install -g openclaw` rather than its own `curl | bash` installer
  intentionally — that installer exists for people who don't want to manage
  Node.js themselves, but Agent Setup deliberately manages Node.js (via
  nvm) itself, consistently across all three agents; using OpenClaw's own
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
- The Docker-based sandbox manager (`scripts/lib/sandbox.sh`) publishes
  ports directly by default. `HARNESS_GATEWAY_ENABLED=1` routes sandbox
  traffic through a single shared reverse-proxy container instead (see
  [Sandbox management](sandbox-management.md)) — still just one plain
  container, with no systemd-managed daemon or cross-process
  port-collision avoidance.
- Intel's Core Ultra iGPU/Arc lineup has no fixed appliance concept, so
  there's no dual-node pairing/reboot-resume receipt handling.
- Model export (`optimum-cli export openvino`) is CPU/host-bound and can be
  slow for large models.
- `mcp register` has Hermes's config shape built in; other agents need
  `HARNESS_MCP_REGISTER_CMD` set to a real registration script.
- `HARNESS_OVMS_EXPORTER=model-download` (an alternative to the default
  `export-model-py`) runs edge-ai-libraries' Model Download microservice as
  a one-shot ephemeral container (`get_model.sh`) instead, then registers the
  resulting graph the same way `export_model.py`'s output is registered (a
  `model_config_list` entry — confirmed by comparing both exporters' output
  side by side; OVMS itself auto-detects the `graph.pbtxt` sitting in
  `base_path`). Newer and less battle-tested than the default path. Its
  Docker image also defaults to the floating `latest` tag unless
  `HARNESS_MODEL_DOWNLOAD_IMAGE_TAG` is pinned, and like Hermes/Docker, its
  `get_model.sh` download requires `HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256`
  (or `HARNESS_ALLOW_UNVERIFIED_MODEL_DOWNLOAD_SCRIPT=1`) since no
  independently-reviewed checksum is pinned yet.
