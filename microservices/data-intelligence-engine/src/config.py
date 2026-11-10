# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
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
LOG_LEVEL = os.getenv("ENGINE_LOG_LEVEL", "INFO").upper()
CORS_ALLOW_ORIGINS = ["*"]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]
# Default page size of `GET /v1/libraries/{library}/assets`.
ASSET_PAGE_SIZE = 20

# --- Workspace ----------------------------------------------------------------
WORKSPACE_DIR = os.getenv(
    "ENGINE_WORKSPACE", str(Path(__file__).resolve().parents[1] / "workspace")
)
MILVUS_DIR = os.path.join(WORKSPACE_DIR, "milvus")
MODEL_DIR = os.getenv("ENGINE_MODEL_ROOT_PATH") or os.path.join(WORKSPACE_DIR, "models")
# Further roots a bare model name is looked up under, after MODEL_DIR.
LEGACY_MODEL_DIR = os.getenv("MODEL_PATH", "")
SHARED_MODEL_DIR = str(Path.home() / "models")
# Shared with the uploading service; same path in both containers.
UPLOAD_DIR = os.getenv("ENGINE_UPLOAD_DIR", os.path.join(WORKSPACE_DIR, "uploads"))
CONFIG_DIR = os.path.join(WORKSPACE_DIR, "configs")
# Root of the default filesystem object database (`ensure_content_database`).
CONTENT_DIR = os.path.join(WORKSPACE_DIR, "content")
ASSET_LIBRARY_FILE = os.path.join(CONFIG_DIR, "asset_library.json")
DATABASE_FILE = os.path.join(CONFIG_DIR, "databases.json")

for _directory in (MODEL_DIR, UPLOAD_DIR, CONFIG_DIR, CONTENT_DIR):
    try:
        os.makedirs(_directory, exist_ok=True)
    except OSError as _error:  # read-only mount: serve without persistence
        print(f"Engine workspace directory {_directory} is not writable: {_error}")

# --- Node parser --------------------------------------------------------------
# Per-source override: `operator_options.chunk_size` / `chunk_overlap`.
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
# Neighbouring text characters per side added to a figure's node.
# Per-source override: `operator_options.figure_context_chars`.
FIGURE_CONTEXT_CHARS = 400

# --- Streaming materialization ------------------------------------------------
# Nodes embedded and inserted per batch, and max built-but-unembedded nodes queued.
INGEST_BATCH_SIZE = 16
INGEST_QUEUE_MAX = 64

# --- Model backends -----------------------------------------------------------
LOCAL_OPENVINO = "local_openvino"
REMOTE_OPENAI_COMPATIBLE = "remote_openai_compatible"
MODEL_BACKENDS = (LOCAL_OPENVINO, REMOTE_OPENAI_COMPATIBLE)


def normalize_model_backend(value: str) -> str:
    normalized = value.lower()
    if normalized not in MODEL_BACKENDS:
        raise ValueError(
            f"model backend must be one of {', '.join(MODEL_BACKENDS)}, got {value!r}"
        )
    return normalized


def _backend(env: str, default: str = LOCAL_OPENVINO) -> str:
    try:
        return normalize_model_backend(os.getenv(env) or default)
    except ValueError as error:
        raise ValueError(f"invalid {env}: {error}") from error


# --- Document embedding model -------------------------------------------------
EMBEDDING_BACKEND = _backend("ENGINE_DOC_EMBEDDING_BACKEND")
EMBEDDING_MODEL_ID = os.getenv(
    "ENGINE_DOC_EMBEDDING_MODEL_ID", "gme-Qwen2-VL-2B-Instruct-OV"
)
EMBEDDING_DEVICE = os.getenv("ENGINE_DOC_EMBEDDING_DEVICE", "CPU")
EMBEDDING_API_BASE = os.getenv("ENGINE_DOC_EMBEDDING_API_BASE", "")  # remote_openai_compatible
EMBEDDING_API_KEY = os.getenv("ENGINE_DOC_EMBEDDING_API_KEY", "unused")
# Upper bound on input length; the genai pipeline pads every input to it.
EMBEDDING_MAX_LENGTH = 512
# Pooling when the model declares none; BGE-family models need CLS pooling.
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
# Instruction for fused (image+text) document embeddings; None keeps the model default.
EMBEDDING_FUSED_INSTRUCTION = None

OPENVINO_CONFIG = {"NUM_STREAMS": "1", "PERFORMANCE_HINT": "LATENCY"}
GME_BATCH_SIZE = 32
IMAGE_LOAD_WORKERS = max(1, min((os.cpu_count() or 1) // 2, 8))
IMAGE_HTTP_TIMEOUT = 30.0  # seconds

# --- Reranker (postprocessing) ------------------------------------------------
RERANK_BACKEND = _backend("ENGINE_RERANK_BACKEND")
RERANK_MODEL_ID = os.getenv("ENGINE_RERANK_MODEL_ID", "Qwen3-VL-Reranker-2B-INT8-OV")
RERANK_DEVICE = os.getenv("ENGINE_RERANK_DEVICE", "CPU")
RERANK_API_BASE = os.getenv("ENGINE_RERANK_API_BASE", "")  # remote_openai_compatible
RERANK_API_KEY = os.getenv("ENGINE_RERANK_API_KEY", "unused")
REMOTE_RERANK_TIMEOUT = 120.0  # seconds

MEDIA_RERANK_BACKEND = _backend("ENGINE_MEDIA_RERANK_BACKEND")
if MEDIA_RERANK_BACKEND != LOCAL_OPENVINO:
    raise ValueError(f"ENGINE_MEDIA_RERANK_BACKEND must be {LOCAL_OPENVINO}")
MEDIA_RERANK_MODEL_ID = os.getenv(
    "ENGINE_MEDIA_RERANK_MODEL_ID", "Qwen3-VL-Reranker-2B-INT8-OV"
)
MEDIA_RERANK_DEVICE = os.getenv("ENGINE_MEDIA_RERANK_DEVICE", "GPU")
MEDIA_RERANK_VIDEO_MAX_FRAMES = _env_int("MEDIA_RERANK_VIDEO_MAX_FRAMES", 8)
# Parallel workers loading rerank candidates' media (blob reads, video decode).
MEDIA_RERANK_DOC_WORKERS = _env_int("ENGINE_MEDIA_RERANK_DOC_WORKERS", 8, maximum=32)

# --- Layout detection (multimodal PDF) ----------------------------------------
# Only PP-DocLayoutV3 on OpenVINO is supported.
LAYOUT_BACKEND = LOCAL_OPENVINO
LAYOUT_MODEL_ID = "PP-DocLayoutV3"
LAYOUT_DEVICE = os.getenv("ENGINE_LAYOUT_DEVICE", "CPU")
# Detections below this confidence are dropped before a block is emitted.
LAYOUT_SCORE_THRESHOLD = 0.3

# --- OCR (multimodal PDF) -----------------------------------------------------
# OCR is used only for PDFs without a text layer (`extract_layout`).
OCR_BACKENDS = ("hybrid", "tesseract", "pdfplumber")
OCR_BACKEND = "tesseract"
# Tesseract recognition languages (Chinese + English).
OCR_LANG = "zh_cn+en"

# Resolution a PDF page is rendered at, for layout detection and figure crops.
LAYOUT_RENDER_DPI = 150

# If > 0, a figure without a caption key has its text re-read from its box extended
# downward by this fraction of its height to pick up a caption below; 0 disables.
LAYOUT_CAPTION_FALLBACK_EXTEND_RATIO = 0.0

# --- Multimodal ingestion -----------------------------------------------------

# Assets per write while a newly attached source backfills a pool.
BACKFILL_BATCH_SIZE = 32

# Videos longer than this get the `long_video` role and are reported as uncovered.
SHORT_VIDEO_MAX_SECONDS = 60.0

# Video: ViCLIP-B by default; ViCLIP-L and Cosmos are alternatives.
VIDEO_EMBEDDING_BACKEND = _backend("ENGINE_VIDEO_EMBEDDING_BACKEND")
VIDEO_EMBEDDING_MODEL_ID = os.getenv(
    "ENGINE_VIDEO_EMBEDDING_MODEL_ID", "viclip-b-fp16"
)
VIDEO_EMBEDDING_DEVICE = os.getenv("ENGINE_VIDEO_EMBEDDING_DEVICE", "CPU")

# Images and media-derived text; requires a pre-exported OpenVINO package.
IMAGE_EMBEDDING_BACKEND = _backend("ENGINE_IMAGE_EMBEDDING_BACKEND")
IMAGE_EMBEDDING_MODEL_ID = os.getenv(
    "ENGINE_IMAGE_EMBEDDING_MODEL_ID", "gme-Qwen2-VL-2B-Instruct-OV"
)
IMAGE_EMBEDDING_DEVICE = os.getenv("ENGINE_IMAGE_EMBEDDING_DEVICE", "CPU")

# Speech recognition for audio `l2_transcript` blocks; the IR must be prepared at
# the model path or its `openvino/` subdirectory.
ASR_BACKEND = LOCAL_OPENVINO
ASR_MODEL_ID = os.getenv("ENGINE_ASR_MODEL_ID", "whisper-small")
ASR_DEVICE = os.getenv("ENGINE_ASR_DEVICE", "CPU")
# Whisper language code ("zh", "en", ...); empty detects it per recording.
ASR_LANGUAGE = os.getenv("ENGINE_ASR_LANGUAGE", "zh")
# Whisper prompt; for zh it steers output toward simplified characters.
ASR_PROMPT = "以下是普通话的句子。" if ASR_LANGUAGE == "zh" else ""
# Max seconds of speech per transcript block (one vector), cut at the nearest pause.
ASR_SEGMENT_SECONDS = 30.0
# Off: audio is indexed by file name only and no ASR model is loaded.
ASR_ENABLED = os.getenv("ENGINE_ASR_ENABLED", "true").lower() in ("1", "true", "yes")

# --- Video summary service (captions) -------------------------------
# Empty base URL disables caption extraction.
VIDEO_SUMMARY_BASE_URL = os.getenv("ENGINE_VIDEO_SUMMARY_BASE_URL", "")
VIDEO_SUMMARY_TASK = "summary"
VIDEO_SUMMARY_TIMEOUT = 300.0

# --- Retrieval defaults -------------------------------------------------------
# Used when a request omits `top_k` / `postprocess.top_n`.
RETRIEVE_TOP_K = 5   # per-method top-k
# Max concepts returned by GET /asset_pools/{pool}/graph (best-connected first).
GRAPH_VIEW_LIMIT = _env_int("ENGINE_GRAPH_VIEW_LIMIT", 1500)
RERANK_TOP_N = 3     # final result count
# RRF smoothing constant k in `score += 1/(k + rank + 1)`; not a result count.
RRF_K = 60.0

# BM25 tokenizer: "jieba" (Chinese) or "whitespace" (\w+); changing it invalidates cached indexes.
BM25_TOKENIZER = "jieba"

# --- Adapter execution --------------------------------------------------------
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
# Defaults for `GraphSearchRetriever`; explicit retriever options win.
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
# Trailing source-annotation markers cut from an OKF summary bullet.
OKF_SUMMARY_SOURCE_MARKERS = (" （来源：", "（来源：", "(source:", "(来源:")
