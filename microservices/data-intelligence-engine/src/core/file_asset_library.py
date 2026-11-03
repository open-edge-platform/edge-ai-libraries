# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The file-and-chunk specialization of an asset library.

**An asset is one file** -- a text document, a PDF, a spreadsheet, an image, a
recording. Not one of the pieces a loader split it out of, and not a modality:
whatever the file holds is normalized into one `ContentStream` of typed blocks,
and it is the projection's job to turn those blocks into whatever its backend
stores. So there is one asset class here, not one per file type.

Everything generic about holding assets, registering sources, and keeping pools
materialized lives in `data-intelligence-engine/src/assetlib/library.py:AssetLibrary`. What is left
here is only what RAG decides:

- **the asset** -- `FileAsset`: where the file came from, and where its
  normalized content is stored,
- **the projections** -- a vector source becomes a `VectorIndexer`, a graph
  source a `GraphIndexer` (`PROJECTION_TYPES`),
- **assets** -- listing and deletion of stored content and its projections
  asset registry, addressed by file name rather than by asset id,
- **chunks** -- the counts the API reports, and the node/chunk conversion the
  retrieval endpoints speak.

There is no active/inactive state. An asset library is identified by name or id
on every call; which libraries a chat retrieves from is the caller's decision.

`postprocess_chunks` at the bottom is the postprocessing stage, and it is a
module function rather than a method on purpose: it reranks a result set that
may have been merged from several asset libraries, so no single one owns it.
"""

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
from assetlib.content import asset_key
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


#: Options that choose which blocks a source takes rather than how it embeds
#: them. Part of a profile all the same: two sources that take different
#: blocks hold different records.
_ROUTING_OPTIONS = ("asset_types", "block_kinds", "block_roles")


def describe_vector_source(configuration: Mapping[str, Any]) -> dict:
    """The profile of a vector source, with engine defaults filled in.

    Defaults are resolved here, at creation, because that is when they decide
    the vectors: a source created while `ENGINE_DOC_EMBEDDING_MODEL_ID` named one
    model keeps saying so after the variable changes. A multimodal source's
    model and its path are also what it is built from later (`build_projection`).
    """
    import config
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
    # This backend is main's document/fused path, even if its model directory
    # also identifies a registry model. It must keep the text indexer contract.
    # An explicit text-capable model ID also inherits the text backend. Keep
    # media-only models (e.g. X-CLIP) on their registry runtime when no backend
    # was requested, just like bare video/image/audio category defaults.
    native_text = not media_scope and backend == "native_openvino_gme" and bool(
        configuration.get("embedding_backend")
    )
    if not media_scope and backend == "native_openvino_gme" and not native_text and (
        configuration.get("embedding_model")
    ):
        model = registry.lookup(
            configuration.get("embedding_model"), None
        )
        native_text = model is None or TEXT in model.supported_kinds
    if native_text:
        model = registry.lookup(
            configuration.get('embedding_model'), None
        )
        # A document adapter is not a way to bypass media source validation.
        if model is not None and TEXT not in model.supported_kinds:
            native_text = False
        if set(configuration.get('block_kinds') or ()) & {AUDIO, VIDEO}:
            native_text = False
    resolved = (
        None if native_text else registry.resolve(configuration)
    )
    if resolved is not None:
        return build_profile(
            "multimodal",
            backend=resolved.backend,
            model=resolved.model_id,
            params={**routing, **resolved.params},
            multimodal_model=resolved.record(),
            device=configuration.get("embedding_device"),
            supported_roles=sorted(resolved.model.supported_roles),
            supported_asset_types=sorted(resolved.model.supported_asset_types),
        )
    model_id = configuration.get("embedding_model") or config.EMBEDDING_MODEL_ID
    model_path = (
        config.EMBEDDING_MODEL_PATH if model_id == config.EMBEDDING_MODEL_ID else model_id
    )
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
        device=configuration.get("embedding_device") or config.EMBEDDING_DEVICE,
        model_id=model_id,
        model_path=model_path,
    )


@dataclass
class FileAsset:
    """One ingested file: where it came from, and where its content lives.

    The content is **not** held here. `content_source_id` names a registered
    `Source` -- a filesystem or object-store location like any other source --
    and `content_key` names the record within it. The stream is read on demand
    and cached, so a library with a large corpus neither serializes every
    file into `asset_library.json` on every save nor keeps the whole corpus
    resident in memory.

    `origin` is provenance and nothing more: a URI saying where the file was
    *read from*. It used to be a `Source` with no adapter -- an object that
    looked like a place you could reach but was not one.

    There is deliberately no `.document` here any more. It was a derived
    llama-index `Document` holding every block's text joined into one string,
    and it existed only so `VectorIndexer` did not have to change when the
    content stream landed. It cost more than it saved: joining the blocks threw
    away the page and bounding box each one carried, so no chunk could be cited
    to a page, and it dropped figures entirely -- which made the figure-as-image
    -node case impossible to express and turned a media file into an empty
    document that silently produced no chunks. Projections read `content` and
    build their own nodes (`data-intelligence-engine/src/core/indexer.py`).
    """

    asset_id: str
    origin: str = ""
    content_source_id: str = ""
    content_key: str = ""
    #: "document" for a normal file, "okf" for a concept bundle (provenance-only).
    asset_kind: str = "document"
    # Neither is persisted: `loader` is bound by the library, `cached` is the
    # stream once read (or the one it was created with).
    loader: Optional[Callable[[], ContentStream]] = field(
        default=None, repr=False, compare=False
    )
    cached: Optional[ContentStream] = field(default=None, repr=False, compare=False)
    # Reads one blob out of the same content source. Bound alongside `loader`,
    # and for the same reason: a projection that embeds a picture is handed
    # assets, not the library, so the way to its bytes has to travel with it.
    blob_reader: Optional[Callable[[str], bytes]] = field(
        default=None, repr=False, compare=False
    )

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
        """A local path the decoders can open for what a media block points at.

        A standalone media file is the asset itself, so its key is the file and
        the path is handed straight over: nothing is read, copied or written.
        Only a blob in the content store has to be put on disk first, because
        OpenCV and ffprobe take a seekable path and not bytes; that temporary
        file is removed when the block exits.
        """
        if is_file_uri(media_key):
            yield self._origin_file(media_key)
            return
        from core.multimodal import frames  # noqa: PLC0415 - decoders are optional

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
        """The file's MIME type, guessed from its name.

        Derived from `origin`, so asking costs nothing -- which matters because
        `Projection.accepts` is asked of every asset on every sync, and loading
        the content stream to answer would cost as much as indexing it.
        """
        return mimetypes.guess_type(_path_of(self.origin))[0] or ""

    @property
    def extension(self) -> str:
        return os.path.splitext(_path_of(self.origin))[1].lower().lstrip(".")

    # --- persistence ----------------------------------------------------------

    def to_record(self) -> dict:
        record = {
            "asset_id": self.asset_id,
            "origin": self.origin,
            "asset_kind": self.asset_kind,
        }
        if self.asset_kind == "okf":
            # An OKF bundle is provenance-only: its concepts are parsed from the
            # directory on disk, not stored as a content stream.
            return record
        if self.content_source_id and self.content_key:
            record["content_source_id"] = self.content_source_id
            record["content_key"] = self.content_key
        else:
            # No content source yet -- an asset restored from an older workspace
            # and not re-ingested since. Keep it inline rather than lose it.
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
            # Older workspaces persisted the llama-index document inline.
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
    """A stable id for the thing this origin names.

    **An asset is one file, or one object a user would recognize as a thing** --
    not one of the pieces a loader happened to split it into. So its id comes
    from where it came from, and re-ingesting the same file updates that asset
    rather than creating a second one. Deriving the id from the loader's
    document id instead, as this used to, made every re-ingest a fresh asset and
    left the previous version's chunks in the collection with nothing pointing
    at them.
    """
    return hashlib.sha256(origin.encode("utf-8")).hexdigest()[:32]


def _origin_uri(record: Mapping[str, Any]) -> str:
    """The provenance URI, however this record spelled it.

    It was a full `Source` record under `origin`, and before that under
    `source`; both carried the path in `collection`.
    """
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


#: Folder, inside a library's upload area, holding the OKF bundles graph sources
#: extracted from documents (one stable folder per pool and source).
EXTRACTED_DIRECTORY = "okf-extracted"
#: What the routing report asks about: one representative block per role a
#: pool can hold, plus a document's prose (which has none).
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

    # Only these source types have a projection; a pool over a sql or object
    # source is a bad request, not an internal error.
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
        # Graph sources turning documents into OKF, off the sync path.
        self.extraction_jobs = ExtractionJobs(
            self._run_extraction_job, on_finished=self._save_after_extraction
        )
        # An unchanged sync must not extend an auto job's quiet period or request
        # another run while it is already extracting. Track document changes,
        # not pool revisions (which also move for generated/uploaded OKF assets).
        self._auto_extraction_revisions: Dict[
            Tuple[str, str], Tuple[SourceSyncStatus, int]
        ] = {}
        # (pool, source) -> the cron minute a `schedule` trigger last fired for.
        self._schedule_fired: Dict[Tuple[str, str], datetime] = {}

    # --- what the library asks of a specialization ----------------------------

    def create_source(self, name, database_id, collection_name="", configuration=None,
                      register=True, **options):
        """As the base class, but a graph source's knowledge settings are checked
        first: its formats (`asset_types`) and, for ``document``, the external
        extractor's access parameters. A bad source is refused here rather than
        failing at its first sync. Other keywords (`enabled`, `labels`...) pass
        through unchanged."""
        source = super().create_source(
            name, database_id, collection_name, configuration, register=False, **options
        )
        if source.source_type == "graph":
            Knowledge(source.configuration)
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
            # So a multimodal projection can read a figure's pixels back by
            # media_key when it precomputes the fused vector. Not persisted:
            # VectorIndexer pops it out of its configuration.
            configuration["blob_reader"] = self.blob_reader()
        # A multimodal source is still a vector source: same type, same adapter,
        # same collection, and it is only the model that differs. So the choice
        # is a configured model rather than a source type of its own -- which
        # also means a pool can hold several of them at different widths.
        profile = source.profile or self.describe_source(source)
        if source_type == "vector" and profile.get("encoder_kind") == "multimodal":
            indexer_type = MultimodalIndexer
            configuration['embedding_backend'] = profile.get('backend')
        elif source_type == "vector":
            # Build from the same frozen options that describe stored vectors,
            # not today's defaults. Older profiles only recorded `model` (an id
            # or path); keep its recorded identity for the missing half.
            for option, value in (
                ("embedding_backend", profile.get("backend")),
                ("embedding_device", profile.get("device")),
                ("embedding_model", profile.get("model_id")
                 or configuration.get("embedding_model") or profile.get("model")),
                ("embedding_model_path", profile.get("model_path")
                 or profile.get("model")),
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

    # --- sync coordination ----------------------------------------------------

    def _sync_projection_order(self, asset_pool):
        # Vector first, so a graph sync can resolve OKF source chunks against
        # chunks already written to Milvus (edgecraftrag relied on two separate
        # uploads for the same ordering).
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
        """The common path of the pool's normal document files, or None.

        Mirrors edgecraftrag's ``os.path.commonpath(file_paths)`` fallback-to-parent.
        Inline (``inline:``) assets have no filesystem path and are skipped.
        """
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
            # Documents changed. Extracting is an LLM pass over the whole corpus,
            # so it is a job of its own (`request_extraction`), not part of
            # syncing: this only records that the generated bundle is behind.
            status = asset_pool.source_statuses.get(projection.source.source_id)
            if status is not None:
                status.note_extraction_input_changed()
        projection.set_okf_context(
            self._resolve_okf_concepts(asset_pool, projection, vector) or None
        )

    def _generated_bundle_path(self, asset_pool, projection) -> Path:
        """Where a graph source's extracted bundle lives: a stable folder in the
        library's upload area, so its asset id survives re-extraction."""
        import config

        def slug(value: str) -> str:
            return re.sub(r"[^0-9A-Za-z_-]+", "-", value).strip("-") or "x"

        source = projection.source
        name = f"{slug(asset_pool.asset_pool_id)}-{slug(source.name or 'graph')}-{source.source_id[:8]}"
        return Path(config.UPLOAD_DIR) / self.idx / EXTRACTED_DIRECTORY / name

    def _extract_documents_to_okf_asset(self, asset_pool, projection, vector, documents):
        """Turn `documents` into an OKF bundle and ingest it as an `okf` asset.

        The extractor service writes the bundle into the shared upload area;
        once its provenance checks out against the pool's chunks it replaces the
        source's previous bundle in a stable folder and is registered (or
        updated) as an asset of this pool -- visible like an uploaded bundle,
        and built into the graph by the next sync. Concepts the previous
        bundle had and this one lacks are retired from the graph and the
        concept index. A failed request or an invalid bundle changes nothing.
        Returns the bundle asset and its concepts.
        """
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
            # Re-extraction can drop or rename concepts; upserting alone would
            # leave the old vertices and seed vectors searchable.
            projection.delete_vertices(obsolete)
            vector.remove_concepts(obsolete)
        return asset, concepts

    # --- extraction jobs --------------------------------------------------------

    def sync_asset_pool(self, asset_pool_id: str, auto_extract: bool = True) -> None:
        """As the base class; then queue extraction for each `auto` graph source
        whose generated bundle the sync found out of date, once changes settle
        (its `debounce_seconds`). Only a new document change resets that wait."""
        super().sync_asset_pool(asset_pool_id)
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
        """Queue extraction for `schedule` graph sources whose cron minute is
        `now` (in their time zone) and whose bundle is out of date. Called by
        `ExtractionScheduler` more than once a minute; each minute fires once."""
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
                # A job still running from an earlier minute is not followed
                # up: changes it missed keep the source outdated for the next.
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
        """Queue extraction of a pool's documents for one graph source (the
        pool's only extracting one when `source_id` is omitted). Returns the job
        and whether it is new; an active job for the same pair is returned
        instead of starting a second one."""
        asset_pool = self._require_asset_pool(asset_pool_id)
        projection = self._extracting_projection(asset_pool, source_id)
        return self.extraction_jobs.request(
            self.idx, asset_pool_id, projection.source.source_id, "manual", force
        )

    def run_extraction(self, asset_pool_id: str, source_id: str, force: bool = False) -> Dict[str, Any]:
        """Extract the pool's documents for one graph source, publish the bundle
        as a pool asset and build it. Skipped when nothing changed since the
        last extraction, unless `force`."""
        asset_pool = self._require_asset_pool(asset_pool_id)
        # Index the documents first: the bundle's provenance resolves to their
        # chunks. This also records any change the extraction should cover.
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
        """Persist the published bundle and statuses (a job ends off-request)."""
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
        """The whole current corpus, so task instructions and entity identities
        do not depend on which documents changed."""
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
        """Which kind of OKF bundle in the pool defines each concept id:
        ``uploaded``, ``generated``, or ``both`` (an uploaded override).
        Read from the bundles on disk; one that cannot be read is skipped."""
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
        """Whether an `okf` asset is a bundle the engine published for one of
        its pools. Known by where it lives -- a graph source's generated folder
        (`_generated_bundle_path`) -- not by carrying a task.json: a copy of an
        engine bundle uploaded elsewhere is the user's, and its manifest names
        documents of another pool."""
        if getattr(asset, "asset_kind", "") != "okf":
            return False
        return any(
            asset.asset_id == asset_id_for(file_origin(str(self._generated_bundle_path(pool, projection))))
            for pool in self._asset_pools.values() if asset.asset_id in pool.asset_ids
            for projection in self._extracting_projections(pool)
        )

    def _uploaded_task_bundle_concepts(self, bundle: Path, sources, documents, vector) -> List[Any]:
        """An uploaded copy of an engine bundle: its task paths name documents
        by a task-local folder (`<id>/02_theft.md`), so match them to this
        pool's documents by file name where that is unique. A concept keeps
        whatever resolves -- like any uploaded bundle, it is not dropped for
        citing a document the pool does not have."""
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
        """The concepts a pool's graph view and graph retrieval keep to, or None
        for all of its graph source's.

        A graph source attached to several pools writes all their concepts into
        one space; each pool then sees only those its own OKF bundles define.
        A graph source of one pool needs no filter (and keeps working for a
        pool whose bundles cannot be read back)."""
        asset_pool = self._require_asset_pool(asset_pool_id)
        graphs = {p.source.source_id for p in asset_pool.projections if isinstance(p, GraphIndexer)}
        shared = any(
            other.asset_pool_id != asset_pool_id and graphs & set(other.source_statuses)
            for other in self._asset_pools.values()
        )
        return set(self.concept_origins(asset_pool_id)) if shared else None

    @staticmethod
    def _task_sources(bundle: Path) -> Optional[Dict[str, str]]:
        """A generated bundle's task manifest as ``{source path: asset id}``,
        or None for a bundle authored outside the engine."""
        manifest = bundle / "task.json"
        if not manifest.is_file():
            return None
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return {item["path"]: item["asset_id"] for item in data["sources"]}

    def _generated_concepts(self, bundle: Path, documents, vector) -> List[Any]:
        """Parse a generated bundle and resolve its provenance by asset id.

        Concepts cite task source paths, mapped to document asset ids by the
        task manifest. Citations of documents no longer in the pool are dropped
        (a concept left with none is dropped too), so a deleted document is
        never reintroduced from an older bundle.
        """
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
        """Parse and provenance-resolve every OKF bundle in the pool, once.

        Returns ``{asset_id: [OKFNode, ...]}`` for all OKF assets the graph
        projection accepts. The graph write (one bundle per batch asset) and the
        concept vector index (the union of every bundle) both read these, so a
        bundle is parsed exactly once per sync rather than once for each.

        ``source_chunk_ids`` resolve against the chunks the vector projection has
        already written (vector syncs first). With no document files in the pool
        there is nothing to resolve against, so a concept that names
        ``source_files`` is an error -- the same contract edgecraftrag enforced.
        """
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
                    # Extracted by the engine: provenance by document asset id.
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
        """Uploaded bundles take precedence over generated ones, per concept.

        A concept both define (same id) is written as the uploaded version --
        its type, title, summaries and body -- plus the relations and chunk
        citations only the generated one has. Every bundle defining it carries
        that same merged node, so which bundle a sync writes first, and whether
        it writes them together, no longer decides the vertex or the concept
        vector. Among uploaded bundles the first in the pool wins, as before.
        """
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
        # Build concept vectors during ingestion only, covering every OKF asset in
        # the pool (deduped by cid), reusing the parse `_prepare_projection_add`
        # did. Retrieval reads persisted concepts and provenance from Nebula.
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
            # Nothing to index -- and checking the index for no concepts would
            # report it missing.
            projection.set_okf_context(None)
            return
        # Propagate errors so sync_asset_pool marks the graph source failed.
        vector.build_concept_index(concepts)
        vector.load_concept_index({node.cid for node in concepts})
        projection.set_okf_context(None)

    def routing(self, asset_pool_id: str) -> dict:
        """Which source takes each kind of content in a pool, and how.

        `via` is `vector` for a model that embeds the content itself, `caption`
        for a text model embedding a media block's caption, `text` for prose,
        `graph` for a knowledge-graph source, `transcript` for a model that
        embeds a recording through its speech transcript. File scopes exclude
        impossible roles, but this summary cannot express extension/MIME-specific
        acceptance; actual indexing always checks the individual file too.
        """
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
        # A report has no actual file, but can exclude impossible parent types:
        # an image-only source cannot hold a PDF's doc_image block, for example.
        if families and families <= {IMAGE, VIDEO, AUDIO}:
            possible = set().union(*(ASSET_ROLES[family] for family in families))
            if kind not in possible:
                return None
        if kind == ROLE_AUDIO and source.source_type == "vector":
            # No model embeds the sound; a recording is covered by whoever
            # embeds its transcript.
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
        """As the library retrieves, with each media hit shown by its description.

        A clip's node keeps the caption it was written with -- its file name,
        since the description arrives minutes later and rewriting the node
        would mean re-encoding the clip for the same vector. The description is
        read from the content stream here instead, so a result always shows the
        latest one and nothing is re-embedded. Display only: the node's vector
        is untouched.
        """
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
        except Exception:  # noqa: BLE001 - a missing record must not fail retrieval
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

    # --- content --------------------------------------------------------------

    def create_asset(
        self,
        origin: str,
        stream: ContentStream,
        source_id: Optional[str] = None,
    ) -> FileAsset:
        """Store a file's normalized content and return the asset that points at it.

        Content is written here, at ingest, and not on the way to disk in
        `to_record` -- so saving the library stays a small, quick write under the
        registry lock however large the corpus is.

        `source_id` names the object source to write to; without it the content
        goes to the library's default. Assets in one library may therefore live
        in different stores, which is why each one records where it went.
        """
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
        """An OKF bundle asset: provenance-only, its concepts parsed from disk.

        The graph projection reads the bundle directory from `origin` at sync
        time; there is no content stream to store. An empty stream is kept in
        memory so `asset.content` never raises on paths that touch it.
        """
        asset = FileAsset(asset_id=asset_id_for(origin), origin=origin, asset_kind="okf")
        asset.cached = ContentStream(asset_id=asset.asset_id, blocks=[])
        return asset

    def _discard_moved_content(self, asset: FileAsset) -> None:
        """Drop the previous record of an asset that has just moved store.

        Asset ids are stable, so re-ingesting a file into a different source
        leaves the old record behind with nothing pointing at it -- and a
        document record is keyed by identity (`assets/<asset_id>.json`), so
        nothing else can be referring to it either. Best effort: the new content
        is already written, and failing the ingest over an unreachable old store
        would be the wrong trade. Blobs are left for the sweep they are designed
        for -- they are content-addressed, so another asset may share them.
        """
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
        except Exception:  # noqa: BLE001 - an orphan record is not worth failing on
            pass

    def blob_writer(self, source_id: Optional[str] = None):
        """A callable that puts bytes in one of this library's content sources.

        Handed to the extractor so a figure's pixels are stored *before* the
        content record that names them is written -- a record can then never
        point at a blob that does not exist, however the ingest ends. Blobs are
        content-addressed, so an ingest that dies after writing them leaves
        unreferenced bytes to be swept, not a broken asset.
        """
        source = self.content_source(source_id)

        def put_blob(data: bytes, content_type: Optional[str] = None) -> str:
            return self.content_store.put_blob(source, data, content_type)

        return put_blob

    def blob_reader(self):
        """A callable that reads bytes back from this library's content sources.

        Symmetric to `blob_writer` and injected into a vector projection: with a
        multimodal embedding model the projection reads a figure's pixels by
        `media_key` to embed image and caption jointly. The asset's own content
        source is passed per call, because assets in one library may live in
        different stores -- and a blob was written to the same source its content
        record went to (`create_asset`), which is `asset.content_source_id`.
        """

        def read_blob(media_key: str, source_id: Optional[str] = None) -> bytes:
            if is_file_uri(media_key):
                # Never treat a caller's URI as permission to open that path.
                # Only an exact binary-block reference in a registered asset
                # grants access, constrained by the requested content/source.
                return self._referenced_media_asset(media_key, source_id).read_blob(media_key)
            source = self._sources.get(source_id) if source_id else None
            if source is not None and source.source_type != "object":
                # Retrieved source_id identifies the projection, not the object
                # store. Resolve its asset before choosing the content source.
                return self._referenced_media_asset(media_key, source_id).read_blob(media_key)
            return self.content_store.get_blob(self.content_source(source_id), media_key)

        return read_blob

    def blob_file_path(self, media_key: str, source_id: Optional[str] = None) -> str:
        """Resolve a local blob for streaming, only after reference authorization.

        Reuse the byte reader's exact asset/block/source checks without loading
        the file's bytes. Callers doing async I/O must offload this lookup, since
        an asset's content record may need to be loaded from its store.
        """
        if not is_file_uri(media_key):
            raise ValueError("media key is not a file:// key")
        asset = self._referenced_media_asset(media_key, source_id)
        return asset._origin_file(media_key)

    def _referenced_media_asset(
        self, media_key: str, source_id: Optional[str] = None
    ) -> FileAsset:
        """Find an exact registered media reference within the requested source.

        An object source constrains where the content lives. A projection source
        constrains pool membership and its asset/block filters. In particular,
        merely living next to a registered file (or sharing its origin URI)
        does not make a path readable.
        """
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
            except Exception:  # noqa: BLE001 - unreadable assets grant no access
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
        """Teach the asset how to read its stream and its blobs, if it has any."""
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

    # --- counts ---------------------------------------------------------------

    @property
    def document_count(self) -> int:
        """Exactly `asset_count`, kept because the API schema still reports it.

        One asset is one file, so there is nothing for this to count separately.
        Derived rather than tallied, so it cannot drift from the truth.
        """
        return self.asset_count

    @property
    def chunk_count(self) -> int:
        """Chunks across every distinct collection this asset library projects to.

        Asked of the backend rather than tallied as ingests go by: the tally was
        never incremented on the way in, so it reported 0 forever. A backend that
        cannot answer contributes 0 rather than failing the request.
        """
        total = 0
        for projection in self.chunk_projections().values():
            try:
                total += projection.count()
            except Exception:  # noqa: BLE001 - reporting must not fail
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
        except Exception:  # noqa: BLE001 - reporting must not fail
            return 0

    # --- assets ---------------------------------------------------------------

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
        relevant_pools = [
            asset_pool
            for asset_pool in self._asset_pools.values()
            if any(asset_id in asset_pool.asset_ids for asset_id in requested)
        ]

        unavailable = {
            source_id
            for asset_pool in relevant_pools
            for source_id in asset_pool.unavailable_sources
        }
        if unavailable:
            raise ValueError(
                "Cannot delete assets while source(s) are unavailable: "
                + ", ".join(sorted(unavailable))
            )

        projections = {
            projection.source.source_id: projection
            for asset_pool in relevant_pools
            for projection in asset_pool.projections
        }
        # Graph sources cannot remove by asset id (see `_graph_removal_plan`), so
        # what each one must lose is worked out now, while the assets' content
        # and bundles can still be read -- and before anything is mutated, so a
        # plan that cannot be made refuses the delete rather than half-doing it.
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
                        + graph.source.source_id
                    )
                graph_plans.append(plan)
        # Frozen bindings hold data but no projection; their rows go too, or a
        # rollback would bring deleted assets back. A source frozen in one pool
        # and live in another is already covered by its projection.
        frozen_sources = {
            source_id: source
            for asset_pool in relevant_pools
            for source_id, source in asset_pool.frozen_sources.items()
            if source_id not in projections
        }
        unsupported = {
            source_id
            for source_id, source in frozen_sources.items()
            if source.source_type != "vector"
            and any(accepts_asset(asset, source.configuration) for asset in assets)
        }
        if unsupported:
            raise ValueError(
                "Cannot delete assets from source(s) without removal support: "
                + ", ".join(sorted(unsupported))
            )
        # Reach every frozen source's database now, before anything is deleted,
        # so an unregistered one fails the request instead of half of it.
        for source in frozen_sources.values():
            self._databasehub.get_adapter(source.database_id)

        # A standalone media file is the asset, so deleting the asset takes the
        # file with it -- but only a file the engine itself holds. A path the
        # caller supplied is theirs, and is left alone and reported.
        owned_files, kept_files = self._media_files_of(assets)

        content_records = []
        for asset in assets:
            if not asset.content_source_id or not asset.content_key:
                continue
            source = self._sources.get(asset.content_source_id)
            if source is None:
                raise ValueError(
                    f"Asset {asset.asset_id!r} content source is not registered"
                )
            content_records.append((source, asset.content_key))

        materializations_removed = 0
        for projection in projections.values():
            if isinstance(projection, GraphIndexer):
                continue
            accepted_ids = [
                asset.asset_id for asset in assets if projection.accepts(asset)
            ]
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
                if accepts_asset(asset, source.configuration)
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
            # Concepts an uploaded bundle overrode fall back to the generated
            # version: rebuild the generated bundles it shared pools with.
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
                        # Nothing left to extract from: the generated bundle goes
                        # too (its concepts were removed with the documents above).
                        self._remove_generated_bundle(pool, projection)
                        if status is not None:
                            status.extraction_done = status.extraction_changes
                        continue
                    # The corpus changed: the generated bundle is out of date
                    # until re-extracted (its source's trigger decides when).
                    # Meanwhile rebuild it, so its concepts stop citing the
                    # deleted documents.
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
        files_removed = []
        for path in owned_files:
            try:
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
        """What deleting `assets` takes out of one graph source, or None.

        - An OKF bundle wrote its concepts, keyed by concept id rather than by
          asset. They are read back from the bundle on disk, and any concept a
          remaining bundle in this source also defines is kept.
                - Generated concepts supported only by deleted documents are removed;
                    a concept supported by a surviving document/manual bundle stays.
                    Surviving concepts drop the deleted chunk ids afterwards
                    (`drop_chunk_provenance`).
        """
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
                        f"Cannot delete OKF asset {asset.asset_id!r}: its bundle cannot be read "
                        f"to tell which concepts it wrote ({error})"
                    ) from error
        if graph.extracts_documents:
            # Generated bundles are pool assets; a concept in one whose live
            # support is only the deleted documents goes now, the rest stay
            # until the corpus is re-extracted on the next sync.
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
                        raise ValueError(f"Cannot delete assets: generated OKF bundle cannot be read ({error})") from error
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
                        # Generated: its concepts' support was weighed per
                        # document above, so it does not keep them wholesale.
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
        """The local files these assets point at, split into engine-owned and not.

        Owned means inside the upload directory, which is where files are staged
        for ingest. Resolved through symlinks first, so a link planted in there
        cannot make a file elsewhere look like the engine's.
        """
        import config  # noqa: PLC0415

        uploads = os.path.realpath(config.UPLOAD_DIR)
        owned: List[str] = []
        kept: List[str] = []
        for asset in assets:
            try:
                keys = asset.content.media_keys()
            except Exception:  # noqa: BLE001 - a missing record must not block deleting
                continue
            for key in keys:
                if not is_file_uri(key):
                    continue
                path = os.path.realpath(file_uri_path(key))
                inside = os.path.commonpath([path, uploads]) == uploads
                (owned if inside else kept).append(path)
        return owned, kept

    # --- reporting ------------------------------------------------------------

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

    # --- persistence ----------------------------------------------------------

    def to_record(self) -> dict:
        """This asset library as persisted in the workspace.

        The chunks already live in Milvus, and the counts are derived from them,
        so what has to be written down is identity, sources, assets, pools, and
        which files were ingested.
        """
        return {**super().to_record(), "file_map": dict(self.file_map)}

    def restore(self, record: Mapping[str, Any]) -> None:
        super().restore(record)
        self.file_map = dict(record.get("file_map") or {})


# --- chunks <-> nodes ---------------------------------------------------------


def nodes_to_chunks(
    nodes: List[NodeWithScore],
    library: Optional[str] = None,
    pool_id: Optional[str] = None,
) -> List[RetrievedChunk]:
    """Retrieved nodes as the chunks the API returns, stamped with their pool.

    `source_id` is left as the node carries it -- the source that produced the
    record, stamped by the library or pool retriever. It used to be overwritten with the
    pool id, which made results from different models in one pool
    indistinguishable.
    """
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
    """Run the postprocessing stage over any chunk set, whoever retrieved it.

    Each chunk keeps the asset library metadata it already carries, so a merged
    result set stays attributable.
    """
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
