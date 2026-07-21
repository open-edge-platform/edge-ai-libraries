---
name: vss-troubleshoot
description: Diagnose a running or failing video-search-and-summarization deployment. Probes Pipeline Manager health and feature/config endpoints to detect whether the backend is up and which mode is live, then runs structured cross-service triage grounded in setup.sh, Docker Compose files, health routes, and OVMS config. Use when users say "is vss up", "what mode is running", "check vss health", "debug vss", "VSS isn't working", "OVMS won't start", "no summary appears", "search returns nothing", containers are crash-looping, healthchecks fail, or ports are conflicting in the VSS sample app.
---

# VSS Troubleshoot

Use this skill to diagnose a broken Video Search & Summarization deployment without guessing. The app is started with `source setup.sh --summary`, `--search`, `--summary --search`/`--dual`, or `--summary-and-search`/`--unified`; stopped with `source setup.sh --down`; user data reset with `source setup.sh --clean-data`.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-troubleshoot. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-troubleshoot"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

## First collect status

Run the read-only collector:

```bash
skills/vss-troubleshoot/scripts/triage.sh
```

It prints Docker Compose/container status, tails recent logs, curls key health endpoints, checks documented host ports, and reports GPU/NPU device visibility. This matters because most failures are dependency chains: `pipeline-manager` depends on storage/database/search/summary services, and UI symptoms often originate in OVMS, vLLM, EVAM, VDMS, MinIO, RabbitMQ, or Postgres.

If Docker Compose cannot resolve services, run from the app root and compare with setup's own generated config:

```bash
source setup.sh --summary config     # or --search config / --summary-and-search config
```

## Quick health & mode check

Before diving into the decision tree, confirm whether the backend is even up and
which mode is live. Set `HOST=http://${HOST_IP:-localhost}:${APP_HOST_PORT:-12345}`
and **run each command yourself**, then relay the result. If nothing is deployed,
hand off to the [`vss-deploy`](../vss-deploy/SKILL.md) skill.

```bash
# 1. Is the Pipeline Manager reachable?
curl -sf --max-time 5 "$HOST/manager/health" && echo "  ← Pipeline Manager healthy" \
  || echo "UNREACHABLE - backend down or wrong HOST_IP/APP_HOST_PORT"

# 2. Which capabilities/mode are live, and the resolved config
curl -s "$HOST/manager/app/features" | jq .   # search/summary flags
curl -s "$HOST/manager/app/config"   | jq .   # resolved system config

# 3. Subsystem probes
curl -s "$HOST/manager/metrics/status" | jq .  # telemetry collector
curl -s "$HOST/manager/audio/models"   | jq .  # whisper models (summary modes)
curl -s "$HOST/manager/pipeline/evam"  | jq .  # EVAM pipeline status
```

`app/features` returns **string flags**, not booleans -
`{"summary":"FEATURE_ON","search":"FEATURE_OFF"}` - so test against the string
(e.g. `jq -e '.search=="FEATURE_ON"'`). Use it to decide which workflow applies:
`vss-search-index` needs `search==FEATURE_ON`; `vss-summarize-video` needs
`summary==FEATURE_ON`. A backend that 404s on `/manager/health` while the model
servers (`ovms-service`, `vllm-cpu-service`, embedding server) are still loading
is usually **starting**, not broken - wait and re-probe.

## Decision tree

### 1. Containers are missing, stopped, unhealthy, or crash-looping

Check these exact services first: `nginx`, `pipeline-manager`, `postgres-service`, `minio-service`, `ovms-service`, `vllm-cpu-service`, `video-ingestion`, `audio-analyzer`, `rabbitmq-service`, `video-search`, `vdms-vector-db`, `vdms-dataprep`, `multimodal-embedding-serving`, and optional `vss-collector`.

Why: Compose `depends_on` gates many services on health. For example, summary mode needs `ovms-service` or `vllm-cpu-service`, `video-ingestion`, `rabbitmq-service`, and `audio-analyzer`; search mode needs `vdms-dataprep` and `multimodal-embedding-serving` healthy.

Actions:
- Read the first failing dependency's logs from `triage.sh`; later services often fail only because they waited for it.
- Verify required environment variables from `setup.sh`: MinIO, Postgres, RabbitMQ credentials; `VLM_MODEL_NAME`, `ENABLED_WHISPER_MODELS`, `OD_MODEL_NAME` for summary; `MULTIMODAL_EMBEDDING_MODEL` for search; `TEXT_EMBEDDING_MODEL` for unified mode.
- If containers start but app state is corrupt, only then consider `source setup.sh --clean-data` (this deletes Docker volumes listed by setup, including MinIO/Postgres/VDMS/data-prep data).

### 2. Port conflict or UI unreachable

Default host ports from `setup.sh`/Compose:
- UI/nginx `12345`; pipeline-manager `3001`; search-ms `7890`
- OVMS REST/gRPC `8300`/`9300`; vLLM `8200`; EVAM `8090`; audio `8999`
- RabbitMQ AMQP/management/MQTT `5672`/`15672`/`1883`
- MinIO API/console `4001`/`4002`; Postgres `5432`; VDMS `55555`; vdms-dataprep `6016`; embedding service `9777`; telemetry `9273`

Why: Compose publishes these host ports. If another process owns one, the container may fail to bind or the UI may talk to the wrong service.

Actions:
- Use the port section in `triage.sh` to identify listeners.
- Stop the conflicting process or override the corresponding environment variable before rerunning `source setup.sh ...`.
- Curl `http://localhost:3001/health` for `pipeline-manager` and `http://localhost:7890/health` for `video-search` when applicable.

### 3. OVMS will not start or final summary is stuck

Inspect `ovms-service` logs and `config/ovms_config/models/config.json`. The sample currently stores OVMS model entries under `config/ovms_config/models/`; setup generates storage-aware names such as `Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8`.

Why: `pipeline-manager` sends VLM/LLM requests to `http://ovms-service/v3` when `ENABLE_VLLM` is false. If OVMS is unhealthy, summary jobs can remain `Ready` or `In Progress`.

Likely fixes:
- Permission/cache issue in `ov-models` volume: run `source setup.sh --down`, then remove `ov-models` and `docker_ov-models`, then restart. This deletes cached/converted models.
- Token limit error like prompt tokens + max tokens exceed model length: lower `PM_SUMMARIZATION_MAX_COMPLETION_TOKENS` below the default `4000`, or use a model with a larger context window.
- `CL_OUT_OF_RESOURCES` or cache at 100%: split VLM/LLM across CPU/GPU, use smaller/quantized models, or tune `OVMS_CACHE_SIZE_GB` cautiously.
- NPU errors: verify the model supports NPU; otherwise set `VLM_TARGET_DEVICE=CPU` or another supported device.

### 4. vLLM backend fails

When `ENABLE_VLLM=true`, setup adds `compose.vllm.yaml`, starts `vllm-cpu-service` on host port `8200`, and points VLM/LLM APIs to `http://vllm-cpu-service:8000/v1`.

Why: In vLLM mode OVMS is not the active inference backend. Debugging OVMS logs will not explain vLLM request failures.

Actions: check `vllm-cpu-service` health at `/health`, logs for model download/context/KV-cache problems, and `VLM_MODEL_NAME`, `HUGGINGFACE_TOKEN`, `VLLM_CPU_KVCACHE_SPACE`, and `VLLM_MAX_MODEL_LEN` settings.

### 5. DLStreamer/EVAM pipeline errors or ingestion stalls

Check `video-ingestion` health (`http://localhost:8090/pipelines`) and logs, then `rabbitmq-service` and `minio-service` health/logs.

Why: summary ingestion uses DLStreamer Pipeline Server/EVAM to process video, publishes over RabbitMQ MQTT port `1883`, and stores media through MinIO. If any of those fail, no chunks reach downstream summarization.

Actions:
- Confirm `OD_MODEL_NAME` exists and setup converted object detection files under `ov_models/yoloworld/v2/...`.
- Check GPU/device visibility if `EVAM_DEVICE` or detection uses accelerators.
- Verify RabbitMQ credentials match `RABBITMQ_USER`/`RABBITMQ_PASSWORD` and MinIO credentials match `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`.

### 6. No summary appears

Follow this order: `pipeline-manager` health → Postgres health → MinIO health → `video-ingestion` → RabbitMQ → `audio-analyzer` → inference backend (`ovms-service` or `vllm-cpu-service`).

Why: `pipeline-manager` persists job state in Postgres, uses MinIO for assets, EVAM/RabbitMQ for video events, audio-analyzer for transcripts, and OVMS/vLLM for captions/final summaries.

Actions:
- Look for `Ready`/`In Progress` stuck states and correlate with OVMS/vLLM logs.
- For hallucinated or poor final summaries, try a larger `VLM_MODEL_NAME`; smaller models may have insufficient capacity.
- On OpenCV/OpenGL/Mesa errors in summary/video processing, install `libgl1-mesa-dri libgl1-mesa-dev`, remove `ov_models/` if needed, redeploy, and retest.

### 7. Search returns nothing

Check `video-search` (`http://localhost:7890/health`), `vdms-dataprep` (`/v1/dataprep/health` on port `6016`), `vdms-vector-db` (`55555`), `multimodal-embedding-serving` (`9777`), MinIO, and whether videos were actually ingested.

Why: search requires embeddings generated by `vdms-dataprep`, stored in VDMS under `VS_INDEX_NAME` (`video_frame_embeddings` for search, `video_summary_embeddings` for unified), and queried by `video-search`.

Actions:
- If `MULTIMODAL_EMBEDDING_MODEL` or `TEXT_EMBEDDING_MODEL` changed, old vectors may have incompatible dimensions. Re-ingest, or reset data with `source setup.sh --clean-data` and rerun the correct setup mode.
- Confirm `EMBEDDING_PROCESSING_MODE` is `sdk` or `api`; in `api` mode the `multimodal-embedding-serving` HTTP service is required, while `sdk` keeps embeddings in `vdms-dataprep`.
- Check accuracy settings: model dimensionality, `FRAME_INTERVAL`, `ENABLE_OBJECT_DETECTION`, and video diversity affect result quality.

## Log and data locations

The Compose files do not define application log files; use Docker stdout/stderr via `docker logs` or `triage.sh`. Important persistent locations are Docker volumes `docker_minio_data`, `docker_pg_data`, `docker_vdms-db`, `docker_audio_analyzer_data`, `docker_data-prep`, `docker_collector_signals`, plus the OVMS model repository at `config/ovms_config/models/` and object detection models under `ov_models/yoloworld/v2/`.

See `references/common-failures.md` for a compact symptom/cause/fix table.
