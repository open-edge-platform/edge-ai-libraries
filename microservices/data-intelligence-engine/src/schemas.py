# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Request/response models for the engine service."""

from typing import Any, Dict, List, Literal, Optional, Union

import config
from pydantic import BaseModel, ConfigDict, Field, computed_field


# --- Asset library --------------------------------------------------------------

class SourceIn(BaseModel):
    name: str
    database_id: str
    # Derived from the library, the source name and the time when omitted.
    collection_name: Optional[str] = None
    operator_options: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    labels: Dict[str, str] = Field(default_factory=dict)


class SourceUpdate(BaseModel):
    """What may change on a source. Its model and parameters may not."""

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

    serving_state: Literal["SERVING", "DEPRECATED"]


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
    # A graph source extracting documents into OKF: its trigger, whether its
    # generated bundle is out of date, and the active/last extraction job.
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
    # Which registered object database this library's content goes to. Optional,
    # and in three steps: this if given, else the sole registered object
    # database, else the engine's own workspace store, registered on demand. So
    # an ingest never fails for want of somewhere to put content, and a
    # deployment with several object stores is asked rather than guessed at.
    content_database: Optional[str] = None


class AssetLibraryOut(BaseModel):
    """An asset library: what it holds, where it writes, and how it is doing."""

    id: str
    name: str
    description: Optional[str] = None
    # Which source new content goes to. One of `sources` below; assets already
    # stored keep reading from whichever source they name, so moving this does
    # not move them.
    default_content_source_id: str = ""
    # That source's database. Derived from it, and reported because it is what a
    # caller names on the way in.
    content_database: str = ""
    asset_count: int = 0
    document_count: int = 0
    chunk_count: int = 0
    sources: List[SourceOut] = Field(default_factory=list)
    asset_pools: List[AssetPoolOut] = Field(default_factory=list)


class AssetLibraryUpdate(BaseModel):
    description: Optional[str] = None
    # Where new content goes, either as a database to register a content source
    # in or as one of the library's existing object sources. Content already
    # written stays where it is and stays readable.
    content_database: Optional[str] = None
    default_content_source_id: Optional[str] = None


class AssetOut(BaseModel):
    id: str
    name: str
    origin: str
    kind: str
    media_type: str = ""
    # Which of the library's sources holds this asset's content. Assets in one
    # library need not share a store.
    content_source_id: str = ""
    asset_pool_ids: List[str] = Field(default_factory=list)
    # Live ingest phase: "materializing" | "text_ready" | "ready", or None when
    # untracked (no ingest in this process, e.g. after a restart). Overlaid by the
    # assets route from the materialize tracker; not persisted with the asset.
    materialization: Optional[str] = None


class AssetPage(BaseModel):
    assets: List[AssetOut] = Field(default_factory=list)
    total: int = 0


class AssetEnrichmentOut(BaseModel):
    """How far the background description (and transcript) of a media asset has got.

    Deliberately separate from a pool's `source_statuses`. A pool reports
    whether a *backend* holds what the asset currently says; this reports
    whether the asset has finished saying it. A clip can be `ready` in every
    pool while its description is still being written, and reading one as the
    other is how "indexing finished" comes to mean "nothing more is coming".
    """

    asset_id: str
    role: str = ""
    # The model-written description: pending | completed | failed | skipped.
    caption_status: str = ""
    error: Optional[str] = None
    updated_at: Optional[float] = None
    # Whether the media gets a *vector*, which is a separate pipeline from the
    # description and is worked out from the sources configured now:
    # not_applicable | unassigned | no_source | pending | ready | failed.
    embedding_status: str = ""
    embedding_reason: str = ""
    # Speech recognition of an audio file, written as `l2_transcript` blocks:
    # pending | completed | failed | skipped. Its own error, because it is a
    # separate job from the description.
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
    # Media files deleted along with their assets (only ones inside the upload
    # directory), and ones left in place because they are not the engine's.
    files_removed: List[str] = Field(default_factory=list)
    files_kept: List[str] = Field(default_factory=list)


# --- Assets ---------------------------------------------------------------------

class AssetCreateRequest(BaseModel):
    asset_pool_ids: List[str] = Field(default_factory=list)
    # Server-local paths, e.g. files an upload service has already saved.
    file_paths: List[str] = Field(default_factory=list)
    # Or raw text to ingest directly.
    text: Optional[str] = None
    # Which of the library's object sources to store this batch's content in.
    # Unset means the library's default. A source rather than a database,
    # because where to write is a database *and* a collection in it.
    content_source_id: Optional[str] = None


class AssetCreateResult(BaseModel):
    library: str
    asset_ids: List[str] = Field(default_factory=list)
    asset_pool_ids: List[str] = Field(default_factory=list)
    file_paths: List[str] = Field(default_factory=list)
    # Where the content went, so a caller need not re-read the library to find
    # out which source the default resolved to.
    content_source_id: str = ""
    # "stored": content already stored. "materializing": accepted; a
    # background task is extracting and indexing it -- the request did not wait
    # for render/detect/OCR or for embedding.
    status: Literal["stored", "materializing"] = "stored"


class UploadResult(BaseModel):
    """A file staged by `PUT /{library}/uploads/{path}`, not yet an asset."""

    library: str
    # Relative to the upload directory: what `POST /assets` takes in
    # `file_paths`. A folder upload's files share a prefix, and naming the
    # folder (`name` up to its first segment) ingests it whole.
    name: str
    file_path: str
    size: int
    # Whether the file can be ingested on its own. A folder may still hold
    # unsupported files; they are skipped when the folder is ingested.
    supported: bool


# --- Retrieval ------------------------------------------------------------------

class RerankerModelIn(BaseModel):
    """Which reranker to run. Sent per request: the caller (its retrieval pipeline)
    owns this configuration, the engine only executes it. Unset fields fall back
    to the engine's configured defaults.

    `model_id` is a model the engine can run — for the openvino backends, one of the
    workspace models reported by GET /v1/models/reranker. `backend` picks the
    provider per request (e.g. `openai_compatible` with `api_base` for a remote
    rerank server); unset uses ENGINE_RERANK_BACKEND."""

    backend: Optional[str] = None
    model_id: Optional[str] = None
    model_path: Optional[str] = None
    device: Optional[str] = None
    weight: Optional[str] = None
    api_base: Optional[str] = None  # for the openai_compatible provider


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
    # The concept's source chunks that made it into `retrieved_chunks`, i.e.
    # what this concept actually contributed to the answer.
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
    # Which OKF bundles define it: `uploaded`, `generated` (extracted from the
    # pool's documents), or `both` -- an uploaded concept overriding an extracted
    # one. Empty when no bundle in the pool defines it any more.
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
    processor_type: str = "reranker"
    top_n: Optional[int] = config.RERANK_TOP_N
    reranker_model: Optional[RerankerModelIn] = None


class RetrieveRequest(BaseModel):
    query: str
    # Names or ids. The engine has no active-library state to fall back on.
    libraries: List[str] = Field(min_length=1)
    # Empty means all asset pools in every selected library.
    asset_pool_ids: List[str] = Field(default_factory=list)
    top_k: int = config.RETRIEVE_TOP_K
    retriever_type: Optional[str] = None
    exclude_chunk_ids: List[str] = Field(default_factory=list)
    postprocess: Optional[PostprocessOptions] = None
    # Report what graph retrieval walked (`graph`, or `rrf` on a pool with a
    # graph source), per pool, in `RetrieveResult.graph_traces`.
    include_graph_trace: bool = False
    # Empty means every searchable source in the selected libraries and pools.
    # `document` covers text only; select `image` alongside it to also search
    # the figures inside documents.
    target_media: List[Literal["document", "audio", "image", "video"]] = Field(default_factory=list)
    allow_missing_targets: bool = False


# --- Models ---------------------------------------------------------------------

class ModelInfo(BaseModel):
    """One model the engine can run for the reported capability."""

    name: str
    path: Optional[str] = None
    # Whether the OpenVINO IR is already exported (an unexported model is exported
    # on first use, which takes a while).
    ready: bool = True
    model_type: str
    # Set when the model must run on a specific backend (the Qwen3-VL reranker
    # needs "openvino_vl"; the text reranker backends cannot load its export).
    backend: Optional[str] = None


class ModelOptions(BaseModel):
    """What a model picker needs: how the engine runs this kind of model, and which
    ones it can choose from."""

    model_type: str
    backend: str
    backends: List[str] = Field(default_factory=list)
    device: Optional[str] = None
    model_id: Optional[str] = None
    # For reranker only: the default model a media (multimodal) search reranks
    # with, which differs from the text reranker in `model_id`.
    media_model_id: Optional[str] = None
    api_base: Optional[str] = None
    workspace: Optional[str] = None
    models: List[ModelInfo] = Field(default_factory=list)


# --- Database -------------------------------------------------------------------

class CollectionInfo(BaseModel):
    name: str
    vector_count: int = 0
    dim: int = 768


# --- Databases ------------------------------------------------------------------

class DatabaseIn(BaseModel):
    """A database the engine may connect to.

    `options` is passed to the backend's adapter verbatim, so it is whatever
    that backend needs -- `uri` for Milvus (plus any `token` / `user` /
    `password` / `db_name` it forwards to the client), `root` for the filesystem
    object store, `endpoint` and keys for MinIO. `GET /backends` lists what each
    one takes.
    """

    id: str
    type: str
    backend: str
    options: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class DatabaseUpdate(BaseModel):
    """A change to a registered database. The type cannot change; see the API."""

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
