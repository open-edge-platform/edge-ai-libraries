# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Collection, Dict, List, Mapping, Optional, Sequence, Set

from assetlib.contracts import Source
from assetlib.sources import exposure
from assetlib.models import (
    GraphIngestRequest,
    GraphRetrieveRequest,
    VectorIngestRequest,
    VectorRetrieveRequest,
)
from core.content import (
    AUDIO,
    BINARY_KINDS,
    IMAGE,
    LAYOUT_METADATA_KEYS,
    MM_DERIVED_ROLES,
    ROLE_DOC_IMAGE,
    ROLE_IMAGE,
    ROLE_L1_SEGMENT,
    ROLE_L2_TRANSCRIPT,
    ROLE_SHORT_VIDEO,
    TEXT,
    ContentBlock,
    ContentStream,
    asset_family,
    role_of,
)
from core.knowledge import OKF, Knowledge, asset_format
from databasehub.adapters.graph import GraphAdapter
from databasehub.adapters.vector import VectorAdapter
from databasehub.models import VectorCollection
from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.indices.vector_store.retrievers import VectorIndexRetriever
from llama_index.core.schema import (
    BaseNode,
    Document,
    ImageNode,
    NodeWithScore,
    TextNode,
)
from llama_index.core.vector_stores.types import MetadataFilters


# Near-constant file/ingest metadata dilutes embeddings; excluded from embed text only.
EMBED_EXCLUDED_METADATA_KEYS = (
    *LAYOUT_METADATA_KEYS,
    "file_path",
    "file_type",
    "file_size",
    "creation_date",
    "last_modified_date",
    "last_accessed_date",
    "library",
    "source_id",
)


def _has_content(asset: Any) -> bool:
    # Checks the class descriptor: reading `asset.content` would fetch the stream.
    return hasattr(type(asset), "content") or "content" in getattr(
        asset, "__dict__", {}
    )


def accepts_block(block: ContentBlock, configuration: Mapping[str, Any]) -> bool:
    """Whether a projection configured with `block_kinds`/`block_roles` should materialize this block."""
    kinds = configuration.get("block_kinds")
    if kinds:
        wanted = {str(entry).lower() for entry in kinds}
        # A transcript also matches the `audio` kind.
        selectable = (
            {block.kind, AUDIO} if role_of(block) == ROLE_L2_TRANSCRIPT else {block.kind}
        )
        if not selectable & wanted:
            return False
    roles = configuration.get("block_roles")
    if roles and role_of(block) not in {str(entry) for entry in roles}:
        return False
    return True


def accepts_asset(asset: Any, configuration: Mapping[str, Any]) -> bool:
    """Whether a projection should hold this asset, decided without reading its content.

    An `asset_types` entry matches an extension, a MIME type, or the asset kind.
    """
    if not (hasattr(asset, "asset_id") and _has_content(asset)):
        return False
    wanted = configuration.get("asset_types")
    if not wanted:
        return True
    extension = str(getattr(asset, "extension", "") or "")
    media_type = str(getattr(asset, "media_type", "") or "").lower()
    return bool(
        {str(entry).strip().lower().lstrip(".") for entry in wanted}
        & {
            str(getattr(asset, "asset_kind", "") or asset_family(extension)),
            extension,
            media_type,
        }
    )


MILVUS_TEXT_MAX_BYTES = 65535


def _truncate_text(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= MILVUS_TEXT_MAX_BYTES:
        return text
    return encoded[:MILVUS_TEXT_MAX_BYTES].decode("utf-8", errors="ignore")


class VectorIndexer:
    """A vector projection: parse, embed, and store assets in one collection."""

    kind = "vector"

    def __init__(
        self,
        projection_id: str,
        name: str,
        source: Source,
        adapter: VectorAdapter,
        configuration: Optional[Mapping[str, Any]] = None,
    ):
        import config
        from core.embedding import build_embedding
        from core.node_parser import build_node_parser

        options = dict(configuration or {})
        # Runtime-injected blob reader; kept out of the persisted configuration.
        self._blob_reader = options.pop("blob_reader", None)
        self.projection_id = projection_id
        self.name = name
        self.source = source
        self.configuration = options
        self.version = 0
        # Chunk nodes, cached across queries and invalidated by `version`.
        self._load_cache: Optional[List[BaseNode]] = None
        self._load_cache_version = -1
        self._adapter = adapter
        embedding_model = options.get("embedding_model_instance") or build_embedding(
            backend=options.get("embedding_backend"),
            model_id=options.get("embedding_model"),
            device=options.get("embedding_device"),
            api_base=options.get("embedding_api_base"),
        )
        self._embedding_model = embedding_model
        self._node_parser = build_node_parser(
            chunk_size=options.get("chunk_size"),
            chunk_overlap=options.get("chunk_overlap"),
        )
        # How much of a figure's neighbouring text goes into its node, per side.
        self._context_chars = int(
            options.get("figure_context_chars") or config.FIGURE_CONTEXT_CHARS
        )
        try:
            self.dimension = len(embedding_model.get_text_embedding("test"))
        except Exception:
            self.dimension = int(options.get("fallback_dimension") or 0)
        if self.collection.dimension <= 0:
            self.source = replace(
                self.source,
                location=VectorCollection(self.collection.name, self.dimension),
            )
        self._validate_collection()
        self._adapter.reconcile(self.collection)
        self._index = VectorStoreIndex(
            nodes=[],
            embed_model=embedding_model,
            storage_context=self._adapter.storage_context(self.collection),
        )

    # --- projection contract --------------------------------------------------

    @property
    def collection(self) -> VectorCollection:
        return self.source.location

    def accepts(self, asset: Any) -> bool:
        if getattr(asset, "asset_kind", "document") == "okf":
            return False
        return accepts_asset(asset, self.configuration)

    def add(self, assets: Sequence[Any]) -> Dict[str, int]:
        """Materialize assets through the streaming embed pipeline."""
        from core.materialize import streaming_materialize

        self._validate_collection()
        return streaming_materialize(self, assets)

    # --- assets -> nodes ------------------------------------------------------

    def nodes_from(self, asset: Any) -> List[BaseNode]:
        """One asset's content blocks as nodes; a chunk never spans two blocks."""
        stream = asset.content
        blocks = stream.ordered()
        base = {**dict(stream.metadata), "asset_id": asset.asset_id}
        nodes: List[BaseNode] = []
        image_nodes: List[ImageNode] = []
        for position in range(len(blocks)):
            for node in self._block_nodes(stream, blocks, position, base):
                nodes.append(node)
                if isinstance(node, ImageNode) and node.metadata.get("media_key"):
                    image_nodes.append(node)
        # Image vectors are precomputed; text nodes are embedded by `insert_nodes`.
        from core.embedding import embed_media_nodes

        if image_nodes:
            embed_media_nodes(
                self._embedding_model,
                image_nodes,
                self._blob_reader,
                getattr(asset, "content_source_id", None),
            )
        return nodes

    def _block_nodes(
        self, stream: ContentStream, blocks: Sequence[ContentBlock], position: int,
        base: Mapping[str, Any],
    ) -> List[BaseNode]:
        """The nodes one block becomes, unembedded: text chunks, a media node, or none."""
        block = blocks[position]
        if not accepts_block(block, self.configuration):
            return []
        if role_of(block) in MM_DERIVED_ROLES:
            # Multimodal-derived blocks are embedded by a multimodal source only.
            return []
        if block.kind in BINARY_KINDS:
            node = self._media_node(stream, position, base)
            return [node] if node is not None else []
        if block.text.strip():
            return list(self._text_nodes(block, base))
        return []

    # --- streaming (producer / consumer) --------------------------------------

    def iter_node_items(self, asset: Any, only_block_ids: Optional[Collection[str]] = None):
        """Stream one asset's nodes as `(node, modality, source_id)`, unembedded.

        `only_block_ids` limits which blocks yield nodes; the full stream is still read for context.
        """
        stream = asset.content
        blocks = stream.ordered()
        base = {**dict(stream.metadata), "asset_id": asset.asset_id}
        source_id = getattr(asset, "content_source_id", None)
        wanted = None if only_block_ids is None else set(only_block_ids)
        for position in range(len(blocks)):
            if wanted is not None and blocks[position].block_id not in wanted:
                continue
            for node in self._block_nodes(stream, blocks, position, base):
                modality = (
                    "fused"
                    if isinstance(node, ImageNode) and node.metadata.get("media_key")
                    else "text"
                )
                yield node, modality, source_id

    def embed_items(self, items: Sequence[Any]) -> None:
        """Precompute each queued node's vector in place, batched by modality.

        Nodes that cannot be embedded here stay `embedding=None` and are embedded from text on insert.
        """
        from llama_index.core.schema import MetadataMode

        from core.embedding import embed_media_nodes

        text_nodes = [node for node, modality, _ in items if modality != "fused"]
        if text_nodes:
            texts = [
                node.get_content(metadata_mode=MetadataMode.EMBED) for node in text_nodes
            ]
            vectors = self._embedding_model.get_text_embedding_batch(texts)
            for node, vector in zip(text_nodes, vectors):
                node.embedding = list(vector)
        fused_by_source: Dict[Any, List[BaseNode]] = {}
        for node, modality, source_id in items:
            if modality == "fused":
                fused_by_source.setdefault(source_id, []).append(node)
        for source_id, nodes in fused_by_source.items():
            embed_media_nodes(
                self._embedding_model, nodes, self._blob_reader, source_id
            )

    def insert_prepared(self, nodes: Sequence[BaseNode]) -> int:
        """Insert a batch of precomputed nodes without flushing; return the count."""
        nodes = list(nodes)
        if nodes:
            self._index.insert_nodes(nodes)
            self.version += 1
        return len(nodes)

    def flush(self) -> None:
        """Seal written batches; bumps `version` so no partial `load` cache survives."""
        self._adapter.flush(self.collection)
        self.version += 1

    def _text_nodes(self, block: ContentBlock, base: Mapping[str, Any]) -> List[BaseNode]:
        document = Document(
            id_=block.block_id,
            text=block.text,
            metadata={**base, **block.layout_metadata()},
        )
        nodes = self._node_parser.run([document])
        for node in nodes:
            node.excluded_embed_metadata_keys = list(EMBED_EXCLUDED_METADATA_KEYS)
            node.excluded_llm_metadata_keys = list(LAYOUT_METADATA_KEYS)
        return nodes

    def _media_node(
        self, stream: ContentStream, position: int, base: Mapping[str, Any]
    ) -> Optional[BaseNode]:
        """A figure or media file as one node, searchable by its caption.

        Surrounding text is used only when there is no caption; a node with neither
        is kept only if the model can embed pixels.
        """
        block = stream.ordered()[position]
        context = "" if block.caption else stream.surrounding_text(position, self._context_chars)
        if not (block.caption or context):
            from core.embedding import FusedEmbedding

            if not (block.media_key and isinstance(self._embedding_model, FusedEmbedding)):
                return None
        metadata = {**base, **block.layout_metadata()}
        if context:
            metadata["surrounding_text"] = context
        node_type = ImageNode if block.kind == IMAGE else TextNode
        node = node_type(
            id_=block.block_id,
            text=block.caption,
            metadata=metadata,
        )
        node.excluded_embed_metadata_keys = list(EMBED_EXCLUDED_METADATA_KEYS)
        node.excluded_llm_metadata_keys = list(LAYOUT_METADATA_KEYS)
        return node

    def remove(self, asset_ids: Collection[str]) -> int:
        return self.delete_by_metadata("asset_id", list(asset_ids))

    def materialize(
        self, request: VectorIngestRequest, documents_added: Optional[int] = None
    ) -> Dict[str, int]:
        """Write nodes into the collection; `documents_added` overrides the document count."""
        self._validate_collection()
        nodes = list(request.nodes)
        if request.documents:
            nodes.extend(self._node_parser.run(request.documents))
        if nodes:
            exposure.stamp_nodes(nodes, self.source)
            self._index.insert_nodes(nodes)
            self._adapter.flush(self.collection)
            self.version += 1
        return {
            "documents_added": (
                len(request.documents) if documents_added is None else documents_added
            ),
            "chunks_added": len(nodes),
        }

    def retrieve(self, query: VectorRetrieveRequest) -> List[NodeWithScore]:
        self._validate_collection()
        return self._retriever(query.top_k, query.filters).retrieve(query.query)

    # --- chunk-projection contract --------------------------------------------

    def indexed_asset_ids(self, asset_ids: Sequence[str]) -> Set[str]:
        return self._adapter.present_metadata_values(
            self.collection, "asset_id", list(asset_ids)
        )

    def count(self) -> int:
        return self._adapter.count_records(self.collection)

    def load(self) -> List[BaseNode]:
        # Cached until `version` changes; callers must treat the list as read-only.
        if self._load_cache is None or self._load_cache_version != self.version:
            self._load_cache = self._adapter.load_nodes(self.collection)
            self._load_cache_version = self.version
        return self._load_cache

    def delete_by_metadata(self, field: str, values: Sequence[str]) -> int:
        deleted = self._adapter.delete_by_metadata(
            self.collection, field, list(values)
        )
        if deleted:
            self.version += 1
        return deleted

    def remove_concepts(self, concept_ids: Sequence[str]) -> int:
        """Drop OKF concept vectors from the sibling ``_concept`` collection."""
        if not concept_ids:
            return 0
        collection = VectorCollection(f"{self.collection.name}_concept", self.dimension)
        return int(self._adapter.delete_by_metadata(collection, "cid", list(concept_ids)) or 0)

    def build_concept_index(self, okf_nodes):
        """A vector index over OKF concepts in the sibling ``_concept`` collection, or None."""
        if not okf_nodes:
            return None
        collection = VectorCollection(
            f"{self.collection.name}_concept", self.dimension
        )
        self._adapter.reconcile(collection)
        docs = []
        for node in okf_nodes:
            text = _truncate_text(f"{node.title}\n{node.body}".strip())
            doc = TextNode(text=text, id_=node.cid, metadata={"cid": node.cid})
            doc.excluded_embed_metadata_keys = ["cid"]
            doc.excluded_llm_metadata_keys = ["cid"]
            docs.append(doc)
        index = VectorStoreIndex(
            nodes=docs,
            embed_model=self._embedding_model,
            storage_context=self._adapter.storage_context(collection),
        )
        self._adapter.flush(collection)
        return index

    def load_concept_index(self, concept_ids: Set[str]):
        """Reuse existing concept vectors; requires every one of `concept_ids` to be present."""
        collection = VectorCollection(f"{self.collection.name}_concept", self.dimension)
        store = self._adapter.existing_concept_store(
            collection, concept_ids, exact=False
        )
        if store is None:
            raise ValueError(
                f"Milvus concept collection {collection.name!r} is missing concepts "
                "or has inconsistent dimensions/concept IDs; re-ingest the OKF assets "
                "into the asset pool before retrieving"
            )
        return VectorStoreIndex.from_vector_store(
            store, embed_model=self._embedding_model
        )

    # --- internals ------------------------------------------------------------

    def _retriever(self, top_k: int, filters: Optional[MetadataFilters] = None):
        # as_retriever would filter by the index's partial local node cache.
        return VectorIndexRetriever(
            index=self._index, similarity_top_k=top_k, filters=filters
        )

    def _validate_collection(self) -> None:
        if self.collection.dimension != self.dimension:
            raise ValueError(
                f"Collection dimension {self.collection.dimension} does not match "
                f"embedding dimension {self.dimension}"
            )


class MultimodalIndexer(VectorIndexer):
    """A vector projection that embeds media bytes with a multimodal model."""

    kind = "vector"

    def __init__(
        self,
        projection_id: str,
        name: str,
        source: Source,
        adapter: VectorAdapter,
        configuration: Optional[Mapping[str, Any]] = None,
    ):
        from core.multimodal import build_multimodal_embedding
        from core.multimodal.routing import effective_configuration, require_asset_types

        require_asset_types(source.configuration)
        options = {**dict(configuration or {}), **effective_configuration(source)}
        self._embedding = options.get("multimodal_embedding_instance")
        if self._embedding is None:
            record = (source.profile or {}).get("multimodal_model")
            if not record:
                raise ValueError(
                    f"Source {source.name or source.source_id!r} records no "
                    "multimodal model; re-create it"
                )
            self._embedding = build_multimodal_embedding(record, options)
        # Use the declared width to skip the base class's costly probe embedding.
        options.setdefault("fallback_dimension", self._embedding.dimension)
        options.setdefault("embedding_model_instance", _DeclaredWidth(self._embedding))
        super().__init__(projection_id, name, source, adapter, options)

    def covers(self, block: ContentBlock) -> bool:
        """Whether this source's model supports the block's role and the block passes filters."""
        role = role_of(block)
        return (
            bool(role)
            and role in self._embedding.supported_roles
            and accepts_block(block, self.configuration)
        )

    def nodes_from(self, asset: Any) -> List[BaseNode]:
        """The blocks this source's model covers: media, and derived text."""
        stream = asset.content
        base = {**dict(stream.metadata), "asset_id": asset.asset_id}
        nodes: List[BaseNode] = []
        texts: List[BaseNode] = []
        for position, block in enumerate(stream.ordered()):
            if not self.covers(block):
                continue
            if block.kind == TEXT:
                if block.text.strip():
                    texts.extend(self._text_nodes(block, base))
                continue
            node = self._media_node(stream, position, base)
            if node is not None:
                nodes.append(node)
        if texts:
            vectors = self._embedding.get_text_embedding_batch(
                [text.get_content() for text in texts]
            )
            for text, vector in zip(texts, vectors):
                text.embedding = vector
            nodes.extend(texts)
        return nodes

    def iter_node_items(self, asset: Any, only_block_ids: Optional[Collection[str]] = None):
        """Stream only covered blocks, with media vectors already attached."""
        stream = asset.content
        base = {**dict(stream.metadata), "asset_id": asset.asset_id}
        source_id = getattr(asset, "content_source_id", None)
        wanted = None if only_block_ids is None else set(only_block_ids)
        for position, block in enumerate(stream.ordered()):
            if wanted is not None and block.block_id not in wanted:
                continue
            if not self.covers(block):
                continue
            if block.kind == TEXT:
                if block.text.strip():
                    for node in self._text_nodes(block, base):
                        yield node, "document", source_id
                continue
            node = self._media_node(stream, position, base)
            if node is not None:
                yield node, "media", source_id

    def embed_items(self, items: Sequence[Any]) -> None:
        """Embed derived text as corpus content; leave media vectors untouched."""
        nodes = [node for node, modality, _ in items if modality == "document"]
        if nodes:
            vectors = self._embedding.get_text_embedding_batch(
                [node.get_content() for node in nodes]
            )
            for node, vector in zip(nodes, vectors):
                node.embedding = list(vector)

    def _media_node(
        self, stream: ContentStream, position: int, base: Mapping[str, Any]
    ) -> Optional[BaseNode]:
        """One media block as a node carrying its own precomputed vector."""
        block = stream.ordered()[position]
        vector = self._vector_for(stream, block)
        if vector is None:
            return None
        metadata = {**base, **block.layout_metadata()}
        node_type = ImageNode if block.kind == IMAGE else TextNode
        # The caption is display text only; it did not produce the vector.
        node = node_type(id_=block.block_id, text=block.caption, metadata=metadata)
        node.embedding = vector
        node.excluded_embed_metadata_keys = list(LAYOUT_METADATA_KEYS)
        node.excluded_llm_metadata_keys = list(LAYOUT_METADATA_KEYS)
        return node

    def _vector_for(
        self, stream: ContentStream, block: ContentBlock
    ) -> Optional[List[float]]:
        from core.multimodal import frames as frame_utils

        role = role_of(block)
        asset = self._asset_of(stream)
        if role in (ROLE_IMAGE, ROLE_DOC_IMAGE):
            from io import BytesIO  # noqa: PLC0415

            from PIL import Image  # noqa: PLC0415

            image = Image.open(BytesIO(asset.read_blob(block.media_key))).convert("RGB")
            return self._embedding.get_image_embeddings([image])[0]
        if role in (ROLE_SHORT_VIDEO, ROLE_L1_SEGMENT):
            import os  # noqa: PLC0415

            suffix = os.path.splitext(stream.metadata.get("file_name") or "")[1] or ".mp4"
            with asset.media_path(block.media_key, suffix) as path:
                sampled = frame_utils.sample_frames(
                    path, getattr(self._embedding, "frames_per_clip", 8)
                )
            return self._embedding.get_video_embedding(sampled)
        return None

    def _asset_of(self, stream: ContentStream) -> Any:
        asset = self._assets_by_stream.get(id(stream))
        if asset is None:
            raise ValueError(
                f"No asset bound for content stream {stream.asset_id!r}"
            )
        return asset

    def add(self, assets: Sequence[Any]) -> Dict[str, int]:
        # `_vector_for` needs the asset behind each stream to read blobs.
        self._assets_by_stream = {id(asset.content): asset for asset in assets}
        try:
            return super().add(assets)
        finally:
            self._assets_by_stream = {}

    _assets_by_stream: Dict[int, Any] = {}


class _DeclaredWidth(BaseEmbedding):
    """A `BaseEmbedding` placeholder that only embeds queries; document vectors are precomputed."""

    _embedding: Any = PrivateAttr()

    def __init__(self, embedding):
        super().__init__()
        self._embedding = embedding

    @classmethod
    def class_name(cls) -> str:
        return "declared-width-multimodal"

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._embedding.get_query_embedding(query)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        # The base constructor's width probe catches this and uses the declared width.
        raise NotImplementedError("Multimodal document vectors must be precomputed")


class GraphIndexer:
    """A graph projection: OKF bundles' concepts as vertices and links as edges."""

    kind = "graph"

    def __init__(
        self,
        projection_id: str,
        name: str,
        source: Source,
        adapter: GraphAdapter,
        configuration: Optional[Mapping[str, Any]] = None,
    ):
        self.projection_id = projection_id
        self.name = name
        self.source = source
        self.configuration = dict(configuration or {})
        self._adapter = adapter
        self._knowledge = Knowledge(self.configuration)
        # Ingest-only: parsed OKF concepts for the current add, keyed by asset id.
        self._okf_context = None
        self.version = 0

    @property
    def collection(self):
        return self.source.location

    def accepts(self, asset: Any) -> bool:
        return self._knowledge.accepts(asset) and accepts_asset(asset, {})

    @property
    def extracts_documents(self) -> bool:
        return self._knowledge.extractor is not None

    @property
    def extraction_trigger(self):
        """When this source extracts documents (`ExtractionTrigger`), or None."""
        extractor = self._knowledge.extractor
        return extractor.config.trigger if extractor is not None else None

    @property
    def okf_context(self):
        """Parsed OKF concepts for the current add, keyed by asset id, or None."""
        return self._okf_context

    def set_okf_context(self, context) -> None:
        """Set pre-parsed OKF concepts for this add as ``{asset_id: [OKFNode, ...]}``."""
        self._okf_context = context

    def extract_documents(self, assets: Sequence[Any], output_dir: Path) -> List[Path]:
        """Extract documents into an OKF bundle under `output_dir`."""
        return self._knowledge.extract(assets, output_dir)

    def add(self, assets: Sequence[Any]) -> Dict[str, int]:
        unsupported = [asset for asset in assets if not self.accepts(asset)]
        if unsupported:
            raise ValueError(f"Projection {self.projection_id!r} cannot accept assets")
        # Documents are not written directly; only extracted OKF bundles are built.
        bundles = [asset for asset in assets if asset_format(asset) == OKF]
        graph = self._knowledge.build(bundles, self._okf_context)
        return self.materialize(GraphIngestRequest(**graph.as_request()))

    def remove(self, asset_ids: Collection[str]) -> Any:
        # Vertices are keyed by concept id; the library calls `delete_vertices` instead.
        raise ValueError(f"Projection {self.projection_id!r} cannot remove assets by id")

    def delete_vertices(self, vertex_ids: Collection[str]) -> int:
        """Delete vertices (and their edges) this projection wrote."""
        deleted = int(self._adapter.delete_vertices(self.collection, list(vertex_ids)) or 0)
        if deleted:
            self.version += 1
        return deleted

    def drop_chunk_provenance(self, chunk_ids: Collection[str]) -> int:
        """Remove deleted chunk ids from concepts' ``source_chunk_ids``; return how many changed."""
        dropped = set(chunk_ids)
        open_store = getattr(self._adapter, "existing_store", None)
        if not dropped or open_store is None:
            return 0
        from core.graph_search import NebulaConceptGraphBackend

        try:
            store = open_store(self.collection.space)
        except ValueError:
            return 0  # no graph space yet: nothing cites anything
        backend = NebulaConceptGraphBackend(store)
        concept_ids = sorted(backend.concept_ids())
        sources = backend.source_chunk_ids(concept_ids) if concept_ids else {}
        affected = [cid for cid, chunks in sources.items() if dropped.intersection(chunks)]
        vertices = []
        for start in range(0, len(affected), 200):
            for node in store.get(ids=affected[start:start + 200]):
                properties = dict(node.properties or {})
                content = json.loads(properties.get("_node_content") or "{}")
                kept = [cid for cid in sources[node.id] if cid not in dropped]
                content["source_chunk_ids"] = json.dumps(kept, ensure_ascii=False)
                content["n_sources"] = len(kept)
                properties["_node_content"] = json.dumps(content, ensure_ascii=False)
                vertices.append({"id": node.id, "label": node.label, "properties": properties})
        if vertices:
            self._adapter.upsert_vertices(self.collection, vertices)
            self.version += 1
        return len(vertices)

    def materialize(self, request: GraphIngestRequest) -> Dict[str, int]:
        """Write a built graph: vertices first so every edge's endpoints exist."""
        if request.vertices:
            self._adapter.upsert_vertices(self.collection, request.vertices)
        if request.edges:
            self._adapter.upsert_edges(self.collection, request.edges)
        if request.vertices or request.edges:
            self.version += 1
        return {
            "vertices_added": len(request.vertices),
            "edges_added": len(request.edges),
        }

    def retrieve(self, query: GraphRetrieveRequest):
        return self._adapter.query(self.collection, query.statement, query.parameters)


__all__ = ["GraphIndexer", "MultimodalIndexer", "VectorIndexer", "accepts_block"]
