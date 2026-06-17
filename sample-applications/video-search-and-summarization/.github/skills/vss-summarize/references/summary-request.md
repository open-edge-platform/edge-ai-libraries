<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# `POST /manager/summary` request schema

Source: `pipeline-manager/src/summary/models/*` (`SummaryPipelineDTO`).

```jsonc
{
  "title": "string",                 // REQUIRED — 400 "Title is required" if absent
  "videoId": "string",               // optional; if given it must exist (else 404)

  "sampling": {                      // REQUIRED block
    "chunkDuration": 20,             // REQUIRED — seconds per chunk
    "samplingFrame": 5,              // REQUIRED — frames sampled per chunk
    "frameOverlap": 0,               // REQUIRED — overlap frame count
    "multiFrame": 5,                 // REQUIRED — batch size; MUST equal frameOverlap + samplingFrame
    "videoStart": 0,                 // optional — clip start (s)
    "videoEnd": 120                  // optional — clip end (s)
  },

  "evam": {                         // REQUIRED block
    "evamPipeline": "object_detection"  // "object_detection" | "video_ingestion"
  },

  "prompts": {                      // optional — all fields optional overrides
    "framePrompt": "string",
    "summaryMapPrompt": "string",
    "summaryReducePrompt": "string",
    "summarySinglePrompt": "string",
    "audioSummaryMapPrompt": "string",
    "audioSummaryReducePrompt": "string",
    "audioSummarySinglePrompt": "string"
  },

  "audio": {                        // optional
    "audioModel": "small.en",        // one of ENABLED_WHISPER_MODELS (GET /manager/audio/models)
    "useFullTranscriptSummary": false
  },

  "produceFinalSummary": true       // optional; true = LLM map-reduce into one final summary,
                                     // false = keep only per-chunk summaries
}
```

Response: `{ "summaryPipelineId": "<stateId>" }` — use it as `stateId` for
`GET /manager/summary/{stateId}` and `.../raw`.

## Validation gotchas (return 400)

- Missing `title` → "Title is required".
- `multiFrame` set but `multiFrame != frameOverlap + samplingFrame` →
  "Multi frame mismatch". (If `multiFrame` is omitted the server computes it.)
- `multiFrame` greater than the configured max batch size → "Current Maximum
  Supported Batch Size is N".
- Missing `evam.evamPipeline` → "Evam pipeline not found".

## Picking audio models

List what's loaded before setting `audio.audioModel`:
```bash
curl -s "$HOST/manager/audio/models" | jq .
```
Driven by `ENABLED_WHISPER_MODELS` at deploy time (e.g. `tiny.en,small.en,medium.en`).
