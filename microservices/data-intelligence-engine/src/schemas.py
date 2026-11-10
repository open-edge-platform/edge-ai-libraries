# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, List, Literal, Optional, Union

import config
from pydantic import BaseModel, ConfigDict, Field, computed_field


# --- Asset library --------------------------------------------------------------

class SourceIn(BaseModel):
    name: str
    database_id: str
    # Derived from the library, source name and time when omitted.
    collection_name: Optional[str] = None
    operator_options: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    labels: Dict[str, str] = Field(default_factory=dict)


class SourceUpdate(BaseModel):
    """Mutable source fields; model and parameters cannot change."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    enabled: Optional[bool] = None
    labels: Optional[Dict[str, str]] = None


class SourceBindingOut(BaseModel):
    pool_id: str
    serving_state: str
    # `serving_state`, or DISABLED while the source is switched off.
    effective_state: str
    status: str


class SourceOut(BaseModel):
    id: str
    name: str
    type: str
    database_id: str
    collection_name: str
    operator_options: Dict[str, Any] = Field(default_factory=dict)
    reconciled: bool = True
    reconciliation_error: Optional[str] = None
    enabled: bool = True
    labels: Dict[str, str] = Field(default_factory=dict)
    created_at: str = ""
    profile: Dict[str, Any] = Field(default_factory=dict)
    bindings: List[SourceBindingOut] = Field(default_factory=list)


class AssetPoolIn(BaseModel):
    id: str
    name: str
    sources: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssetPoolSourceRef(BaseModel):
    """A source to attach, and optionally the one it replaces in this pool."""

    source_id: str
    replaces: Optional[str] = None


class AssetPoolSourcesIn(BaseModel):
    sources: List[Union[str, AssetPoolSourceRef]]


class SourceServingStateUpdate(BaseModel):
    """A per-pool stop/resume intent. PREPARING is computed by the engine."""

    model_config = ConfigDict(extra="forbid")

    serving_state: Literal["SERVING", "DEGRADE"]


class AssetPoolAssetsIn(BaseModel):
    asset_ids: List[str]


class SourceSyncStatusOut(BaseModel):
    source_id: str
    status: str
    indexed_revision: int
    indexed_asset_ids: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    updated_at: str
    serving_state: str = "SERVING"
    effective_state: str = "SERVING"
    replaces: Optional[str] = None
    serving_history: List[Dict[str, Any]] = Field(default_factory=list)
    # OKF extraction state of a graph source: trigger, outdated flag, active/last job.
    extraction: Optional[Dict[str, Any]] = None

    @computed_field
    @property
    def display_status(self) -> str:
        """Overall user readiness, separate from persisted projection-sync state."""
        if self.status != "ready" or not self.extraction:
            return self.status
        extraction = self.extraction
        if extraction.get("state") == "running":
            return "extracting"
        if extraction.get("state") == "queued":
            return "extraction_waiting" if (extraction.get("active") or {}).get("not_before") else "extraction_queued"
        if extraction.get("outdated"):
            return "extraction_failed" if (extraction.get("last") or {}).get("state") == "failed" else "extraction_pending"
        return "ready"


class ExtractionRequest(BaseModel):
    # The graph source to extract for; optional when the pool has only one.
    source_id: Optional[str] = None
    # Extract even when no document changed since the last extraction.
    force: bool = False


class ExtractionOut(BaseModel):
    extraction_id: str
    library: str
    asset_pool_id: str
    source_id: str
    trigger: str
    force: bool = False
    state: str
    requested_at: str
    not_before: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    result: Dict[str, Any] = Field(default_factory=dict)


class PoolRouteOut(BaseModel):
    source_id: str
    source_name: str
    # vector | caption | transcript | text | graph
    via: str
    serving_state: str
    effective_state: str


class PoolRoutingOut(BaseModel):
    pool_id: str
    routes: Dict[str, List[PoolRouteOut]] = Field(default_factory=dict)
    # Kinds of content no serving source takes.
    uncovered: List[str] = Field(default_factory=list)


class AssetPoolOut(BaseModel):
    id: str
    name: str
    asset_ids: List[str] = Field(default_factory=list)
    revision: int = 0
    source_statuses: List[SourceSyncStatusOut] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def display_status(self) -> str:
        statuses = {status.display_status for status in self.source_statuses}
        for state in (
            "failed", "extraction_failed", "indexing", "extracting",
            "extraction_waiting", "extraction_queued", "pending", "extraction_pending",
        ):
            if state in statuses:
                return state
        return "ready" if statuses else "unconfigured"

class AssetLibraryIn(BaseModel):
    name: str
    description: Optional[str] = None
    # Object database for content; defaults to the sole registered one, else the workspace store.
    content_database: Optional[str] = None


class AssetLibraryOut(BaseModel):
    """An asset library: what it holds, where it writes, and how it is doing."""

    id: str
    name: str
    description: Optional[str] = None
    # Source new content goes to; existing assets keep their own source.
    default_content_source_id: str = ""
    # Database of the default content source.
    content_database: str = ""
    asset_count: int = 0
    document_count: int = 0
    chunk_count: int = 0
    sources: List[SourceOut] = Field(default_factory=list)
    asset_pools: List[AssetPoolOut] = Field(default_factory=list)


class AssetLibraryUpdate(BaseModel):
    description: Optional[str] = None
    # Where new content goes: a database or an existing object source; old content stays put.
    content_database: Optional[str] = None
    default_content_source_id: Optional[str] = None


class AssetOut(BaseModel):
    id: str
    name: str
    origin: str
    kind: str
    media_type: str = ""
    # Source holding this asset's content.
    content_source_id: str = ""
    asset_pool_ids: List[str] = Field(default_factory=list)
    # "materializing" | "text_ready" | "ready", or None when untracked; not persisted.
    materialization: Optional[str] = None


class AssetPage(BaseModel):
    assets: List[AssetOut] = Field(default_factory=list)
    total: int = 0


class AssetEnrichmentOut(BaseModel):
    """Progress of a media asset's background description, embedding and transcript."""

    asset_id: str
    role: str = ""
    # pending | completed | failed | skipped
    caption_status: str = ""
    error: Optional[str] = None
    updated_at: Optional[float] = None
    # not_applicable | unassigned | no_source | pending | ready | failed
    embedding_status: str = ""
    embedding_reason: str = ""
    # pending | completed | failed | skipped
    transcript_status: str = ""
    transcript_error: Optional[str] = None
    transcript_updated_at: Optional[float] = None
    transcript_segments: int = 0


class AssetDeleteRequest(BaseModel):
    asset_ids: List[str] = Field(default_factory=list)


class AssetDeleteResult(BaseModel):
    library: str
    removed: List[str] = Field(default_factory=list)
    materializations_removed: int = 0
    # Only files inside the upload directory are removed; others are kept.
    files_removed: List[str] = Field(default_factory=list)
    files_kept: List[str] = Field(default_factory=list)


# --- Assets ---------------------------------------------------------------------

class AssetCreateRequest(BaseModel):
    asset_pool_ids: List[str] = Field(default_factory=list)
    # Server-local paths.
    file_paths: List[str] = Field(default_factory=list)
    text: Optional[str] = None
    # Object source to store content in; defaults to the library's default.
    content_source_id: Optional[str] = None


class AssetCreateResult(BaseModel):
    library: str
    asset_ids: List[str] = Field(default_factory=list)
    asset_pool_ids: List[str] = Field(default_factory=list)
    file_paths: List[str] = Field(default_factory=list)
    content_source_id: str = ""
    # "materializing": accepted; extraction and indexing continue in the background.
    status: Literal["stored", "materializing"] = "stored"


class UploadResult(BaseModel):
    """A file staged by `PUT /{library}/uploads/{path}`, not yet an asset."""

    library: str
    # Relative to the upload directory, as `POST /assets` takes in `file_paths`.
    name: str
    file_path: str
    size: int
    # Whether the file type can be ingested.
    supported: bool


# --- Retrieval ------------------------------------------------------------------

class RerankerModelIn(BaseModel):
    """Per-request reranker selection; unset fields fall back to engine defaults."""

    backend: Optional[str] = None
    model_id: Optional[str] = None
    device: Optional[str] = None
    weight: Optional[str] = None
    api_base: Optional[str] = None  # for the remote_openai_compatible backend


class RetrievedChunk(BaseModel):
    id: str
    text: str
    score: float = Field(description="Score for this stage: retrieval score before reranking, reranker score after successful reranking.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    relation: str = ""


class GraphTraceConcept(BaseModel):
    id: str
    hop: int
    weight: float = 0.0
    # The concept's source chunks that made it into `retrieved_chunks`.
    hit_chunk_ids: List[str] = Field(default_factory=list)


class GraphTrace(BaseModel):
    """One pool's concept-graph walk: seeds, everything reached, edges crossed."""

    library: str
    asset_pool_id: str
    seeds: List[str] = Field(default_factory=list)
    concepts: List[GraphTraceConcept] = Field(default_factory=list)
    edges: List[GraphEdgeOut] = Field(default_factory=list)


class RetrieveResult(BaseModel):
    """Recall candidates and final hits from the shared retrieval pipeline."""
    query: str
    libraries: List[str] = Field(default_factory=list)
    retrieved_chunks: List[RetrievedChunk] = Field(default_factory=list, description="Recall candidates in stable source-round-robin order before postprocessing.")
    chunks: List[RetrievedChunk] = Field(default_factory=list, description="Postprocessed hits, or the recall order when postprocessing is absent or inference fails.")
    graph_traces: List[GraphTrace] = Field(default_factory=list)
    # Set when postprocessing failed and `chunks` fell back to the recall order.
    postprocess_error: Optional[str] = None


class GraphNodeOut(BaseModel):
    id: str
    label: str = ""
    title: str = ""
    degree: int = 0
    # OKF bundle defining it: uploaded | generated | both, or empty if none.
    origin: str = ""


class PoolGraph(BaseModel):
    """A pool's concept graph, for drawing. `truncated` when `total` exceeds the limit."""

    library: str
    asset_pool_id: str
    nodes: List[GraphNodeOut] = Field(default_factory=list)
    edges: List[GraphEdgeOut] = Field(default_factory=list)
    total: int = 0
    truncated: bool = False


class PostprocessOptions(BaseModel):
    query: Optional[str] = None
    processor_type: Literal["reranker"] = "reranker"
    top_n: Optional[int] = config.RERANK_TOP_N
    reranker_model: Optional[RerankerModelIn] = None


class RetrieveRequest(BaseModel):
    query: str
    # Names or ids.
    libraries: List[str] = Field(min_length=1)
    # Empty means all asset pools in every selected library.
    asset_pool_ids: List[str] = Field(default_factory=list)
    top_k: int = config.RETRIEVE_TOP_K
    retriever_type: Optional[str] = None
    exclude_chunk_ids: List[str] = Field(default_factory=list)
    postprocess: Optional[PostprocessOptions] = None
    # Report graph walks per pool in `RetrieveResult.graph_traces`.
    include_graph_trace: bool = False
    # Empty means all; `document` is text only, add `image` to search document figures.
    target_media: List[Literal["document", "audio", "image", "video"]] = Field(default_factory=list)
    allow_missing_targets: bool = False


# --- Models ---------------------------------------------------------------------

class ModelInfo(BaseModel):
    """One model the engine can run for the reported capability."""

    name: str
    path: Optional[str] = None
    # Whether inference artifacts are prepared; the runtime never exports models.
    ready: bool = True
    model_type: str
    # A media (multimodal) reranker the text reranker cannot load.
    media: bool = False


class ModelOptions(BaseModel):
    """Backend configuration and available models for one model type."""

    model_type: str
    backend: str
    backends: List[str] = Field(default_factory=list)
    device: Optional[str] = None
    model_id: Optional[str] = None
    # Reranker only: default model for media (multimodal) reranking.
    media_model_id: Optional[str] = None
    media_backend: Optional[str] = None
    media_device: Optional[str] = None
    api_base: Optional[str] = None
    workspace: Optional[str] = None
    models: List[ModelInfo] = Field(default_factory=list)


class EmbeddingModelInfo(ModelInfo):
    """One embedding model and its supported asset families."""

    # Asset families may be supported through derived text (e.g. transcripts).
    supported_asset_types: List[str] = Field(default_factory=list)


class ModelDefault(BaseModel):
    """The inherited configuration for one asset family, without loading a model."""

    backend: str
    model_id: Optional[str] = None
    model_path: Optional[str] = None
    device: Optional[str] = None
    api_base: Optional[str] = None


class EmbeddingModelOptions(BaseModel):
    """Available embeddings and inherited configuration per asset family."""

    model_type: Literal["embedding", "multimodal"]
    backends: List[str] = Field(default_factory=list)
    workspace: Optional[str] = None
    models: List[EmbeddingModelInfo] = Field(default_factory=list)
    defaults: Dict[str, ModelDefault] = Field(default_factory=dict)


# --- Database -------------------------------------------------------------------

class CollectionInfo(BaseModel):
    name: str
    vector_count: int = 0
    dim: int = 768


# --- Databases ------------------------------------------------------------------

class DatabaseIn(BaseModel):
    """A database registration; `options` is passed verbatim to the backend adapter."""

    id: str
    type: str
    backend: str
    options: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class DatabaseUpdate(BaseModel):
    """A change to a registered database; the type cannot change."""

    backend: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


class DatabaseOut(BaseModel):
    """A registration as reported. Credentials in `options` come back masked."""

    id: str
    type: str
    backend: str
    options: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    in_use_by: List[str] = Field(default_factory=list)


class DatabaseCheck(BaseModel):
    """Whether the engine can actually reach a registered database right now."""

    database_id: str
    reachable: bool
    error: Optional[str] = None


class BackendOption(BaseModel):
    database_type: str
    backends: List[str] = Field(default_factory=list)
