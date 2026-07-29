---
name: vdms-dataprep-user
description: >
  Deploy and consume the VDMS DataPrep video-ingestion stack (dataprep + VDMS
  vector DB + MinIO) — bring it up with setup.sh + docker compose (from a repo
  clone, or by fetching those same files from GitHub when no clone exists)
  using the prebuilt intel/vdms-dataprep image, then upload/ingest MP4s, add
  text-summary embeddings, and list/download/delete videos through the REST API
  at http://localhost:6007/v1/dataprep. Ingestion only: it does not answer
  search queries. Not for modifying the service's source — that is
  vdms-dataprep-dev.
---

# VDMS DataPrep — User

Run the ingestion stack and feed it videos. **Run commands yourself** and
relay output. API base: `http://localhost:6007/v1/dataprep`. Scope note: this
service **ingests** (video → embeddings → VDMS); querying/searching those
embeddings is a different component (e.g. a video-search app reading the same
VDMS).

## When to Use

- Bring up the dataprep + VDMS + MinIO stack and confirm health
- Upload/ingest MP4s (direct upload or from MinIO) with embeddings
- Add text-summary embeddings for a video time range
- List, download, or delete ingested videos
- Diagnose 413 uploads, dimension mismatches, or MinIO credential errors

## Example Prompts

Sample Problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [manufacturing-inspection-archive.md](./example-prompts/manufacturing-inspection-archive.md) | Archive production-line clips with frame + object-crop metadata |
| [object-aware-video-catalog.md](./example-prompts/object-aware-video-catalog.md) | Catalog clips by detected objects with confidence thresholds and tags |
| [edge-video-preprocessing-box.md](./example-prompts/edge-video-preprocessing-box.md) | Preprocess camera MP4s near the source (MinIO + VDMS) before central sync |

## Docs & deploy files — with or without a clone

All paths below are relative to
`microservices/visual-data-preparation-for-retrieval/vdms/` in the
[edge-ai-libraries](https://github.com/open-edge-platform/edge-ai-libraries)
repo. **No clone?** Fetch any of them from GitHub raw:

```
https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/visual-data-preparation-for-retrieval/vdms/<path>
```

Load these existing docs only when needed:

| Resource | Load when… |
|---|---|
| `docs/user-guide/api-reference.md` + `docs/user-guide/api-docs/openapi.yaml` | building requests beyond a simple upload (minio ingest, summaries, delete/download, telemetry) |
| `docs/user-guide/get-started.md` | env-var tables, detection/ROI tuning, more curl examples, troubleshooting |
| `docs/user-guide/Overview.md` + `docs/user-guide/overview-architecture.md` | how the pipeline works (frames → detection → embeddings → VDMS) |
| `setup.sh`, `docker/compose.yaml` | the deploy artifacts used below |

## 1. Context routing — repo clone or standalone?

```bash
[ -f setup.sh ] && grep -q 'name = "vdms-dataprep"' pyproject.toml 2>/dev/null \
  && echo REPO || echo STANDALONE
```

- **REPO** → run Step 2 from the microservice root.
- **STANDALONE** → fetch the two deploy files, then the exact same Step 2:
  ```bash
  RAW=https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/visual-data-preparation-for-retrieval/vdms
  mkdir -p vdms-dataprep/docker && cd vdms-dataprep
  curl -fsSL $RAW/setup.sh -o setup.sh
  curl -fsSL $RAW/docker/compose.yaml -o docker/compose.yaml
  ```
- Already running (`curl -sf http://localhost:6007/v1/dataprep/health`) →
  Step 3.

## 2. Bring-up (identical in both contexts)

Credentials are never committed — export strong values in-shell and retain
them securely if clients must keep using the same credentials across
restarts. `setup.sh` must be **sourced**; `--nosetup` exports env without
touching containers, `REGISTRY_URL=intel` selects the prebuilt image, and
`--no-build` prevents a source build (building is the `-dev` skill's job).
Run in the background — image pulls plus embedding/YOLOX model downloads take
a while:

```bash
bash -c 'export MINIO_ROOT_USER="<existing-or-new-user>" MINIO_ROOT_PASSWORD="<existing-or-new-strong-password>" \
  EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32" REGISTRY_URL=intel TAG=latest \
  && source ./setup.sh --nosetup \
  && docker compose -f docker/compose.yaml up -d --no-build'
```

`setup.sh` fixes `INDEX_NAME=video-rag`, which compose passes as
`DB_COLLECTION`; `VS_INDEX_NAME` is unused. Then wait for API readiness:

```bash
until curl -sf http://localhost:6007/v1/dataprep/health \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("embedding_mode") != "sdk" or d.get("sdk_client_status") == "preloaded" else 1)'
do
  sleep 10
done
```

Health shows `embedding_mode` (`sdk` default) and, in SDK mode, require
`sdk_client_status=preloaded`. This endpoint does not probe MinIO or VDMS, so
also check the Compose services and MinIO separately:

```bash
docker compose -f docker/compose.yaml ps
curl -sf http://localhost:6010/minio/health/live
timeout 2 bash -c '</dev/tcp/localhost/6020'
```

Teardown later with
`docker compose -f docker/compose.yaml down`.

## 3. Ingest a video

Upload an MP4 — it is stored in MinIO and embedded in one step:

```bash
curl -s -X POST 'http://localhost:6007/v1/dataprep/videos/upload?frame_interval=15' \
  -F 'file=@/path/to/video.mp4;type=video/mp4'
```

`201` → `{"status":"success","message":"..."}`. First ingestion also
downloads the YOLOX detector (needs network; without it, object detection is
silently skipped).

Other flows — ingest from MinIO (`POST /videos/minio`), text summaries
(`POST /summary`), RTSP, detection tuning:
`docs/user-guide/api-reference.md`.

The upload response contains only status/message. Obtain the generated
`dp_video_<timestamp>` identifier from `GET /videos`, then attach a summary
using that exact bucket and `video_id`:

```bash
curl -s -X POST 'http://localhost:6007/v1/dataprep/summary' \
  -H 'Content-Type: application/json' \
  -d '{
    "bucket_name": "video-summary",
    "video_id": "dp_video_1730000000",
    "video_summary": "forklift narrowly misses pedestrian",
    "video_start_time": 33,
    "video_end_time": 41
  }'
```

## 4. Manage & observe

```bash
curl -s 'http://localhost:6007/v1/dataprep/videos'              # list (default bucket video-summary)
curl -s 'http://localhost:6007/v1/dataprep/telemetry?limit=5'   # ingestion timings
```

Download: `GET /videos/download?video_id=…`. Delete:
`DELETE /videos/{bucket_name}/{video_id}[?video_name=…]` — without
`video_name` it deletes the **whole video directory**; destructive, **confirm
with the user first**. MinIO console: `http://localhost:6011`.

## Troubleshooting

| Symptom | Likely cause → action |
|---|---|
| Health never responds on 6007 | still pulling/downloading models → `docker compose -f docker/compose.yaml logs -f vdms-dataprep` |
| `setup.sh` errors about MINIO_ROOT_USER/PASSWORD | export them before sourcing |
| Startup error "model name must be provided" | `EMBEDDING_MODEL_NAME` unset → export and redeploy |
| Ingestion fails with "Dimensions mismatch" | collection was built with a different embedding model → override `INDEX_NAME` after `source setup.sh --nosetup`, or wipe (destructive — confirm), then re-ingest |
| 413 on upload | the source endpoint has no implemented size check despite its docs; identify the rejecting proxy/server from headers and logs. For large files, avoid buffering through this endpoint: stage in MinIO and use `POST /videos/minio` |
| Detected objects missing from results | YOLOX download failed on first run (no network) → restart with network access |
| MinIO auth errors after re-deploy | inspect the effective container `MINIO_ROOT_*` environment and ensure clients use the same current credentials |
| MinIO bind-mount errors at start | `setup.sh` overwrites `MINIO_MOUNT_PATH=/mnt/miniodata`; after `source setup.sh --nosetup`, export a writable path, then invoke Compose manually |
