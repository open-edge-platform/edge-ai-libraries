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
argument-hint: >
  Describe what you want to deploy or ingest (e.g. "bring up the stack and
  ingest this mp4", or "add a text summary embedding for a video time range")
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

Credentials are never committed — export strong values in-shell and **reuse
the same pair across restarts** (the MinIO data volume remembers the first
ones). `setup.sh` must be **sourced**; `--nosetup` exports env without
touching containers, `REGISTRY_URL=intel` selects the prebuilt image, and
`--no-build` prevents a source build (building is the `-dev` skill's job).
Run in the background — image pulls plus embedding/YOLOX model downloads take
a while:

```bash
bash -c 'export MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD="$(openssl rand -hex 16)" \
  EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32" REGISTRY_URL=intel TAG=latest \
  VS_INDEX_NAME="video-rag" \
  && source ./setup.sh --nosetup \
  && docker compose -f docker/compose.yaml up -d --no-build'
```

(`VS_INDEX_NAME` pins the VDMS collection name — without it the compose file
falls back to the code default `video-rag-test`.) Then wait for readiness:

```bash
until curl -sf http://localhost:6007/v1/dataprep/health; do sleep 10; done
```

Health shows `embedding_mode` (`sdk` default) and, in SDK mode, the loaded
model/device. Teardown later with
`docker compose -f docker/compose.yaml down`.

## 3. Ingest a video

Upload an MP4 (≤500 MB) — it is stored in MinIO and embedded in one step:

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

## 4. Manage & observe

```bash
curl -s 'http://localhost:6007/v1/dataprep/videos'              # list (default bucket vdms-bucket)
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
| Ingestion fails with "Dimensions mismatch" | collection was built with a different embedding model → new `VS_INDEX_NAME` or wipe (destructive — confirm) and re-ingest |
| 413 on upload | file >500 MB → put it in MinIO (console :6011) and use `POST /videos/minio` |
| Detected objects missing from results | YOLOX download failed on first run (no network) → restart with network access |
| MinIO auth errors after re-deploy | creds differ from the ones the MinIO volume was created with → reuse originals |
| MinIO bind-mount errors at start | default `MINIO_MOUNT_PATH=/mnt/miniodata` not writable → export a writable path first |
