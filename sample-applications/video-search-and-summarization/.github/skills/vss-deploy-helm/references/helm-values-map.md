# VSS Helm values map

This map is grounded in `chart/Chart.yaml`, `chart/values.yaml`, the override files, subchart values/templates, `docker/compose.*.yaml`, and `setup.sh`.

## Compose/setup mode to Helm values

| Compose/setup concept | Helm value key(s) / override file(s) | Effect in the actual chart |
|---|---|---|
| `compose.base.yaml` common services | Always installed main chart plus `minioserver`, `postgresql`, `pipelinemanager`, `nginx` | Nginx NodePort reverse proxy, pipeline-manager, MinIO, Postgres |
| `setup.sh --summary` / `compose.summary.yaml` | `summary_override.yaml`; `rabbitmq.enabled=true`, `ovms.enabled=true`, `videoingestion.enabled=true`, `audioanalyzer.enabled=true`, `summaryui.enabled=true`, `pipelinemanager.env.SUMMARY_FEATURE=FEATURE_ON` | Summary stack with OVMS backend and singleton Summary UI |
| `ENABLE_VLLM=true` / `compose.vllm.yaml` | Add `xeon_vllm_values.yaml`; `vllm.enabled=true`, `ovms.enabled=false`, `pipelinemanager.env.USE_VLLM=CONFIG_ON` | vLLM CPU backend replaces OVMS; vLLM service is `cpu-vllm-service` on port 80/target 8000 |
| `setup.sh --search` / `compose.search.yaml` | `search_override.yaml`; `multimodalembeddingms.enabled=true`, `vdmsdataprep.enabled=true`, `vdmsvectordb.enabled=true`, `videosearch.enabled=true`, `searchui.enabled=true`, `global.vdmsIndexName=video_frame_embeddings` | Search-only stack with singleton Search UI |
| `setup.sh --summary-and-search`, `--all`, `--unified` | `unified_summary_search.yaml`; enables summary+search services and `summaryui.name=unified-ui`, `summaryui.feature.mux=SUMMARY_SEARCH`, `searchui.enabled=false`, `global.vdmsIndexName=video_summary_embeddings` | One UI for summarization and search over summary text embeddings |
| `setup.sh --dual` | `summary_override.yaml` + `search_override.yaml`; both `summaryui.enabled` and `searchui.enabled` | Two UI services; nginx routes `/summary/` and `/search/` |
| `NGINX_UI_CONFIG=dual_ui.conf` | No direct key; chart infers dual UI from `summaryui.enabled && searchui.enabled` in `templates/nginx-deployment.yaml` | Enables path-based routing to separate UIs |
| `APP_SUMMARY_FEATURE`, `APP_SEARCH_FEATURE`, `APP_FEATURE_MUX` | `summaryui.feature.summary`, `summaryui.feature.search`, `summaryui.feature.mux`; `searchui.feature.*`; `pipelinemanager.env.SUMMARY_FEATURE`, `pipelinemanager.env.SEARCH_FEATURE` | Controls UI feature switches and backend feature switches |
| `VLM_MODEL_NAME` | `global.vlmName` | Required for summary/unified; passed to OVMS init or vLLM `--model` |
| `OVMS_LLM_MODEL_NAME` / split-model mode | `global.llmName` | Optional separate OVMS LLM for final summarization; empty reuses `global.vlmName` |
| Compose model-download service | `global.modelDownload.image.repository/tag/pullPolicy`, `global.modelDownload.ovmsReleaseTag` | OVMS and video-ingestion init containers start the image as a local REST service, download/convert their model, then exit |
| `MULTIMODAL_EMBEDDING_MODEL` | `global.embeddingModelName` with search/dual | Model used by `multimodalembeddingms`, `vdmsdataprep`, `videosearch`; use multimodal model such as `CLIP/clip-vit-b-32` |
| `TEXT_EMBEDDING_MODEL` | `global.embeddingModelName` with unified mode | Use text embedding model such as `QwenText/qwen3-embedding-0.6b` |
| `VS_INDEX_NAME=video_frame_embeddings` | `global.vdmsIndexName` from `search_override.yaml` | VDMS DB collection/index for frame embeddings |
| `VS_INDEX_NAME=video_summary_embeddings` | `global.vdmsIndexName` from `unified_summary_search.yaml` | VDMS DB collection/index for summary text embeddings |
| `DATAPREP_EMBEDDING_DEVICE`, `DATAPREP_DETECTION_DEVICE`, `MME_EMBEDDING_DEVICE` | `global.devices.vdmsDataprep.embedding.device/key`, `global.devices.vdmsDataprep.detection.device/key`, `global.devices.multimodalEmbedding.device/key` | Independently schedules SDK embedding, DataPrep detection, and API embedding; each non-CPU setting needs its resource key |
| `VLM_TARGET_DEVICE`, `LLM_TARGET_DEVICE` | `global.devices.ovms.vlm.device`, `global.devices.ovms.llm.device` | OVMS target device per model: `CPU`, `GPU`, `NPU`, or `HETERO:GPU,CPU` |
| Intel device plugin resource | `global.devices.*.key` | Required when a device is GPU/NPU/HETERO; examples: `gpu.intel.com/i915`, `gpu.intel.com/xe`, `npu.intel.com/accel` |
| `VLM_COMPRESSION_WEIGHT_FORMAT`, `LLM_COMPRESSION_WEIGHT_FORMAT` | `ovms.env.VLM_WEIGHT_FORMAT`, `ovms.env.LLM_WEIGHT_FORMAT` | Overrides auto weight format; default is CPU `int8`, GPU/NPU `int4` |
| `MINIO_ROOT_USER/PASSWORD` | `global.env.MINIO_ROOT_USER`, `global.env.MINIO_ROOT_PASSWORD` | Required by MinIO and services that access buckets |
| `POSTGRES_USER/PASSWORD` | `global.env.POSTGRES_USER`, `global.env.POSTGRES_PASSWORD` | Required by pipeline-manager/PostgreSQL |
| `RABBITMQ_USER/PASSWORD` | `global.env.RABBITMQ_DEFAULT_USER`, `global.env.RABBITMQ_DEFAULT_PASS` | Required by summary video ingestion pipeline |
| `HUGGINGFACE_TOKEN` | `global.huggingfaceToken`; vLLM also accepts `vllm.env.huggingfaceToken` but global is used by the template | Token for gated/private models |
| `http_proxy`, `https_proxy`, `no_proxy` | `global.proxy.http_proxy`, `global.proxy.https_proxy`, `global.proxy.no_proxy` | Propagated into templates for VSS services |
| `PM_LLM_CONCURRENT`, `PM_VLM_CONCURRENT` | `pipelinemanager.env.LLM_CONCURRENT`, `pipelinemanager.env.VLM_CONCURRENT` | Pipeline-manager concurrency; OVMS accelerator path forces both to `1` in template |
| `PM_MULTI_FRAME_COUNT` | `pipelinemanager.env.MULTI_FRAME_COUNT` | Frames per VLM request; OVMS accelerator path renders `6` |
| `PM_SUMMARIZATION_MAX_COMPLETION_TOKENS` | `pipelinemanager.env.SUMMARIZATION_MAX_COMPLETION_TOKENS` | Final summary token cap |
| `PM_CAPTIONING_MAX_COMPLETION_TOKENS` | `pipelinemanager.env.CAPTIONING_MAX_COMPLETION_TOKENS` | Captioning token cap |
| `PM_LLM_MAX_CONTEXT_LENGTH` | `pipelinemanager.env.MAX_CONTEXT_LENGTH` | LLM context length used by pipeline-manager |
| `AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` | `pipelinemanager.env.AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` | Include full audio transcript summary by default |
| `PRODUCE_FINAL_SUMMARY` | `pipelinemanager.env.PRODUCE_FINAL_SUMMARY` | Consolidate chunk summaries into final summary by default |
| `SEARCH_DATAPREP_TIMEOUT_MS` | `pipelinemanager.env.SEARCH_DATAPREP_TIMEOUT_MS`; `videosearch.env.SEARCH_DATAPREP_TIMEOUT_MS` | Timeout for search dataprep |
| `OD_MODEL_NAME` | `videoingestion.odModelName` | Generic YOLO id accepted by the model-download Ultralytics plugin; YOLO-World names fall back to `yolov8l` |
| Compose storage | `global.usePvc`, `global.keepPvc`, `sharedClaimSize`, `*.claimSize`, `*.modelPvc.size`, `vllm.pvc.size` | Kubernetes service-specific PVC sizes and retention controls |
| `ENABLE_VSS_COLLECTOR=true` / `compose.telemetry.yaml` | `vsscollector.enabled=true`, `vsscollector.websocketUrl`, `vsscollector.signalVolume.subPath` | Deploys `vss-collector`; only useful when search or unified enables `vdmsdataprep` |

## Important actual values.yaml keys

| Key | Default | Why it matters |
|---|---:|---|
| `global.volumeHostPath` | `/mnt/vss-data` | HostPath fallback location when not using PVC; for Kubernetes deployment prefer PVCs. |
| `global.usePvc` | `false` in `values.yaml`; `true` in `user_values_override.yaml` | Controls whether chart creates/uses PVC storage. |
| `global.keepPvc` | `false` | Adds keep behavior to service PVC templates that honor it. The vLLM model-cache PVC does not currently honor this value. |
| `global.sharedPvcName` | `vss-shared-pvc` | Collector-signal PVC shared only by pipeline-manager and `vss-collector`. |
| `sharedClaimSize` | `7Gi` | Size of the collector-signal PVC; it does not store OVMS, DataPrep, or embedding models. |
| `global.huggingfaceToken` | empty | Required for gated Hugging Face models and passed to OVMS/vLLM paths. |
| `global.vlmName` | empty | VLM model used by OVMS or vLLM; required in summary/unified. |
| `global.llmName` | empty | Optional separate OVMS LLM model; empty means shared VLM model. |
| `global.embeddingModelName` | empty | Required for search/unified; drives embedding service, dataprep, video search. |
| `global.modelDownload.image.repository/tag/pullPolicy` | `intel/model-download` / `2026.2.0-ww30` / `IfNotPresent` | Image used by model-download init containers for OVMS VLM/LLM and video-ingestion OD models. |
| `global.modelDownload.ovmsReleaseTag` | `v2026.1` | OVMS export version used by the model-download OpenVINO plugin. |
| `global.vdmsIndexName` | empty | Set by search/unified override files to choose VDMS collection. |
| `global.devices.multimodalEmbedding.device/key` | `CPU` / empty | GPU scheduling for multimodal embedding service. |
| `global.devices.vdmsDataprep.embedding.device/key` | `CPU` / empty | SDK embedding device and scheduling key for DataPrep. |
| `global.devices.vdmsDataprep.detection.device/key` | `CPU` / empty | Detection device and scheduling key for DataPrep. |
| `global.devices.ovms.vlm.device/key` | `CPU` / empty | OVMS VLM device and K8s resource key. |
| `global.devices.ovms.llm.device/key` | `CPU` / empty | OVMS LLM device and K8s resource key. |
| `global.env.POSTGRES_DB` | `video_summary_db` | DB name used by Postgres/pipeline-manager. |
| `global.env.POSTGRES_USER/PASSWORD` | empty | Required credentials. |
| `global.env.MINIO_ROOT_USER/PASSWORD` | empty | Required credentials. |
| `global.env.RABBITMQ_DEFAULT_USER/PASS` | empty | Required credentials for summary modes. |
| `pipelinemanager.image.repository/tag` | `intel/pipeline-manager` / `2026.1.0-rc1` | Main backend image. |
| `pipelinemanager.env.USE_VLLM` | `CONFIG_OFF` | Must be `CONFIG_ON` when `vllm.enabled=true`; set by `xeon_vllm_values.yaml`. |
| `pipelinemanager.env.SUMMARY_FEATURE` | `FEATURE_OFF` | Turned on by summary/unified/dual overrides. |
| `pipelinemanager.env.SEARCH_FEATURE` | `FEATURE_OFF` | Turned on by search/unified/dual overrides. |
| `nginx.service.type` | `NodePort` | External UI access is via service `vss-nginx` when release name is `vss`. |
| `ovms.enabled` | `false`; summary/search/unified overrides set true except vLLM override disables it | OVMS inference backend. |
| `ovms.image.repository/tag/Gputag` | `openvino/model_server` / `2026.1` / `2026.1-gpu` | Template chooses GPU tag when OVMS device uses GPU. |
| `ovms.claimSize` | `6Gi` from parent | OVMS model PVC size. |
| `videoingestion.claimSize` | `2Gi` from parent | Object-detection model PVC size. |
| `vdmsdataprep.modelPvc.size` | chart value | DataPrep model-cache PVC size when enabled. |
| `multimodalembeddingms.modelPvc.size` | chart value | Multimodal embedding model-cache PVC size when enabled. |
| `vllm.enabled` | `false` | vLLM backend gate. |
| `vllm.image.repository/tag` | `public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo` / `v0.17.1` | vLLM CPU image. |
| `vllm.service.name/port/targetPort` | `cpu-vllm-service` / `80` / `8000` | Pipeline-manager calls `http://cpu-vllm-service:80/v1`. |
| `vllm.pvc.size` | `80Gi` | vLLM model cache size. |
| `vllm.env.vllmCpuKvCacheSpace` | `48` | vLLM CPU KV cache space. |
| `vllm.model.maxModelLen` | `32000` | vLLM max model length. |
| `vllm.model.maxNumBatchedTokens` | `2048` | vLLM batching limit. |
| `vllm.model.tensorParallelSize` | `1` | vLLM tensor parallel size. |
| `rabbitmq.enabled` | `false` | Enabled by summary/unified. Service name `rabbitmq`. |
| `audioanalyzer.enabled` | `false` | Enabled by summary/unified. Image `intel/audio-analyzer:1.3.3`. |
| `videoingestion.enabled` | `false` | Enabled by summary/unified. Image `intel/video-ingestion:2026.1.0-rc1`. |
| `multimodalembeddingms.enabled` | `false` | Enabled by search/unified. Image `intel/multimodal-embedding-serving:2026.1.0-rc1`. |
| `vdmsdataprep.enabled` | `false` | Enabled by search/unified. Image `intel/vdms-dataprep:2026.1.0-rc1`. |
| `vdmsvectordb.enabled` | `false` | Enabled by search/unified. Image `intellabs/vdms:v2.12.0`. |
| `videosearch.enabled` | `false` | Enabled by search/unified. Image `intel/video-search:2026.1.0-rc1`. |
| `summaryui.enabled`, `searchui.enabled` | `false` | UI aliases. `summaryui` becomes summary or unified UI; `searchui` is separate Search UI in search/dual. |
| `vsscollector.enabled` | `false` | Deploys telemetry collector image `docker.io/intel/vippet-collector:2026.0.0`. |

## Rendered resource names with release `vss`

| Resource | Name pattern/value |
|---|---|
| Nginx service/deployment | `vss-nginx` |
| Pipeline-manager deployment | `vss-pipelinemanager` |
| Pipeline-manager service | value of `pipelinemanager.name`: `pipelinemanager` |
| OVMS service | `ovms` |
| vLLM service | `cpu-vllm-service` |
| MinIO service | `minio-server` |
| PostgreSQL service | `postgresql` |
| RabbitMQ service | `rabbitmq` |
| Video ingestion service | `videoingestion` |
| Video search service | `videosearch` |
| VDMS dataprep service | `vdms-dataprep` |
| VDMS vector DB service | `vdms-vectordb` |
| Multimodal embedding service | `multimodal-embedding-ms` |
