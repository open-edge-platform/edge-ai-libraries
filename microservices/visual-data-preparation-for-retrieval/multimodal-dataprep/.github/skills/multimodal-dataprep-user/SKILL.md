---
name: multimodal-dataprep-user
description: >
  Deploy and consume Intel Multimodal DataPrep from prebuilt images or a
  repository checkout. Use for configuring VDMS or Milvus vector storage,
  MinIO or local media storage, checking service dependencies, and ingesting,
  listing, streaming, or deleting videos and images; submitting batch jobs;
  adding text-summary embeddings; and inspecting telemetry. This service
  prepares retrieval data but does not execute semantic search. Use
  multimodal-dataprep-dev for source changes, tests, or image builds.
---

# Multimodal DataPrep — User

Run deployment and API commands when authorized, then report their actual
output. API base: `http://localhost:6007/v1/dataprep`.

Multimodal DataPrep creates embeddings and metadata for retrieval. It does not
offer a vector-query/search endpoint.

## Load project resources as needed

Paths are relative to
`microservices/visual-data-preparation-for-retrieval/multimodal-dataprep/`.

| Resource | Read when |
|---|---|
| `docs/user-guide/api-reference.md` and `docs/user-guide/api-docs/openapi.yaml` | Constructing media, image, batch, summary, download, delete, or telemetry requests |
| `docs/user-guide/get-started.md` | Configuring devices, detection, batching, duplicate policy, or environment variables |
| `docs/user-guide/pluggable-backends.md` | Selecting VDMS/Milvus or MinIO/local and diagnosing backend behavior |
| `docs/user-guide/telemetry-metrics.md` | Reading ingestion telemetry or configuring Metrics Manager |
| `setup.sh` and `docker/compose*.yaml` | Deploying a stack |

Example scenarios:

| Example | Purpose |
|---|---|
| [manufacturing-inspection-archive.md](./example-prompts/manufacturing-inspection-archive.md) | Ingest object-aware production media |
| [object-aware-video-catalog.md](./example-prompts/object-aware-video-catalog.md) | Build retrieval-ready frame and crop records |
| [edge-video-preprocessing-box.md](./example-prompts/edge-video-preprocessing-box.md) | Batch-ingest a mounted edge directory |

## 1. Select deployment backends

| Vector backend | Media storage | Compose files |
|---|---|---|
| VDMS (default) | MinIO (default) | `docker/compose.yaml` |
| Milvus | MinIO | `docker/compose-milvus.yaml` |
| VDMS | Local filesystem | `docker/compose.yaml` then `docker/compose.storage-local.yaml` |

Use `MM_DATAPREP_VECTORDB_BACKEND` (`vdms` or `milvus`) and
`MM_DATAPREP_STORAGE_BACKEND` (`minio` or `local`) for custom deployments.
Keep the service, retriever, and collection naming consistent.

## 2. Obtain deployment files

In a repository checkout, run from the microservice root.

Without a checkout, fetch the setup script and the compose file(s) for the
selected backend:

```bash
RAW='https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/visual-data-preparation-for-retrieval/multimodal-dataprep'
mkdir -p multimodal-dataprep/docker
cd multimodal-dataprep
curl -fsSLo setup.sh "$RAW/setup.sh"
curl -fsSLo docker/compose.yaml "$RAW/docker/compose.yaml"
```

Also fetch `docker/compose-milvus.yaml` or
`docker/compose.storage-local.yaml` when selected.

## 3. Start the prebuilt stack

Never commit credentials. For the default VDMS + MinIO deployment:

```bash
export MINIO_ROOT_USER='<user>'
export MINIO_ROOT_PASSWORD='<strong-password>'
export EMBEDDING_MODEL_NAME='CLIP/clip-vit-b-32'
export REGISTRY_URL='docker.io/intel'
export TAG='latest'

source ./setup.sh --nosetup
docker compose -f docker/compose.yaml up -d --no-build
```

For Milvus, replace the compose file with `docker/compose-milvus.yaml`. For
local media storage, layer the storage override after `docker/compose.yaml`.

`setup.sh` must be sourced because it exports Compose variables. With no
argument it only exports defaults; it does not start containers.

## 4. Verify readiness and dependencies

Wait for the in-process embedding client:

```bash
until curl -fsS http://localhost:6007/v1/dataprep/health \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("status") == "ok" and d.get("embedding_client_status") == "preloaded" else 1)'
do
  sleep 10
done
```

The current fields are `embedding_client_status`, `model_name`,
`embedding_device`, `use_openvino`, `detection_model`, and
`detection_device`.

Check dependencies separately:

```bash
docker compose -f docker/compose.yaml ps
curl -fsS http://localhost:6010/minio/health/live
timeout 2 bash -c '</dev/tcp/localhost/6020'   # default VDMS
```

For Milvus, use the Milvus compose file and probe `localhost:19530`. DataPrep's
health response is not a substitute for checking every dependency.

## 5. Ingest supported media

Upload a video:

```bash
curl -fsS -X POST \
  'http://localhost:6007/v1/dataprep/media/upload?frame_interval=15&enable_object_detection=true&tags=camera-1' \
  -F 'file=@/path/to/video.mp4;type=video/mp4'
```

Upload an image through the same multipart endpoint:

```bash
curl -fsS -X POST \
  'http://localhost:6007/v1/dataprep/media/upload?enable_object_detection=true&tags=inspection' \
  -F 'file=@/path/to/image.jpg;type=image/jpeg'
```

For inline base64 or remote HTTP(S) images, use `POST /media/ingest`. For media
already in the selected storage backend, use `POST /media/process`.

Asynchronous workflows:

- `POST /media/upload/batch`
- `POST /media/process/batch`
- `POST /media/ingest/batch`
- `POST /media/ingest-dir` (also `store_copy: false` to embed files in place
  without copying them into storage — such media is still listed by `GET /media`
  with `"stored": false` and streamable via `GET /media/download` — and
  `metadata` / `meta/<basename>.json` sidecars for user-defined filterable
  fields)
- `GET /media/jobs/{job_id}`
- `DELETE /media/jobs/{job_id}` to request cancellation

Clean-up: `DELETE /media/{bucket_name}/{video_id}` removes one item,
`DELETE /media/{bucket_name}` clears a whole bucket (storage + embeddings).

Read the API reference for exact request schemas and configured batch limits.

## 6. Add a text summary

Use the `video_id` returned by media listing/job results and its bucket:

```bash
curl -fsS -X POST 'http://localhost:6007/v1/dataprep/summary' \
  -H 'Content-Type: application/json' \
  -d '{
    "bucket_name": "video-summary",
    "video_id": "dp_video_1730000000",
    "video_summary": "forklift narrowly misses pedestrian",
    "video_start_time": 33,
    "video_end_time": 41,
    "tags": ["safety"]
  }'
```

The selected model must support text embeddings.

## 7. Manage and observe

```bash
curl -fsS 'http://localhost:6007/v1/dataprep/media'
curl -fsS 'http://localhost:6007/v1/dataprep/telemetry?limit=5'
curl -L 'http://localhost:6007/v1/dataprep/media/download?video_id=dp_video_1730000000' \
  -o media.bin
```

`GET /media/download` supports HTTP Range requests for seeking.

Deletion removes the entire media directory and its matching vectors:

```bash
curl -fsS -X DELETE \
  'http://localhost:6007/v1/dataprep/media/video-summary/dp_video_1730000000'
```

There is no current single-file `video_name` deletion option. Deletion is
destructive, so obtain explicit confirmation before running it.

Set `MM_DATAPREP_METRICS_MANAGER_URL` to publish completed-pipeline
`dataprep_embeddings_per_second` values asynchronously. `/telemetry` remains
the direct source for detailed per-ingestion stage timings.

## Troubleshooting

| Symptom | Action |
|---|---|
| API is unavailable | Inspect `docker compose ... ps` and DataPrep logs; initial model/YOLOX downloads can take time |
| `embedding_client_status` is `not_loaded` or `error` | Verify `EMBEDDING_MODEL_NAME`, model compatibility, device access, and startup logs |
| Dimension mismatch | Use a fresh collection compatible with the selected model; never wipe an existing collection without confirmation |
| Milvus connection failure behind a proxy | Use `docker/compose-milvus.yaml` and ensure Milvus/etcd/in-cluster addresses bypass proxies |
| MinIO authentication failure | Verify the effective `MM_DATAPREP_MINIO_*` values and reuse the same credentials across restarts |
| Large upload returns 413 | Identify the rejecting proxy/server from headers and logs; stage media in storage and call `/media/process` |
| Duplicate upload returns 409 | `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS=false` is enforcing content-hash deduplication |
| Object crops are absent | Check whether YOLOX downloaded and whether detection is enabled on a supported device |
| Local directory ingest is rejected | Keep `dir_path` beneath `MM_DATAPREP_INGEST_DATA_ROOT`; traversal outside that root is intentionally blocked |
