# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Vector and graph projections, each owning the machinery it is built from.

Both indexers *hold* their backing machinery rather than inheriting it: a
`VectorIndexer` owns a LlamaIndex `VectorStoreIndex` plus the `VectorAdapter`
for what an index cannot express, a `GraphIndexer` owns a `GraphAdapter` and
nothing else. Subclassing the LlamaIndex indices used to expose their whole
surface -- `insert`, `delete_ref_doc`, `refresh_ref_docs`, `as_query_engine` --
alongside the projection contract, and every one of those bypassed the
invariants this class exists to hold: the collection dimension check, the
`version` bump, and the metadata the parser stamps on each node. What a
projection promises is now exactly what it implements
(`assetlib/contracts.py:Projection`).

**Parsing happens here, from the asset's content blocks.** An asset is a file
and its durable form is a `ContentStream`; how that becomes nodes depends on the
embedding model and the chunk size, which are the projection's business and not
the file's. Two vector sources at different chunk sizes therefore share one
extraction and disagree only about chunking.
"""

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


# SimpleDirectoryReader stamps every chunk with filesystem metadata (path, type,
# size, ctime/mtime) and ingestion adds library/source ids. None of it describes
# what the chunk *says*, yet MetadataMode.EMBED prepends it to the embedded text.
# With a short-context embedder (e.g. bge-m3 at max_length=512) this header eats
# the token budget and, being near-constant across chunks (ingest date, size,
# library/source), pulls every mean-pooled vector toward a common direction --
# collapsing inter-chunk discrimination and tanking recall. Keep file_name (a weak
# topical signal, as the old EdgeCraftRAG baseline did) and drop the rest from the
# embedding only; they stay in metadata for citation, filtering and deletion.
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
    """Whether the asset exposes content, *without* asking it for any.

    `hasattr(asset, "content")` would read the property, and reading it fetches
    the stream out of the object store -- so the cheap filter would become the
    expensive thing it exists to avoid. Looking the descriptor up on the class
    answers the same question and touches nothing.
    """
    return hasattr(type(asset), "content") or "content" in getattr(
        asset, "__dict__", {}
    )


def accepts_block(block: ContentBlock, configuration: Mapping[str, Any]) -> bool:
    """Whether a projection configured this way should materialize this block.

    `accepts_asset` decides which *files* a source takes; this decides which
    *parts* of one it takes, and the two are not the same question. A pool now
    holds several vector sources over the same assets -- text in one, clips in
    another -- and without this they would each index everything, embedding a
    caption twice and handing a video to a model that cannot see.

    Whether a model can actually embed the block is the *projection's* question
    (`MultimodalIndexer.covers`), not this one's: it depends on which model the
    source was configured with, which only the projection knows.

    Two filters, both of which must pass when set:

    - `block_kinds` -- the block's kind (`text`, `image`, `video`, `audio`),
      which is what a user chooses content by. A transcript also matches
      `audio`, so `["audio"]` selects a recording's transcript, which is text;
    - `block_roles` -- a block's `role` (`l2_transcript`, `l2_caption`, ...),
      for a source that wants only some derived content. A block with no role
      never matches.

    How a block is processed -- a short clip or a long recording -- is not a
    filter: the model decides that (`MultimodalIndexer.covers`).
    """
    kinds = configuration.get("block_kinds")
    if kinds:
        wanted = {str(entry).lower() for entry in kinds}
        # A transcript is text, and to a user it is also the audio it was heard in.
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
    """Whether a projection configured this way should hold this asset.

    Two questions, and both are answered without reading the asset's content:
    is it an asset at all, and did the source ask for only some kinds of file?
    The second is what lets one pool mix documents and recordings -- a graph
    source configured `{"asset_types": ["pdf", "docx"]}` receives only those,
    while the vector source beside it takes everything.

    Deciding from `origin` alone is deliberate. `sync_asset_pool` asks this of
    every asset in the pool on every sync, so a filter that had to load each
    content stream would cost about as much as indexing them.

    An entry matches an extension (`"pdf"`), a full MIME type
    (`"application/pdf"`), or a MIME family (`"image"`).
    """
    if not (hasattr(asset, "asset_id") and _has_content(asset)):
        return False
    wanted = configuration.get("asset_types")
    if not wanted:
        return True
    media_type = str(getattr(asset, "media_type", "") or "").lower()
    return bool(
        {str(entry).strip().lower().lstrip(".") for entry in wanted}
        & {
            str(getattr(asset, "asset_kind", "document") or "document"),
            str(getattr(asset, "extension", "") or ""),
            media_type,
            media_type.split("/")[0],
        }
    )


MILVUS_TEXT_MAX_BYTES = 65535


def _truncate_text(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= MILVUS_TEXT_MAX_BYTES:
        return text
    return encoded[:MILVUS_TEXT_MAX_BYTES].decode("utf-8", errors="ignore")


class VectorIndexer:
    """A vector projection: parse, embed, and store assets in one collection.

    Owns the `VectorStoreIndex` that does the embedding and the searching, and
    the `VectorAdapter` for everything the index cannot express -- enumerating
    the collection, deleting by metadata, flushing what was written.
    """

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
        # Injected by the library, not part of a source's persisted configuration:
        # a reader for a figure's pixels by media_key. Popped so it never lands in
        # `self.configuration`, which is compared and reported as plain data.
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
            model_path=options.get("embedding_model_path"),
            device=options.get("embedding_device"),
            api_base=options.get("embedding_api_base"),
        )
        # Kept so image nodes can be embedded through the embedding layer
        # (`embed_media_nodes`), the same model that embeds text -- the indexer
        # builds nodes and delegates what their vectors are, it does not compute
        # them itself.
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
            # A source may be registered before its dimension is knowable; the
            # embedding model settles it here.
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
        # OKF concepts have no chunks to embed; the graph source holds them.
        if getattr(asset, "asset_kind", "document") == "okf":
            return False
        return accepts_asset(asset, self.configuration)

    def add(self, assets: Sequence[Any]) -> Dict[str, int]:
        """Materialize assets through the streaming embed pipeline.

        Rather than building every node for every asset up front and embedding
        the lot in one shot, a producer thread builds nodes block by block onto a
        bounded queue and this thread (the single, GME-serial consumer)
        micro-batches them -- embedding text and figures as they arrive and
        inserting each batch (`core/materialize.py:streaming_materialize`). A huge
        document therefore never holds all its nodes in memory at
        once, and its early text is embedded without waiting for the rest.
        """
        from core.materialize import streaming_materialize

        self._validate_collection()
        return streaming_materialize(self, assets)

    # --- assets -> nodes ------------------------------------------------------

    def nodes_from(self, asset: Any) -> List[BaseNode]:
        """One asset's content blocks as the nodes this collection will hold.

        Blocks are parsed individually rather than joined, which is the whole
        point of doing it here: every chunk keeps the page and bounding box of
        the block it came from, so a retrieved chunk can be cited. Joining them
        first -- which is what reading `asset.document` used to do -- destroyed
        that, and destroyed the figures with it.

        One consequence worth knowing: a chunk never spans two blocks, so a
        page shorter than the chunk size stays a short chunk instead of being
        merged with the next page.

        This is the batch builder -- the whole asset at once, image vectors
        precomputed, text left for `insert_nodes`. The streaming path
        (`iter_node_items` + the consumer's `embed_items`) shares the same
        per-block construction (`_block_nodes`) but defers every vector.
        """
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
        # Image nodes cannot go through the text batch path, so the embedding
        # layer precomputes their vectors now; text nodes are left for
        # `insert_nodes` to embed. Delegated, not done here: computing a vector is
        # the model's concern (`core/embedding.py:embed_media_nodes`).
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
        """The nodes one block becomes, unembedded: text chunks, a media node, or none.

        The single place that turns a block into nodes, shared by the batch path
        (`nodes_from`) and the streaming producer (`iter_node_items`) so the two
        cannot drift. A binary block becomes at most one media node; a text block
        becomes its chunks; an empty text block becomes nothing.
        """
        block = blocks[position]
        if not accepts_block(block, self.configuration):
            return []
        if role_of(block) in MM_DERIVED_ROLES:
            # Segments, captions, transcripts: derived by a multimodal
            # pipeline, and embedded by a multimodal source only.
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

        The streaming counterpart of `nodes_from`: it yields each node as it is
        built so the producer thread can hand it to the consumer without holding
        the whole asset's nodes in memory. `modality` tells the consumer how to
        embed it -- `"fused"` for an image node whose pixels it must read back,
        `"text"` otherwise; `source_id` is the content source those pixels live
        in (`embed_media_nodes` reads a blob through it).

        `only_block_ids` restricts which blocks produce nodes while still reading
        the whole stream for context: the two-phase materializer embeds path-1 text
        first, then comes back for only the path-2 blocks -- and a figure's
        `surrounding_text` still sees the full stream around it (`_media_node`).
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

        Text nodes embed as one batch through the same call `insert_nodes` would
        use, so a precomputed vector is identical to the one it would otherwise
        get. Image nodes read their pixels back and embed jointly, grouped by
        content source (`embed_media_nodes`). A node whose vector cannot be
        precomputed -- a text-only model, or unreadable pixels -- is left at
        `embedding=None` for `insert_prepared` to embed from its text, the same
        fallback `nodes_from` relies on.
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
        """Insert a batch whose vectors are already computed; count what was written.

        `insert_nodes` embeds only the nodes still without a vector (the fallback
        path), so a precomputed node is stored as-is. The adapter is not flushed
        per batch -- `flush` seals the whole write once at the end.
        """
        nodes = list(nodes)
        if nodes:
            self._index.insert_nodes(nodes)
            self.version += 1
        return len(nodes)

    def flush(self) -> None:
        """Seal what the batches wrote, so a read through the adapter sees it.

        Bumps `version` too: a `load` between the last batch and the seal would
        otherwise cache a partial chunk list under the final version and keep
        serving it (BM25, graph back-projection and OKF provenance all read it).
        """
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
            # Coordinates and ids describe where a chunk is, not what it says;
            # embedding them would pollute the vector with layout noise. They
            # stay in the metadata for citation and for deletion by asset.
            node.excluded_embed_metadata_keys = list(EMBED_EXCLUDED_METADATA_KEYS)
            node.excluded_llm_metadata_keys = list(LAYOUT_METADATA_KEYS)
        return nodes

    def _media_node(
        self, stream: ContentStream, position: int, base: Mapping[str, Any]
    ) -> Optional[BaseNode]:
        """A figure or a media file as one node, searchable by its caption.

        The embedded text is the caption when the figure has one -- exactly the
        reference text the POC pairs, with no surrounding prose appended. Only when
        there is no caption does `surrounding_text` stand in, so an untitled figure
        still carries some searchable text. `media_key` in the metadata says where
        the bytes are for display; with a multimodal model the bytes are read back
        and embedded jointly with that text.

        A figure with neither a caption nor any surrounding text is kept only when
        the model can embed its pixels: a text-only model has nothing to match on
        and an unembeddable node would fail the collection dimension check, so the
        node is dropped; a multimodal model (`FusedEmbedding`) embeds the bytes
        themselves, so an untitled figure stays reachable by image similarity.
        """
        block = stream.ordered()[position]
        # The caption is the preferred text (POC parity); surrounding prose only
        # fills in for a figure that has no caption at all.
        context = "" if block.caption else stream.surrounding_text(position, self._context_chars)
        if not (block.caption or context):
            # The joint vector would be image-only here. Only a model that can
            # actually embed pixels may keep it; a text-only model drops it.
            from core.embedding import FusedEmbedding

            if not (block.media_key and isinstance(self._embedding_model, FusedEmbedding)):
                return None
        metadata = {**base, **block.layout_metadata()}
        if context:
            metadata["surrounding_text"] = context
        # An ImageNode so a multimodal reader downstream can tell a figure from
        # a paragraph; anything else binary has no node type of its own.
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
        """Write nodes into the collection.

        `documents_added` is what `add` reports, since it parsed the blocks
        itself and knows how many assets they came from. A caller that hands in
        `documents` directly is counted by those instead.
        """
        self._validate_collection()
        nodes = list(request.nodes)
        if request.documents:
            nodes.extend(self._node_parser.run(request.documents))
        if nodes:
            exposure.stamp_nodes(nodes, self.source)
            self._index.insert_nodes(nodes)
            # The index wrote the rows; only the adapter can seal them, and
            # `load`/`delete_by_metadata` below read through the adapter.
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
        # Re-read from Milvus only when the collection changed. `version` bumps on
        # every write/delete, so the cached list is exactly as fresh as the last
        # materialization. Retrieval builds both BM25 and the graph arm's chunk
        # back-projection from this list on every query, so caching it here is what
        # keeps them from re-scanning the whole collection per query. Callers must
        # treat the returned list as read-only.
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
        """A vector index over OKF concepts, for the graph seeder.

        Concept text is title+body (the seeder's semantic text), keyed by ``cid``
        in metadata, in a sibling Milvus collection ``{chunk_collection}_concept``
        -- matching edgecraftrag's separate concept collection. Returns None when
        there is nothing to index.
        """
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
        """Reuse existing vectors without embedding/inserting concepts.

        The lightweight check assumes unchanged concept text and embedding
        configuration; it validates the collection dimension and that every one
        of `concept_ids` is there. Other concepts may be too: the collection
        belongs to this vector source, and a source attached to several pools
        holds all their concepts (graph search keeps to its own graph's seeds).
        """
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
        """Search the collection, not the index's partial local node cache.

        With a text-storing backend, LlamaIndex caches only image/index nodes;
        as_retriever would use those IDs as a filter and exclude stored text.
        """
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
    """A vector projection whose model can see.

    `VectorIndexer` embeds a picture by embedding the words near it, because
    its model only reads. That is the right fallback when there is no better
    one, and it is why a standalone recording currently indexes as its own file
    name. This subclass is the better one: the bytes go to a model that
    produces a vector in a space a text query also lands in, so a clip is found
    by what it shows rather than by what it was called.

    Everything else is inherited deliberately -- the adapter, the dimension
    check, the delete-then-write that makes a retry idempotent, the collection
    bookkeeping. Both batch and streaming builders use this model's coverage
    and media vectors; derived text is embedded on its document side, never
    through the query adapter the base index holds.
    """

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
            # Built from what the profile fixed at creation, not from the
            # engine defaults as they are now.
            self._embedding = build_multimodal_embedding(record, options)
        # The base class probes its text model for a width by embedding a word.
        # Here the width is declared by the model card, and probing would mean
        # a full inference -- seconds, for a constant -- every time a source is
        # built. Passed through so `_validate_collection` still runs.
        options.setdefault("fallback_dimension", self._embedding.dimension)
        options.setdefault("embedding_model_instance", _DeclaredWidth(self._embedding))
        super().__init__(projection_id, name, source, adapter, options)

    def covers(self, block: ContentBlock) -> bool:
        """Whether this source's model can embed this block, as of now.

        Derived from the model rather than read off the block, which records
        only what the file is. A long recording is therefore uncovered by every
        source today and becomes covered the moment one is configured with a
        model that declares the role -- with nothing in the stored content to
        rewrite.
        """
        role = role_of(block)
        return (
            bool(role)
            and role in self._embedding.supported_roles
            and accepts_block(block, self.configuration)
        )

    def nodes_from(self, asset: Any) -> List[BaseNode]:
        """The blocks this source's model covers: media, and derived text.

        A document's prose has no role and stays with a text source. Derived
        text -- a clip's description, a transcript -- goes here when the model
        embeds text into the same space as its media (GME), so a text query
        finds the picture and what was said about it in one collection.
        """
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
            vectors = self._embedding.embed_documents(
                [text.get_content() for text in texts]
            )
            for text, vector in zip(texts, vectors):
                text.embedding = vector
            nodes.extend(texts)
        return nodes

    def iter_node_items(self, asset: Any, only_block_ids: Optional[Collection[str]] = None):
        """Stream only covered blocks, with media vectors already attached.

        A media node's vector comes from `_vector_for`, just as in the batch
        builder, not from its display caption. Derived text is queued separately
        so `embed_items` uses the model's corpus-side batch interface. The base
        text/fused embedding path must never overwrite a media vector or send
        derived content through `_DeclaredWidth`'s query tower.
        """
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
            vectors = self._embedding.embed_documents(
                [node.get_content() for node in nodes]
            )
            for node, vector in zip(nodes, vectors):
                node.embedding = list(vector)

    def _media_node(
        self, stream: ContentStream, position: int, base: Mapping[str, Any]
    ) -> Optional[BaseNode]:
        """One media block as a node carrying its own vector.

        The vector is attached here rather than left to the index, which only
        embeds nodes whose `embedding` is still unset. That is what lets a
        model this index knows nothing about decide the vector, while the index
        keeps doing the writing, the deleting and the searching.
        """
        block = stream.ordered()[position]
        vector = self._vector_for(stream, block)
        if vector is None:
            return None
        metadata = {**base, **block.layout_metadata()}
        node_type = ImageNode if block.kind == IMAGE else TextNode
        # The caption is kept as the node's text so a result is readable and
        # citable; it is not what produced the vector.
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
            return self._embedding.embed_image([image])[0]
        if role in (ROLE_SHORT_VIDEO, ROLE_L1_SEGMENT):
            import os  # noqa: PLC0415

            suffix = os.path.splitext(stream.metadata.get("file_name") or "")[1] or ".mp4"
            with asset.media_path(block.media_key, suffix) as path:
                sampled = frame_utils.sample_frames(
                    path, getattr(self._embedding, "frames_per_clip", 32)
                )
            return self._embedding.embed_video(sampled)
        # A role with no pipeline. `covers` normally keeps these out; reaching
        # here means a block was written before the role existed.
        return None

    def _asset_of(self, stream: ContentStream) -> Any:
        asset = self._assets_by_stream.get(id(stream))
        if asset is None:
            raise ValueError(
                f"No asset bound for content stream {stream.asset_id!r}"
            )
        return asset

    def add(self, assets: Sequence[Any]) -> Dict[str, int]:
        # Both node builders hand `_vector_for` a stream, but reading a blob
        # needs its asset. Keep the pairing until the streaming producer joins,
        # then release it even if materialization failed.
        self._assets_by_stream = {id(asset.content): asset for asset in assets}
        try:
            return super().add(assets)
        finally:
            self._assets_by_stream = {}

    _assets_by_stream: Dict[int, Any] = {}


class _DeclaredWidth(BaseEmbedding):
    """Stands in for an embedding model that the index must never call.

    `VectorStoreIndex` requires one -- and requires it to be a real
    `BaseEmbedding`, `resolve_embed_model` asserts the type rather than duck
    typing it. Every node this projection produces arrives with its vector
    already set, so the index has nothing to embed -- except a *query*, which
    does go through the real model's text tower.
    """

    _embedding: Any = PrivateAttr()

    def __init__(self, embedding):
        super().__init__()
        self._embedding = embedding

    @classmethod
    def class_name(cls) -> str:
        return "declared-width-multimodal"

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._embedding.embed_text([query])[0]

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        # The base constructor catches this and uses the declared width. Any
        # later call means a corpus node reached the index without its vector;
        # failing is safer than silently encoding it as a query.
        raise NotImplementedError("Multimodal document vectors must be precomputed")


class GraphIndexer:
    """A graph projection: OKF bundles' concepts and links, stored as a graph.

    Which assets it takes is its `Knowledge`'s formats (`asset_types`: ``okf``
    by default, ``document`` via an external extractor). A bundle's concepts become vertices
    and its links edges (`core/knowledge:Knowledge.build`), each concept
    citing the document chunks it was drawn from -- chunks that live in the
    pool's vector source. Documents themselves are not written here.

    Everything goes through the `GraphAdapter`; there is no LlamaIndex graph
    index involved, so none is constructed. Note the absence of `load` and
    `delete_by_metadata`: a graph holds concepts, not chunks addressed by file,
    so this is not a `ChunkProjection`.
    """

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
        # Which formats this source builds from, and the extractor for
        # documents, come from its `operator_options` (core/knowledge).
        self._knowledge = Knowledge(self.configuration)
        # Ingest-only: the OKF concepts the library parsed and provenance-resolved
        # for this add, keyed by asset id. Query state is read from Nebula/Milvus,
        # not retained OKFNode objects.
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
        """When this source extracts documents (`ExtractionTrigger`), or None
        for a source that does not."""
        extractor = self._knowledge.extractor
        return extractor.config.trigger if extractor is not None else None

    @property
    def okf_context(self):
        """The OKF concepts the library parsed for this add, keyed by asset id,
        or None when the batch has no OKF assets. See ``set_okf_context``."""
        return self._okf_context

    def set_okf_context(self, context) -> None:
        """Provide the pre-parsed, provenance-resolved OKF concepts for this add
        as ``{asset_id: [OKFNode, ...]}`` (None when the batch has no OKF assets).

        The library parses each bundle once -- the graph write here and the
        concept vector index both read these, so a bundle is never parsed twice.
        """
        self._okf_context = context

    def extract_documents(self, assets: Sequence[Any], output_dir: Path) -> List[Path]:
        """Extract documents into an OKF bundle under `output_dir`; the library
        ingests it as an `okf` asset of the pool."""
        return self._knowledge.extract(assets, output_dir)

    def add(self, assets: Sequence[Any]) -> Dict[str, int]:
        unsupported = [asset for asset in assets if not self.accepts(asset)]
        if unsupported:
            raise ValueError(f"Projection {self.projection_id!r} cannot accept assets")
        # Documents add nothing here directly: syncing them only records that
        # the source's extraction is out of date. An extraction job turns them
        # into an OKF bundle asset (`extract_documents`), which a later sync
        # builds like any other. The
        # knowledge builds the batch's bundles (a concept two define is one
        # vertex) from the concepts the library already parsed and
        # provenance-resolved (`set_okf_context`); this indexer writes them.
        bundles = [asset for asset in assets if asset_format(asset) == OKF]
        graph = self._knowledge.build(bundles, self._okf_context)
        return self.materialize(GraphIngestRequest(**graph.as_request()))

    def remove(self, asset_ids: Collection[str]) -> Any:
        # A bundle's vertices are keyed by concept id, not asset id, and another
        # bundle may define the same concept; the library works out what goes
        # and calls `delete_vertices` (see FileAssetLibrary.delete_assets).
        raise ValueError(f"Projection {self.projection_id!r} cannot remove assets by id")

    def delete_vertices(self, vertex_ids: Collection[str]) -> int:
        """Delete vertices (and their edges) this projection wrote."""
        deleted = int(self._adapter.delete_vertices(self.collection, list(vertex_ids)) or 0)
        if deleted:
            self.version += 1
        return deleted

    def drop_chunk_provenance(self, chunk_ids: Collection[str]) -> int:
        """Take deleted document chunks out of every OKF concept's provenance.

        A concept names the chunks it was drawn from (``source_chunk_ids``), and
        graph retrieval refuses a graph that names chunks the vector source no
        longer has. So when a document goes, the concepts citing it are
        rewritten to cite what remains. Returns how many concepts changed.
        """
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
        """Write a built graph to this source's database: vertices first, so
        every edge's endpoints exist when it lands."""
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
