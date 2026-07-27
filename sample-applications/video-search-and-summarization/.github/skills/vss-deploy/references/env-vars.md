# VSS environment variables

Sources: `setup.sh`, `docker/compose.*.yaml`, `README.md`, `docs/user-guide/get-started.md`, `docs/user-guide/get-started/system-requirements.md`, and `docs/user-guide/build-from-source.md`. Deployment reads shell environment; no top-level `.env` or `.env.example` is present. The checked-in env files are `ui/react/.env` for Vite placeholder names and `mcp/.env.example` for the separate MCP server.

## Required before starting containers

`setup.sh` validates these unless the command is `--stop`, `--clean-data`, or config-only.

| Variable | Required when | What it controls |
|---|---|---|
| `MINIO_ROOT_USER` | all deployment modes | MinIO username; passed to `minio-service`, `pipeline-manager`, `video-ingestion`, `audio-analyzer`, `multimodal-dataprep`. |
| `MINIO_ROOT_PASSWORD` | all deployment modes | MinIO password/secret key. |
| `POSTGRES_USER` | all deployment modes | PostgreSQL user for `postgres-service` and `pipeline-manager`. |
| `POSTGRES_PASSWORD` | all deployment modes | PostgreSQL password. |
| `RABBITMQ_USER` | all deployment modes | RabbitMQ user for `rabbitmq-service`, `pipeline-manager`, `video-ingestion`. |
| `RABBITMQ_PASSWORD` | all deployment modes | RabbitMQ password. |
| `VLM_MODEL_NAME` | Summary, Dual UI, Unified UI | VLM model source for captioning/summarization. In vLLM mode it is also the final-summary model. |
| `ENABLED_WHISPER_MODELS` | Summary, Dual UI, Unified UI | Comma-separated Whisper models for `audio-analyzer` via `ENABLED_WHISPER_MODELS`. |
| `OD_MODEL_NAME` | Summary, Dual UI, Unified UI | YOLO object detection model converted by `video-ingestion/resources/scripts/converter.py` into `ov_models/yoloworld/v2`. |
| `MULTIMODAL_EMBEDDING_MODEL` | Search, Dual UI | Model for video frame embeddings; assigned to `EMBEDDING_MODEL_NAME`. |
| `TEXT_EMBEDDING_MODEL` | Unified UI | Text embedding model for summary-text search; assigned to `EMBEDDING_MODEL_NAME`. |
| `OVMS_LLM_MODEL_NAME` | only if `ENABLE_OVMS_LLM_SUMMARY=true` or `ENABLE_OVMS_LLM_SUMMARY_GPU=true` for modes with summary | Dedicated OVMS final-summary LLM model. Otherwise OVMS falls back to `VLM_MODEL_NAME`. |

## Proxy and image registry

| Variable | Default / behavior | What it controls |
|---|---|---|
| `http_proxy`, `https_proxy`, `no_proxy` | no default | Passed into nearly every service. Compose appends internal names such as `pipeline-manager`, `minio-service`, `ovms-service`, `multimodal-dataprep`, `vector-retriever`, `multimodal-embedding-serving`, and `localhost` to `no_proxy`. |
| `REGISTRY_URL` | empty | `setup.sh` trims/adds a trailing slash, combines with `PROJECT_NAME`, and exports `REGISTRY`. |
| `PROJECT_NAME` | empty | Also normalized with trailing slash before composing `${REGISTRY_URL}${PROJECT_NAME}`. |
| `REGISTRY` | derived | Prefix for images such as `${REGISTRY:-}pipeline-manager:${TAG:-latest}`. |
| `TAG` | `latest` in `setup.sh`; docs example `2026.1.0-rc1` | Image tag for app images. |

## Common ports and hosts set by `setup.sh`

| Variable | Default | Service / use |
|---|---:|---|
| `APP_HOST_PORT` | `12345` | nginx external UI/proxy port. |
| `HOST_IP` | `ip route get 1 | awk '{print $7}'` | Printed in UI URLs and used in UI `no_proxy`. |
| `PM_HOST_PORT`, `PM_HOST` | `3001`, `pipeline-manager` | Pipeline Manager host port/name. |
| `OVMS_HTTP_HOST_PORT`, `OVMS_GRPC_HOST_PORT`, `OVMS_HOST` | `8300`, `9300`, `ovms-service` | OVMS REST/gRPC exposure and internal host. |
| `VLLM_HOST_PORT`, `VLLM_HOST`, `VLLM_ENDPOINT` | `8200`, `vllm-cpu-service`, `http://vllm-cpu-service:8000/v1` | vLLM service and OpenAI-compatible endpoint. |
| `EVAM_PIPELINE_HOST_PORT`, `EVAM_HOST` | `8090`, `video-ingestion` | Video ingestion API. |
| `AUDIO_HOST_PORT`, `AUDIO_HOST`, `AUDIO_ENDPOINT` | `8999`, `audio-analyzer`, `http://audio-analyzer:8000` | Audio Analyzer. |
| `RABBITMQ_AMQP_HOST_PORT`, `RABBITMQ_MANAGEMENT_UI_HOST_PORT`, `RABBITMQ_MQTT_HOST_PORT`, `RABBITMQ_HOST` | `5672`, `15672`, `1883`, `rabbitmq-service` | RabbitMQ. |
| `POSTGRES_HOST_PORT`, `POSTGRES_DB`, `POSTGRES_HOST` | `5432`, `video_summary_db`, `postgres-service` | PostgreSQL. |
| `MINIO_API_HOST_PORT`, `MINIO_CONSOLE_HOST_PORT`, `MINIO_HOST` | `4001`, `4002`, `minio-service` | MinIO API/console. |
| `VDMS_VDB_HOST_PORT`, `VDMS_VDB_HOST` | `55555`, `vdms-vector-db` | VDMS vector DB. |
| `VDMS_DATAPREP_HOST_PORT`, `VDMS_DATAPREP_HOST`, `VDMS_DATAPREP_ENDPOINT` | `6016`, `multimodal-dataprep`, `http://multimodal-dataprep:8000` | Search data preparation service (`multimodal-dataprep`; env var names retain the `VDMS_DATAPREP_` prefix). |
| `VECTOR_RETRIEVER_HOST_PORT` | `6008` | Vector Retriever service; `video-search` delegates all similarity search to it at `http://vector-retriever:8000/query`. Backend flavor (`vector-retriever-vdms`/`vector-retriever-milvus`) is baked at build time from `VECTORDB_BACKEND`. |
| `VS_HOST_PORT`, `VS_HOST`, `VS_ENDPOINT` | `7890`, `video-search`, `http://video-search:8000` | Video Search service. |
| `EMBEDDING_SERVER_PORT`, `MULTIMODAL_EMBEDDING_HOST`, `MULTIMODAL_EMBEDDING_ENDPOINT` | `9777`, `multimodal-embedding-serving`, `http://multimodal-embedding-serving:8000/embeddings` | Embedding service. |

## Summarization backend and model controls

| Variable | Default | What it controls |
|---|---|---|
| `ENABLE_VLLM` | `false` | When `true`, `setup.sh` uses `compose.vllm.yaml`, profile `vllm`, sets `USE_VLLM=CONFIG_ON`, and ignores a separate OVMS LLM model. |
| `USE_VLLM` | `CONFIG_OFF` unless vLLM enabled | Passed to `pipeline-manager`. |
| `VLM_TARGET_DEVICE` | `CPU` | OVMS VLM target; supports CPU/GPU/NPU/HETERO forms per docs. If contains `GPU`, setup adds `compose.gpu_ovms.yaml`. |
| `LLM_TARGET_DEVICE` | `CPU` | OVMS final-summary LLM target; if contains `GPU`, setup adds `compose.gpu_ovms.yaml`. |
| `VLM_COMPRESSION_WEIGHT_FORMAT` | auto: `int8` for CPU, `int4` for GPU/NPU | OVMS export weight format for VLM unless overridden. |
| `LLM_COMPRESSION_WEIGHT_FORMAT` | auto: `int8` for CPU, `int4` for GPU/NPU | OVMS export weight format for LLM unless overridden. |
| `OVMS_CACHE_SIZE_GB` | dynamic | Overrides computed OVMS KV cache size; must be a positive integer. |
| `OVMS_ALLOWED_MEDIA_DOMAINS` | `${MINIO_HOST},localhost` | Passed to `ovms-service --allowed_media_domains`. |
| `PM_SUMMARIZATION_MAX_COMPLETION_TOKENS` | `4000` | Pipeline manager final-summary max completion tokens. |
| `PM_CAPTIONING_MAX_COMPLETION_TOKENS` | `1024`, changed to `256` in defaulted vLLM mode | Captioning token limit. |
| `PM_LLM_MAX_CONTEXT_LENGTH` | `90000` | Pipeline manager LLM context length. |
| `PM_LLM_CONCURRENT` | `2`, but setup may reduce for vLLM/GPU | LLM request concurrency. |
| `PM_VLM_CONCURRENT` | `4`, but setup may reduce for vLLM/GPU | VLM request concurrency. |
| `PM_MULTI_FRAME_COUNT` | `12`, may reduce to `6` for non-CPU OVMS VLM | Multi-frame captioning count. |
| `PM_AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` | `true` in compose | Enables full-transcript summary injection by default. |
| `PM_PRODUCE_FINAL_SUMMARY` | `true` | Whether Pipeline Manager produces final summary. |
| `GATED_MODEL`, `HUGGINGFACE_TOKEN` | unset | If `GATED_MODEL=true`, setup logs into Hugging Face during OVMS export; vLLM passes `HUGGING_FACE_HUB_TOKEN=${HUGGINGFACE_TOKEN:-}`. |

## vLLM-specific controls

`compose.vllm.yaml` starts `vllm-cpu-service` and passes these variables.

| Variable | Default | What it controls |
|---|---|---|
| `VLLM_IMAGE` | `public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:v0.17.1` | vLLM CPU image. |
| `VLLM_CPU_KVCACHE_SPACE` | `48` | CPU KV cache space. |
| `VLLM_RPC_TIMEOUT` | `100000` | RPC timeout. |
| `VLLM_ALLOW_LONG_MAX_MODEL_LEN` | `1` | Allows long max model length. |
| `VLLM_ENGINE_ITERATION_TIMEOUT_S` | `120` | Engine iteration timeout. |
| `VLLM_CPU_NUM_OF_RESERVED_CPU` | `0` | Reserved CPU count. |
| `VLLM_LOGGING_LEVEL` | `INFO` | vLLM logging level. |
| `VLLM_DTYPE` | `bfloat16` | `--dtype`. |
| `VLLM_BLOCK_SIZE` | `128` | `--block-size`. |
| `VLLM_MAX_NUM_BATCHED_TOKENS` | `2048` | `--max-num-batched-tokens`. |
| `VLLM_MAX_NUM_SEQS` | `256` | `--max-num-seqs`. |
| `VLLM_MAX_MODEL_LEN` | `32000` | `--max_model_len`. |
| `VLLM_TENSOR_PARALLEL_SIZE` | `1` | `--tensor-parallel-size`. |

## Search and embedding controls

| Variable | Default | What it controls |
|---|---|---|
| `VS_INDEX_NAME` | set by mode | `video_frame_embeddings` for Search/Dual; `video_summary_embeddings` for Unified. |
| `VS_WATCHER_DIR` | `$PWD/data` | Host directory mounted into `video-search` at `/tmp/watcher-dir`; setup creates it. |
| `VS_DELETE_PROCESSED_FILES` | `false` | Whether `video-search` deletes processed files. |
| `VS_INITIAL_DUMP` | `false` | Initial watcher dump. |
| `VS_WATCH_DIRECTORY_RECURSIVE` | `false` | Recursive directory watch. |
| `VS_DEBOUNCE_TIME` | `10` | Watch debounce time. |
| `VECTORDB_BACKEND` | `vdms` | Selects the vector DB backend (`vdms` or `milvus`) for both `multimodal-dataprep` writes and the `vector-retriever` flavor used at query time. |
| `VDB_METRIC_TYPE`, `VDB_INDEX_TYPE` | `IP`, `FLAT` | Distance metric and index type; must match between `multimodal-dataprep` and `vector-retriever`. |
| `ENABLE_EMBEDDING_GPU` | unset/false | If `true`, setup sets `DATAPREP_EMBEDDING_DEVICE=GPU`. |
| `DATAPREP_EMBEDDING_DEVICE` | `CPU` | Device for in-process embedding in `multimodal-dataprep`. |
| `DATAPREP_DETECTION_DEVICE` | `CPU` | Device for YOLOX object detection in `multimodal-dataprep`. |
| `MME_EMBEDDING_DEVICE` | `CPU` | Device for `multimodal-embedding-serving` (used by `vector-retriever` to embed queries). |
| `SDK_USE_OPENVINO` | `true` | OpenVINO use for in-process `multimodal-dataprep` embedding; forced true by GPU/NPU configuration. |
| `EMBEDDING_DEVICE` | `$MME_EMBEDDING_DEVICE` | Device passed to `multimodal-embedding-serving`. |
| `EMBEDDING_USE_OV` | `$SDK_USE_OPENVINO` | OpenVINO use for embedding server. |
| `OV_MODELS_DIR`, `EMBEDDING_OV_MODELS_DIR` | `/app/ov_models` | OpenVINO model cache mount paths. |
| `OV_PERFORMANCE_MODE` | `THROUGHPUT` | OpenVINO performance mode. |
| `FRAME_INTERVAL` | `15` | Frame sampling interval. |
| `ENABLE_OBJECT_DETECTION` | `true` | Enable object detection in dataprep. |
| `DETECTION_CONFIDENCE` | `0.85` | Detection threshold. |
| `ROI_CONSOLIDATION_ENABLED` | `false` | Enable ROI consolidation. |
| `ROI_CONSOLIDATION_IOU_THRESHOLD` | `0.2` | ROI grouping threshold. |
| `ROI_CONSOLIDATION_CLASS_AWARE` | `false` | Merge only same class when true. |
| `ROI_CONSOLIDATION_CONTEXT_SCALE` | `0.2` | Expand merged ROI. |
| `VDMS_DATAPREP_LOG_LEVEL` | `INFO` | Data prep log level. |
| `EMBEDDING_BATCH_SIZE` | `32` | Embedding batch size. |
| `MAX_PARALLEL_WORKERS` | empty | Optional data prep worker limit. |
| `AGGREGATION_ENABLED` | `true` | Frame-to-video aggregation. |
| `AGGREGATION_SEGMENT_DURATION` | `8` | Segment duration. |
| `AGGREGATION_MIN_GAP` | `0` | Merge gap. |
| `AGGREGATION_MAX_RESULTS` | `20` | Aggregated result limit. |
| `AGGREGATION_INITIAL_K` | `1000` | Initial vector search K. |
| `AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS` | `0` | Context seek offset. |

## UI and telemetry controls

| Variable | Default | What it controls |
|---|---|---|
| `NGINX_UI_CONFIG` | set by mode | `config/nginx/singleton_ui.conf` for single UI modes; `config/nginx/dual_ui.conf` for Dual UI. |
| `UI_PM_ENDPOINT` | `/manager` | UI backend endpoint when using nginx. |
| `UI_ASSETS_ENDPOINT` | `/datastore` | UI asset/datastore endpoint when using nginx. |
| `CONFIG_SOCKET_APPEND` | unset; UI defaults `CONFIG_OFF` | Set to `CONFIG_ON` if nginx is not used, per setup comment. |
| `APP_FEATURE_MUX` | set by mode | `ATOMIC` for singleton summary/search; `SUMMARY_SEARCH` for Unified. |
| `APP_SUMMARY_FEATURE` | set by mode | UI summary feature flag. |
| `APP_SEARCH_FEATURE` | set by mode | UI search feature flag. |
| `ENABLE_VSS_COLLECTOR` | `false` | Adds `compose.telemetry.yaml` when `true`. |
| `OTLP_TRACE_URL` | empty | Pipeline Manager telemetry trace URL. |
| `DATAPREP_TELEMETRY_URL` | `http://multimodal-dataprep:8000/v1/dataprep/telemetry?limit=1` | Pipeline Manager data prep telemetry URL. |
| `TELEMETRY_SIGNAL_DIR` | `/app/.collector-signals` | Shared collector signal directory. |
