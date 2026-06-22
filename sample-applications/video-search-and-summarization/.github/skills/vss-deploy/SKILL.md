---
name: vss-deploy
description: Guides developers to deploy, switch, inspect, and tear down the Video Search & Summarization sample application using its real setup.sh modes, Docker Compose overlays, profiles, services, ports, and environment variables. Use when users say "spin up VSS", "run summary mode", "switch to search", "use GPU/vLLM", "which compose files do I need", "bring VSS down", or ask deployment questions for sample-applications/video-search-and-summarization.
---

# VSS Deploy

Use this skill only for `sample-applications/video-search-and-summarization`. Ground every answer in the repository files, especially `setup.sh` and `docker/compose.*.yaml`; do not invent flags, services, ports, or variables.

## Quick deployment flow

1. Work from the app root:

   ```bash
   cd sample-applications/video-search-and-summarization
   ```

2. Export credentials in the current shell. `setup.sh` reads shell env directly; there is no top-level deployment `.env` or `.env.example`.

   ```bash
   export MINIO_ROOT_USER=<user> MINIO_ROOT_PASSWORD=<password>
   export POSTGRES_USER=<user> POSTGRES_PASSWORD=<password>
   export RABBITMQ_USER=<user> RABBITMQ_PASSWORD=<password>
   ```

3. Export model variables for the chosen mode:

   ```bash
   # Required for --summary, --dual, --unified
   export VLM_MODEL_NAME=<vlm-model>
   export ENABLED_WHISPER_MODELS=<comma-separated-whisper-models>
   export OD_MODEL_NAME=<yolo-model>

   # Required for --search and --dual
   export MULTIMODAL_EMBEDDING_MODEL=<multimodal-embedding-model>

   # Required for --unified / --summary-and-search
   export TEXT_EMBEDDING_MODEL=<text-embedding-model>
   ```

4. Stop before switching modes:

   ```bash
   source setup.sh --stop   # alias: source setup.sh --down
   ```

5. Start one mode. Always use `source setup.sh ...`, not `./setup.sh`, because the script uses `return` and exports environment while building the Compose command.

   ```bash
   source setup.sh --summary              # Summary UI: http://<host-ip>:12345/
   source setup.sh --search               # Search UI: http://<host-ip>:12345/
   source setup.sh --summary --search     # Dual UI: /summary/ and /search/
   source setup.sh --summary-and-search   # Unified UI: http://<host-ip>:12345/
   ```

## Mode aliases and config-only inspection

`setup.sh` normalizes `--summary --search` and `--search --summary` to `--dual`; `--summary-and-search`, `--search-and-summary`, and `--all` to `--unified`; `config` to `--dual config`; `config --summary` to `--summary config`; and `--down` to `--stop`.

Use config mode to verify resolved Compose without starting containers:

```bash
source setup.sh --summary config
source setup.sh --search config
source setup.sh --summary --search config
source setup.sh --summary-and-search config
```

## Choose OVMS, vLLM, CPU, or GPU

Default summarization backend is OVMS (`ovms-service`, profile `ovms`) from `docker/compose.summary.yaml`.

```bash
source setup.sh --summary                                               # OVMS CPU default
VLM_TARGET_DEVICE=GPU source setup.sh --summary                         # OVMS GPU for VLM
LLM_TARGET_DEVICE=GPU OVMS_LLM_MODEL_NAME=<llm> source setup.sh --summary # OVMS GPU for LLM
ENABLE_VLLM=true source setup.sh --summary                              # vLLM CPU backend
ENABLE_EMBEDDING_GPU=true source setup.sh --search                       # GPU for search embeddings
```

For vLLM, `setup.sh` adds `docker/compose.vllm.yaml`, starts `vllm-cpu-service` (profile `vllm`) on host port `8200`, and uses `VLM_MODEL_NAME` for both captioning and final summary. For OVMS GPU, `setup.sh` adds `docker/compose.gpu_ovms.yaml` and switches `ovms-service` to `openvino/model_server:2026.1-gpu`.

## Bring down or reset

```bash
source setup.sh --stop       # stop/remove containers across all VSS overlays/profiles
source setup.sh --down       # alias for --stop
source setup.sh --clean-data # also removes Docker volumes and .ov_venv
```

`--clean-data` removes `docker_minio_data`, `docker_pg_data`, `docker_vdms-db`, `docker_audio_analyzer_data`, `docker_data-prep`, and `docker_collector_signals`.

## References

- Exact mode-to-overlay/profile/service/URL mapping: [references/modes-and-overlays.md](references/modes-and-overlays.md).
- Required and optional environment variables: [references/env-vars.md](references/env-vars.md).
