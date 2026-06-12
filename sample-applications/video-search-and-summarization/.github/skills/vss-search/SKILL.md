---
name: vss-search
description: Search a video library with natural language via the VSS Pipeline Manager — upload a video (POST /videos), generate its embeddings (POST /videos/search-embeddings/{id}), then run a query (POST /search/query) with optional tag and time filters and read the ranked clip results. Use when the user says "search my videos", "find <thing> in the videos", "when did X happen", or wants to ingest/index a video for search. Requires a search-capable deployment (--search, --dual, or --unified).
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "vss operational search"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Search

Natural-language search over the indexed video library. **Run the curl commands
yourself** and relay results. Endpoints use the nginx `/manager` prefix.

Set `HOST=http://${HOST_IP:-localhost}:${APP_HOST_PORT:-12345}`.

## Preconditions

Backend healthy and **search enabled** — probe first; if not, use
[`vss-doctor`](../vss-doctor/SKILL.md) / [`vss-up`](../vss-up/SKILL.md):
```bash
curl -sf "$HOST/manager/health" >/dev/null && \
curl -s "$HOST/manager/app/features" | jq '.search // .'
```

## 1. Upload a video (if not already ingested)

`POST /manager/videos` — `multipart/form-data`, field name **`video`**, optional
comma-separated `tags`. File must be a streamable MP4 (server rejects otherwise).
```bash
curl -s -X POST "$HOST/manager/videos" \
  -F "video=@/path/to/clip.mp4" \
  -F "tags=outdoor,daytime" | jq .
# → { "videoId": "<VIDEO_ID>" }
```
List / inspect existing videos instead. The list response is an **object**
`{ "videos": [...] }`, **not a bare array**; `name` is a generated hash, so use
`url` / `dataStore.fileName` for the real filename:
```bash
curl -s "$HOST/manager/videos" | jq '.videos[] | {videoId, file: .dataStore.fileName}'
curl -s "$HOST/manager/videos/<VIDEO_ID>" | jq '.video'   # single record is wrapped under .video
```

## 2. Generate search embeddings

A video is **not searchable until embeddings exist**. Trigger them after upload
(or to retry a failed run):
```bash
curl -s -X POST "$HOST/manager/videos/search-embeddings/<VIDEO_ID>" | jq .
```
Wait for completion (re-check the video record) before querying.

## 3. Query

One-off query — `POST /manager/search/query`. **The response is an object
`{ "results": [ { "query_id", "results": [ … ] } ] }`** — wrapped, NOT a bare
array — so the ranked clips are at `.results[].results[]`:
```bash
curl -s -X POST "$HOST/manager/search/query" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "person wearing a hat",
    "tags": "indoor",
    "timeFilter": { "value": 7, "unit": "days" }
  }' | jq -r '.results[].results[]
      | "score=\(.metadata.relevance_score)  clip=\(.metadata.segment_start)-\(.metadata.segment_end)s  seek=\(.metadata.seek_timestamp)s  video_id=\(.metadata.video_id)"'
```
- `query` (required): natural language.
- `tags` (optional): comma-separated, intersected with the query.
- `timeFilter` (optional): **either** relative (`value` + `unit` =
  `minutes|hours|days|weeks`) **or** absolute (`start`/`end` ISO-8601). See
  [`references/search-request.md`](./references/search-request.md).

Each clip's `metadata` carries `relevance_score` (0..1; top hit can be exactly
`1`), `video_id`, `video_url`, `segment_start`/`segment_end`, `seek_timestamp`,
`tags`, and `video_metadata` (duration/fps). In search mode `page_content` is a
segment **locator** ("Video segment from Ns to Ms…"), not a caption.

**Filename is NOT in the result** — `metadata` has `video_id` but no `video` /
`file_name`. To show the clip's filename, join `video_id` against the video list
(`.videos[].dataStore.fileName`):
```bash
curl -s "$HOST/manager/videos" \
  | jq '[.videos[] | {key:.videoId, value:.dataStore.fileName}] | from_entries' > /tmp/idmap.json
curl -s -X POST "$HOST/manager/search/query" -H 'Content-Type: application/json' \
  -d '{ "query": "person wearing a hat" }' \
  | jq --slurpfile m /tmp/idmap.json -r '.results[].results[]
      | "score=\(.metadata.relevance_score)  file=\($m[0][.metadata.video_id] // "?")  clip=\(.metadata.segment_start)-\(.metadata.segment_end)s"'
```
Present top hits with their **filename** + clip window + seek time.

## 4. Saved / managed queries (optional)

```bash
curl -s -X POST "$HOST/manager/search" -H 'Content-Type: application/json' \
  -d '{"query":"forklift"}' | jq .          # create a persistent query → queryId
curl -s "$HOST/manager/search/<QUERY_ID>" | jq .          # fetch results
curl -s -X POST "$HOST/manager/search/<QUERY_ID>/refetch" | jq .   # re-run
curl -s -X PATCH "$HOST/manager/search/<QUERY_ID>/watch" \
  -H 'Content-Type: application/json' -d '{"watch":true}'   # auto-refresh
curl -s "$HOST/manager/search/watched" | jq .
curl -s -X DELETE "$HOST/manager/search/<QUERY_ID>"
```
