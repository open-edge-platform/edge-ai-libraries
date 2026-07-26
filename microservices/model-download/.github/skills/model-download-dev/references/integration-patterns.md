<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Integration Patterns Reference

Use this reference when a developer wants to wire the Model Download service into
their own application.

## 1. Minimal application-side contract

Treat model-download as an external dependency with a narrow contract:

- `GET /api/v1/health` → service readiness
- `POST /api/v1/models/download?download_path=<subdir>` → start work
- `GET /api/v1/jobs/{job_id}` → poll status
- `GET /api/v1/models/results` → inspect completed jobs

Avoid importing `src.core.*` or plugin code into the caller application. That couples the app to service internals and bypasses plugin activation, env setup, and job management.

## 2. Recommended caller workflow

### Runtime on-demand download

Use this when the application may need different models over time:

1. App receives a request that needs a model.
2. App checks whether the model already exists in the shared model path or its own metadata store.
3. If missing, app submits a model-download job.
4. App polls job status or stores the job ID for a background worker.
5. After completion, app loads the model from the reported path.

This is a good fit when startup time matters more than first-use latency.

### Deployment-time provisioning

Use this when the model list is known ahead of time:

1. Deployment or CI job starts model-download.
2. Provisioning step submits all required model jobs.
3. Deployment waits for completion.
4. Inference service starts only after models are present.

This is the simplest pattern for stable production environments.

### Admin-triggered downloads

Use this when operators decide which models to stage:

1. Internal admin API or UI calls model-download.
2. App stores job IDs and exposes progress to operators.
3. Inference services react only after a model is marked ready.

This works well when model lifecycle is controlled centrally.

## 3. Storage and volume wiring

Model download writes under the mounted host path exposed as `/opt/models` inside the container.

For Compose/Kubernetes:

- mount the same persistent volume into model-download and the serving application
- keep the path stable across restarts
- use subdirectories per workflow (`download_path`) to avoid collisions

Typical pattern:

- model-download writes to `/opt/models/<download_path>/...`
- inference service mounts the same volume read-only if possible

## 4. Plugin and environment selection

Enable only the plugins your integration needs:

- `huggingface` for raw HF downloads
- `huggingface,openvino` when the workflow converts to OVMS-ready IR
- `ollama` for Ollama model pulls
- `ultralytics` for YOLO downloads
- `geti` for Intel Geti
- `pipeline-zoo-models` for DL Streamer model bundles
- `hls` for healthcare demo assets

Important consequence: if the app submits a request for a hub whose plugin was not activated at startup, the job fails with a plugin-availability error. Application-side code should surface that clearly.

## 5. Polling strategy

Application code should expect:

- `queued`
- `downloading`
- `converting`
- `completed`
- `failed`

Recommended behavior:

- poll every 2–5 seconds for interactive workflows
- poll less often or use a background worker for long-running provisioning jobs
- enforce a timeout in the caller so jobs do not hang forever from the app's perspective

## 6. Failure handling

Application integrations should handle at least:

- service unavailable (`/health` failing)
- plugin not activated
- missing credentials (`HF_TOKEN`, Geti vars)
- job timeout
- job status `failed` with error details

Prefer explicit failures over silent fallback. If the model is mandatory, fail startup or fail the user request clearly.

## 7. Output paths to use

For standard downloads, use the job result's `details.download_path` or the plugin-specific returned path.

For OpenVINO conversions, use the conversion result path reported by the job result. Do not reconstruct paths by guesswork if the API already returned them.

## 8. What to produce for the user

When helping a developer integrate model-download, prefer producing:

- a concrete Compose/Helm change
- a small client wrapper for submit + poll
- env/plugin activation instructions
- a clear startup or provisioning sequence

Be specific about where the model files end up and which service consumes them next.
