<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Search query schema

Source: `pipeline-manager/src/search/models/*` (`SearchQueryDTO`,
`TimeFilterSelection`, `SearchResult`).

## Request: `POST /manager/search/query`

```jsonc
{
  "query": "person walking",        // REQUIRED: natural-language query
  "tags": "outdoor,daytime",        // optional: comma-separated; results must match
  "timeFilter": {                   // optional: relative OR absolute, not both
    "value": 7,                     // relative: amount...
    "unit": "days",                 // ...with unit: minutes | hours | days | weeks
    "start": "2025-01-01T00:00:00Z",// absolute: ISO-8601 start
    "end":   "2025-12-31T23:59:59Z" // absolute: ISO-8601 end
  }
}
```

To search by image instead of text (`--search`/`--dual` only), replace
`query` with exactly one of:

- `"image": "data:image/jpeg;base64,..."` - inline base64 or data URL.
- `"imageUrl": "<imageUrl | imagePath | imageId>"` - an image previously
  uploaded with `POST /manager/search/images` (multipart field `image`;
  `.jpg`/`.jpeg`/`.png`/`.webp`, at most 2 MB). The response gives `imageId`,
  `imageUrl` (the gateway URL `$HOST/datastore/<bucket>/search-images/<id>`)
  and `imagePath` (the same path without the host). Any host is accepted in
  `imageUrl`; only the path is used. Delete it with
  `DELETE /manager/search/images/{imageId}`.

`timeFilter` is normalized server-side into `{ start, end }`. Use **relative**
(`value`+`unit`) for "last 7 days" style, or **absolute** (`start`/`end`) for a
fixed window. Omit entirely for no time constraint.

## Response shape

`POST /manager/search/query` returns an **object that wraps** the result groups
(NOT a bare array) - the ranked clips are at `.results[].results[]`:

```jsonc
{
  "results": [
    {
      "query_id": "uuid",
      "results": [                       // ← iterate .results[].results[]
        {
          "id": null,
          "page_content": "Video segment from 24s to 32s, seeking to 30.0s",  // locator, not a caption
          "metadata": {
            "video_id": "f079427b-…",
            "video_url": "http://multimodal-dataprep:8000/v1/dataprep/media/download?video_id=…&bucket_name=…",
            "video_rel_url": "/v1/dataprep/media/download?video_id=…&bucket_name=…",
            "relevance_score": 1,        // 0..1; top hit can be exactly 1
            "rank": 1,
            "segment_start": 24,         // clip window, seconds
            "segment_end": 32,
            "seek_timestamp": 30,        // jump-to point, seconds
            "timestamp": 30,
            "date_time": "",             // often empty for uploaded files
            "tags": "indoor,people",
            "bucket_name": "video-summary",
            "video_metadata": { "duration": 49.67, "fps": 12, "tags": ["indoor","people"] }
            // ...plus aggregated, best_frame_info, created_at, score_breakdown
          }
        }
      ]
    }
  ]
}
```

Sort by `metadata.relevance_score`. Surface `segment_start`/`segment_end` +
`seek_timestamp` + `video_url` so the user can jump to the clip.

One additional top-level field is attached per result hit (sibling to
`metadata`, not inside it), when the hit's `video_id` matches a still-known
video in `GET /manager/videos`:

- `videoPlaybackUrl` - datastore-relative path to the full source video, e.g.
  `/my-bucket/<videoId>/source.mp4`. Prefix with the datastore base URL (same
  host as the search request, `/datastore` in place of `/manager`) for a
  fetchable link.
It is absent if the video was deleted after being indexed.

**No filename in the result.** `metadata` has `video_id` but no `video` /
`file_name`. Join `video_id` against the video list to get the filename
(`GET /manager/videos` → `.videos[].dataStore.fileName`):
```bash
curl -s "$HOST/manager/videos" \
  | jq '[.videos[] | {key:.videoId, value:.dataStore.fileName}] | from_entries' > /tmp/idmap.json
curl -s -X POST "$HOST/manager/search/query" -H 'Content-Type: application/json' \
  -d '{"query":"person wearing a hat"}' \
  | jq --slurpfile m /tmp/idmap.json -r '.results[].results[]
      | "\($m[0][.metadata.video_id] // "?")  \(.metadata.segment_start)-\(.metadata.segment_end)s  score=\(.metadata.relevance_score)"'
```

## Persistent vs one-off

- `POST /manager/search/query` - stateless, returns results immediately.
- `POST /manager/search` - creates a stored query (`queryId`) you can
  `GET`, `refetch`, `watch`, list via `/search/watched`, or `DELETE`.
