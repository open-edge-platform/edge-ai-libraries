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
| **Search** | `POST /search`, `GET /search`, `POST /search/query`, `GET /search/{queryId}`, `DELETE /search/{queryId}`, `POST /search/{queryId}/refetch`, `PATCH /search/{queryId}/watch`, `GET /search/watched`, `POST /search/images`, `DELETE /search/images/{imageId}` | Search query management and execution; query-image upload for search-by-image |
| **Summary** | `POST /summary`, `GET /summary`, `GET /summary/ui`, `GET /summary/{stateId}`, `GET /summary/{stateId}/raw`, `DELETE /summary/{stateId}` | Video summarization pipeline |

> [!NOTE]
> When accessing the Pipeline Manager through nginx, all paths are prefixed with `/manager/` (for example, `GET /manager/health`).

For full request/response schemas, refer to the interactive docs or the OpenAPI spec.

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
