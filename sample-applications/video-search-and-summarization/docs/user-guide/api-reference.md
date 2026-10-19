# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: _assets/vss-api.yaml
```hide_directive-->

The Video Search and Summarization application exposes REST APIs through several microservices. The full OpenAPI specification for the Pipeline Manager is available in [`_assets/vss-api.yaml`](_assets/vss-api.yaml).

## Interactive API Documentation

Each service listed below auto-generates an interactive API explorer (powered by [Swagger UI](https://swagger.io/tools/swagger-ui/) via FastAPI / NestJS) where you can browse endpoints, inspect request/response schemas, and execute live requests directly from the browser using **Try it out**.

> **Prerequisite:** The application must be running (via `source setup.sh --summary`, `--search`, `--dual`, or `--unified`).

| Service | URL | Availability |
| ------- | --- | ------------ |
| **Pipeline Manager** | `http://<HOST_IP>:<APP_HOST_PORT>/manager/docs` | All modes |
| **Data Prep** | `http://<HOST_IP>:<VS_HOST_PORT>/docs` | `--search`, `--dual`, `--unified` |
| **Multimodal Embedding Serving** | `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/docs` | `--search`, `--dual`, `--unified` |

With default ports, the URLs are:

```bash
# Pipeline Manager — video upload, search, summarization, health, config
http://<HOST_IP>:12345/manager/docs

# Data Prep — data ingestion and frame processing
http://<HOST_IP>:7890/docs

# Multimodal Embedding Serving — embedding generation
http://<HOST_IP>:9777/docs
```

Replace `<HOST_IP>` with the IP address or hostname of the machine running the application.

## Pipeline Manager API Overview

The Pipeline Manager is the primary API for interacting with the application. Its endpoints are organized into the following groups:

| Category | Endpoints | Description |
| -------- | --------- | ----------- |
| **Health** | `GET /health` | Service health status |
| **App** | `GET /app/config`, `GET /app/features` | System configuration and feature flags |
| **Pipeline** | `GET /pipeline/frames`, `GET /pipeline/evam` | Frame and EVAM pipeline status |
| **Audio** | `GET /audio/models` | Available audio transcription models |
| **Tags** | `GET /tags`, `DELETE /tags/{tagId}` | Tag management |
| **Video** | `POST /videos`, `GET /videos`, `GET /videos/{videoId}`, `POST /videos/search-embeddings/{videoId}` | Video upload, listing, and embedding creation |
| **Search** | `POST /search`, `GET /search`, `POST /search/query`, `GET /search/{queryId}`, `DELETE /search/{queryId}`, `POST /search/{queryId}/refetch`, `PATCH /search/{queryId}/watch`, `GET /search/watched`, `GET /search/refresh-config`, `GET /search/config`, `POST /search/images`, `DELETE /search/images/{imageId}` | Search query management and execution; query-image upload for search-by-image. `GET /search/refresh-config` returns the effective auto-refresh settings applied to watched queries; `GET /search/config` returns search defaults such as `minPeakScoreDefault`. |
| **Frames** | `GET /frames` | One stored frame (whole, or cropped to a detected object) located by a search hit's `best_frame_info`; raw JPEG, or base64 JSON with `format=json` (search deployments only) |
| **Live Streams** | `POST /streams`, `POST /streams/batch`, `GET /streams`, `GET /streams/{streamId}`, `PATCH /streams/{streamId}`, `DELETE /streams/{streamId}`, `DELETE /streams` | RTSP camera registration and lifecycle (search deployments only) |
| **Summary** | `POST /summary`, `GET /summary`, `GET /summary/ui`, `GET /summary/{stateId}`, `GET /summary/{stateId}/raw`, `DELETE /summary/{stateId}` | Video summarization pipeline |

> [!NOTE]
> The **Live Streams** and **Frames** endpoints are a thin pass-through to the
> Multimodal DataPrep service. They are available only when
> `SEARCH_DATAPREP_ENDPOINT` (or `STREAMS_DATAPREP_ENDPOINT`) is configured,
> which is the case in `--search` and `--dual` deployments. In summary-only
> deployments these routes return an error explaining that the feature is
> not configured.

> [!NOTE]
> When accessing the Pipeline Manager through nginx, all paths are prefixed with `/manager/` (for example, `GET /manager/health`).

For full request/response schemas, refer to the interactive docs or the OpenAPI spec.

## Video Embedding Status

Each video returned by `GET /videos` and `GET /videos/{videoId}` records which
search index it has been embedded into. These flags apply to **uploaded videos
only**; live RTSP cameras have no video record, and their ingestion progress is
reported by `GET /streams` (`stats.embeddings_created`).

| Field | Set by | Meaning |
| ----- | ------ | ------- |
| `searchEmbeddings` | `POST /videos/search-embeddings/{videoId}` and `POST /videos/search-embeddings-batch` | `true` once frame embeddings were created (`--search`, `--dual`); `false` if DataPrep rejected the request or the batch item failed |
| `textEmbeddings` | Summary pipeline, when search is enabled (`--unified`, `--dual`) | `true` once at least one chunk caption was embedded |

`null` means no outcome has been recorded, either because embedding was never
requested or because the video was embedded before this status was tracked. A
`true` flag is never reset by a later failed attempt, and a timed-out request
leaves the flag unchanged because DataPrep may still complete it. Batch jobs are
followed by Pipeline Manager until they finish, so their result is recorded even
if no client polls `GET /videos/search-embeddings-jobs/{jobId}`.

## Re-adding an Existing Video

`POST /videos/{videoId}/copy` adds an already-uploaded video again as a new,
independent video, exactly as if its file were uploaded again. The stored file
is copied inside the object store to a new `videoId`, and a new record with the
same name is created. The response is `{ "videoId": "<new id>" }`.

- Tags are the source video's tags plus any passed in the optional `tags` body
  field (comma-separated).
- Embeddings, embedding status and summaries are not copied. Call
  `POST /videos/search-embeddings/{videoId}` (or the batch endpoint) with the
  new ID to index it.
- The source video is not changed.
- Each copy is indexed and ranked separately, so a query can return the same
  moment once per copy.
- With `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS=false`, embedding a copy is
  rejected with `409` and the copy is removed, the same as a content-identical
  upload.

The UI uses this when you pick videos from **recent uploads** in the search
upload dialog. Calling `POST /videos/search-embeddings/{videoId}` on a video
that is already indexed adds a second set of embeddings under the same ID
instead.

## Filtering Search Results by Minimum Peak Score

`POST /search`, `POST /search/query` and `POST /search/{queryId}/refetch`
accept an optional `minPeakScore` (a number from 0 to 1). Frames whose
similarity score is below it are dropped at retrieval, in the Vector Retriever,
before frames are aggregated into segments. Every returned result's peak
(best-frame) score is therefore at least `minPeakScore`, and the
`AGGREGATION_MAX_RESULTS` results returned are the best ones that pass the
filter rather than what remains of an unfiltered top N.

| Value | Behavior |
| ----- | -------- |
| omitted | The query's saved value (refetch only), otherwise the deployment default `SEARCH_MIN_PEAK_SCORE` |
| `0` | Filter off (the default) |
| `0` < value ≤ `1` | Only frames scoring at least `value` are ranked; outside `[0, 1]` returns `400` |

A query created with `POST /search` saves the value it ran with. Refetching
with a new `minPeakScore` replaces the saved value, and watched-query refreshes
reuse it. `GET /search/config` returns `{ "minPeakScoreDefault": <number> }` so
clients can show the deployment default.

```bash
curl -s -X POST "$BASE/search" -H 'Content-Type: application/json' \
  -d '{"query": "forklift", "minPeakScore": 0.2}'
curl -s -X POST "$BASE/search/<queryId>/refetch" -H 'Content-Type: application/json' \
  -d '{"minPeakScore": 0.3}'
```

> [!NOTE]
> - Scores are compared to the raw similarity the vector database returns,
>   which assumes higher is better (inner product, the VSS default for both
>   VDMS and Milvus).
> - With the filter on, segment scores are computed only from frames that pass
>   it, so the ranking can also change, not only the number of results.
> - A high threshold can return no results. In unified mode (`--unified`), the
>   score is a text-to-text similarity over summaries and is distributed
>   differently from frame similarity, so choose the threshold separately.
> - Live-stream hits go through the same path and are filtered the same way.

## Search by an Uploaded Image

In `--search` and `--dual` modes, search-by-image can use an image stored in the
object store instead of inline base64 data (claim-check pattern). This keeps
large image payloads out of search requests and out of agent/MCP tool calls.

1. Upload the image with `POST /search/images` (`multipart/form-data`, field
   `image`). Accepted: `.jpg`/`.jpeg` (`image/jpeg`), `.png` (`image/png`),
   `.webp` (`image/webp`), at most 2 MB. The file content must match its
   extension. The response carries `imageId`, `imageUrl`, and `imagePath`.
   `imageUrl` is the image's externally reachable gateway URL, for example
   `http://<HOST_IP>:12345/datastore/<bucket>/search-images/<imageId>`. It is
   built from `PM_PUBLIC_BASE_URL` (`setup.sh` defaults it to
   `http://$HOST_IP:$APP_HOST_PORT`; set it for a DNS name or TLS proxy). If
   that is unset, it is built from the request's `Host`/`X-Forwarded-*`
   headers. `imagePath` is the same URL without the host.
2. Search with `imageUrl` in place of `image` or `query` on `POST /search/query`
   or `POST /search`. It accepts the returned `imageUrl`, `imagePath`, or the
   bare `imageId`. Any host is accepted, so a caller can use whatever address
   reaches the gateway. Only the path is used, and it must name an image stored
   by step 1: Pipeline Manager reads the object from its own bucket and never
   fetches any other URL.
3. Delete the image with `DELETE /search/images/{imageId}` when it is no longer
   needed. After that, searching by its URL returns `404`.

```bash
BASE=http://<HOST_IP>:12345/manager
IMAGE_URL=$(curl -s -F "image=@frame.jpg;type=image/jpeg" "$BASE/search/images" | jq -r .imageUrl)
curl -s -X POST "$BASE/search/query" -H 'Content-Type: application/json' \
  -d "{\"imageUrl\": \"$IMAGE_URL\"}"
curl -s -X DELETE "$BASE/search/images/$(basename "$IMAGE_URL")"
```

## Using the OpenAPI Specification Offline

The Pipeline Manager OpenAPI spec is available in two ways:

**From the repository:**

The file [`docs/user-guide/_assets/vss-api.yaml`](_assets/vss-api.yaml) can be loaded into any OpenAPI-compatible tool:

- [Swagger Editor](https://editor.swagger.io/) — paste or import the YAML to browse and try endpoints
- [Bruno](https://www.usebruno.com/) — import the YAML file to generate a ready-to-use request collection

**From a running instance:**

The Pipeline Manager also serves its spec at runtime:

```bash
# JSON format
curl http://<HOST_IP>:<APP_HOST_PORT>/manager/swagger/json

# YAML format
curl http://<HOST_IP>:<APP_HOST_PORT>/manager/swagger/yaml
```
