# VSS modes and Docker Compose overlays

Sources: `setup.sh`, `docker/compose.base.yaml`, `docker/compose.summary.yaml`, `docker/compose.search.yaml`, `docker/compose.ui.yaml`, `docker/compose.vllm.yaml`, `docker/compose.gpu_ovms.yaml`, and `docker/compose.telemetry.yaml`.

`setup.sh` always begins active app deployments with `-f docker/compose.base.yaml`, appends mode overlays, appends `-f docker/compose.ui.yaml`, then appends backend/telemetry overlays as needed. The final command is:

```bash
docker compose $APP_COMPOSE_FILE --profile $BACKEND_PROFILE --profile $UI_PROFILE up -d
```

For config-only inspection, `up -d` becomes `config`.

| Mode | User command / aliases | Compose overlays in setup order | Profiles | Principal services | UI URL(s) |
|---|---|---|---|---|---|
| Summary | `source setup.sh --summary` | `compose.base.yaml`, `compose.summary.yaml`, `compose.ui.yaml` | `ovms`, `singleton_summary_ui` | `nginx`, `pipeline-manager`, `postgres-service`, `minio-service`, `ovms-service`, `video-ingestion`, `audio-analyzer`, `rabbitmq-service`, `vss-singleton-ui` | `http://<host-ip>:12345/` |
| Search | `source setup.sh --search` | `compose.base.yaml`, `compose.search.yaml`, `compose.ui.yaml` | `ovms`, `singleton_search_ui` | `nginx`, `pipeline-manager`, `postgres-service`, `minio-service`, `video-search`, `vdms-vector-db`, `vdms-dataprep`, `multimodal-embedding-serving`, `vss-singleton-ui` | `http://<host-ip>:12345/` |
| Dual UI | `source setup.sh --summary --search`; alias `--search --summary`; internal `--dual` | `compose.base.yaml`, `compose.summary.yaml`, `compose.search.yaml`, `compose.ui.yaml` | `ovms`, `dual_ui` | base services plus summary services plus search services plus `vss-summary-ui` and `vss-search-ui` | Summary: `http://<host-ip>:12345/summary/`; Search: `http://<host-ip>:12345/search/`; root redirects to Summary |
| Unified UI | `source setup.sh --summary-and-search`; aliases `--search-and-summary`, `--all`; internal `--unified` | `compose.base.yaml`, `compose.summary.yaml`, `compose.search.yaml`, `compose.ui.yaml` | `ovms`, `singleton_unified_ui` | base services plus summary services plus search services plus `vss-singleton-ui`; search index is `video_summary_embeddings` | `http://<host-ip>:12345/` |

## Backend and acceleration variants

| Variant | Applies to | Env toggle | Additional overlay | Profiles | Effect |
|---|---|---|---|---|---|
| OVMS CPU default | Summary, Dual UI, Unified UI | leave `ENABLE_VLLM` unset/false; default `VLM_TARGET_DEVICE=CPU`, `LLM_TARGET_DEVICE=CPU` | none beyond `compose.summary.yaml` | `ovms` | Starts `ovms-service` image `openvino/model_server:2026.1` on `${OVMS_HTTP_HOST_PORT}:80` and `${OVMS_GRPC_HOST_PORT}:81` (defaults `8300`, `9300`). |
| OVMS GPU | Summary, Dual UI, Unified UI | `VLM_TARGET_DEVICE` or `LLM_TARGET_DEVICE` contains `GPU` | `compose.gpu_ovms.yaml` | `ovms` | Overrides `ovms-service` image to `openvino/model_server:2026.1-gpu` and mounts `${DRI_MOUNT_PATH:-/dev/null}:/dev/dri`. |
| OVMS NPU | Summary, Dual UI, Unified UI | e.g. `LLM_TARGET_DEVICE=NPU` | none | `ovms` | `ovms-service` already passes `${ACCEL_MOUNT_PATH:-/dev/null}:/dev/accel/accel0`. No GPU overlay unless a target contains `GPU`. |
| vLLM CPU | Summary, Dual UI, Unified UI | `ENABLE_VLLM=true` | `compose.vllm.yaml` | `vllm` plus UI profile | Starts `vllm-cpu-service` image `${VLLM_IMAGE:-public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:v0.17.1}` on `${VLLM_HOST_PORT:-8200}:8000`; `setup.sh` sets `USE_VLLM=CONFIG_ON`, `LLM_SUMMARIZATION_API` and `VLM_ENDPOINT` to `http://vllm-cpu-service:8000/v1`. |
| Search embedding GPU | Search, Dual UI | `ENABLE_EMBEDDING_GPU=true` | none | unchanged | `setup.sh` sets `VDMS_DATAPREP_DEVICE=GPU`; `vdms-dataprep` and `multimodal-embedding-serving` mount `${DRI_MOUNT_PATH:-/dev/null}:/dev/dri`. |
| Telemetry | Search, Dual UI in docs; script can append when `ENABLE_VSS_COLLECTOR=true` | `ENABLE_VSS_COLLECTOR=true` | `compose.telemetry.yaml` | unchanged | Starts `vss-collector` on host port `9273`, streaming to `ws://pipeline-manager:3000/metrics/ws/collector`. |

## Service names and default host ports

| Service | Compose file | Default host port(s) from `setup.sh` / compose | Purpose |
|---|---|---:|---|
| `nginx` | `compose.base.yaml`, `compose.ui.yaml` | `APP_HOST_PORT=12345` -> container `80` | Reverse proxy for UI, manager, datastore, OVMS routes. |
| `pipeline-manager` | `compose.base.yaml` plus mode overlays | `PM_HOST_PORT=3001` -> container `3000` | Orchestrates summary/search pipelines; health at container `/health`. |
| `postgres-service` | `compose.base.yaml` | `POSTGRES_HOST_PORT=5432` -> container `5432` | Pipeline database. |
| `minio-service` | `compose.base.yaml` | `MINIO_API_HOST_PORT=4001` -> `80`; `MINIO_CONSOLE_HOST_PORT=4002` -> `81` | Object storage and console. |
| `ovms-service` | `compose.summary.yaml`; GPU override in `compose.gpu_ovms.yaml` | `OVMS_HTTP_HOST_PORT=8300` -> `80`; `OVMS_GRPC_HOST_PORT=9300` -> `81` | OVMS VLM/LLM inference backend. |
| `vllm-cpu-service` | `compose.vllm.yaml` | `VLLM_HOST_PORT=8200` -> `8000` | vLLM CPU inference backend. |
| `video-ingestion` | `compose.summary.yaml` | `EVAM_PIPELINE_HOST_PORT=8090` -> `8080` | Video ingestion/object detection pipeline. |
| `audio-analyzer` | `compose.summary.yaml` | `AUDIO_HOST_PORT=8999` -> `8000` | Whisper audio analysis. |
| `rabbitmq-service` | `compose.summary.yaml` | `5672`, `15672`, `1883` | AMQP, management UI, MQTT. |
| `video-search` | `compose.search.yaml` | `VS_HOST_PORT=7890` -> `8000` | Search API/microservice. |
| `vdms-vector-db` | `compose.search.yaml` | `VDMS_VDB_HOST_PORT=55555` -> `55555` | VDMS vector DB. |
| `vdms-dataprep` | `compose.search.yaml` | `VDMS_DATAPREP_HOST_PORT=6016` -> `8000` | Frame extraction, object detection, embedding prep. |
| `multimodal-embedding-serving` | `compose.search.yaml` | `EMBEDDING_SERVER_PORT=9777` -> `8000` | Embedding service; API endpoint `http://multimodal-embedding-serving:8000/embeddings`. |
| `vss-singleton-ui` | `compose.ui.yaml` | behind nginx | Single Summary, Search, or Unified UI. |
| `vss-summary-ui`, `vss-search-ui` | `compose.ui.yaml` | behind nginx | Separate Dual UI frontends. |
| `vss-collector` | `compose.telemetry.yaml` | `9273:9273` | Optional telemetry collector. |

## Index and UI behavior

- Summary mode unsets `VS_INDEX_NAME` and sets `APP_SUMMARY_FEATURE=FEATURE_ON`, `APP_SEARCH_FEATURE=FEATURE_OFF`.
- Search mode sets `VS_INDEX_NAME=video_frame_embeddings`, `APP_SUMMARY_FEATURE=FEATURE_OFF`, `APP_SEARCH_FEATURE=FEATURE_ON`.
- Dual UI sets `VS_INDEX_NAME=video_frame_embeddings` and uses `config/nginx/dual_ui.conf`.
- Unified UI sets `EMBEDDING_MODEL_NAME=${TEXT_EMBEDDING_MODEL}`, `VS_INDEX_NAME=video_summary_embeddings`, `APP_FEATURE_MUX=SUMMARY_SEARCH`, and uses `config/nginx/singleton_ui.conf`.
