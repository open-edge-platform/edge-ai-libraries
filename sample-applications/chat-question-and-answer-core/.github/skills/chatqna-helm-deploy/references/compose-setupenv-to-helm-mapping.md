<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Compose and setup_env.sh Translation

Use this mapping when a user provides Docker Compose or `setup_env.sh`
configuration and asks for Kubernetes/Helm deployment.

| Compose/setup_env input | Helm values key | Notes |
| --- | --- | --- |
| `BACKEND=openvino` | `global.MODEL_RUNTIME=openvino` | Use `values-openvino.yaml` base file |
| `BACKEND=ollama` | `global.MODEL_RUNTIME=ollama` | Use `values-ollama.yaml` base file |
| `DEVICE=gpu` | `gpu.enabled=true` | OpenVINO only |
| `DEVICE=cpu` | `gpu.enabled=false` | Default |
| `/dev/dri` usage + render group | `gpu.devices=/dev/dri`, `gpu.key=<cluster-gpu-label>` | `RENDER_DEVICE_GID` is not needed in chart values |
| `REGISTRY` | `image.registry` | Keep trailing slash style used by chart |
| `BACKEND_TAG` (OpenVINO CPU) | `image.tags.openvinoCPU` | |
| `BACKEND_TAG` (OpenVINO GPU) | `image.tags.openvinoGPU` | |
| `BACKEND_TAG` (Ollama) | `image.tags.ollama` | |
| `MODEL_CACHE_PATH` volume | `global.model_cache_path` | PVC mount path inside container |
| `HUGGINGFACEHUB_API_TOKEN` / `HF_ACCESS_TOKEN` | `global.huggingface.apiToken` | OpenVINO path |
| `http_proxy` | `global.http_proxy` | |
| `https_proxy` | `global.https_proxy` | |
| `no_proxy` | `global.no_proxy` | chart appends `,127.0.0.1` in deployment |
| `APP_BACKEND_URL=/v1/chatqna` | `subchart.chatqna-ui.global.app_backend_url` | Default already `/v1/chatqna` |
| `UI_TAG` | `subchart.chatqna-ui.image.tag` | Only if overriding UI image tag |
| `HOST_IP` published bind | `global.ui_nodeport` + node host IP discovery | Kubernetes exposes NodePort instead of host bind |
| `MODEL_CONFIG_PATH` bind mount | `configmap.enabled=true` + model keys in values | Translate file content into values fields, not host path mount |

When translating, always emit an explicit override file:

```yaml
# values-override.yaml
global:
  MODEL_RUNTIME: openvino
  huggingface:
    apiToken: "${HUGGINGFACEHUB_API_TOKEN}"
  EMBEDDING_MODEL: BAAI/bge-small-en-v1.5
  LLM_MODEL: microsoft/Phi-3.5-mini-instruct
  RERANKER_MODEL: BAAI/bge-reranker-base
gpu:
  enabled: false
image:
  registry: intel/
  tags:
    openvinoCPU: core_1.3.3
```