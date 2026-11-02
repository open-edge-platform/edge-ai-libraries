# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Engine service configuration.

Only what differs between deployments is read from the environment: where the
service listens, where its state lives, which models it loads and on which
device, and the language of the corpus. Local models must be prepared before
the engine starts; it never downloads or exports missing models. Everything
else is a module constant -- tuning that a request or a source can already
override per call, and internal limits that no deployment should need to change.
"""

import json
import os
from pathlib import Path


def _env_int(
    name: str, default: int, *, minimum: int = 1, maximum: int | None = None
) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from error
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(
            f"{name} must be >= {minimum}"
            + (f" and <= {maximum}" if maximum is not None else "")
        )
    return value


HOST = os.getenv("ENGINE_HOST", "0.0.0.0")
PORT = _env_int("ENGINE_PORT", 16022, maximum=65535)
# Level of the engine's own log lines (background jobs, sync, extraction).
LOG_LEVEL = os.getenv("ENGINE_LOG_LEVEL", "INFO").upper()
CORS_ALLOW_ORIGINS = ["*"]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]
# Default page size of `GET /v1/libraries/{library}/assets`; `page_size` overrides.
ASSET_PAGE_SIZE = 20

# --- Workspace ----------------------------------------------------------------
# One directory holds runtime state: the Milvus stack's volumes, uploaded files,
# and persisted asset libraries. Models live here by default but can share an
# external collection through ENGINE_MODEL_ROOT_PATH. Back up that collection
# as well when it is outside the workspace.
#
#   workspace/
#     milvus/{etcd,minio,db}       Milvus stack data (bind-mounted by compose)
#     models/                      embedding + rerank models
#     uploads/                     uploaded files, ingested from here
#     content/                     asset content: blobs and content streams
#     configs/asset_library.json   the asset libraries themselves
#     configs/databases.json       the database connections they write to
WORKSPACE_DIR = os.getenv(
    "ENGINE_WORKSPACE", str(Path(__file__).resolve().parents[1] / "workspace")
)
MILVUS_DIR = os.path.join(WORKSPACE_DIR, "milvus")
# Every local model capability shares this root. Empty uses the workspace
# default, just like an unset variable; individual paths are derived below.
MODEL_DIR = os.getenv("ENGINE_MODEL_ROOT_PATH") or os.path.join(WORKSPACE_DIR, "models")
# Further roots a bare model name is looked up under, after MODEL_DIR: the legacy
# `MODEL_PATH` variable, then `~/models` of the process user.
LEGACY_MODEL_DIR = os.getenv("MODEL_PATH", "")
SHARED_MODEL_DIR = str(Path.home() / "models")
# A service that uploads files for the engine writes them here (same path in both
# containers), and the engine ingests them from here.
UPLOAD_DIR = os.getenv("ENGINE_UPLOAD_DIR", os.path.join(WORKSPACE_DIR, "uploads"))
CONFIG_DIR = os.path.join(WORKSPACE_DIR, "configs")
# Where asset content goes when nothing else has been registered to hold it.
# `DatabaseHubManager.ensure_content_database` registers a filesystem object
# database rooted here the first time a library needs somewhere to put content,
# so an ingest cannot fail for want of an object store.
CONTENT_DIR = os.path.join(WORKSPACE_DIR, "content")
ASSET_LIBRARY_FILE = os.path.join(CONFIG_DIR, "asset_library.json")
DATABASE_FILE = os.path.join(CONFIG_DIR, "databases.json")

for _directory in (MODEL_DIR, UPLOAD_DIR, CONFIG_DIR, CONTENT_DIR):
    try:
        os.makedirs(_directory, exist_ok=True)
    except OSError as _error:  # read-only mount: the engine still serves, minus persistence
        print(f"Engine workspace directory {_directory} is not writable: {_error}")

# --- Databases ----------------------------------------------------------------
# There is deliberately nothing here.
#
# Database connections used to be configured through this file -- MILVUS_URI,
# NEBULA_URI, POSTGRES_DSN, the MinIO credentials, one default backend per
# category -- and `DatabaseHubManager.__init__` registered four fixed ids from
# them at import time. That made a connection a deployment-time decision: you
# could not point the engine at a second Milvus, could not change one without a
# restart, and could not ask what it was connected to.
#
# They are runtime state now: registered over HTTP (`api/databases.py`),
# persisted in DATABASE_FILE, restored before the asset libraries that name
# them. A fresh engine is connected to nothing until something registers a
# database, which is the intended behaviour and not a missing default.

# --- Node parser --------------------------------------------------------------
# A chunk never spans two content blocks -- the projection parses each block on
# its own so every chunk keeps the page it came from -- so a block shorter than
# CHUNK_SIZE stays a short chunk rather than merging with the next one.
# Per-source override: `operator_options.chunk_size` / `chunk_overlap`.
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
# Characters of neighbouring text, per side, that go into a figure's node. A
# figure has no text of its own, so its caption plus this window is the whole of
# what a query can match against. Per-source override:
# `operator_options.figure_context_chars`.
FIGURE_CONTEXT_CHARS = 400

# --- Streaming materialization ------------------------------------------------
# A vector projection embeds an asset's nodes through a producer/consumer pipeline
# (`core/materialize.py`): a producer builds nodes block by block onto a bounded
# queue, a single consumer micro-batches and embeds them. BATCH_SIZE is how many
# nodes are embedded and inserted at once (one GME call per modality per batch);
# QUEUE_MAX bounds how many built-but-unembedded nodes may wait, so a huge
# document does not build every node before any is embedded (backpressure).
INGEST_BATCH_SIZE = 16
INGEST_QUEUE_MAX = 64

# --- Model providers ----------------------------------------------------------
# These names describe how the engine reaches a model, not the model family:
#   llamaindex_openvino -> LlamaIndex/Optimum adapter over a standard OV IR
#   openvino_genai      -> OpenVINO GenAI text pipeline
#   openai_compatible   -> remote OpenAI-compatible HTTP endpoint (vLLM, TEI, ...)
#   native_openvino_gme -> model-specific native OV runtime for multimodal GME
#
# Embedding and rerank share this list for now. Some providers are
# capability-specific: native_openvino_gme is embedding-only and the reranker
# factory rejects it if selected there.
MODEL_BACKENDS = (
    "llamaindex_openvino",
    "openvino_genai",
    "openai_compatible",
    "native_openvino_gme",
)
# Providers that load a model directory out of the workspace, so a caller (the
# UI) picks one of the models found there rather than typing a remote model name.
LOCAL_MODEL_BACKENDS = (
    "llamaindex_openvino",
    "openvino_genai",
    "native_openvino_gme",
)

# Persisted source options and deployment environments may still use the old
# names. Normalize them at each construction boundary instead of requiring a
# coordinated migration of existing workspaces.
_MODEL_BACKEND_ALIASES = {
    "openvino": "llamaindex_openvino",
    "openai": "openai_compatible",
    "gme": "native_openvino_gme",
}


def normalize_model_backend(value: str) -> str:
    normalized = _MODEL_BACKEND_ALIASES.get(value.lower(), value.lower())
    if normalized not in MODEL_BACKENDS:
        raise ValueError(
            f"model backend must be one of {', '.join(MODEL_BACKENDS)}, got {value!r}"
        )
    return normalized


def _backend(env: str, default: str = "llamaindex_openvino") -> str:
    try:
        return normalize_model_backend(os.getenv(env) or default)
    except ValueError as error:
        raise ValueError(f"invalid {env}: {error}") from error


# --- Document embedding model -------------------------------------------------
EMBEDDING_BACKEND = _backend("ENGINE_DOC_EMBEDDING_BACKEND", "native_openvino_gme")
EMBEDDING_MODEL_ID = os.getenv(
    "ENGINE_DOC_EMBEDDING_MODEL_ID", "gme-Qwen2-VL-2B-Instruct-OV"
)
EMBEDDING_MODEL_PATH = os.path.join(
    MODEL_DIR, EMBEDDING_MODEL_ID.rsplit("/", 1)[-1]
)
EMBEDDING_DEVICE = os.getenv("ENGINE_DOC_EMBEDDING_DEVICE", "CPU")
EMBEDDING_API_BASE = os.getenv("ENGINE_DOC_EMBEDDING_API_BASE", "")  # openai_compatible
EMBEDDING_API_KEY = os.getenv("ENGINE_DOC_EMBEDDING_API_KEY", "unused")
# Model properties are parsed from the model directory, never read from the
# environment. The GME package carries its own precision, dim and lengths in
# gme_openvino_config.json (inference.gme_runtime); the two helpers below serve the
# openvino_genai text backend.
# Upper bound on the input length: openvino_genai pads every input to it, so a
# model's full context (8192 for bge-m3) would make each call that long.
EMBEDDING_MAX_LENGTH = 512
# Pooling when the model declares none. BGE-family dense retrievers (bge-m3,
# bge-*) are trained for CLS (first-token) pooling; using mean collapses recall
# (bge-m3 R@20 0.66 -> 0.44 on an internal recall set).
EMBEDDING_POOLING = "cls"


def _model_json(model_path: str, name: str) -> dict:
    try:
        with open(os.path.join(model_path, name), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def embedding_max_length(model_path: str) -> int:
    """The model's tokenizer ``model_max_length``, capped at EMBEDDING_MAX_LENGTH."""
    declared = _model_json(model_path, "tokenizer_config.json").get("model_max_length")
    if isinstance(declared, int) and 0 < declared < EMBEDDING_MAX_LENGTH:
        return declared
    return EMBEDDING_MAX_LENGTH


def embedding_pooling(model_path: str) -> str:
    """The pooling a sentence-transformers export declares (1_Pooling/config.json)."""
    pooling = _model_json(model_path, os.path.join("1_Pooling", "config.json"))
    if pooling.get("pooling_mode_mean_tokens"):
        return "mean"
    return EMBEDDING_POOLING
# Optional system instruction for the fused (image+text) corpus side of a
# multimodal model. None keeps the model's default document instruction -- which
# honours GME's query/document asymmetry (a task instruction on the query, the
# default on documents); set it only to deliberately steer fused embeddings.
EMBEDDING_FUSED_INSTRUCTION = None

OPENVINO_CONFIG = {"NUM_STREAMS": "1", "PERFORMANCE_HINT": "LATENCY"}
GME_BATCH_SIZE = 32
IMAGE_LOAD_WORKERS = max(1, min((os.cpu_count() or 1) // 2, 8))
IMAGE_HTTP_TIMEOUT = 30.0  # seconds

# --- Reranker (postprocessing) ------------------------------------------------
RERANK_BACKEND = _backend("ENGINE_RERANK_BACKEND")
RERANK_MODEL_ID = os.getenv("ENGINE_RERANK_MODEL_ID", "BAAI/bge-reranker-large")
# Preserve vendor subdirectories used by existing reranker exports.
RERANK_MODEL_PATH = os.path.join(MODEL_DIR, RERANK_MODEL_ID)
RERANK_DEVICE = os.getenv("ENGINE_RERANK_DEVICE", "CPU")
RERANK_API_BASE = os.getenv("ENGINE_RERANK_API_BASE", "")  # openai_compatible
RERANK_API_KEY = os.getenv("ENGINE_RERANK_API_KEY", "unused")
REMOTE_RERANK_TIMEOUT = 120.0  # seconds

# Media reranking is requested through the existing postprocess field. Keep its
# defaults separate from text reranking: an unset media model must never select
# bge-reranker-large.
MEDIA_RERANK_BACKEND = os.getenv("ENGINE_MEDIA_RERANK_BACKEND", "openvino_vl")
if MEDIA_RERANK_BACKEND != "openvino_vl":
    raise ValueError("ENGINE_MEDIA_RERANK_BACKEND must be openvino_vl")
MEDIA_RERANK_MODEL_ID = os.getenv(
    "ENGINE_MEDIA_RERANK_MODEL_ID", "Qwen/Qwen3-VL-Reranker-2B-INT8"
)
MEDIA_RERANK_MODEL_PATH = os.path.join(
    MODEL_DIR, f"{MEDIA_RERANK_MODEL_ID.rsplit('/', 1)[-1]}-OV"
)
MEDIA_RERANK_DEVICE = os.getenv("ENGINE_MEDIA_RERANK_DEVICE", "GPU")
MEDIA_RERANK_VIDEO_MAX_FRAMES = _env_int("MEDIA_RERANK_VIDEO_MAX_FRAMES", 8)
# Parallel workers for loading rerank candidates' media (blob reads + video
# decode) before scoring; that phase outweighs scoring itself.
MEDIA_RERANK_DOC_WORKERS = _env_int("ENGINE_MEDIA_RERANK_DOC_WORKERS", 8, maximum=32)

# --- Layout detection (multimodal PDF) ----------------------------------------
# The layout detector is a standalone capability, not a llama-index component, so
# it has its own backend list rather than sharing MODEL_BACKENDS (embedding/rerank
# backends). "openvino" runs a cached ONNX model through OpenVINO; "torch" is
# the explicit reference path over the source model. Only PP-DocLayoutV3 is
# supported, so backend and model are fixed here rather than deployment settings.
LAYOUT_BACKENDS = ("openvino", "torch")
LAYOUT_BACKEND = "openvino"
LAYOUT_MODEL_ID = "PaddlePaddle/PP-DocLayoutV3_safetensors"
LAYOUT_MODEL_PATH = os.path.join(MODEL_DIR, "PP-DocLayoutV3")
LAYOUT_DEVICE = os.getenv("ENGINE_LAYOUT_DEVICE", "CPU")
# Detections below this confidence are dropped before a block is emitted.
LAYOUT_SCORE_THRESHOLD = 0.3

# --- OCR (multimodal PDF) -----------------------------------------------------
# PP-DocLayout only draws boxes, so every block's text comes from a separate OCR
# step. Like layout, OCR is a standalone capability with its own backend list.
# The only caller of the OCR module is the scanned path (`extract_layout`), reached
# only when the PDF has NO text layer on any page -- so the PDF text layer yields
# nothing there and "tesseract" is the right default. A digital PDF never reaches
# this module (it reads its text layer directly in `extract_layout_digital`), which
# is why "hybrid"/"pdfplumber" are kept as selectable backends (for a direct
# `extract_layout` caller or the text-layer-read-error fallback) but not the default.
OCR_BACKENDS = ("hybrid", "tesseract", "pdfplumber")
OCR_BACKEND = "tesseract"
# Tesseract recognition languages (Chinese + English).
OCR_LANG = "zh_cn+en"

# Resolution a PDF page is rendered at, for layout detection and figure crops.
LAYOUT_RENDER_DPI = 150

# A figure's caption (`Figure 3`) often sits just *below* the detected box, so a
# figure whose own text carries no caption key cannot be paired by key. When this
# ratio is > 0, such a figure's text is re-read from a box extended downward by
# that fraction of its height, pulling the caption line (and its key) in; the
# stored crop is unchanged -- only the text read for pairing grows. 0 disables it.
# Off by default (like the POC): it adds an OCR re-read per keyless figure and can
# pull in adjacent prose, so it is opt-in and tuned per corpus (the POC swept
# 0.1-0.5). Ported from mmdir `related_text_extract.caption_fallback_bbox_extend_ratio`.
LAYOUT_CAPTION_FALLBACK_EXTEND_RATIO = 0.0

# --- Multimodal ingestion -----------------------------------------------------
# A media file is embedded by a model that can see it, rather than by the text
# model embedding its caption. Configured exactly like the text model above: a
# runtime (`*_BACKEND`), a model (`*_MODEL_ID`, a Hugging Face id), the shared
# ENGINE_MODEL_ROOT_PATH and a device. A source's `operator_options` can still
# override individual model paths; which models are multimodal, and what they
# can embed, is decided by the model (core/multimodal/registry.py), not these names.

# Assets per write while a newly attached source catches up with a pool
# (assetlib/sources/backfill.py). Bounds memory and makes a failed backfill
# resume where it stopped; it does not change what is written.
BACKFILL_BATCH_SIZE = 32

# Where a video stops being short enough to hand to a vision model whole: the
# extractor gives it the `short_video` or `long_video` role by this. A long one
# needs L1 segments first, which are not implemented yet, so it is stored and
# reported as uncovered (core/multimodal/coverage.py).
SHORT_VIDEO_MAX_SECONDS = 60.0

# Video: X-CLIP, with its checkpoint and OpenVINO IR prepared beforehand.
VIDEO_EMBEDDING_BACKEND = _backend("ENGINE_VIDEO_EMBEDDING_BACKEND")
VIDEO_EMBEDDING_MODEL_ID = os.getenv(
    "ENGINE_VIDEO_EMBEDDING_MODEL_ID", "microsoft/xclip-base-patch16-zero-shot"
)
VIDEO_EMBEDDING_MODEL_PATH = os.path.join(
    MODEL_DIR, VIDEO_EMBEDDING_MODEL_ID.rsplit("/", 1)[-1]
)
VIDEO_EMBEDDING_DEVICE = os.getenv("ENGINE_VIDEO_EMBEDDING_DEVICE", "CPU")

# Images (and the text derived from media): GME-Qwen2-VL, from an exported
# OpenVINO package that has to be in place -- it cannot be prepared from its id.
IMAGE_EMBEDDING_BACKEND = _backend("ENGINE_IMAGE_EMBEDDING_BACKEND")
IMAGE_EMBEDDING_MODEL_ID = os.getenv(
    "ENGINE_IMAGE_EMBEDDING_MODEL_ID", "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"
)
IMAGE_EMBEDDING_MODEL_PATH = os.path.join(
    MODEL_DIR,
    "gme-Qwen2-VL-2B-Instruct-OV"
    if IMAGE_EMBEDDING_MODEL_ID == "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"
    else IMAGE_EMBEDDING_MODEL_ID.rsplit("/", 1)[-1],
)
IMAGE_EMBEDDING_DEVICE = os.getenv("ENGINE_IMAGE_EMBEDDING_DEVICE", "CPU")

# Speech recognition, which writes `l2_transcript` blocks for audio
# (core/multimodal/transcription.py) in the background after ingest. Not an
# embedding model, so it is not in the multimodal registry: the transcript is
# text, embedded by whichever source takes derived text (GME). Only `openvino`
# is implemented; its IR and processor/tokenizer must already be prepared at
# the configured path or under its `openvino/` subdirectory.
# Like layout, this is a standalone capability with one implemented runtime,
# not a llama-index embedding provider. In particular it must not normalize to
# llamaindex_openvino, which the Whisper loader cannot run.
ASR_BACKEND = "openvino"
ASR_MODEL_ID = os.getenv("ENGINE_ASR_MODEL_ID", "openai/whisper-small")
ASR_MODEL_PATH = os.path.join(
    MODEL_DIR, ASR_MODEL_ID.rsplit("/", 1)[-1]
)
ASR_DEVICE = os.getenv("ENGINE_ASR_DEVICE", "CPU")
# Spoken language as Whisper names it ("zh", "en", ...). Set it empty to detect
# per recording, which costs a little accuracy on short clips.
ASR_LANGUAGE = os.getenv("ENGINE_ASR_LANGUAGE", "zh")
# Text Whisper is conditioned on, as if it had just heard it; steers script and
# punctuation. For zh, a prompt that gets simplified characters (Whisper
# otherwise often writes traditional); for other languages, none.
ASR_PROMPT = "以下是普通话的句子。" if ASR_LANGUAGE == "zh" else ""
# Seconds of speech per transcript block, and so per vector: the unit a query
# matches and a result cites. Cut at the nearest pause before the limit.
# Default 30 s is Whisper's input window; longer joins several windows into one block.
ASR_SEGMENT_SECONDS = 30.0
# Off: audio is stored and found by its file name only, and no model is loaded.
ASR_ENABLED = os.getenv("ENGINE_ASR_ENABLED", "true").lower() in ("1", "true", "yes")

# --- Video summary service (captions) -------------------------------
# Empty base URL disables caption extraction: a short clip still gets its vector
# and its file-name caption, just no model-written description.
VIDEO_SUMMARY_BASE_URL = os.getenv("ENGINE_VIDEO_SUMMARY_BASE_URL", "")
VIDEO_SUMMARY_TASK = "summary"
VIDEO_SUMMARY_TIMEOUT = 300.0

# --- Retrieval defaults -------------------------------------------------------
# Used when a request omits `top_k` / `postprocess.top_n`.
RETRIEVE_TOP_K = 5   # per-method top-k
# Most concepts GET /asset_pools/{pool}/graph returns for drawing; beyond it the
# best-connected ones are kept.
GRAPH_VIEW_LIMIT = _env_int("ENGINE_GRAPH_VIEW_LIMIT", 1500)
RERANK_TOP_N = 3     # final result count
# RRF fusion smoothing constant k in `score += 1/(k + rank + 1)` (core/retrievers.py
# RRFRetriever). It is NOT the result count -- it damps how much a top rank outweighs
# a lower one, independent of top_k. The RRF paper's value is 60; raise it to flatten
# the rank weighting, lower it to let the top ranks dominate.
RRF_K = 60.0

# Tokenizer the BM25 arm indexes and queries chunk text with (core/retrievers.py):
#   "jieba"      -> Chinese word segmentation (default; matches the CN-tuned corpus)
#   "whitespace" -> Unicode word split (\w+), for space-delimited / multilingual text
# A BM25 index is built per tokenizer, so switching this invalidates cached indexes.
BM25_TOKENIZER = "jieba"

# --- Adapter execution (connections are registered through the API) -----------
# Milvus caps one query at 16384 rows (offset + limit).
MILVUS_QUERY_LIMIT = 16384
MILVUS_QUERY_BATCH_SIZE = 1000
NEBULA_TIMEOUT_MS = 5000
NEBULA_SPACE_READY_TIMEOUT = 30.0     # seconds
NEBULA_SPACE_POLL_INTERVAL = 1.0      # seconds
NEBULA_SCHEMA_READY_ATTEMPTS = 10
NEBULA_SCHEMA_WRITE_ATTEMPTS = 50
NEBULA_SCHEMA_RETRY_INTERVAL = 5.0    # seconds
NEBULA_FETCH_BATCH_SIZE = 500

# --- Concept graph search -----------------------------------------------------
# Defaults for `GraphSearchRetriever`; a retriever's explicit options win.
GRAPH_SEARCH_DEFAULTS = {
    "similarity_top_k": RETRIEVE_TOP_K,
    "seed_m": 6,
    "seed_windows": 2,
    "seed_overlap": 4,
    "seed_min_win": 6,
    "hops": 2,
    "decay": 0.5,
    "coreach_coef": 0.6,
    "coreach_mode": "linear",   # linear | log
    "inverse_freq": True,
    "breadth_mode": "log",      # linear | sqrt | log
    "file_density_coef": 1.1,
    "hub_gate": True,
    "hub_gate_mu": 18.0,
    "hub_gate_sigma": 4.0,
}
GRAPH_HUB_GATE_FALLBACK_SIGMA = 1.0

# --- OKF parsing --------------------------------------------------------------
# An OKF concept's summary bullet may carry a trailing source annotation, e.g.
# "- did X （来源：report.pdf）"; the gloss keeps only the text before the
# earliest of these markers. Both the Chinese and the ASCII forms are covered.
OKF_SUMMARY_SOURCE_MARKERS = (" （来源：", "（来源：", "(source:", "(来源:")
