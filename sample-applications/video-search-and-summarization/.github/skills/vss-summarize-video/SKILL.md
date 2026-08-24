---
name: vss-summarize-video
description: Summarize a video through the VSS Pipeline Manager - start a summary pipeline with POST /summary (full required body), poll GET /summary/{stateId} until complete, then return the summary via GET /summary/{stateId}/raw. Use when the user says "summarize this video", "create a summary", "what happens in this video" (on an ingested video), or wants to run/inspect the summarization pipeline. Requires a summary-capable deployment (--summary, --dual, or --unified).
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

Run the summarization pipeline via the Pipeline Manager. Call the documented
API yourself and report only observed responses. Endpoints use the nginx
`/manager` prefix.

Set `HOST=http://${HOST_IP:-localhost}:${APP_HOST_PORT:-12345}`.

## Answer contract when VSS is not reachable

The user may be away from the deployment, `$HOST` may refuse connections, or a
live precondition may fail (for example, summary mode is disabled or the named
video is absent). In any of those cases **do not stall and do not invent
responses.** Report the observed blocker, then answer with the complete exact
call sequence the user can run after fixing it: full endpoint paths, request
bodies / form fields, the field each step carries over from the previous
response, and the condition that says a step is finished. Do not abbreviate or
omit the requested summary flow merely because it could not be executed. State
plainly which commands were not executed. Never end the answer by asking
whether to run them.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It resolves the app root in this order and prints it
as the only line on stdout:

1. **Walk up from the current directory** looking for a VSS app root - a
   directory carrying all three markers `setup.sh`, `docker/`, and
   `pipeline-manager/`.
2. **Ask git for the enclosing repository** (`git rev-parse --show-toplevel`) and
   check whether it holds `sample-applications/video-search-and-summarization`,
   or is itself a VSS app root. This is what makes your own clone - or a fork -
   work unchanged.
3. **Reuse a checkout a previous bootstrap already placed** in
   `${XDG_CACHE_HOME:-$HOME/.cache}/vss-src/edge-ai-libraries`.

If any of those hit, that checkout is **reused and NO clone is performed**. Only
when all three miss does it clone - and then only a **shallow (`--depth 1`),
single-branch, sparse** checkout of just
`sample-applications/video-search-and-summarization` from `main`:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-summarize-video. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-summarize-video"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it. The bootstrap refuses
to overwrite an existing non-VSS clone destination.

## Preconditions

1. Backend healthy and summary enabled - probe first; if not, use the installed
   `vss-troubleshoot` or `vss-deploy` skill by name:
   ```bash
   curl -sf "$HOST/manager/health" >/dev/null && \
   curl -s "$HOST/manager/app/features" | jq '.summary // .'   # confirm summary capability
   ```
2. A `videoId` to summarize - upload one with `POST /manager/videos` (multipart,
   field `video`), which returns `{ "videoId": "…" }`. Or list existing - note the
   response is an **object** `{ "videos": [...] }`, **not a bare array**, and
   `name` is a generated hash (the real filename is in `url` / `dataStore.fileName`):
   ```bash
   curl -s -X POST "$HOST/manager/videos" -F "video=@/path/to/clip.mp4" | jq .
   curl -s "$HOST/manager/videos" | jq '.videos[] | {videoId, file: .dataStore.fileName}'
   ```

## 1. Start the summary pipeline

`POST /manager/summary`. The body has **required** fields; missing any of
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

To summarize only part of a clip, add the optional `sampling.videoStart` and
`sampling.videoEnd` (seconds) - e.g. the first ten minutes is
`"videoStart": 0, "videoEnd": 600`.

## 2. Poll until complete

The returned `summaryPipelineId` is the `stateId`. **`GET /manager/summary/{stateId}`
has no top-level `status`/`progress` field** (only `/raw` does) - progress lives in
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
> `produceFinalSummary: false` there is no final stage - gate on
> `frameSummaryStatus.inProgress == 0` instead.

```bash
until curl -s "$HOST/manager/summary/$STATE_ID" \
       | jq -e '.videoSummaryStatus == "complete"' >/dev/null; do sleep 10; done
```
Summarization is slow (VLM per-chunk + LLM map-reduce) - minutes, not seconds.

## 3. Retrieve the summary

```bash
curl -s "$HOST/manager/summary/$STATE_ID" | jq -r '.summary'   # final map-reduced summary
# Per-chunk captions live in .frameSummaries[] (each: frameKey, status, summary).
# NOT in .chunks[] - those only carry {chunkId, duration, audioTranscripts}:
curl -s "$HOST/manager/summary/$STATE_ID" | jq -r '.frameSummaries[] | "[\(.frameKey)] \(.summary)"'
curl -s "$HOST/manager/summary/$STATE_ID/raw" | jq .   # everything (audio, frames, status, …)
```
Present the final summary text; offer the per-chunk detail if useful. Audio with
no speech yields an `audioTranscriptSummary` that says so - not an error.

## Manage

```bash
curl -s "$HOST/manager/summary" | jq '.[] | {stateId, title}'   # list all
curl -s -X DELETE "$HOST/manager/summary/$STATE_ID"             # delete one
```
