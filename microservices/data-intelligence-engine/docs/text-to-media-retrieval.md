# Text-to-Media Retrieval

Use `POST /v1/retrieve` with `target_media` to search document, image, video, or audio content with a text query. The Engine searches the eligible sources independently and returns the same `retrieved_chunks` / `chunks` response shape as text retrieval. If `target_media` is omitted, the request searches all serving sources in the selected pools.

Audio search indexes text produced by automatic speech recognition (ASR). It retrieves transcript segments rather than audio waveforms.

## Requirements

- Provide at least one Library name or ID in `libraries`.
- Configure at least one serving projection for each requested modality across the selected Libraries (or across the pools named in `asset_pool_ids`). A missing projection returns HTTP 503 unless `allow_missing_targets` applies. Multiple serving projections for one modality are allowed and are searched independently.
- For audio search, allow transcription and indexing to complete before querying. `GET /v1/libraries/{library}/assets/{asset_id}/enrichment` reports `transcript_status` and `embedding_status`.

## Request

```bash
curl -sS -X POST http://localhost:16022/v1/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"a person is talking","libraries":["your-library"],"target_media":["video","image"],"top_k":3}'
```

| Field                     | Description                                                                                                                                                                                                                                                   |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `query`                 | Non-empty text query.                                                                                                                                                                                                                                         |
| `libraries`             | One or more Library names or IDs.                                                                                                                                                                                                                             |
| `asset_pool_ids`        | Optional. Restricts the search to the named asset pools. The default (empty) searches every pool in the selected Libraries that serves a requested modality.                                                                                                  |
| `target_media`          | Array containing `document`, `video`, `image`, or `audio`. `document` selects text/table chunks; `image` also selects figures inside documents. Omit it or pass `[]` to search all serving sources. |
| `top_k`                 | From 1 to 100. Maximum candidates retrieved per serving source; without reranking, also the maximum returned per source. With one source per modality, this is equivalent to a per-modality limit.                                                                                                                                                     |
| `exclude_chunk_ids`     | Optional chunk IDs to exclude from the results. Excluded IDs are allowed for in the search depth, up to 100.                                                                                                                                                  |
| `allow_missing_targets` | Optional. When `true`, a missing projection is omitted from the results if at least one requested modality is available. The default is `false`.                                                                                                          |
| `postprocess`           | Optional media reranker: `{"processor_type":"reranker","top_n":3}`. `top_n` controls the final global result count (default 3, from `RERANK_TOP_N`), while `top_k` controls each source's input candidates. See [Media reranking](#media-reranking). |

`asset_pool_ids` narrows a media request to the named pools; with the default empty list, every pool serving a requested modality is searched. Without `postprocess`, `top_k` applies separately to each serving source. Graph retrieval runs on the document path; select `document` or omit `target_media` and set `retriever_type` to `graph` or `rrf` as appropriate.

## Response

Media results use `retrieved_chunks` for recall candidates and `chunks` for final hits:

```json
{
  "query": "a person is talking",
  "libraries": ["your-library"],
  "retrieved_chunks": [{
    "id": "video-chunk-id",
    "text": "Video description",
    "score": 0.28,
    "metadata": {"file_name": "example.mp4", "target_media": "video", "representation": "video_clip", "source_rank": 1, "rank": 1}
  }],
  "chunks": [{
    "id": "video-chunk-id",
    "text": "Video description",
    "score": 0.28,
    "metadata": {"file_name": "example.mp4", "target_media": "video", "representation": "video_clip", "source_rank": 1, "rank": 1}
  }],
  "postprocess_error": null,
  "graph_traces": []
}
```

Without reranking, the two arrays contain the same hits. Each source's hits are ordered by descending recall score, and the source result lists are interleaved round-robin in the merged response; they are not concatenated in requested `target_media` order or globally sorted by score. Scores are not comparable across modalities. `metadata.target_media` identifies each hit's modality; an empty modality has no hits. `metadata.source_rank` is the position within its source before exclusions, so excluded hits can leave gaps. `metadata.rank` is the position in the merged response, not a per-modality rank or a calibrated global relevance ranking. Asset paths in metadata refer to server-side locations and may not be accessible to remote clients.

For example, if source A returns `A1` (0.90), `A2` (0.80) and source B returns
`B1` (0.70), `B2` (0.60), the merged order is `A1, B1, A2, B2`. It is not a
single score-sorted ranking; use media reranking to compare candidates across
sources.

If any requested modality fails to search, the whole request returns HTTP 503. With `allow_missing_targets=true`, modalities without a serving projection are silently omitted when at least one requested modality is available; if all are missing, the request returns HTTP 503.

## Media reranking

With `postprocess`, media reranking uses a `Qwen3-VL` reranker model to jointly re-score candidate hits from the image, audio, and video channels, producing one global ranking that is comparable across media types. `retrieved_chunks` keeps the candidates and their recall scores; `chunks` contains the global best `postprocess.top_n` hits. On success, each final hit's `metadata.rank` is its global rank.

Without an explicit `postprocess.reranker_model`, image/video/audio targets or
non-document media hits select the media reranker automatically. It also scores
document text in mixed results; document-only requests keep text reranking.

```json
{
  "query": "red bag on the table",
  "libraries": ["media-library"],
  "target_media": ["image", "audio", "video"],
  "top_k": 20,
  "postprocess": {"processor_type": "reranker", "top_n": 3}
}
```

Each hit has one `score`: in `retrieved_chunks` it is the modality's retrieval score, and in `chunks` after successful reranking it is the reranker score used for global order. A failed reranker leaves `retrieved_chunks` intact and falls `chunks` back to the complete merged recall list; it is not truncated to `top_n`. Fallback scores remain recall scores and fallback `metadata.rank` is the position in that merged list. The response includes `postprocess_error`, but an internally degraded reranker can leave it `null`; inspect Engine logs to diagnose every fallback. If a retrieved media candidate cannot be read, the strict request path returns HTTP 503 rather than silently omitting it.

### Quick test with curl

Without `postprocess`, each modality's hits retain their own recall order:

```bash
curl -sS -X POST http://localhost:16022/v1/retrieve \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "a person is talking",
    "libraries": ["your-library"],
    "target_media": ["video", "image"],
    "top_k": 3
  }' | jq
```

Add `postprocess` to enable the media reranker and get one global ranking:

```bash
curl -sS -X POST http://localhost:16022/v1/retrieve \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "a person is talking",
    "libraries": ["your-library"],
    "target_media": ["video", "image"],
    "top_k": 20,
    "postprocess": {"processor_type": "reranker", "top_n": 3}
  }' | jq
```

Reranked hits carry their final reranker value in `chunks[].score`.

### Deployment configuration

| Environment variable              | Default                             |
| --------------------------------- | ----------------------------------- |
| `ENGINE_MEDIA_RERANK_BACKEND`   | `openvino_vl`                     |
| `ENGINE_MEDIA_RERANK_MODEL_ID`  | `Qwen/Qwen3-VL-Reranker-2B-INT8`  |
| `ENGINE_MEDIA_RERANK_DEVICE`    | `GPU`                             |
| `MEDIA_RERANK_VIDEO_MAX_FRAMES` | `8`                               |

Video uses eight sampled frames by default.

### Prepare the OpenVINO model

The runtime defaults to the INT8 weight-only package
(`Qwen/Qwen3-VL-Reranker-2B-INT8`, read from
`Qwen3-VL-Reranker-2B-INT8-OV/`). Prepare it with
`data-intelligence-engine/scripts/prepare-models.sh media-reranker-int8`, which
downloads the checkpoint, exports all three modes to FP16 OpenVINO IRs, and
quantizes them to INT8 as described in
[How to prepare models](how-to-guides/how-to-prepare-models.md). To serve the
FP16 export instead, set `ENGINE_MEDIA_RERANK_MODEL_ID=Qwen/Qwen3-VL-Reranker-2B`.
The manual procedure below shows what the preparation step does.

`Qwen/Qwen3-VL-Reranker-2B-INT8` is an Engine configuration ID, not a separate
Hugging Face repository. The upstream checkpoint is
`Qwen/Qwen3-VL-Reranker-2B`. The Engine takes the configured ID's last
component and appends `-OV` to find the local package under
`$ENGINE_MODEL_ROOT_PATH`; `/v1/models/reranker` lists that package by its
directory name, `Qwen3-VL-Reranker-2B-INT8-OV`.

Install the `media-export` optional dependency and place the official
`Qwen/Qwen3-VL-Reranker-2B` checkpoint in a local directory. Export each media
mode that the engine will serve:

```bash
PYTHONPATH=data-intelligence-engine/src python data-intelligence-engine/scripts/export_qwen3_vl_reranker_ov.py \
  --source /path/to/Qwen3-VL-Reranker-2B \
  --output data-intelligence-engine/workspace/models/Qwen3-VL-Reranker-2B-OV \
  --mode image --sample /path/to/example.jpg
```

Use `--mode text` for audio transcripts. For video, add `--mode video` and
`--sample /path/to/example.mp4`. The source directory must contain the official
`1_LogitScore/config.json` and reference script. The exporter writes the
processor files and one `reranker_<mode>.xml`/`.bin` pair per invocation.

Quantize the exported FP16 IRs to the default INT8 package with
`data-intelligence-engine/scripts/quantize_qwen3_vl_reranker_int8.py` (NNCF
`compress_weights`, INT8_ASYM per-channel). It halves the model size; per the
frozen-pool comparison, image and audio quality is unchanged within noise while
video loses part of the FP16 reranking gain. Build it with
`prepare-models.sh media-reranker-int8`; the default model ID loads its package
from `Qwen3-VL-Reranker-2B-INT8-OV`. When video quality matters, select the
FP16 package explicitly.

Before serving, compare OpenVINO scores and rankings against the official
reference script using the repository checker:

```bash
python data-intelligence-engine/scripts/check_qwen3_vl_reranker_parity.py \
  --source /path/to/Qwen3-VL-Reranker-2B \
  --ov data-intelligence-engine/workspace/models/Qwen3-VL-Reranker-2B-INT8-OV \
  --fixtures /path/to/pairs.jsonl --device GPU
```

Each JSONL row contains `query`, `target`, and either `text` for audio or a
local `path` for image/video. The checker exits with a nonzero status when
scores exceed its tolerance or a query's within-media ranking changes. The
engine runs the reranker only for requests that include `postprocess`.
The OpenVINO IR package is read from `$ENGINE_MODEL_ROOT_PATH/<model-id-last-component>-OV`;
place the exported package there.

## Limitations

Audio language filtering is unavailable because transcript metadata does not contain a language field.
