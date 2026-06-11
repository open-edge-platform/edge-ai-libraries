---
name: vss-summarize
description: Summarize a video through the VSS Pipeline Manager — start a summary pipeline with POST /summary (full required body), poll GET /summary/{stateId} until complete, then return the summary via GET /summary/{stateId}/raw. Use when the user says "summarize this video", "create a summary", "what happens in this video" (on an ingested video), or wants to run/inspect the summarization pipeline. Requires a summary-capable deployment (--summary, --dual, or --unified).
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "vss operational summarization"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Summarize

Run the summarization pipeline via the Pipeline Manager. **Run the curl commands
yourself** and relay results. Endpoints use the nginx `/manager` prefix.

Set `HOST=http://${HOST_IP:-localhost}:${APP_HOST_PORT:-12345}`.

## Preconditions

1. Backend healthy and summary enabled — probe first; if not, use
   [`vss-doctor`](../vss-doctor/SKILL.md) / [`vss-up`](../vss-up/SKILL.md):
   ```bash
   curl -sf "$HOST/manager/health" >/dev/null && \
   curl -s "$HOST/manager/app/features" | jq '.summary // .'   # confirm summary capability
   ```
2. A `videoId` to summarize — upload one with `POST /manager/videos` (multipart,
   field `video`), which returns `{ "videoId": "…" }`. Or list existing — note the
   response is an **object** `{ "videos": [...] }`, **not a bare array**, and
   `name` is a generated hash (the real filename is in `url` / `dataStore.fileName`):
   ```bash
   curl -s -X POST "$HOST/manager/videos" -F "video=@/path/to/clip.mp4" | jq .
   curl -s "$HOST/manager/videos" | jq '.videos[] | {videoId, file: .dataStore.fileName}'
   ```

## 1. Start the summary pipeline

`POST /manager/summary`. The body has **required** fields — missing any of
`title`, `sampling.*`, or `evam.evamPipeline` returns 400. See
[`references/summary-request.md`](./references/summary-request.md) for the full
schema, prompt overrides, and audio options.

Minimal valid request:
```bash
curl -s -X POST "$HOST/manager/summary" \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Loading dock review",
    "videoId": "<VIDEO_ID>",
    "sampling": { "chunkDuration": 20, "samplingFrame": 5, "frameOverlap": 0, "multiFrame": 5 },
    "evam": { "evamPipeline": "object_detection" },
    "produceFinalSummary": true
  }' | jq .
# → { "summaryPipelineId": "<STATE_ID>" }
```

> **Sampling constraint:** the Pipeline Manager enforces
> `multiFrame == frameOverlap + samplingFrame`. With `frameOverlap: 0`, set
> `multiFrame == samplingFrame`. Mismatch → 400 "Multi frame mismatch".
> `evamPipeline` is one of `object_detection` | `video_ingestion`.

## 2. Poll until complete

The returned `summaryPipelineId` is the `stateId`. **`GET /manager/summary/{stateId}`
has no top-level `status`/`progress` field** (only `/raw` does) — progress lives in
per-stage fields:
```bash
STATE_ID=<STATE_ID>
curl -s "$HOST/manager/summary/$STATE_ID" | jq '{
  chunking: .chunkingStatus,         # string, "complete" when chunked
  frames:   .frameSummaryStatus,     # COUNTS object: {complete, inProgress, na, ready}
  video:    .videoSummaryStatus,     # string: "na" → "inProgress" → "complete"  ← real done signal
  audio:    .audioTranscriptSummaryStatus,
  summary_len: (.summary | length)
}'
```

> **⚠️ Completion is `videoSummaryStatus == "complete"`, NOT `summary` being
> non-empty.** The final `summary` text is **streamed in incrementally** while
> `videoSummaryStatus` is still `"inProgress"`, so polling on "summary length > 0"
> returns a **truncated, mid-sentence** result. Always gate on `videoSummaryStatus`. With
> `produceFinalSummary: false` there is no final stage — gate on
> `frameSummaryStatus.inProgress == 0` instead.

```bash
until curl -s "$HOST/manager/summary/$STATE_ID" \
       | jq -e '.videoSummaryStatus == "complete"' >/dev/null; do sleep 10; done
```
Summarization is slow (VLM per-chunk + LLM map-reduce) — minutes, not seconds.

## 3. Retrieve the summary

```bash
curl -s "$HOST/manager/summary/$STATE_ID" | jq -r '.summary'   # final map-reduced summary
# Per-chunk captions live in .frameSummaries[] (each: frameKey, status, summary).
# NOT in .chunks[] — those only carry {chunkId, duration, audioTranscripts}:
curl -s "$HOST/manager/summary/$STATE_ID" | jq -r '.frameSummaries[] | "[\(.frameKey)] \(.summary)"'
curl -s "$HOST/manager/summary/$STATE_ID/raw" | jq .   # everything (audio, frames, status, …)
```
Present the final summary text; offer the per-chunk detail if useful. Audio with
no speech yields an `audioTranscriptSummary` that says so — not an error.

## Manage

```bash
curl -s "$HOST/manager/summary" | jq '.[] | {stateId, title}'   # list all
curl -s -X DELETE "$HOST/manager/summary/$STATE_ID"             # delete one
```
