<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Download Models at Startup

The service can schedule model downloads and conversions automatically from a user-mounted YAML file. Startup downloads use the same validation, enabled plugins, job manager, and model volume as requests submitted to `POST /models/download` `STARTUP_MODELS_CONFIG` selects the configuration by its path inside the service container; the Compose and Helm workflows below set that variable for their mounted configuration.

Copy and update the shipped example:

```bash
cp startup-models.example.yaml startup-models.yaml
```

## Configuration Schema

| Field | Required | Description |
|-------|----------|-------------|
| `download_path` | Yes | Default destination for models that do not define their own `download_path`. It must resolve under the service's model directory (`/opt/models` in the container). |
| `parallel_downloads` | No | Enables plugin-supported parallel file downloads. Default: `false`. |
| `models` | Yes | One to 100 model entries. |
| `models[].name` | Yes | Model identifier. |
| `models[].hub` | Yes | `huggingface`, `ollama`, `ultralytics`, `pipeline-zoo-models`, `openvino`, `geti`, or `hls`. The corresponding plugin must be enabled. |
| `models[].type` | No | `llm`, `vlm`, `embeddings`, `rerank`, `image_generation`, `text2speech`, `speech2text`, `vision`, `3d-pose`, `rppg`, or `ai-ecg`. |
| `models[].is_ovms` | No | Whether to create an OpenVINO conversion job. Default: `false`. |
| `models[].revision` | No | Model revision, version, or tag. |
| `models[].config` | No | The same plugin or conversion configuration accepted by `ModelRequest`, such as `precision`, `device`, `cache_size`, or `quantize`. |
| `models[].download_path` | No | Destination override for this model. It must resolve under the service's model directory. |

For example:

```yaml
download_path: preloaded
parallel_downloads: false
models:
  - name: <Model-Name>
    hub: huggingface
    type: embeddings
  - name: <Model-Name>
    hub: ultralytics
    type: vision
    download_path: vision
```

The file must be a regular UTF-8 `.yaml`, `.yml` file no larger than 1 MiB.
Unknown fields, an empty model list, and malformed or unsupported values make the whole file
invalid. If `STARTUP_MODELS_CONFIG` is unset, startup downloads are disabled. If it names a
missing, unreadable, or invalid file, the service logs an actionable
`startup_models_config_unusable` error, schedules no models from that file, and continues serving.
For a valid file, a model that cannot be submitted logs `startup_model_submission_failed` without
preventing later entries from being scheduled.

Do not store credentials in this file. Supply credentials through the existing environment
variables, including `HUGGINGFACEHUB_API_TOKEN` for gated Hugging Face models and
`GETI_HOST`, `GETI_TOKEN`, and `GETI_WORKSPACE_ID` for Geti software.

## Docker Compose

Set `STARTUP_MODELS_CONFIG_HOST_PATH` to the absolute host path of the configuration. Docker
Compose mounts it read-only and sets the container's `STARTUP_MODELS_CONFIG` automatically:

```bash
export STARTUP_MODELS_CONFIG_HOST_PATH="$PWD/startup-models.yaml"
source scripts/run_service.sh up \
  --plugins huggingface,ultralytics \
  --model-path "$PWD/models"
```

The host file must exist before Compose starts. Unset `STARTUP_MODELS_CONFIG_HOST_PATH` to disable
the mount and startup downloads.

## Readiness and Restarts

Configuration is validated and its jobs are queued during application startup, but model transfer
and conversion run asynchronously. Consequently, a successful `/health` response means the API is
ready; it does not mean the configured models are complete.

Startup-created jobs appear in the existing endpoints:

```bash
curl "http://<host-ip>:8200/api/v1/jobs"
curl "http://<host-ip>:8200/api/v1/jobs/<job_id>"
curl "http://<host-ip>:8200/api/v1/models/jobs?model_name=<model-name>"
```

Job records are in memory and are not restored after a service restart. Downloaded artifacts remain
on the mounted model volume. Restarting with the configuration schedules new jobs; existing
artifact reuse, caching, or overwrite behavior remains specific to each plugin and its
configuration (for example, OpenVINO's `config.overwrite_models`).

## Helm Chart

Startup model loading is disabled by default in Helm. To enable ConfigMap-backed configuration,
set:

```yaml
modeldownload:
  startupConfig:
    enabled: true
    config:
      download_path: preloaded
      parallel_downloads: false
      models:
        - name: <Model-Name>
          hub: huggingface
          type: embeddings
        - name: <Model-Name>
          hub: ultralytics
          type: vision
          download_path: vision
```

Enable every plugin referenced by the model entries in
`modeldownload.env.ENABLED_PLUGINS`. The chart sets `STARTUP_MODELS_CONFIG` to the mounted
ConfigMap path. Keep tokens out of `startupConfig.config`; provide credentials through the
existing environment values or your deployment's secret-injection mechanism.

Model work continues after the readiness probe succeeds. Use the existing jobs endpoints or
`kubectl logs` to monitor jobs. The PVC preserves downloaded artifacts across pod restarts,
but in-memory job records are not restored and configured entries are scheduled again.
