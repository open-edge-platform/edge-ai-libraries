# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import gc
import hashlib
import json
import mimetypes
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

import config
from assetlib.content import BLOB_PREFIX, asset_key
from assetlib.contracts import ChunkProjection, Source
from assetlib.library import AssetLibrary, collection_name
from assetlib.pool import SourceSyncStatus
from assetlib.sources import frozen as frozen_bindings
from assetlib.sources import routing as source_routing
from assetlib.sources.binding import effective_state
from assetlib.sources.profile import build_profile
from core.knowledge import Knowledge, redact_operator_options
from core.knowledge.extraction_jobs import ExtractionJob, ExtractionJobs
from core.content import (
    AUDIO,
    BINARY_KINDS,
    DOCUMENT,
    IMAGE,
    MM_ROLES,
    ROLE_AUDIO,
    ROLE_DOC_IMAGE,
    ROLE_IMAGE,
    ROLE_L1_SEGMENT,
    ROLE_L2_CAPTION,
    ROLE_L2_TRANSCRIPT,
    ROLE_L3_WIKI,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    TEXT,
    VIDEO,
    MM_DERIVED_ROLES,
    ContentBlock,
    ContentStream,
    asset_family,
    file_uri,
    file_uri_path,
    is_file_uri,
    role_of,
)
from core.indexer import (
    GraphIndexer,
    MultimodalIndexer,
    VectorIndexer,
    accepts_asset,
    accepts_block,
)
from core.postprocessor import postprocess_nodes
from databasehub.adapters.graph import GraphAdapter
from databasehub.adapters.vector import VectorAdapter
from databasehub.models import GraphCollection, VectorCollection
from schemas import (
    AssetOut,
    AssetPage,
    AssetLibraryOut,
    AssetPoolOut,
    CollectionInfo,
    RetrievedChunk,
    SourceBindingOut,
    SourceOut,
    SourceSyncStatusOut,
)
from llama_index.core.schema import MetadataMode, NodeWithScore, TextNode

KnowledgeIndexer = Union[VectorIndexer, GraphIndexer]


def _is_multimodal(configuration: Mapping[str, Any]) -> bool:
    """Whether this vector source's model embeds media rather than words."""
    return describe_vector_source(configuration)["encoder_kind"] == "multimodal"


#: Options that choose which blocks a source takes; part of its profile.
_ROUTING_OPTIONS = ("asset_types", "block_kinds", "block_roles")


def describe_vector_source(configuration: Mapping[str, Any]) -> dict:
    """The profile of a vector source, with engine defaults resolved at creation."""
    import config
    from core.embedding import embedding_is_fused, embedding_runtime
    from core.multimodal import registry
    from core.multimodal.routing import asset_families, string_list, validate_options

    validate_options(configuration)

    roles = sorted(set(string_list(configuration, 'block_roles')) - MM_ROLES)
    if roles:
        # A misspelt value would silently match nothing.
        raise ValueError(
            f"Unknown block_roles {', '.join(roles)}; known: {', '.join(sorted(MM_ROLES))}"
        )
    routing = {key: configuration[key] for key in _ROUTING_OPTIONS if key in configuration}
    backend = config.normalize_model_backend(
        configuration.get("embedding_backend") or config.EMBEDDING_BACKEND
    )
    families = asset_families(configuration)
    media_scope = bool(families & {IMAGE, VIDEO, AUDIO})
    # Text source unless it asks for media blocks or its explicit model embeds only media.
    text_source = not media_scope and not (
        set(configuration.get("block_kinds") or ()) & {AUDIO, VIDEO}
    )
    if text_source and backend == config.LOCAL_OPENVINO and configuration.get("embedding_model"):
        model = registry.lookup(configuration["embedding_model"], None)
        text_source = model is None or TEXT in model.supported_kinds
    resolved = None if text_source else registry.resolve(configuration)
    if resolved is not None:
        return build_profile(
            "multimodal",
            backend=resolved.backend,
            model=resolved.model_id,
            params={**routing, **resolved.params},
            multimodal_model=resolved.record(),
            runtime=resolved.model.runtime,
            device=configuration.get("embedding_device"),
            supported_roles=sorted(resolved.model.supported_roles),
            supported_asset_types=sorted(resolved.model.supported_asset_types),
        )
    model_id = configuration.get("embedding_model") or config.EMBEDDING_MODEL_ID
    return build_profile(
        "text",
        backend=backend,
        model=model_id,
        params={
            **{
                key: int(configuration[key] if configuration.get(key) is not None else default)
                for key, default in (
                    ("chunk_size", config.CHUNK_SIZE),
                    ("chunk_overlap", config.CHUNK_OVERLAP),
                    ("figure_context_chars", config.FIGURE_CONTEXT_CHARS),
                )
            },
            **routing,
        },
        runtime=embedding_runtime(backend, model_id),
        fused=embedding_is_fused(backend, model_id),
        device=configuration.get("embedding_device") or config.EMBEDDING_DEVICE,
        model_id=model_id,
    )


@dataclass
class FileAsset:
    """One ingested file: its provenance `origin` and the content source/key holding its stream."""

    asset_id: str
    origin: str = ""
    content_source_id: str = ""
    content_key: str = ""
    #: "okf" for a concept bundle, else the file family ("document", "image", "video", "audio").
    asset_kind: str = DOCUMENT
    # Not persisted: `loader` is bound by the library, `cached` is the stream once read.
    loader: Optional[Callable[[], ContentStream]] = field(
        default=None, repr=False, compare=False
    )
    cached: Optional[ContentStream] = field(default=None, repr=False, compare=False)
    # Reads one blob out of the same content source; bound by the library.
    blob_reader: Optional[Callable[[str], bytes]] = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if self.asset_kind != "okf":
            self.asset_kind = asset_family(self.extension)

    def bind(self, loader: Callable[[], ContentStream]) -> None:
        self.loader = loader

    def bind_blobs(self, reader: Callable[[str], bytes]) -> None:
        self.blob_reader = reader

    def read_blob(self, media_key: str) -> bytes:
        """The bytes a media block points at."""
        if not media_key:
            raise ValueError(f"Asset {self.asset_id!r} block has no media key")
        if is_file_uri(media_key):
            with open(self._origin_file(media_key), "rb") as handle:
                return handle.read()
        if self.blob_reader is None:
            raise ValueError(
                f"Asset {self.asset_id!r} has no way to read its blobs"
            )
        return self.blob_reader(media_key)

    def _origin_file(self, media_key: str) -> str:
        """The local file a `file://` media key names, which must still be there."""
        path = file_uri_path(media_key)
        if not os.path.isfile(path):
            raise ValueError(
                f"Asset {self.asset_id!r} origin file is gone: {path!r}"
            )
        return path

    @contextmanager
    def media_path(self, media_key: str, suffix: str = ".mp4") -> Iterator[str]:
        """A local path for a media block; stored blobs go to a temp file removed on exit."""
        if is_file_uri(media_key):
            yield self._origin_file(media_key)
            return
        from core.multimodal import frames  # noqa: PLC0415

        path = frames.materialize(self.read_blob(media_key), suffix)
        try:
            yield path
        finally:
            frames.discard(path)

    @property
    def content(self) -> ContentStream:
        if self.cached is None:
            if self.loader is None:
                raise ValueError(
                    f"Asset {self.asset_id!r} has no content and no way to load it"
                )
            self.cached = self.loader()
        return self.cached

    @property
    def file_name(self) -> str:
        """The name of the file this asset is, from its provenance URI."""
        return os.path.basename(_path_of(self.origin))

    @property
    def media_type(self) -> str:
        """The file's MIME type, guessed from its name without loading content."""
        return mimetypes.guess_type(_path_of(self.origin))[0] or ""

    @property
    def extension(self) -> str:
        return os.path.splitext(_path_of(self.origin))[1].lower().lstrip(".")

    def to_record(self) -> dict:
        record = {
            "asset_id": self.asset_id,
            "origin": self.origin,
            "asset_kind": self.asset_kind,
        }
        if self.asset_kind == "okf":
            # OKF bundles are provenance-only: concepts are parsed from disk.
            return record
        if self.content_source_id and self.content_key:
            record["content_source_id"] = self.content_source_id
            record["content_key"] = self.content_key
        else:
            # No content source: keep the content inline.
            record["content"] = self.content.to_record()
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "FileAsset":
        asset_id = str(record["asset_id"])
        asset = cls(
            asset_id=asset_id,
            origin=_origin_uri(record),
            content_source_id=str(record.get("content_source_id") or ""),
            content_key=str(record.get("content_key") or ""),
            asset_kind=str(record.get("asset_kind") or "document"),
        )
        if asset.asset_kind == "okf":
            # An empty stream so `asset.content` never raises on paths that touch it.
            asset.cached = ContentStream(asset_id=asset.asset_id, blocks=[])
            return asset
        if "content" in record:
            asset.cached = ContentStream.from_record(record["content"])
        elif "document" in record:
            # Legacy record with an inline llama-index document.
            asset.cached = ContentStream.from_document_record(record["document"])
        return asset


def file_origin(path: str) -> str:
    """The provenance URI for a document read off the filesystem."""
    return file_uri(path)


def inline_origin(reference: str) -> str:
    """The provenance URI for a document supplied in a request body."""
    return f"inline:{reference}"


def _path_of(origin: str) -> str:
    """The filesystem path inside a provenance URI, or the URI as written."""
    if origin.startswith("file://"):
        return origin[len("file://"):]
    return origin


def asset_id_for(origin: str) -> str:
    """A stable id derived from the origin, so re-ingesting a file updates the same asset."""
    return hashlib.sha256(origin.encode("utf-8")).hexdigest()[:32]


def _origin_uri(record: Mapping[str, Any]) -> str:
    """The provenance URI, also accepting legacy `Source`-shaped `origin`/`source` records."""
    origin = record.get("origin")
    if isinstance(origin, str):
        return origin
    legacy = origin if isinstance(origin, Mapping) else record.get("source")
    if isinstance(legacy, Mapping):
        location = legacy.get("collection")
        if isinstance(location, str) and location:
            return location if "://" in location else f"file://{location}"
        return str(legacy.get("source_id") or "")
    return ""


#: Folder in a library's upload area holding OKF bundles extracted from documents.
EXTRACTED_DIRECTORY = "okf-extracted"
#: One representative block per role (plus plain text) for the routing report.
ROUTING_KINDS = {
    "text": ContentBlock("routing", kind=TEXT, text="-"),
    **{
        role: ContentBlock("routing", kind=kind, text="-" if kind == TEXT else "", metadata={"role": role})
        for role, kind in (
            (ROLE_IMAGE, IMAGE),
            (ROLE_DOC_IMAGE, IMAGE),
            (ROLE_SHORT_VIDEO, VIDEO),
            (ROLE_LONG_VIDEO, VIDEO),
            (ROLE_AUDIO, AUDIO),
            (ROLE_L1_SEGMENT, VIDEO),
            (ROLE_L2_CAPTION, TEXT),
            (ROLE_L2_TRANSCRIPT, TEXT),
            (ROLE_L3_WIKI, TEXT),
        )
    },
}


class FileAssetLibrary(AssetLibrary[FileAsset]):
    """An asset library whose assets are documents and whose records are chunks."""

    # Only these source types have a projection.
    PROJECTION_TYPES = {
        "vector": (VectorIndexer, VectorCollection, VectorAdapter),
        "graph": (GraphIndexer, GraphCollection, GraphAdapter),
    }
    BACKFILL_BATCH_SIZE = config.BACKFILL_BATCH_SIZE

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        idx: Optional[str] = None,
        databasehub=None,
        content_database: str = "",
    ):
        super().__init__(
            name=name,
            description=description,
            idx=idx,
            databasehub=databasehub,
            content_database=content_database,
        )
        # Ingested file name -> the path it was read from.
        self.file_map: Dict[str, str] = {}
        self.extraction_jobs = ExtractionJobs(
            self._run_extraction_job, on_finished=self._save_after_extraction
        )
        # (pool, source) -> (status, document-change count) last used to request an auto extraction.
        self._auto_extraction_revisions: Dict[
            Tuple[str, str], Tuple[SourceSyncStatus, int]
        ] = {}
        # (pool, source) -> the cron minute a `schedule` trigger last fired for.
        self._schedule_fired: Dict[Tuple[str, str], datetime] = {}

    def create_source(self, name, database_id, collection_name="", configuration=None,
                      register=True, **options):
        """As the base class, but validates graph knowledge settings and vector `asset_types` first."""
        from core.multimodal.routing import validate_asset_types

        source = super().create_source(
            name, database_id, collection_name, configuration, register=False, **options
        )
        if source.source_type == "graph":
            Knowledge(source.configuration)
        elif source.source_type == "vector":
            validate_asset_types(source.configuration)
        return self.add_source(source) if register else source

    def describe_source(self, source: Source) -> dict:
        if source.source_type.lower() == "vector":
            return describe_vector_source(source.configuration)
        return super().describe_source(source)

    def detach_source(self, source_id: str) -> bool:
        if source_id not in self.sources or self.assets_in_source(source_id):
            return super().detach_source(source_id)
        self.extraction_jobs.detach_source(source_id)
        removed = super().detach_source(source_id)
        self._auto_extraction_revisions = {
            key: value for key, value in self._auto_extraction_revisions.items() if key[1] != source_id
        }
        self._schedule_fired = {
            key: value for key, value in self._schedule_fired.items() if key[1] != source_id
        }
        return removed

    def _source_problem(self, source: Source) -> str:
        problem = super()._source_problem(source)
        if problem or source.source_type != 'vector':
            return problem
        try:
            from core.multimodal.routing import validate_source

            validate_source(source)
            if not source.profile:
                describe_vector_source(source.configuration)
        except (ValueError, FileNotFoundError) as error:
            return str(error)
        return ''

    def _source_accepts_asset(self, source: Source, asset: FileAsset) -> bool:
        from core.multimodal.routing import effective_configuration

        if source.source_type == "vector" and asset.asset_kind == "okf":
            return False
        return accepts_asset(asset, effective_configuration(source))

    def build_projection(
        self, projection_id: str, name: str, source: Source
    ) -> KnowledgeIndexer:
        source_type = source.source_type.lower()
        projection = self.PROJECTION_TYPES.get(source_type)
        if projection is None:
            raise ValueError(
                f"Source type {source_type!r} has no projection; supported: "
                + ", ".join(sorted(self.PROJECTION_TYPES))
            )
        indexer_type, collection_type, adapter_type = projection
        registration = self._databasehub.get_registration(source.database_id)
        if registration.database_type != source_type:
            raise ValueError(
                f"Source type {source_type!r} needs a {source_type!r} adapter, but "
                f"{source.database_id!r} is registered for "
                f"{registration.database_type!r}"
            )
        adapter = self._databasehub.get_adapter(source.database_id)
        if not isinstance(source.location, collection_type):
            raise TypeError(
                f"Projection type {source_type!r} requires "
                f"{collection_type.__name__}"
            )
        if not isinstance(adapter, adapter_type):
            raise TypeError(
                f"Adapter {source.database_id!r} is not a {adapter_type.__name__}"
            )
        from core.multimodal.routing import effective_configuration, validate_source

        if source_type == 'vector':
            validate_source(source)
        configuration = effective_configuration(source)
        if source_type == "vector":
            # Not persisted: VectorIndexer pops it out of its configuration.
            configuration["blob_reader"] = self.blob_reader()
        profile = source.profile or self.describe_source(source)
        if source_type == "vector" and profile.get("encoder_kind") == "multimodal":
            indexer_type = MultimodalIndexer
            configuration['embedding_backend'] = profile.get('backend')
        elif source_type == "vector":
            # Build from the profile's frozen options; profiles without `model_id` fall back to `model`.
            for option, value in (
                ("embedding_backend", profile.get("backend")),
                ("embedding_device", profile.get("device")),
                ("embedding_model", profile.get("model_id")
                 or configuration.get("embedding_model") or profile.get("model")),
            ):
                if value is not None:
                    configuration[option] = value
            configuration.update(profile.get("params") or {})
        return indexer_type(
            projection_id=projection_id,
            name=name,
            source=source,
            adapter=adapter,
            configuration=configuration,
        )

    def _sync_projection_order(self, asset_pool):
        # Vector first, so a graph sync can resolve OKF source chunks against written chunks.
        return sorted(
            asset_pool.projections,
            key=lambda projection: 0 if getattr(projection, "kind", "") == "vector" else 1,
        )

    def _vector_projection(self, asset_pool):
        return next(
            (
                projection
                for projection in asset_pool.serving
                if isinstance(projection, VectorIndexer)
                and not isinstance(projection, MultimodalIndexer)
                and getattr(projection.source, "enabled", True)
            ),
            None,
        )

    def _okf_source_root(self, asset_pool) -> Optional[Path]:
        """The common directory of the pool's file-backed document assets, or None."""
        paths = []
        for asset_id in asset_pool.asset_ids:
            asset = self._assets.get(asset_id)
            if asset is None or getattr(asset, "asset_kind", "") == "okf":
                continue
            origin = str(getattr(asset, "origin", "") or "")
            if origin.startswith("file://"):
                paths.append(origin[len("file://"):])
        if not paths:
            return None
        root = os.path.commonpath(paths)
        if not os.path.isdir(root):
            root = os.path.dirname(root)
        return Path(root)

    def _prepare_projection_add(self, asset_pool, projection, assets):
        if not isinstance(projection, GraphIndexer):
            return
        projection.set_okf_context(None)
        vector = self._vector_projection(asset_pool)
        if vector is None:
            raise ValueError("OKF graph indexing requires a vector source in the asset pool")
        if projection.extracts_documents and any(
            getattr(asset, "asset_kind", "document") != "okf" for asset in assets
        ):
            # Extraction runs as a separate job; only mark the generated bundle outdated.
            status = asset_pool.source_statuses.get(projection.source.source_id)
            if status is not None:
                status.note_extraction_input_changed()
        projection.set_okf_context(
            self._resolve_okf_concepts(asset_pool, projection, vector) or None
        )

    def _generated_bundle_path(self, asset_pool, projection) -> Path:
        """Stable folder for a graph source's extracted bundle, so its asset id survives re-extraction."""
        return self._generated_bundle_dir(asset_pool, projection.source)

    def _generated_bundle_dir(self, asset_pool, source) -> Path:
        import config

        def slug(value: str) -> str:
            return re.sub(r"[^0-9A-Za-z_-]+", "-", value).strip("-") or "x"

        name = f"{slug(asset_pool.asset_pool_id)}-{slug(source.name or 'graph')}-{source.source_id[:8]}"
        return Path(config.UPLOAD_DIR) / self.idx / EXTRACTED_DIRECTORY / name

    def _extract_documents_to_okf_asset(self, asset_pool, projection, vector, documents):
        """Extract `documents` into an OKF bundle, ingest it as a pool asset; return (asset, concepts)."""
        from core.knowledge.okf import parse_okf_bundle

        target = self._generated_bundle_path(asset_pool, projection)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".staging-{target.name}"
        staging.mkdir(exist_ok=True)
        try:
            paths = projection.extract_documents(documents, staging) if documents else []
            if len(paths) != 1:
                for path in paths:
                    shutil.rmtree(path, ignore_errors=True)
                raise ValueError("An extraction task must return exactly one OKF bundle")
            candidate = paths[0]
            try:
                concepts = self._generated_concepts(candidate, documents, vector)
            except Exception:
                # A rejected candidate must not replace the good bundle.
                shutil.rmtree(candidate, ignore_errors=True)
                raise
            previous_ids = (
                {node.cid for node in parse_okf_bundle(target)} if target.is_dir() else set()
            )
            retired = target.parent / f".retired-{target.name}"
            shutil.rmtree(retired, ignore_errors=True)
            if target.exists():
                target.rename(retired)
            candidate.rename(target)
            shutil.rmtree(retired, ignore_errors=True)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        asset = self.create_okf_asset(file_origin(str(target)))
        known = asset.asset_id in self._assets
        self.register_assets([asset])
        if asset.asset_id not in asset_pool.asset_ids:
            self.add_assets_to_pool(asset_pool.asset_pool_id, [asset.asset_id])
        if known:
            self.note_assets_changed([asset.asset_id])
        obsolete = sorted(previous_ids - {node.cid for node in concepts})
        if obsolete:
            # Retire concepts dropped by re-extraction from the graph and concept index.
            projection.delete_vertices(obsolete)
            vector.remove_concepts(obsolete)
        return asset, concepts

    def sync_asset_pool(self, asset_pool_id: str, auto_extract: bool = True) -> None:
        """As the base class; then queue debounced extraction for outdated `auto` graph sources."""
        super().sync_asset_pool(asset_pool_id)
        from core.retrievers import warm_graph_arm

        try:
            warm_graph_arm(self, self._require_asset_pool(asset_pool_id))
        except Exception:  # noqa: BLE001
            pass
        if not auto_extract:
            return
        asset_pool = self._require_asset_pool(asset_pool_id)
        for projection in self._extracting_projections(asset_pool):
            trigger = projection.extraction_trigger
            status = asset_pool.source_statuses.get(projection.source.source_id)
            if (
                trigger.mode == "auto"
                and status is not None and status.status == "ready"
                and status.extraction_outdated
            ):
                key = (asset_pool_id, projection.source.source_id)
                previous = self._auto_extraction_revisions.get(key)
                if (
                    previous is not None and previous[0] is status
                    and previous[1] >= status.extraction_changes
                    and self.extraction_jobs.active(self.idx, asset_pool_id, projection.source.source_id) is not None
                ):
                    continue
                self._auto_extraction_revisions[key] = (status, status.extraction_changes)
                self.extraction_jobs.request(
                    self.idx, asset_pool_id, projection.source.source_id, "auto",
                    delay=trigger.debounce_seconds,
                )

    def run_scheduled_extractions(self, now: datetime) -> List[ExtractionJob]:
        """Queue extraction for outdated `schedule` graph sources whose cron matches `now`; each minute fires once."""
        from zoneinfo import ZoneInfo

        fired = self._schedule_fired
        jobs = []
        for asset_pool in list(self._asset_pools.values()):
            for projection in self._extracting_projections(asset_pool):
                trigger = projection.extraction_trigger
                if trigger.mode != "schedule":
                    continue
                source_id = projection.source.source_id
                minute = now.astimezone(ZoneInfo(trigger.timezone)).replace(second=0, microsecond=0)
                key = (asset_pool.asset_pool_id, source_id)
                if fired.get(key) == minute or not trigger.schedule().matches(minute):
                    continue
                fired[key] = minute
                status = asset_pool.source_statuses.get(source_id)
                # Skip while a job is running; missed changes keep the source outdated.
                busy = self.extraction_jobs.active(self.idx, asset_pool.asset_pool_id, source_id)
                if status is not None and status.extraction_outdated and busy is None:
                    job, _ = self.extraction_jobs.request(
                        self.idx, asset_pool.asset_pool_id, source_id, "schedule",
                    )
                    jobs.append(job)
        return jobs

    def request_extraction(
        self, asset_pool_id: str, source_id: Optional[str] = None, force: bool = False,
    ) -> Tuple[ExtractionJob, bool]:
        """Queue extraction for one graph source; returns (job, is_new), reusing an active job."""
        asset_pool = self._require_asset_pool(asset_pool_id)
        projection = self._extracting_projection(asset_pool, source_id)
        return self.extraction_jobs.request(
            self.idx, asset_pool_id, projection.source.source_id, "manual", force
        )

    def run_extraction(self, asset_pool_id: str, source_id: str, force: bool = False) -> Dict[str, Any]:
        """Extract the pool's documents for one graph source and publish the bundle; skipped if up to date unless `force`."""
        asset_pool = self._require_asset_pool(asset_pool_id)
        # Index documents first: the bundle's provenance resolves to their chunks.
        self.sync_asset_pool(asset_pool_id, auto_extract=False)
        projection = self._extracting_projection(asset_pool, source_id)
        status = asset_pool.source_statuses[source_id]
        covers = status.extraction_changes
        generated = self._generated_bundle_path(asset_pool, projection)
        if not force and not status.extraction_outdated and generated.is_dir():
            return {"outcome": "up_to_date"}
        documents = self._extraction_documents(asset_pool, projection)
        if not documents:
            self._remove_generated_bundle(asset_pool, projection)
            status.extraction_done = max(status.extraction_done, covers)
            return {"outcome": "no_documents"}
        vector = self._vector_projection(asset_pool)
        if vector is None:
            raise ValueError("OKF extraction requires a serving text vector source in the asset pool")
        asset, concepts = self._extract_documents_to_okf_asset(asset_pool, projection, vector, documents)
        status = asset_pool.source_statuses.get(source_id)
        if status is not None:
            status.extraction_done = max(status.extraction_done, covers)
        self.sync_asset_pool(asset_pool_id, auto_extract=False)
        return {
            "outcome": "extracted", "documents": len(documents),
            "concepts": len(concepts), "bundle_asset_id": asset.asset_id,
        }

    def _run_extraction_job(self, job: ExtractionJob) -> Dict[str, Any]:
        return self.run_extraction(job.asset_pool_id, job.source_id, job.force)

    def _save_after_extraction(self, job: ExtractionJob) -> None:
        from core.manager import registry

        if registry.get(self.idx) is self:
            registry.save()

    def _extracting_projections(self, asset_pool) -> List[GraphIndexer]:
        return [
            projection for projection in asset_pool.projections
            if isinstance(projection, GraphIndexer) and projection.extracts_documents
        ]

    def _extracting_projection(self, asset_pool, source_id: Optional[str]) -> GraphIndexer:
        extracting = self._extracting_projections(asset_pool)
        if source_id is None:
            if len(extracting) != 1:
                raise ValueError(
                    f"Asset pool {asset_pool.asset_pool_id!r} has {len(extracting)} graph "
                    "sources that extract documents; name one with source_id"
                )
            return extracting[0]
        for projection in extracting:
            if projection.source.source_id == source_id:
                return projection
        raise ValueError(
            f"Source {source_id!r} is not a graph source extracting documents in asset "
            f"pool {asset_pool.asset_pool_id!r}"
        )

    def _extraction_documents(self, asset_pool, projection) -> List[Any]:
        """The pool's whole current document corpus accepted by `projection`."""
        return [
            self._assets[asset_id] for asset_id in list(asset_pool.asset_ids)
            if getattr(self._assets[asset_id], "asset_kind", "document") != "okf"
            and projection.accepts(self._assets[asset_id])
        ]

    def _remove_generated_bundle(self, asset_pool, projection) -> None:
        """Forget a source's generated bundle asset and delete its folder."""
        target = self._generated_bundle_path(asset_pool, projection)
        generated_id = asset_id_for(file_origin(str(target)))
        if generated_id in self._assets:
            self.forget_assets([generated_id])
        shutil.rmtree(target, ignore_errors=True)

    @staticmethod
    def _trigger_out(trigger) -> Dict[str, Any]:
        out: Dict[str, Any] = {"trigger": trigger.mode, "trigger_options": trigger.to_out()}
        if trigger.mode == "schedule":
            from zoneinfo import ZoneInfo

            upcoming = trigger.schedule().next_after(datetime.now(ZoneInfo(trigger.timezone)))
            out["next_run"] = upcoming.isoformat() if upcoming else None
        return out

    def extraction_out(self, asset_pool, status) -> Optional[Dict[str, Any]]:
        """A graph source's extraction state for `SourceSyncStatusOut`."""
        projection = next(
            (p for p in self._extracting_projections(asset_pool)
             if p.source.source_id == status.source_id),
            None,
        )
        if projection is None:
            return None
        active = self.extraction_jobs.active(self.idx, asset_pool.asset_pool_id, status.source_id)
        history = self.extraction_jobs.list(asset_pool.asset_pool_id, status.source_id)
        last = next((job for job in history if job.state not in ("queued", "running")), None)
        generated = self._generated_bundle_path(asset_pool, projection)
        return {
            **self._trigger_out(projection.extraction_trigger),
            "state": active.state if active else "idle",
            "outdated": status.extraction_outdated,
            "bundle_asset_id": (
                asset_id_for(file_origin(str(generated))) if generated.is_dir() else None
            ),
            "active": active.to_out() if active else None,
            "last": last.to_out() if last else None,
        }

    def concept_origins(self, asset_pool_id: str) -> Dict[str, str]:
        """Concept id -> ``uploaded``, ``generated`` or ``both``; unreadable bundles are skipped."""
        from core.knowledge.okf import parse_okf_bundle

        asset_pool = self._require_asset_pool(asset_pool_id)
        origins: Dict[str, str] = {}
        for asset_id in list(asset_pool.asset_ids):
            asset = self._assets.get(asset_id)
            if asset is None or getattr(asset, "asset_kind", "") != "okf":
                continue
            bundle = Path(_path_of(asset.origin))
            try:
                kind = "generated" if self._is_generated_bundle(asset) else "uploaded"
                cids = {node.cid for node in parse_okf_bundle(bundle)}
            except (OSError, ValueError, KeyError):
                continue
            for cid in cids:
                origins[cid] = kind if origins.get(cid, kind) == kind else "both"
        return origins

    def _is_generated_bundle(self, asset) -> bool:
        """Whether an `okf` asset lives in one of its pools' generated bundle folders."""
        if getattr(asset, "asset_kind", "") != "okf":
            return False
        return any(
            asset.asset_id == asset_id_for(file_origin(str(self._generated_bundle_path(pool, projection))))
            for pool in self._asset_pools.values() if asset.asset_id in pool.asset_ids
            for projection in self._extracting_projections(pool)
        )

    def _uploaded_task_bundle_concepts(self, bundle: Path, sources, documents, vector) -> List[Any]:
        """Concepts of an uploaded engine bundle, matching task source paths to pool documents by unique file name."""
        from core.knowledge.okf import parse_okf_bundle

        by_name: Dict[str, List[str]] = {}
        for document in documents:
            by_name.setdefault(Path(_path_of(document.origin)).name, []).append(document.asset_id)
        mapped = {
            path: by_name[PurePosixPath(path).name][0]
            for path in sources
            if len(by_name.get(PurePosixPath(path).name, [])) == 1
        }
        chunks_by_asset: Dict[str, List[str]] = {}
        for chunk in vector.load():
            asset_id = str((chunk.metadata or {}).get("asset_id") or "")
            if asset_id:
                chunks_by_asset.setdefault(asset_id, []).append(chunk.node_id)
        concepts = parse_okf_bundle(bundle)
        for concept in concepts:
            concept.source_files = [path for path in concept.source_files if path in mapped]
            concept.source_chunk_ids = list(dict.fromkeys(
                chunk_id for path in concept.source_files for chunk_id in chunks_by_asset.get(mapped[path], [])
            ))
        return concepts

    def pool_concept_scope(self, asset_pool_id: str) -> Optional[Set[str]]:
        """Concepts the pool's graph is restricted to when its graph source is shared; None if not shared."""
        asset_pool = self._require_asset_pool(asset_pool_id)
        graphs = {p.source.source_id for p in asset_pool.projections if isinstance(p, GraphIndexer)}
        shared = any(
            other.asset_pool_id != asset_pool_id and graphs & set(other.source_statuses)
            for other in self._asset_pools.values()
        )
        return set(self.concept_origins(asset_pool_id)) if shared else None

    @staticmethod
    def _task_sources(bundle: Path) -> Optional[Dict[str, str]]:
        """A generated bundle's task manifest as ``{source path: asset id}``, or None if absent."""
        manifest = bundle / "task.json"
        if not manifest.is_file():
            return None
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return {item["path"]: item["asset_id"] for item in data["sources"]}

    def _generated_concepts(self, bundle: Path, documents, vector) -> List[Any]:
        """Parse a generated bundle and resolve provenance by asset id, dropping citations of removed documents."""
        from core.knowledge.okf import parse_okf_bundle, resolve_task_source_chunk_ids

        sources = self._task_sources(bundle)
        if sources is None:
            raise ValueError("A generated OKF bundle needs its task.json manifest")
        live_ids = {asset.asset_id for asset in documents}
        concepts = parse_okf_bundle(bundle)
        for concept in concepts:
            if not concept.ctype or not concept.title or not concept.source_files:
                raise ValueError("Extracted OKF concepts require type, title and source_files")
            unknown = [path for path in concept.source_files if path not in sources]
            if unknown:
                raise ValueError(f"Extracted OKF cites unknown task sources: {unknown}")
            concept.source_files = [path for path in concept.source_files if sources[path] in live_ids]
        concepts = [concept for concept in concepts if concept.source_files]
        resolve_task_source_chunk_ids(concepts, vector.load(), sources)
        return concepts

    def _resolve_okf_concepts(self, asset_pool, projection, vector):
        """``{asset_id: [OKFNode, ...]}`` for every accepted OKF bundle in the pool, provenance-resolved."""
        from core.knowledge.okf import parse_okf_bundle, resolve_source_chunk_ids

        concepts_by_asset: Dict[str, List[Any]] = {}
        manual: List[Any] = []
        generated: List[str] = []
        documents = [
            self._assets[asset_id] for asset_id in asset_pool.asset_ids
            if getattr(self._assets[asset_id], "asset_kind", "document") != "okf"
        ]
        for asset_id in list(asset_pool.asset_ids):
            asset = self._assets.get(asset_id)
            if (
                asset is not None
                and getattr(asset, "asset_kind", "document") == "okf"
                and projection.accepts(asset)
            ):
                bundle = Path(_path_of(asset.origin))
                if self._is_generated_bundle(asset):
                    concepts_by_asset[asset_id] = self._generated_concepts(bundle, documents, vector)
                    generated.append(asset_id)
                elif self._task_sources(bundle) is not None:
                    concepts_by_asset[asset_id] = self._uploaded_task_bundle_concepts(
                        bundle, self._task_sources(bundle), documents, vector,
                    )
                else:
                    concepts_by_asset[asset_id] = parse_okf_bundle(bundle)
                    manual.extend(concepts_by_asset[asset_id])
        all_concepts = manual
        source_root = self._okf_source_root(asset_pool)
        if source_root is not None:
            resolve_source_chunk_ids(all_concepts, vector.load(), source_root)
        elif any(node.source_files for node in all_concepts):
            raise ValueError(
                "OKF source_files require indexed document files in the same pool "
                "to resolve source_chunk_ids before writing to Nebula"
            )
        return self._layer_concepts(concepts_by_asset, generated)

    @staticmethod
    def _layer_concepts(concepts_by_asset: Dict[str, List[Any]], generated: Sequence[str]):
        """Per concept, the uploaded version wins, plus links and chunk ids only generated bundles have."""
        uploaded: Dict[str, Any] = {}
        for asset_id, nodes in concepts_by_asset.items():
            if asset_id not in generated:
                for node in nodes:
                    uploaded.setdefault(node.cid, node)
        layered: Dict[str, Any] = {}
        for asset_id in generated:
            for node in concepts_by_asset[asset_id]:
                top = uploaded.get(node.cid)
                if top is None:
                    continue
                merged = layered.get(node.cid)
                if merged is None:
                    merged = layered[node.cid] = replace(
                        top, links=list(top.links), source_chunk_ids=list(top.source_chunk_ids),
                    )
                merged.links.extend(link for link in node.links if link not in merged.links)
                merged.source_chunk_ids.extend(
                    chunk for chunk in node.source_chunk_ids if chunk not in merged.source_chunk_ids
                )
        if not layered:
            return concepts_by_asset
        return {
            asset_id: [layered.get(node.cid, node) for node in nodes]
            for asset_id, nodes in concepts_by_asset.items()
        }

    def _finish_projection_add(self, asset_pool, projection, assets):
        if not isinstance(projection, GraphIndexer):
            return
        concepts_by_asset = projection.okf_context
        if not concepts_by_asset:
            return
        concepts = list(
            {
                node.cid: node
                for nodes in concepts_by_asset.values()
                for node in nodes
            }.values()
        )
        vector = self._vector_projection(asset_pool)
        if vector is None:
            raise ValueError("OKF graph indexing requires a vector source in the asset pool")
        if not concepts:
            projection.set_okf_context(None)
            return
        # Propagate errors so sync_asset_pool marks the graph source failed.
        vector.build_concept_index(concepts)
        vector.load_concept_index({node.cid for node in concepts})
        projection.set_okf_context(None)

    def routing(self, asset_pool_id: str) -> dict:
        """Which source takes each kind of content in a pool, and how (`vector`, `caption`, `text`, `graph`, `transcript`)."""
        return source_routing.pool_routing(
            self._require_asset_pool(asset_pool_id),
            self._sources,
            list(ROUTING_KINDS),
            self._covers,
        )

    def _covers(self, source: Source, kind: str) -> Optional[str]:
        from core.multimodal.routing import (
            ASSET_ROLES, asset_families, effective_configuration,
        )

        options = effective_configuration(source)
        families = asset_families(options)
        # Exclude roles impossible for the source's asset families.
        if families and families <= {IMAGE, VIDEO, AUDIO}:
            possible = set().union(*(ASSET_ROLES[family] for family in families))
            if kind not in possible:
                return None
        elif families == {DOCUMENT} and kind not in ("text", ROLE_DOC_IMAGE):
            return None
        if kind == ROLE_AUDIO and source.source_type == "vector":
            # Audio is covered by whichever source embeds its transcript.
            profile = source.profile or self.describe_source(source)
            if profile.get("encoder_kind") == "multimodal" and self._covers(
                source, ROLE_L2_TRANSCRIPT
            ):
                return "transcript"
        block = ROUTING_KINDS[kind]
        if not accepts_block(block, options):
            return None
        if source.source_type == "graph":
            return "graph" if block.kind == TEXT else None
        if source.source_type != "vector":
            return None
        profile = source.profile or self.describe_source(source)
        role = role_of(block)
        if profile.get("encoder_kind") == "multimodal":
            return "vector" if role in (profile.get("supported_roles") or ()) else None
        if role in MM_DERIVED_ROLES:
            return None  # derived content is for multimodal sources only
        return "text" if block.kind == TEXT else "caption"

    def retrieve(self, requests: Mapping[str, Any]) -> Dict[str, Any]:
        """As the library retrieves, with each media hit's text replaced by its latest description."""
        results = super().retrieve(requests)
        for scored in (result for found in results.values() for result in found):
            self._show_description(getattr(scored, "node", scored))
        return results

    def _show_description(self, node: Any) -> None:
        """Replace a media node's text with its `l2_caption`, if it has one."""
        metadata = getattr(node, "metadata", None) or {}
        block_id = metadata.get("block_id")
        asset = self._assets.get(str(metadata.get("asset_id") or ""))
        if asset is None or not block_id or metadata.get("kind") not in BINARY_KINDS:
            return
        try:
            stream = asset.content
        except Exception:  # noqa: BLE001
            return
        for block in stream.blocks:
            if (
                role_of(block) == ROLE_L2_CAPTION
                and block.metadata.get("source_block_id") == block_id
                and block.text.strip()
            ):
                node.set_content(block.text)
                return

    def asset_to_record(self, asset: FileAsset) -> dict:
        return asset.to_record()

    def asset_from_record(self, record: Mapping[str, Any]) -> FileAsset:
        asset = FileAsset.from_record(record)
        self._bind_content(asset)
        return asset

    def create_asset(
        self,
        origin: str,
        stream: ContentStream,
        source_id: Optional[str] = None,
    ) -> FileAsset:
        """Store a file's normalized content (in `source_id` or the default store) and return its asset."""
        source = self.content_source(source_id)
        key = asset_key(stream.asset_id)
        self.content_store.put_record(source, key, stream.to_record())
        asset = FileAsset(
            asset_id=stream.asset_id,
            origin=origin,
            content_source_id=source.source_id,
            content_key=key,
            cached=stream,
        )
        self._discard_moved_content(asset)
        self._bind_content(asset)
        return asset

    def create_okf_asset(self, origin: str) -> FileAsset:
        """An OKF bundle asset: provenance-only, its concepts parsed from disk."""
        asset = FileAsset(asset_id=asset_id_for(origin), origin=origin, asset_kind="okf")
        asset.cached = ContentStream(asset_id=asset.asset_id, blocks=[])
        return asset

    def _discard_moved_content(self, asset: FileAsset) -> None:
        """Best-effort drop of the old record of an asset that moved store; shared blobs are left to the sweep."""
        previous = self._assets.get(asset.asset_id)
        if previous is None or not previous.content_source_id:
            return
        if previous.content_source_id == asset.content_source_id:
            return
        source = self._sources.get(previous.content_source_id)
        if source is None:
            return
        try:
            self.content_store.delete(source, previous.content_key)
        except Exception:  # noqa: BLE001
            pass

    def blob_writer(self, source_id: Optional[str] = None):
        """A callable that puts bytes in one of this library's content sources."""
        source = self.content_source(source_id)

        def put_blob(data: bytes, content_type: Optional[str] = None) -> str:
            return self.content_store.put_blob(source, data, content_type)

        return put_blob

    def blob_reader(self):
        """A callable that reads bytes back from this library's content sources."""

        def read_blob(media_key: str, source_id: Optional[str] = None) -> bytes:
            if is_file_uri(media_key):
                # Only a path referenced by a registered asset's block may be opened.
                return self._referenced_media_asset(media_key, source_id).read_blob(media_key)
            source = self._sources.get(source_id) if source_id else None
            if source is not None and source.source_type != "object":
                # A projection source_id: resolve the asset to find its content source.
                return self._referenced_media_asset(media_key, source_id).read_blob(media_key)
            return self.content_store.get_blob(self.content_source(source_id), media_key)

        return read_blob

    def blob_file_path(self, media_key: str, source_id: Optional[str] = None) -> str:
        """Authorized local path of a `file://` blob; blocking, so async callers must offload it."""
        if not is_file_uri(media_key):
            raise ValueError("media key is not a file:// key")
        asset = self._referenced_media_asset(media_key, source_id)
        return asset._origin_file(media_key)

    def _referenced_media_asset(
        self, media_key: str, source_id: Optional[str] = None
    ) -> FileAsset:
        """The registered asset with a binary block referencing `media_key`, within the requested source."""
        from core.multimodal.routing import effective_configuration

        source = self._sources.get(source_id) if source_id else None
        if source_id and source is None:
            raise KeyError(source_id)
        options = effective_configuration(source) if source is not None else {}
        for asset in self._assets.values():
            if source is not None:
                if source.source_type == "object":
                    if asset.content_source_id != source_id:
                        continue
                elif not (
                    accepts_asset(asset, options)
                    and any(
                        asset.asset_id in pool.asset_ids
                        and (
                            source_id in pool.source_statuses
                            or any(p.source.source_id == source_id for p in pool.projections)
                        )
                        for pool in self._asset_pools.values()
                    )
                ):
                    continue
            try:
                blocks = asset.content.blocks
            except Exception:  # noqa: BLE001
                continue
            if any(
                block.kind in BINARY_KINDS
                and block.media_key == media_key
                and (
                    source is None
                    or source.source_type == "object"
                    or accepts_block(block, options)
                )
                for block in blocks
            ):
                return asset
        raise FileNotFoundError("media key is not referenced by a registered asset in this source")

    def _bind_content(self, asset: FileAsset) -> None:
        if not (asset.content_source_id and asset.content_key):
            return

        def load() -> ContentStream:
            source = self.source_for(asset.content_source_id)
            return ContentStream.from_record(
                self.content_store.get_record(source, asset.content_key)
            )

        def read_blob(media_key: str) -> bytes:
            source = self.source_for(asset.content_source_id)
            return self.content_store.get_blob(source, media_key)

        asset.bind(load)
        asset.bind_blobs(read_blob)

    @property
    def document_count(self) -> int:
        return self.asset_count

    @property
    def chunk_count(self) -> int:
        """Chunks across every distinct collection; unreachable backends count as 0."""
        total = 0
        for projection in self.chunk_projections().values():
            try:
                total += projection.count()
            except Exception:  # noqa: BLE001
                continue
        return total

    def collection_infos(self) -> List[CollectionInfo]:
        return [
            CollectionInfo(
                name=collection.name,
                vector_count=self._safe_count(projection),
                dim=collection.dimension,
            )
            for collection, projection in self.chunk_projections().items()
            if isinstance(collection, VectorCollection)
        ]

    @staticmethod
    def _safe_count(projection: ChunkProjection) -> int:
        try:
            return projection.count()
        except Exception:  # noqa: BLE001
            return 0

    def list_assets(self, page_num: int = 1, page_size: int = 20) -> AssetPage:
        """One stable page of stored file and inline-text assets."""
        assets = sorted(
            self._assets.values(), key=lambda asset: (asset.file_name, asset.asset_id)
        )
        start = max(0, (max(1, page_num) - 1) * max(1, page_size))
        window = assets[start: start + max(1, page_size)]
        return AssetPage(
            assets=[self._asset_out(asset) for asset in window],
            total=len(assets),
        )

    def _asset_out(self, asset: FileAsset) -> AssetOut:
        if asset.asset_kind == "okf":
            return AssetOut(
                id=asset.asset_id,
                name=asset.file_name,
                origin=asset.origin,
                kind="okf",
                media_type="",
                content_source_id=asset.content_source_id,
                asset_pool_ids=[
                    asset_pool_id
                    for asset_pool_id, asset_pool in self._asset_pools.items()
                    if asset.asset_id in asset_pool.asset_ids
                ],
            )
        kind = "file" if asset.origin.startswith("file://") else "text"
        return AssetOut(
            id=asset.asset_id,
            name=(
                asset.file_name
                if kind == "file"
                else f"Inline text {asset.asset_id[:8]}"
            ),
            origin=asset.origin,
            kind=kind,
            media_type=asset.media_type or ("text/plain" if kind == "text" else ""),
            content_source_id=asset.content_source_id,
            asset_pool_ids=[
                asset_pool_id
                for asset_pool_id, asset_pool in self._asset_pools.items()
                if asset.asset_id in asset_pool.asset_ids
            ],
        )

    def delete_assets(self, asset_ids: Sequence[str]) -> dict:
        """Delete assets only after every materialized copy can be removed."""
        requested = list(dict.fromkeys(asset_ids))
        missing = [asset_id for asset_id in requested if asset_id not in self._assets]
        if missing:
            raise ValueError(f"Asset(s) not found: {', '.join(missing)}")
        assets = [self._assets[asset_id] for asset_id in requested]
        generated_bundles = [
            f"{asset.file_name!r} ({asset.asset_id})" for asset in assets if self._is_generated_bundle(asset)
        ]
        if generated_bundles:
            raise ValueError(
                "Generated OKF bundle(s) cannot be deleted directly: "
                + ", ".join(generated_bundles)
                + ". The engine owns them: to remove one, delete the documents it was extracted "
                "from (it goes once its pool has no documents left) or delete its asset pool; "
                "to refresh it, run the pool's extraction again"
            )
        relevant_pools = [
            asset_pool
            for asset_pool in self._asset_pools.values()
            if any(asset_id in asset_pool.asset_ids for asset_id in requested)
        ]

        unavailable = {
            source_id: source
            for asset_pool in relevant_pools
            for source_id, source in asset_pool.unavailable_sources.items()
        }
        if unavailable:
            raise ValueError(
                "Cannot delete assets while source(s) are unavailable: "
                + self._source_labels(unavailable)
                + ". " + self.UNAVAILABLE_HINT
            )

        projections = {
            projection.source.source_id: projection
            for asset_pool in relevant_pools
            for projection in asset_pool.projections
        }
        # Plan graph removals before mutating anything, while content and bundles are still readable.
        graph_plans = []
        planned = set()
        for asset_pool in relevant_pools:
            vector = next(
                (p for p in asset_pool.projections
                 if getattr(p, "kind", "") == "vector" and not isinstance(p, MultimodalIndexer)),
                None,
            )
            for graph in asset_pool.projections:
                if not isinstance(graph, GraphIndexer) or graph.source.source_id in planned:
                    continue
                planned.add(graph.source.source_id)
                plan = self._graph_removal_plan(graph, vector, assets, requested)
                if plan is None:
                    continue
                adapter = getattr(graph, "_adapter", None)
                if plan["vertices"] and type(adapter).delete_vertices is GraphAdapter.delete_vertices:
                    raise ValueError(
                        "Cannot delete assets from source(s) without removal support: "
                        + self._source_label(graph.source.source_id, graph.source)
                        + ". " + self.NO_REMOVAL_HINT
                    )
                graph_plans.append(plan)
        # Frozen bindings must lose the rows too, or a rollback would restore them.
        frozen_sources = {
            source_id: source
            for asset_pool in relevant_pools
            for source_id, source in asset_pool.frozen_sources.items()
            if source_id not in projections
        }
        unsupported = {
            source_id: source
            for source_id, source in frozen_sources.items()
            if source.source_type != "vector"
            and any(accepts_asset(asset, source.configuration) for asset in assets)
        }
        if unsupported:
            raise ValueError(
                "Cannot delete assets from source(s) without removal support: "
                + self._source_labels(unsupported)
                + ". " + self.FROZEN_HINT
            )
        # Fail before deleting anything if a frozen source's database is unregistered.
        for source in frozen_sources.values():
            self._databasehub.get_adapter(source.database_id)

        # Only media files the engine holds are deleted; caller-supplied paths are kept.
        owned_files, kept_files = self._media_files_of(assets)

        content_records = []
        blob_candidates = {}
        for asset in assets:
            if not asset.content_source_id or not asset.content_key:
                continue
            source = self._sources.get(asset.content_source_id)
            if source is None:
                raise ValueError(
                    f"Asset {asset.asset_id!r} content source is not registered: its content is in "
                    f"source {asset.content_source_id!r}, which is missing from this library's "
                    "saved configuration. Restore that source entry in the workspace "
                    "configuration and restart the engine, then retry the delete"
                )
            content_records.append((source, asset.content_key))
            for key in self._blob_keys_of(asset):
                blob_candidates.setdefault((source.database_id, source.location, key), source)

        # Remove every deleted asset from each vector source regardless of its current filter.
        materializations_removed = 0
        for projection in projections.values():
            if isinstance(projection, GraphIndexer):
                continue
            accepted_ids = [asset.asset_id for asset in assets]
            if accepted_ids:
                materializations_removed += int(projection.remove(accepted_ids) or 0)
        for plan in graph_plans:
            graph, vector = plan["graph"], plan["vector"]
            materializations_removed += graph.delete_vertices(plan["vertices"])
            if plan["concepts"] and vector is not None and hasattr(vector, "remove_concepts"):
                vector.remove_concepts(plan["concepts"])
            if plan["chunk_ids"]:
                graph.drop_chunk_provenance(plan["chunk_ids"])
        for source_id, source in frozen_sources.items():
            accepted_ids = [
                asset.asset_id
                for asset in assets
                if source.source_type == "vector" or accepts_asset(asset, source.configuration)
            ]
            materializations_removed += sum(
                frozen_bindings.delete_assets(
                    self._databasehub, {source_id: source}, accepted_ids
                ).values()
            )
        for source, key in content_records:
            self.content_store.delete(source, key)

        removed_origins = {asset.origin for asset in assets}
        uploaded_bundles_removed = any(
            asset.asset_kind == "okf" and not self._is_generated_bundle(asset) for asset in assets
        )
        self.forget_assets(requested)
        if uploaded_bundles_removed:
            # Overridden concepts fall back to the generated version: rebuild those bundles.
            for pool in relevant_pools:
                for projection in self._extracting_projections(pool):
                    generated_id = asset_id_for(file_origin(str(
                        self._generated_bundle_path(pool, projection)
                    )))
                    if generated_id in pool.asset_ids:
                        self.note_assets_changed([generated_id], [projection.source.source_id])
        if any(asset.asset_kind != "okf" for asset in assets):
            for pool in relevant_pools:
                extracting = self._extracting_projections(pool)
                if not extracting:
                    continue
                live_documents = [asset_id for asset_id in pool.asset_ids
                                  if self._assets[asset_id].asset_kind != "okf"]
                for projection in extracting:
                    status = pool.source_statuses.get(projection.source.source_id)
                    if not live_documents:
                        self._remove_generated_bundle(pool, projection)
                        if status is not None:
                            status.extraction_done = status.extraction_changes
                        continue
                    # Mark outdated and rebuild so concepts stop citing deleted documents.
                    if status is not None:
                        status.note_extraction_input_changed()
                    generated_id = asset_id_for(file_origin(str(
                        self._generated_bundle_path(pool, projection)
                    )))
                    if generated_id in pool.asset_ids:
                        self.note_assets_changed([generated_id], [projection.source.source_id])
        self.file_map = {
            name: path
            for name, path in self.file_map.items()
            if file_origin(path) not in removed_origins and path not in removed_origins
        }
        self._delete_unreferenced_blobs(blob_candidates)
        files_removed = []
        for path in owned_files:
            try:
                os.unlink(path)
                files_removed.append(path)
            except FileNotFoundError:
                pass
            except OSError:
                kept_files.append(path)
        for path in self._uploaded_originals(assets, owned_files):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.unlink(path)
                files_removed.append(path)
            except FileNotFoundError:
                pass
            except OSError:
                kept_files.append(path)
        return {
            "removed": requested,
            "materializations_removed": materializations_removed,
            "files_removed": files_removed,
            "files_kept": kept_files,
        }

    def _graph_removal_plan(self, graph, vector, assets, requested) -> Optional[dict]:
        """Vertices, concepts and chunk ids that deleting `assets` removes from one graph source, or None."""
        from core.knowledge.okf import parse_okf_bundle

        documents = [a for a in assets if getattr(a, "asset_kind", "document") != "okf"]
        bundles = [a for a in assets if getattr(a, "asset_kind", "document") == "okf" and graph.accepts(a)]
        vertices: List[str] = []
        concepts: List[str] = []
        removing = set(requested)
        kept = set()
        if bundles:
            for asset in bundles:
                try:
                    concepts.extend(node.cid for node in parse_okf_bundle(Path(_path_of(asset.origin))))
                except (OSError, ValueError) as error:
                    raise ValueError(
                        f"Cannot delete OKF asset {asset.file_name!r} ({asset.asset_id}): its bundle "
                        f"cannot be read to tell which concepts it wrote ({error}). Restore the bundle "
                        f"folder at {_path_of(asset.origin)!r}, or remove graph source "
                        f"{self._source_label(graph.source.source_id, graph.source)} from the asset "
                        "pool's sources (its concepts stay in the graph database), then retry"
                    ) from error
        if graph.extracts_documents:
            # Remove generated concepts supported only by the deleted documents.
            for pool in self._asset_pools.values():
                if not any(p.source.source_id == graph.source.source_id for p in pool.projections):
                    continue
                for asset_id in pool.asset_ids:
                    generated = self._assets.get(asset_id)
                    if generated is None or asset_id in removing or generated.asset_kind != "okf":
                        continue
                    bundle = Path(_path_of(generated.origin))
                    try:
                        if not self._is_generated_bundle(generated):
                            continue
                        sources = self._task_sources(bundle) or {}
                        for node in parse_okf_bundle(bundle):
                            support = {sources[path] for path in node.source_files
                                       if sources[path] in self._assets and sources[path] in pool.asset_ids}
                            if support <= removing:
                                concepts.append(node.cid)
                            else:
                                kept.add(node.cid)
                    except (OSError, ValueError, KeyError) as error:
                        raise ValueError(
                            f"Cannot delete assets: the generated OKF bundle of asset pool "
                            f"{pool.asset_pool_id!r} cannot be read ({error}). Run the pool's extraction "
                            f"again to rebuild it (folder {str(bundle)!r}), or remove graph source "
                            f"{self._source_label(graph.source.source_id, graph.source)} from the pool's "
                            "sources, then retry"
                        ) from error
        if concepts:
            for other in self._assets.values():
                if other.asset_id in removing or getattr(other, "asset_kind", "") != "okf":
                    continue
                if not any(
                    other.asset_id in pool.asset_ids
                    and any(p.source.source_id == graph.source.source_id for p in pool.projections)
                    for pool in self._asset_pools.values()
                ):
                    continue
                other_bundle = Path(_path_of(other.origin))
                try:
                    if self._is_generated_bundle(other):
                        continue
                    kept.update(node.cid for node in parse_okf_bundle(other_bundle))
                except (OSError, ValueError, KeyError):
                    # Cannot tell what this bundle shares, so share everything.
                    kept.update(concepts)
            concepts = [cid for cid in dict.fromkeys(concepts) if cid not in kept]
        vertices.extend(concepts)
        chunk_ids: List[str] = []
        if documents and vector is not None:
            gone = {asset.asset_id for asset in documents}
            chunk_ids = [
                node.node_id for node in vector.load()
                if (getattr(node, "metadata", None) or {}).get("asset_id") in gone
            ]
        if not vertices and not chunk_ids:
            return None
        return {
            "graph": graph, "vector": vector,
            "vertices": list(dict.fromkeys(vertices)), "concepts": concepts, "chunk_ids": chunk_ids,
        }

    @staticmethod
    def _media_files_of(assets: Sequence["FileAsset"]) -> tuple:
        """The assets' local media files split into (inside the upload dir, elsewhere), symlinks resolved."""
        import config  # noqa: PLC0415

        uploads = os.path.realpath(config.UPLOAD_DIR)
        owned: List[str] = []
        kept: List[str] = []
        for asset in assets:
            try:
                keys = asset.content.media_keys()
            except Exception:  # noqa: BLE001
                continue
            for key in keys:
                if not is_file_uri(key):
                    continue
                path = os.path.realpath(file_uri_path(key))
                inside = os.path.commonpath([path, uploads]) == uploads
                (owned if inside else kept).append(path)
        return owned, kept

    UNAVAILABLE_HINT = (
        "Their database is not registered or cannot be reached: register or reconnect it on the "
        "Database connections page, or remove the source from the asset pool's sources, then retry"
    )
    NO_REMOVAL_HINT = (
        "This graph backend cannot delete vertices: remove the source from the asset pool's "
        "sources first (its data stays in the database), then retry"
    )
    FROZEN_HINT = (
        "It is stopped or disabled in the asset pool, and its records can only be removed while "
        "it serves: start serving it again or enable it, or remove it from the asset pool's "
        "sources (its data stays in the database), then retry"
    )

    def _source_label(self, source_id: str, source: Any = None) -> str:
        source = source or self._sources.get(source_id)
        name = getattr(source, "name", "") or ""
        return f"{name!r} ({source_id})" if name and name != source_id else repr(source_id)

    def _source_labels(self, sources: Mapping[str, Any]) -> str:
        return ", ".join(
            self._source_label(source_id, source) for source_id, source in sorted(sources.items())
        )

    @staticmethod
    def _syncing_message(asset_pool_id: str, target: str) -> str:
        return (
            f"Asset pool {asset_pool_id!r} is syncing its sources. Wait until every source of the "
            f"pool shows ready or failed, then delete the {target} again"
        )

    @staticmethod
    def _extracting_message(asset_pool_id: str, target: str) -> str:
        return (
            f"Asset pool {asset_pool_id!r} has a running OKF extraction, which cannot be cancelled "
            f"mid-run. Wait for it to finish (see the pool's extraction status), then delete the "
            f"{target} again"
        )

    @staticmethod
    def _blob_keys_of(asset) -> List[str]:
        try:
            keys = asset.content.media_keys()
        except Exception:  # noqa: BLE001
            return []
        return [key for key in keys if key.startswith(f"{BLOB_PREFIX}/")]

    def _sharing_libraries(self) -> List["FileAssetLibrary"]:
        from core.manager import registry

        return [self, *(library for library in registry.list() if library is not self)]

    def _delete_unreferenced_blobs(self, candidates: Mapping[tuple, Source]) -> List[str]:
        from core import materialize

        if not candidates or materialize.ingest_active():
            return []
        stores = {(database_id, location) for database_id, location, _ in candidates}
        referenced = set()
        for library in self._sharing_libraries():
            for asset in list(library.assets.values()):
                source = library.sources.get(asset.content_source_id)
                if source is None or (source.database_id, source.location) not in stores:
                    continue
                try:
                    stream = asset.cached
                    if stream is None and asset.content_key:
                        stream = ContentStream.from_record(
                            library.content_store.get_record(source, asset.content_key)
                        )
                    keys = stream.media_keys() if stream is not None else []
                except Exception:  # noqa: BLE001
                    return []
                referenced.update((source.database_id, source.location, key) for key in keys)
        removed = []
        for candidate, source in candidates.items():
            if candidate in referenced:
                continue
            try:
                self.content_store.delete(source, candidate[2])
                removed.append(candidate[2])
            except Exception:  # noqa: BLE001
                pass
        return removed

    def _uploaded_originals(self, assets: Sequence["FileAsset"], handled: Sequence[str]) -> List[str]:
        seen = set(handled)
        candidates = {}
        for asset in assets:
            if asset.origin.startswith("file://"):
                path = os.path.realpath(_path_of(asset.origin))
                if path not in seen:
                    candidates.setdefault(path, asset.origin)
        if not candidates:
            return []
        root = os.path.realpath(os.path.join(config.UPLOAD_DIR, self.library_id))
        generated_root = os.path.join(root, EXTRACTED_DIRECTORY)
        others = {
            asset.origin
            for library in self._sharing_libraries()
            for asset in library.assets.values()
        }
        return [
            path for path, origin in candidates.items()
            if origin not in others
            and path != root
            and os.path.commonpath([path, root]) == root
            and os.path.commonpath([path, generated_root]) != generated_root
        ]

    def _okf_bundles_in(self, asset_pool, accepts: Callable[[Any], bool]) -> List["FileAsset"]:
        return [
            self._assets[asset_id]
            for asset_id in asset_pool.asset_ids
            if asset_id in self._assets
            and getattr(self._assets[asset_id], "asset_kind", "") == "okf"
            and accepts(self._assets[asset_id])
        ]

    @staticmethod
    def _bundle_concept_ids(asset) -> Set[str]:
        from core.knowledge.okf import parse_okf_bundle

        return {node.cid for node in parse_okf_bundle(Path(_path_of(asset.origin)))}

    def _concepts_defined_elsewhere(
        self, asset_pool_id: str, source_id: str, accepts: Callable[[Any], bool]
    ) -> Optional[Set[str]]:
        kept: Set[str] = set()
        for other in self._asset_pools.values():
            if other.asset_pool_id == asset_pool_id or source_id not in other.source_statuses:
                continue
            for bundle in self._okf_bundles_in(other, accepts):
                try:
                    kept |= self._bundle_concept_ids(bundle)
                except (OSError, ValueError, KeyError):
                    return None
        return kept

    def _pool_removal_plan(self, asset_pool) -> Dict[str, Any]:
        pool_id = asset_pool.asset_pool_id
        others = {
            other.asset_pool_id: (set(other.asset_ids), set(other.source_statuses))
            for other in self._asset_pools.values()
            if other.asset_pool_id != pool_id
        }

        def exclusive(source_id: str) -> List[str]:
            return [
                asset_id for asset_id in asset_pool.asset_ids
                if asset_id in self._assets and not any(
                    asset_id in held and source_id in bound for held, bound in others.values()
                )
            ]

        def accept_all(asset) -> bool:
            return True

        def concepts_here(accepts, strict: bool = True) -> Optional[Set[str]]:
            found: Set[str] = set()
            for bundle in self._okf_bundles_in(asset_pool, accepts):
                try:
                    found |= self._bundle_concept_ids(bundle)
                except (OSError, ValueError, KeyError) as error:
                    if not strict:
                        return None
                    raise ValueError(
                        f"Cannot delete asset pool {pool_id!r}: OKF bundle {bundle.file_name!r} "
                        f"({bundle.asset_id}) cannot be read to tell which concepts it wrote ({error}). "
                        f"Restore the bundle folder at {_path_of(bundle.origin)!r}, or remove the graph "
                        "source from the pool's sources first (its concepts stay in the graph "
                        "database), then delete the pool again"
                    ) from error
            return found

        text_vector = next(
            (p for p in asset_pool.projections
             if getattr(p, "kind", "") == "vector" and not isinstance(p, MultimodalIndexer)),
            None,
        )
        vectors, graphs, concept_vectors, frozen = [], [], [], []
        for projection in asset_pool.projections:
            source_id = projection.source.source_id
            if isinstance(projection, GraphIndexer):
                vertices = concepts_here(projection.accepts)
                if vertices:
                    kept = self._concepts_defined_elsewhere(pool_id, source_id, projection.accepts)
                    vertices = sorted(vertices - kept) if kept is not None else []
                adapter = getattr(projection, "_adapter", None)
                if vertices and type(adapter).delete_vertices is GraphAdapter.delete_vertices:
                    raise ValueError(
                        f"Cannot delete asset pool {pool_id!r} from source(s) without removal support: "
                        + self._source_label(source_id, projection.source)
                        + ". " + self.NO_REMOVAL_HINT
                    )
                chunk_ids: List[str] = []
                if text_vector is not None:
                    gone = {
                        asset_id for asset_id in exclusive(text_vector.source.source_id)
                        if getattr(self._assets[asset_id], "asset_kind", "document") != "okf"
                    }
                    if gone:
                        chunk_ids = [
                            node.node_id for node in text_vector.load()
                            if (getattr(node, "metadata", None) or {}).get("asset_id") in gone
                        ]
                if vertices or chunk_ids:
                    graphs.append((projection, vertices, chunk_ids))
                continue
            ids = exclusive(source_id)
            if ids:
                vectors.append((projection, ids))
            if hasattr(projection, "remove_concepts") and not isinstance(projection, MultimodalIndexer):
                concepts = concepts_here(accept_all, strict=False)
                if concepts:
                    kept = self._concepts_defined_elsewhere(pool_id, source_id, accept_all)
                    if kept is not None and concepts - kept:
                        concept_vectors.append((projection, sorted(concepts - kept)))
        for source_id, source in asset_pool.frozen_sources.items():
            ids = [
                asset_id for asset_id in exclusive(source_id)
                if source.source_type == "vector"
                or self._source_accepts_asset(source, self._assets[asset_id])
            ]
            if not ids:
                continue
            if source.source_type != "vector":
                raise ValueError(
                    f"Cannot delete asset pool {pool_id!r} from source(s) without removal support: "
                    + self._source_label(source_id, source)
                    + ". " + self.FROZEN_HINT
                )
            self._databasehub.get_adapter(source.database_id)
            frozen.append((source_id, source, ids))
        unavailable = {
            source_id: source
            for source_id, source in asset_pool.unavailable_sources.items()
            if any(
                self._source_accepts_asset(source, self._assets[asset_id])
                for asset_id in exclusive(source_id)
            )
        }
        if unavailable:
            raise ValueError(
                f"Cannot delete asset pool {pool_id!r} while source(s) are unavailable: "
                + self._source_labels(unavailable)
                + ". " + self.UNAVAILABLE_HINT
            )
        graph_sources = [p.source for p in asset_pool.projections if isinstance(p, GraphIndexer)]
        graph_sources += [
            source for source in (*asset_pool.frozen_sources.values(), *asset_pool.unavailable_sources.values())
            if source.source_type == "graph"
        ]
        return {
            "vectors": vectors, "graphs": graphs, "concept_vectors": concept_vectors,
            "frozen": frozen, "generated": [self._generated_bundle_dir(asset_pool, s) for s in graph_sources],
        }

    def delete_asset_pool(self, asset_pool_id: str) -> Dict[str, Any]:
        from core import materialize

        asset_pool = self._require_asset_pool(asset_pool_id)
        lock = self._sync_lock(asset_pool_id)
        if not lock.acquire(blocking=False):
            raise ValueError(self._syncing_message(asset_pool_id, "pool"))
        try:
            if materialize.ingest_active(self.idx, asset_pool_id):
                raise ValueError(
                    f"Asset pool {asset_pool_id!r} is ingesting assets. Wait until they show ready "
                    "or failed in the asset list, then delete the pool again"
                )
            if self.extraction_jobs.running_for_pool(self.idx, asset_pool_id):
                raise ValueError(self._extracting_message(asset_pool_id, "pool"))
            plan = self._pool_removal_plan(asset_pool)
            self.extraction_jobs.cancel_pool(self.idx, asset_pool_id)

            removed = 0
            for projection, ids in plan["vectors"]:
                removed += int(projection.remove(ids) or 0)
            concepts_removed = 0
            for graph, vertices, chunk_ids in plan["graphs"]:
                if vertices:
                    concepts_removed += int(graph.delete_vertices(vertices) or 0)
                if chunk_ids:
                    graph.drop_chunk_provenance(chunk_ids)
            for vector, concepts in plan["concept_vectors"]:
                vector.remove_concepts(concepts)
            for source_id, source, ids in plan["frozen"]:
                removed += sum(
                    frozen_bindings.delete_assets(self._databasehub, {source_id: source}, ids).values()
                )
            bundles_removed = []
            for target in plan["generated"]:
                generated_id = asset_id_for(file_origin(str(target)))
                if any(
                    generated_id in other.asset_ids
                    for other in self._asset_pools.values()
                    if other.asset_pool_id != asset_pool_id
                ):
                    continue
                if generated_id in self._assets:
                    self.forget_assets([generated_id])
                    bundles_removed.append(generated_id)
                shutil.rmtree(target, ignore_errors=True)

            self._auto_extraction_revisions = {
                key: value for key, value in self._auto_extraction_revisions.items() if key[0] != asset_pool_id
            }
            self._schedule_fired = {
                key: value for key, value in self._schedule_fired.items() if key[0] != asset_pool_id
            }
            self.remove_asset_pool(asset_pool_id)
            with self._sync_locks_guard:
                self._sync_locks.pop(asset_pool_id, None)
        finally:
            lock.release()
        gc.collect()
        return {
            "asset_pool_id": asset_pool_id,
            "materializations_removed": removed,
            "concepts_removed": concepts_removed,
            "generated_bundles_removed": bundles_removed,
        }

    def delete_all(self) -> Dict[str, Any]:
        from core import materialize

        if materialize.ingest_active(self.idx):
            raise ValueError(
                f"Asset library {self.name!r} is ingesting assets. Wait until they show ready or "
                "failed in the asset list, then delete the library again"
            )
        locks = []
        try:
            for asset_pool_id in list(self._asset_pools):
                lock = self._sync_lock(asset_pool_id)
                if not lock.acquire(blocking=False):
                    raise ValueError(self._syncing_message(asset_pool_id, "library"))
                locks.append(lock)
                if self.extraction_jobs.running_for_pool(self.idx, asset_pool_id):
                    raise ValueError(self._extracting_message(asset_pool_id, "library"))
            deletable = [
                asset_id for asset_id, asset in self._assets.items()
                if not self._is_generated_bundle(asset)
            ]
            try:
                result = self.delete_assets(deletable) if deletable else {
                    "removed": [], "materializations_removed": 0, "files_removed": [], "files_kept": [],
                }
                for asset_pool_id in list(self._asset_pools):
                    self.delete_asset_pool(asset_pool_id)
                if self._assets:
                    self.delete_assets(list(self._assets))
            except ValueError as error:
                raise ValueError(f"Cannot delete asset library {self.name!r}: {error}") from error
        finally:
            for lock in locks:
                lock.release()
        self._clear_own_content()
        self.clear()
        self.file_map = {}
        uploads = os.path.realpath(config.UPLOAD_DIR)
        folder = os.path.realpath(os.path.join(uploads, self.library_id))
        if os.path.dirname(folder) == uploads:
            shutil.rmtree(folder, ignore_errors=True)
        return result

    def _clear_own_content(self) -> None:
        shared = {
            (source.database_id, source.location)
            for library in self._sharing_libraries() if library is not self
            for source in library.sources.values()
            if source.source_type.lower() == "object"
        }
        for source in list(self._sources.values()):
            if (
                source.source_type.lower() != "object"
                or collection_name(source.location) != self.library_id
                or (source.database_id, source.location) in shared
            ):
                continue
            try:
                self._databasehub.get_object_adapter(source.database_id).clear(source.location)
            except Exception:  # noqa: BLE001
                pass

    def to_out(self) -> AssetLibraryOut:
        return AssetLibraryOut(
            id=self.idx,
            name=self.name,
            description=self.description,
            default_content_source_id=self.default_content_source_id,
            content_database=self.content_database,
            asset_count=self.asset_count,
            document_count=self.document_count,
            chunk_count=self.chunk_count,
            sources=[
                SourceOut(
                    id=source.source_id,
                    name=source.name,
                    type=source.source_type,
                    database_id=source.database_id,
                    collection_name=collection_name(source.location),
                    operator_options=redact_operator_options(source.configuration),
                    reconciled=(
                        source.source_id not in self.source_reconciliation_errors
                    ),
                    reconciliation_error=self.source_reconciliation_errors.get(
                        source.source_id
                    ),
                    enabled=source.enabled,
                    labels=dict(source.labels),
                    created_at=source.created_at,
                    profile=dict(source.profile),
                    bindings=[
                        SourceBindingOut(
                            pool_id=pool_id,
                            serving_state=status.serving_state,
                            effective_state=effective,
                            status=status.status,
                        )
                        for pool_id, status, effective in self.source_bindings(
                            source.source_id
                        )
                    ],
                )
                for source in self._sources.values()
            ],
            asset_pools=[
                AssetPoolOut(
                    id=asset_pool.asset_pool_id,
                    name=asset_pool.name,
                    asset_ids=list(asset_pool.asset_ids),
                    revision=asset_pool.revision,
                    source_statuses=[
                        SourceSyncStatusOut(
                            source_id=status.source_id,
                            status=status.status,
                            indexed_revision=status.indexed_revision,
                            indexed_asset_ids=list(status.indexed_asset_ids),
                            error=status.error,
                            updated_at=status.updated_at,
                            serving_state=status.serving_state,
                            effective_state=effective_state(
                                self._sources.get(status.source_id), status
                            ),
                            replaces=status.replaces,
                            serving_history=list(status.serving_history),
                            extraction=self.extraction_out(asset_pool, status),
                        )
                        for status in asset_pool.source_statuses.values()
                    ],
                    metadata=dict(asset_pool.metadata),
                )
                for asset_pool in self._asset_pools.values()
            ],
        )

    def to_record(self) -> dict:
        return {**super().to_record(), "file_map": dict(self.file_map)}

    def restore(self, record: Mapping[str, Any]) -> None:
        super().restore(record)
        self.file_map = dict(record.get("file_map") or {})


def nodes_to_chunks(
    nodes: List[NodeWithScore],
    library: Optional[str] = None,
    pool_id: Optional[str] = None,
) -> List[RetrievedChunk]:
    """Retrieved nodes as the chunks the API returns, stamped with their library and pool."""
    chunks = []
    for scored in nodes:
        node = scored.node
        metadata = {**(node.metadata or {})}
        if library is not None:
            metadata["library"] = library
        if pool_id is not None:
            metadata["pool_id"] = pool_id
        chunks.append(
            RetrievedChunk(
                id=node.node_id,
                text=node.get_content(metadata_mode=MetadataMode.NONE),
                score=float(scored.score) if scored.score is not None else 0.0,
                metadata=metadata,
            )
        )
    return chunks


def chunks_to_nodes(chunks: List[RetrievedChunk]) -> List[NodeWithScore]:
    """Chunks back into nodes, so a stage that works on nodes can run on them."""
    return [
        NodeWithScore(
            node=TextNode(id_=chunk.id, text=chunk.text, metadata=chunk.metadata),
            score=chunk.score,
        )
        for chunk in chunks
    ]


def postprocess_chunks(
    query: str,
    chunks: List[RetrievedChunk],
    processor_type: str = "reranker",
    top_n: Optional[int] = None,
    reranker_model=None,
    *,
    media_libraries=None,
    options=None,
) -> Optional[List[RetrievedChunk]]:
    """Run the postprocessing stage over any chunk set, possibly merged from several libraries."""
    if media_libraries is not None:
        from core.multimodal.reranking import rerank_media

        groups = []
        for chunk in chunks:
            library_name = chunk.metadata.get("library")
            library = media_libraries.get(library_name)
            if library is None:
                raise ValueError(f"retrieved candidate has unknown library {library_name!r}")
            target = chunk.metadata.get("target_media") or "document"
            groups.append((target, [chunk], library))
        ranked, _ = rerank_media(
            query, groups, options, top_n or config.RERANK_TOP_N, strict=True,
        )
        return ranked
    processed = postprocess_nodes(
        query, chunks_to_nodes(chunks), processor_type, top_n, reranker_model
    )
    return nodes_to_chunks(processed)
