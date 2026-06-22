# VSS search architecture reference

This reference is grounded in the current code under `sample-applications/video-search-and-summarization`. Use it when explaining or changing VSS search, embeddings, VDMS retrieval, relevance scoring, time filters, or the watcher.

## Key files

Search microservice:

- `search-ms/server.py`
- `search-ms/src/vdms_retriever/retriever.py`
- `search-ms/src/vdms_retriever/embedding_wrapper.py`
- `search-ms/src/vdms_retriever/__init__.py`
- `search-ms/src/utils/common.py`
- `search-ms/src/utils/time_filters.py`
- `search-ms/src/utils/directory_watcher.py`
- `search-ms/src/utils/utils.py`
- `search-ms/config.yaml`
- `search-ms/pyproject.toml`

Pipeline-manager:

- `pipeline-manager/src/search/controllers/search.controller.ts`
- `pipeline-manager/src/search/services/search-state.service.ts`
- `pipeline-manager/src/search/services/search-shim.service.ts`
- `pipeline-manager/src/search/services/search-db.service.ts`
- `pipeline-manager/src/search/model/search.model.ts`
- `pipeline-manager/src/search/model/search.entity.ts`
- `pipeline-manager/src/data-prep/services/data-prep-shim.service.ts`
- `pipeline-manager/src/data-prep/models/data-prep.models.ts`
- `pipeline-manager/src/video-upload/controllers/video.controller.ts`
- `pipeline-manager/src/video-upload/services/video.service.ts`
- `pipeline-manager/src/state-manager/queues/chunking.service.ts`

Docs and deployment:

- `docs/user-guide/how-it-works/video-search.md`
- `docs/user-guide/how-it-works/video-search-and-summarization.md`
- `docs/user-guide/get-started.md`
- `docker/compose.search.yaml`
- `setup.sh`
- `chart/user_values_override.yaml`
- `chart/unified_summary_search.yaml`

## Runtime dependencies and configuration

`search-ms/pyproject.toml` depends on `langchain-vdms` (`^0.2.0`), `langchain-core`, `watchdog`, `dateparser`, `tzlocal`, `word2number`, and `requests`.

`search-ms/src/utils/common.py` defines `Settings` through `pydantic_settings.BaseSettings`. Important keys:

- VDMS: `VDMS_VDB_HOST`, `VDMS_VDB_PORT`, `SEARCH_ENGINE`, `DISTANCE_STRATEGY`, `INDEX_NAME`.
- Embedding service: `EMBEDDINGS_ENDPOINT`, `EMBEDDINGS_MODEL_NAME`, process-local cache `EMBEDDING_LENGTH`.
- Proxies: `no_proxy_env`, `http_proxy`, `https_proxy`.
- Watcher/upload: `WATCH_DIRECTORY`, `WATCH_DIRECTORY_CONTAINER_PATH`, `DEBOUNCE_TIME`, `VIDEO_UPLOAD_ENDPOINT`, `VS_INITIAL_DUMP`, `DELETE_PROCESSED_FILES`, `WATCH_DIRECTORY_RECURSIVE`.
- Aggregation: `AGGREGATION_SEGMENT_DURATION`, `AGGREGATION_MIN_GAP`, `AGGREGATION_MAX_RESULTS`, `AGGREGATION_INITIAL_K`, `AGGREGATION_ENABLED`, `AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS`, `AGGREGATION_QUAL_MAX_WEIGHT`, `AGGREGATION_QUAL_TOP_WEIGHT`, `AGGREGATION_QUAL_TOP_RATIO`, `AGGREGATION_QUAL_TOP_MIN_COUNT`, `AGGREGATION_QUAL_TOP_MAX_COUNT`, `AGGREGATION_CONTEXT_SIGMA_SECONDS`, `AGGREGATION_CONTEXT_BOOST_STRENGTH`.

`docker/compose.search.yaml` wires `video-search` to those settings. It maps `EMBEDDINGS_ENDPOINT` to `${MULTIMODAL_EMBEDDING_ENDPOINT}`, `EMBEDDINGS_MODEL_NAME` to `${EMBEDDING_MODEL_NAME}`, `INDEX_NAME` to `${VS_INDEX_NAME}`, and watcher settings to `VS_*` environment variables.

`search-ms/config.yaml` describes aggregation defaults and environment variable mappings, but runtime values are read from `Settings` in `common.py`, not from that YAML file directly.

## Frame/image embeddings vs summary-text embeddings

### Search-only / Dual UI: video frame embeddings

`setup.sh` sets the mode:

- For `--search`: `VS_INDEX_NAME="video_frame_embeddings"`, `APP_SEARCH_FEATURE="FEATURE_ON"`, `APP_SUMMARY_FEATURE="FEATURE_OFF"`, and Search UI singleton routing.
- For `--dual`: `VS_INDEX_NAME="video_frame_embeddings"` with separate Summary and Search UIs.
- Before the case statement, `EMBEDDING_MODEL_NAME=${MULTIMODAL_EMBEDDING_MODEL}` for `--summary`, `--search`, `--dual`, and `--unified`, then Unified overrides it.

The frame-indexing path:

1. A user or watcher uploads a video to pipeline-manager.
2. `pipeline-manager/src/video-upload/controllers/video.controller.ts` exposes `POST /videos/search-embeddings/:videoId` through `VideoController.createSearchEmbeddings()`.
3. `VideoService.createSearchEmbeddings()` loads the video, verifies `video.dataStore`, and builds `DataPrepMinioDTO`:
   - `bucket_name`
   - `video_id`
   - `video_name`
   - `tags`
4. `DataPrepShimService.createEmbeddings()` POSTs the DTO to `${search.dataPrep}/videos/minio` and emits `SearchEvents.EMBEDDINGS_UPDATE` on success.
5. VDMS DataPrep creates embeddings from video/frame content and stores them in the `video_frame_embeddings` index.

This is the path that pairs text queries with frame/image embeddings from a multimodal embedding model such as `CLIP/clip-vit-b-32`.

### Unified UI: summary-text embeddings

`setup.sh` changes the mode:

- For `--unified`: `EMBEDDING_MODEL_NAME=${TEXT_EMBEDDING_MODEL}`, `VS_INDEX_NAME="video_summary_embeddings"`, `APP_FEATURE_MUX="SUMMARY_SEARCH"`, `APP_SUMMARY_FEATURE="FEATURE_ON"`, `APP_SEARCH_FEATURE="FEATURE_ON"`, and compose overlays include both `compose.summary.yaml` and `compose.search.yaml`.
- `chart/unified_summary_search.yaml` sets `global.vdmsIndexName: "video_summary_embeddings"`, enables summary and search, and sets UI mux to `SUMMARY_SEARCH`.

The summary-text indexing path:

1. The summarization pipeline chunks a video, captions frames/chunks, and calls `ChunkingService.inferenceCompleteHandler()`.
2. If `this.$feature.hasFeature(FeaturesEnum.SEARCH)` is true, `inferenceCompleteHandler()` emits `PipelineEvents.CHUNK_SEARCH_EMBEDDINGS` with `{ stateId, frameIds, caption }`.
3. `ChunkingService.createChunkSearchEmbeddings()` handles that event.
4. It derives a midpoint frame, chunk start/end from `state.userInputs.chunkDuration`, and builds `DataPrepSummaryDTO`:
   - `bucket_name: this.$dataStore.bucket`
   - `video_id: state.video.videoId`
   - `video_summary: caption`
   - `video_start_time: chunkStartTime`
   - `video_end_time: chunkEndTime`
   - `tags: state.video.tags`
5. It calls `DataPrepShimService.createEmbeddingsFromSummary()`.
6. `createEmbeddingsFromSummary()` POSTs to `${search.dataPrep}/summary` and emits `SearchEvents.EMBEDDINGS_UPDATE` on success.
7. VDMS DataPrep embeds the generated summary/caption text and stores it in `video_summary_embeddings`.

This path should use a text embedding model such as `QwenText/qwen3-embedding-0.6b` because indexed content is text, not image/frame vectors.

### Why the distinction matters

- **Model compatibility:** Search/Dual uses a multimodal model for text-to-image/frame retrieval. Unified uses a text embedding model for text-to-text retrieval over summaries. Mixing them can degrade relevance or break dimensions.
- **Index compatibility:** `INDEX_NAME`/`VS_INDEX_NAME` separates `video_frame_embeddings` from `video_summary_embeddings`. Existing vectors are not re-embedded when the model changes.
- **Metadata assumptions:** Search-ms aggregation code was written around frame-like metadata (`timestamp`, `frame_number`, `frame_type`, `fps`, `total_frames`, `video_url`). Summary-text entries may expose chunk start/end metadata instead, depending on VDMS DataPrep output. Verify actual returned metadata before tuning aggregation for Unified mode.
- **Result granularity:** Frame embeddings find visual moments and then aggregate nearby frames into segments. Summary-text embeddings find caption/summary chunks; the best answer may reflect a summarized interval rather than a raw image frame.

## Query flow: pipeline-manager to search-ms to VDMS

1. `SearchController.addQuery()` accepts `SearchQueryDTO` with `query`, optional comma-separated `tags`, and optional `timeFilter`. It calls `SearchStateService.newQuery()`.
2. `SearchStateService.newQuery()` normalizes time with `normalizeTimeFilter()`, persists a `SearchQuery`, marks it `RUNNING`, and emits `SearchEvents.RUN_QUERY`.
3. `SearchStateService.reRunQuery()` handles `RUN_QUERY`, updates status, and calls `runSearch()`.
4. `runSearch()` builds a `SearchShimQuery` with `query`, `query_id`, `tags`, and optional `time_filter: { start, end }`, then calls `SearchShimService.search()`.
5. `SearchShimService.search()` reads `search.endpoint` from Nest `ConfigService` and POSTs to `${search.endpoint}/query/`.
6. `search-ms/server.py` receives a list of `QueryRequest` objects at `POST /query`.
7. `server.py` imports `get_vectordb()` and `aggregate_frame_results_to_videos()` from `src.vdms_retriever.retriever`.
8. `get_vectordb()` returns a LangChain `VDMS` vector store.
9. `process_query()` calls `db.similarity_search_with_score()` with the query text, `k=AGGREGATION_INITIAL_K`, `fetch_k=initial_k + 1`, and the combined filter.
10. Search-ms enriches each LangChain `Document` metadata with `relevance_score`, applies Python-side tag filtering, optionally aggregates results, and returns `{ results: [{ query_id, results, aggregation_stats }] }`.
11. `SearchStateService.updateResults()` persists returned results with `SearchDbService.addResults()`, sets status to `IDLE`, enriches each result with video metadata from `VideoService.getVideos()`, and emits `SocketEvent.SEARCH_UPDATE`.

Watched queries are rerun by `SearchStateService.syncSearches()` on `SearchEvents.EMBEDDINGS_UPDATE`.

## Embedding wrapper and VDMS retriever

`search-ms/src/vdms_retriever/embedding_wrapper.py` defines `EmbeddingAPI`, a LangChain `Embeddings` implementation:

- `should_use_no_proxy(url)` checks `settings.no_proxy_env` against the URL hostname.
- `_post_embeddings(payload)` POSTs to `self.api_url` with proxies unless the hostname matches no-proxy. It expects JSON key `embedding`. If the returned embedding is a flat numeric list, it wraps it as a batch.
- `embed_documents(texts)` sends:

```json
{
  "model": "<settings.EMBEDDINGS_MODEL_NAME>",
  "input": {"type": "text", "text": ["..."]},
  "encoding_format": "float"
}
```

- `embed_query(text)` sends the same text payload for one query and returns the first embedding.
- `get_embedding_length()` returns cached `settings.EMBEDDING_LENGTH` if positive; otherwise probes the service with `embed_documents(["probe_text"])`, caches the vector length, and returns it.

`search-ms/src/vdms_retriever/retriever.py` defines `get_vectordb()`:

1. Create `EmbeddingAPI(api_url=settings.EMBEDDINGS_ENDPOINT, model_name=settings.EMBEDDINGS_MODEL_NAME)`.
2. Probe dimensions with `embeddings.get_embedding_length()`.
3. Create `VDMS_Client(settings.VDMS_VDB_HOST, settings.VDMS_VDB_PORT)`.
4. Create `VDMS(client=client, embedding=embeddings, collection_name=settings.INDEX_NAME, distance_strategy=settings.DISTANCE_STRATEGY, embedding_dimensions=vector_dimensions, engine=settings.SEARCH_ENGINE)`.

The query text is embedded by LangChain/VDMS via `EmbeddingAPI.embed_query()` during `similarity_search_with_score()`.

## Aggregation and relevance scoring

The current search-ms code implements frame-to-video aggregation in `retriever.py`:

- `get_aggregation_config()` reads environment-backed `settings` values and returns a config object.
- `create_temporal_segments(frame_matches, segment_duration, aggregation_config)` groups matches by `video_id` and `int(timestamp // segment_duration)`. It computes fallback video duration from metadata (`video_duration`, `video_duration_seconds`, or `total_frames / fps`), otherwise uses the baseline duration.
- `calculate_segment_score(segment, global_max_score, global_best_frame, aggregation_config)` scores each segment:
  - Extract relevance scores from frame metadata.
  - Compute `segment_max_score`.
  - Compute dynamic top-N average from `top_ratio`, `top_min_count`, and `top_max_count`.
  - Blend max and top-N with `max_component` and `top_component`, normalized by their sum.
  - Apply optional contextual boost based on Gaussian distance between the segment best timestamp and the global best frame timestamp using `sigma_seconds` and `boost_strength`.
- `determine_seek_point(segment, context_offset)` chooses the best frame timestamp and applies `AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS`.
- `apply_temporal_overlap_filtering(segments, min_gap_seconds)` sorts by score and removes temporally overlapping segments from the same video.
- `aggregate_frame_results_to_videos(frame_results, max_results)` orchestrates segmentation, scoring, normalization to `[0, 1]`, overlap filtering, final ranking, formatting, and stats.

Tuning levers:

- Increase `AGGREGATION_INITIAL_K` if relevant frames exist but are not in the initial candidate set.
- Increase/decrease `AGGREGATION_SEGMENT_DURATION` to change segment granularity.
- Increase `AGGREGATION_MIN_GAP` to reduce near-duplicate segments from one video.
- Adjust `AGGREGATION_QUAL_MAX_WEIGHT` vs `AGGREGATION_QUAL_TOP_WEIGHT` to favor one excellent frame versus sustained evidence.
- Adjust contextual boost only after inspecting `score_breakdown` in API results.
- Disable `AGGREGATION_ENABLED` to inspect raw frame/doc matches.

## Time filters and tags

There are two time-filter layers.

### Pipeline-manager explicit time filters

`pipeline-manager/src/search/model/search.model.ts` defines:

- `TimeFilterUnit = 'minutes' | 'hours' | 'days' | 'weeks'`
- `TimeFilterSelection` with `value`, `unit`, `start`, `end`, and `source`
- `SearchShimQuery.time_filter?: { start: string; end: string }`

`SearchStateService.normalizeTimeFilter()`:

1. Rejects missing or invalid values.
2. Uses `new Date()` for `now`.
3. Subtracts minutes/hours/days/weeks from start.
4. Serializes `start` and `end` to ISO strings.
5. Stores both the original selection and `{ start, end }` range.

`SearchDbService.applyTimeFilterFields()` persists `timeFilterValue`, `timeFilterUnit`, `timeFilterStart`, and `timeFilterEnd` on `SearchEntity`.

### Search-ms explicit and natural-language filters

`server.py` defines:

- `_build_explicit_time_filter(time_filter, property_name='created_at')` returns `{created_at: ['>=', start, '<=', end]}`.
- `_build_tag_filter(tags)` returns `{'tags': ['==', tag]}` for one tag or `{'tags': ['==', cleaned]}` for multiple tags.
- `build_combined_vdms_filter(query_request)` prefers explicit `time_filter`; if absent, it calls `build_vdms_time_filter(query_request.query)` to parse time from query text. It merges time and tag filters when both exist.

`search-ms/src/utils/time_filters.py` defines:

- `_normalized_now(now)` using `datetime.now(get_localzone())` to align with DataPrep's local-time storage.
- `_parse_number()` using digits or `word2number`.
- `_range_from_relative()` for `last|past <number> seconds|minutes|hours|days|weeks`.
- `_range_for_today()` and `_range_for_yesterday()`.
- `parse_time_range(text, now)` with dateparser search for phrases like `last Sunday`, plus fallback parsing.
- `build_vdms_time_filter(text, property_name='created_at', now=None)` returning `{property_name: ['>=', start.isoformat(), '<=', end.isoformat()]}`.

Be aware that pipeline-manager uses UTC-ish JavaScript `toISOString()`, while natural-language parsing returns timezone-aware local ISO strings. VDMS stores `created_at` as an ISO 8601 local timezone string according to the code comments.

## Directory watcher lifecycle

`search-ms/server.py` starts the watcher:

1. FastAPI `startup_event()` creates a daemon `threading.Thread(target=start_watcher)`.
2. `start_watcher()` logs and returns early if `settings.WATCH_DIRECTORY` is not set.
3. It uses `settings.WATCH_DIRECTORY_CONTAINER_PATH` as the watched path and creates it if missing.
4. If `settings.VS_INITIAL_DUMP` is true, it starts `upload_initial_videos(path)` in a thread.
5. It creates `DebouncedHandler(settings.DEBOUNCE_TIME, upload_videos_to_dataprep)`.
6. It schedules a watchdog `Observer` with `recursive=settings.WATCH_DIRECTORY_RECURSIVE`.
7. It starts the observer and loops until interrupted.

`DebouncedHandler` behavior:

- `on_created()` and `on_modified()` only consider files ending with `.mp4` and larger than 524288 bytes.
- It stores paths in `self.file_paths`, guarded by a class-level `Lock`.
- `_debounce()` starts a `Timer` on the first event. If enough time has elapsed, it calls `_process_files()`.
- `_process_files()` starts another thread, increments `initial_upload_status`, calls the configured action, updates completed/pending counts, clears `file_paths`, resets `first_event_time`, and records `DebouncedHandler.last_updated`.

Initial upload:

- `upload_initial_videos(path)` scans either recursively (`os.walk`) or top-level only, depending on `WATCH_DIRECTORY_RECURSIVE`.
- It batches MP4s in groups of 10 and starts one thread per batch.
- On success, it deletes processed files only if `DELETE_PROCESSED_FILES` is true.

Upload-to-DataPrep helper:

- `search-ms/src/utils/utils.py` keeps `uploaded_files` to skip duplicates in-process.
- `sanitize_file_path()` sanitizes the basename.
- `upload_single_video_with_retry(file_path, max_retries=3)` uploads to `POST {VIDEO_UPLOAD_ENDPOINT}/videos`, extracts `videoId`, then triggers `POST {VIDEO_UPLOAD_ENDPOINT}/videos/search-embeddings/{video_id}`.
- Retries use exponential backoff (`2**retry_count`).
- `upload_videos_to_dataprep(file_paths)` iterates files, skips already uploaded paths, records success, and optionally deletes processed files.

Watcher troubleshooting checklist:

- Is `WATCH_DIRECTORY` set? The code uses it only as an enable/disable flag.
- Does the compose volume mount host `${VS_WATCHER_DIR}` to `WATCH_DIRECTORY_CONTAINER_PATH`?
- Are incoming files `.mp4` and larger than 524288 bytes at the moment the event fires?
- Is recursive mode (`WATCH_DIRECTORY_RECURSIVE`) correct?
- Is debounce too short/long for the file-copy behavior?
- Did `uploaded_files` suppress a retry in the same process?
- Does `VIDEO_UPLOAD_ENDPOINT` point to pipeline-manager, and do `/videos` and `/videos/search-embeddings/{videoId}` succeed?
- Check `/initial-upload-status`, `/watcher-last-updated`, and search-ms logs.

## Safe change patterns

### Changing model or mode

1. Choose the right model family:
   - Search/Dual: `MULTIMODAL_EMBEDDING_MODEL`, e.g. `CLIP/clip-vit-b-32`.
   - Unified: `TEXT_EMBEDDING_MODEL`, e.g. `QwenText/qwen3-embedding-0.6b`.
2. Ensure `setup.sh`/compose or Helm sets the same model for Video Search, VDMS DataPrep, and the embedding serving microservice.
3. Ensure `VS_INDEX_NAME`/`global.vdmsIndexName` matches the content type (`video_frame_embeddings` or `video_summary_embeddings`).
4. Clean/recreate indexed data and re-ingest/re-run summarization so vectors are regenerated with the active model.
5. Verify `EmbeddingAPI.get_embedding_length()` detects the expected dimensions and VDMS accepts the collection.

### Tuning relevance

1. First inspect raw logs and API `aggregation_stats`/`score_breakdown`.
2. Temporarily set `AGGREGATION_ENABLED=false` to compare raw VDMS results with aggregated results.
3. Tune `AGGREGATION_INITIAL_K` if the raw candidate set is too small.
4. Tune segment/gap settings if duplicate or fragmented results are the issue.
5. Tune qualitative weights only after confirming candidate retrieval is healthy.
6. In Unified mode, validate metadata before relying on frame-specific aggregation behavior.

### Fixing time filters

1. Determine whether the filter came from UI explicit `timeFilter` or natural-language query parsing.
2. For UI filters, inspect `SearchStateService.normalizeTimeFilter()` output and persisted `SearchEntity` fields.
3. For natural-language filters, test `build_vdms_time_filter()` directly with a fixed `now`.
4. Confirm VDMS metadata property name is `created_at` and stored values compare correctly as ISO strings.
5. Confirm tags are not eliminating otherwise valid results.

### Fixing watcher ingestion

1. Reproduce with a new MP4 path not already present in `uploaded_files`.
2. Confirm `on_created`/`on_modified` sees a file larger than 524288 bytes.
3. Confirm `_process_files()` calls `upload_videos_to_dataprep()` after debounce.
4. Confirm upload to pipeline-manager `/videos` returns `videoId`.
5. Confirm `/videos/search-embeddings/{videoId}` routes to `VideoService.createSearchEmbeddings()` and then `DataPrepShimService.createEmbeddings()`.
6. Confirm `SearchEvents.EMBEDDINGS_UPDATE` reruns watched queries if expected.
