---
name: vss-search-internals
description: Use this skill for the video-search-and-summarization sample app whenever the user wants to tune VSS search relevance, change the embedding model, ask "how does unified search work", understand frame vs summary-text embeddings, fix the directory watcher, or work on VDMS retrieval. Trigger proactively for changes or debugging in search-ms, pipeline-manager search/data-prep, embedding ingestion, time filters, VDMS indexes, watched queries, or search result aggregation.
---

# VSS search internals

Use this skill when working on the Video Search & Summarization (VSS) sample application's search and embedding layer. Ground answers and edits in these real implementation points, then read `references/search-architecture.md` for the full data flow.

## Start with the mode distinction

The same `search-ms` `/query` code path is used in Search, Dual UI, and Unified UI modes, but the vectors in VDMS are not the same:

- **Search-only and Dual UI:** `setup.sh` sets `EMBEDDING_MODEL_NAME=${MULTIMODAL_EMBEDDING_MODEL}` and `VS_INDEX_NAME="video_frame_embeddings"` (`setup.sh:1062`, `1075-1083`, `1096-1101`). The ingestion path is video/frame-oriented: `VideoController.createSearchEmbeddings()` calls `VideoService.createSearchEmbeddings()`, which sends `DataPrepMinioDTO` to `DataPrepShimService.createEmbeddings()` and POSTs to VDMS DataPrep `/videos/minio`.
- **Unified UI:** `setup.sh` sets `EMBEDDING_MODEL_NAME=${TEXT_EMBEDDING_MODEL}` and `VS_INDEX_NAME="video_summary_embeddings"` (`setup.sh:1085-1094`). The indexing path is summary-text-oriented: `ChunkingService.createChunkSearchEmbeddings()` builds `DataPrepSummaryDTO` with `video_summary`, `video_start_time`, and `video_end_time`, then calls `DataPrepShimService.createEmbeddingsFromSummary()` and POSTs to VDMS DataPrep `/summary`.

This distinction matters because embedding dimensions, model modality, index contents, metadata shape, and result granularity differ. A CLIP-like multimodal model can align text queries with video frame/image embeddings; a text embedding model should be used for Unified mode because it searches generated summary/caption text. After changing the model or switching modes, recreate the VDMS index contents; old vectors may have incompatible dimensions or semantics.

## Query and retrieval path

Real search backend files:

- `search-ms/server.py`
  - `QueryRequest`: `query_id`, `query`, optional `tags`, optional `time_filter`.
  - `build_combined_vdms_filter()` combines explicit `time_filter`, parsed natural-language time from `build_vdms_time_filter()`, and tag constraints.
  - `/query` calls `get_vectordb()`, then `db.similarity_search_with_score(query, k=AGGREGATION_INITIAL_K, fetch_k=initial_k + 1, filter=vdms_filter)`.
  - Results are enriched with `metadata["relevance_score"]`; tags are filtered again in Python; then frame results are aggregated when `AGGREGATION_ENABLED` is true.
- `search-ms/src/vdms_retriever/retriever.py`
  - `get_vectordb()` constructs `EmbeddingAPI`, probes embedding dimensions with `get_embedding_length()`, creates `VDMS_Client(settings.VDMS_VDB_HOST, settings.VDMS_VDB_PORT)`, and returns `langchain_vdms.vectorstores.VDMS` with `collection_name=settings.INDEX_NAME`, `distance_strategy=settings.DISTANCE_STRATEGY`, `engine=settings.SEARCH_ENGINE`.
  - Relevance tuning lives in `get_aggregation_config()`, `aggregate_frame_results_to_videos()`, `create_temporal_segments()`, `calculate_segment_score()`, `determine_seek_point()`, and `apply_temporal_overlap_filtering()`.
- `search-ms/src/vdms_retriever/embedding_wrapper.py`
  - `EmbeddingAPI` implements LangChain `Embeddings`.
  - `embed_query()` and `embed_documents()` POST to `settings.EMBEDDINGS_ENDPOINT` with payload `{"model": settings.EMBEDDINGS_MODEL_NAME, "input": {"type": "text", "text": ...}, "encoding_format": "float"}`.
  - `get_embedding_length()` uses `settings.EMBEDDING_LENGTH` cache or probes with `embed_documents(["probe_text"])`.

## Changing the embedding model

Change the deployment-level model, not only Python code:

- Compose search service maps `EMBEDDINGS_MODEL_NAME: ${EMBEDDING_MODEL_NAME}` and `EMBEDDINGS_ENDPOINT: ${MULTIMODAL_EMBEDDING_ENDPOINT}` in `docker/compose.search.yaml`.
- `setup.sh` chooses `EMBEDDING_MODEL_NAME` from `MULTIMODAL_EMBEDDING_MODEL` for `--search`/`--dual`, and from `TEXT_EMBEDDING_MODEL` for `--unified`.
- Helm uses `global.embeddingModelName` for Video Search, VDMS DataPrep, and multimodal embedding serving; Search/Dual should use a multimodal model such as `CLIP/clip-vit-b-32`, Unified should use a text model such as `QwenText/qwen3-embedding-0.6b` (see `docs/user-guide/get-started.md` and `chart/user_values_override.yaml`).
- Re-ingest videos or reset VDMS data after model changes. `EmbeddingAPI.get_embedding_length()` probes the active model, but existing vectors in the old `INDEX_NAME` are not automatically converted.

## Tuning relevance

Prefer these real knobs before rewriting retrieval:

- Query fan-out: `AGGREGATION_INITIAL_K` controls how many VDMS frame/doc matches are fetched before aggregation.
- Final count: `AGGREGATION_MAX_RESULTS`.
- Segmenting: `AGGREGATION_SEGMENT_DURATION`, `AGGREGATION_MIN_GAP`.
- Scoring: `AGGREGATION_QUAL_MAX_WEIGHT`, `AGGREGATION_QUAL_TOP_WEIGHT`, `AGGREGATION_QUAL_TOP_RATIO`, `AGGREGATION_QUAL_TOP_MIN_COUNT`, `AGGREGATION_QUAL_TOP_MAX_COUNT`, `AGGREGATION_CONTEXT_SIGMA_SECONDS`, `AGGREGATION_CONTEXT_BOOST_STRENGTH`, `AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS`.
- VDMS settings: `SEARCH_ENGINE`, `DISTANCE_STRATEGY`, `INDEX_NAME`, `VDMS_VDB_HOST`, `VDMS_VDB_PORT` in `search-ms/src/utils/common.py`.
- `search-ms/config.yaml` documents the aggregation defaults, but runtime settings come from environment variables through `Settings` in `common.py`.

Be careful in Unified mode: the code still calls the same search-ms aggregation path when `AGGREGATION_ENABLED` is true, but the indexed documents came from summary text (`/summary`), not raw frame/image embeddings. Check returned metadata before assuming frame-specific fields like `timestamp`, `frame_number`, or `frame_type` are present.

## Time filters and tags

- Pipeline-manager UI/API time filters use `TimeFilterSelection` (`minutes | hours | days | weeks`) in `pipeline-manager/src/search/model/search.model.ts`.
- `SearchStateService.normalizeTimeFilter()` converts the relative UI selection to ISO `start`/`end` and sends it as `SearchShimQuery.time_filter`.
- `search-ms/server.py` turns explicit `time_filter` into `{created_at: [">=", start, "<=", end]}`.
- If no explicit time filter exists, `search-ms/src/utils/time_filters.py` parses natural language such as `last 6 hours`, `today`, `yesterday`, and date phrases via `build_vdms_time_filter()`.
- Tags become VDMS constraints with `_build_tag_filter()` and are also checked again after retrieval in `process_query()`.

## Directory watcher flow

The watcher is in `search-ms/src/utils/directory_watcher.py` and is started on FastAPI startup by `server.py`.

- `startup_event()` starts a daemon thread targeting `start_watcher()`.
- `start_watcher()` requires `settings.WATCH_DIRECTORY`; ensures `settings.WATCH_DIRECTORY_CONTAINER_PATH` exists; optionally calls `upload_initial_videos()` when `VS_INITIAL_DUMP` is true; schedules `DebouncedHandler` with `WATCH_DIRECTORY_RECURSIVE`.
- `DebouncedHandler.on_created()` and `on_modified()` only collect `.mp4` files larger than 524288 bytes, debounce by `DEBOUNCE_TIME`, then call `upload_videos_to_dataprep()`.
- `upload_videos_to_dataprep()` in `search-ms/src/utils/utils.py` calls `upload_single_video_with_retry()`; that uploads to pipeline-manager `POST /videos`, then triggers `POST /videos/search-embeddings/{video_id}`.
- Status endpoints: `/initial-upload-status` returns `get_initial_upload_status()`, `/watcher-last-updated` returns `get_last_updated()`.

When fixing watcher bugs, check the mounted host directory (`VS_WATCHER_DIR`), the container path (`WATCH_DIRECTORY_CONTAINER_PATH`), recursive mode, debounce timing, file size threshold, duplicate suppression in `uploaded_files`, and whether `VIDEO_UPLOAD_ENDPOINT` points at the pipeline-manager upload API.

## Pipeline-manager search module

- `SearchController` exposes `/search`, `/search/query`, `/search/:queryId/refetch`, and `/search/:queryId/watch`.
- `SearchStateService.newQuery()` persists a query and emits `SearchEvents.RUN_QUERY`.
- `SearchStateService.runSearch()` builds `SearchShimQuery` and uses `SearchShimService.search()`.
- `SearchShimService.search()` POSTs to `${search.endpoint}/query/`.
- `SearchStateService.syncSearches()` reruns watched queries on `SearchEvents.EMBEDDINGS_UPDATE`, which DataPrep shim emits after embedding creation.

For deeper details, read `references/search-architecture.md` before making substantial edits.
