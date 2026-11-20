# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import threading
from collections import defaultdict
from itertools import zip_longest
from typing import Any, Dict, List, Optional, Set

import config
from llama_index.core.llms.mock import MockLLM
from assetlib.models import VectorRetrieveRequest
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.schema import BaseNode, NodeWithScore, QueryBundle, MetadataMode
from llama_index.core.vector_stores.types import FilterOperator, MetadataFilter, MetadataFilters
from llama_index.core.vector_stores.utils import metadata_dict_to_node, node_to_metadata_dict

from core import materialize
from core.indexer import MultimodalIndexer

RETRIEVER_TYPES = ("rrf", "vectorsimilarity", "bm25", "graph", "auto_merge")


def _bm25_tokenize(text: str) -> List[str]:
    if config.BM25_TOKENIZER == "whitespace":
        import re

        return re.findall(r"\w+", text, flags=re.UNICODE)
    if config.BM25_TOKENIZER == "jieba":
        import jieba

        return [token for token in jieba.lcut(text) if token.strip()]
    raise ValueError(
        f"unknown BM25 tokenizer {config.BM25_TOKENIZER!r}; "
        "set config.BM25_TOKENIZER to 'jieba' or 'whitespace'"
    )


class SimpleBM25Retriever(BaseRetriever):
    """A bm25s index over tokenized chunk text (MetadataMode.NONE)."""

    def __init__(self, nodes: List[BaseNode], top_k: int):
        super().__init__()
        self._top_k = min(top_k, len(nodes)) or 1
        import bm25s

        corpus_tokens = [
            _bm25_tokenize(node.get_content(metadata_mode=MetadataMode.NONE))
            for node in nodes
        ]
        bm25 = bm25s.BM25()
        bm25.index(corpus_tokens, show_progress=False)
        self._bm25 = bm25
        self.corpus = [node_to_metadata_dict(node) | {"node_id": node.node_id} for node in nodes]

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        indexes, scores = self._bm25.retrieve(
            [_bm25_tokenize(query_bundle.query_str)], k=self._top_k, show_progress=False
        )
        return [
            NodeWithScore(node=metadata_dict_to_node(self.corpus[int(idx)]), score=float(score))
            for idx, score in zip(indexes[0], scores[0])
        ]


def hydrate_nodes(projection) -> List[BaseNode]:
    """Load stored chunks through the database adapter for BM25 indexing."""
    return projection.load()


# Keyed by (projection, version, top_k, filter_key); rebuilt only when the collection version changes.
_bm25_cache: Dict[tuple, Any] = {}

# Graph snapshots keyed by graph/vector projection versions and pool.
_graph_cache: Dict[tuple, Any] = {}


def _bm25_retriever(projection, top_k: int, node_filter=None, filter_key=None):
    """A BM25 retriever over the projection's chunks, cached by collection version."""
    key = (projection.projection_id, projection.version, top_k, filter_key)
    cached = _bm25_cache.get(key)
    if cached is not None:
        return cached
    nodes = hydrate_nodes(projection)
    if node_filter is not None:
        nodes = [node for node in nodes if node_filter(node)]
    if not nodes:
        return None
    cached = SimpleBM25Retriever(nodes, top_k)
    _bm25_cache[key] = cached
    return cached


class ProjectionVectorRetriever(BaseRetriever):
    """Adapt a vector projection to llama-index's retriever contract."""

    def __init__(self, projection, top_k: int, filters=None, node_filter=None):
        super().__init__()
        self._projection = projection
        self._top_k = top_k
        self._filters = filters
        self._node_filter = node_filter

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        nodes = self._projection.retrieve(
            VectorRetrieveRequest(query=query_bundle.query_str, top_k=self._top_k, filters=self._filters)
        )
        return [hit for hit in nodes if self._node_filter(hit.node)] if self._node_filter else nodes


class ScopedRetriever(BaseRetriever):
    """Apply the same node scope to graph and other non-vector retrieval arms."""

    def __init__(self, retriever, node_filter):
        super().__init__()
        self._retriever = retriever
        self._node_filter = node_filter

    def _retrieve(self, query_bundle):
        return [hit for hit in self._retriever.retrieve(query_bundle) if self._node_filter(hit.node)]


class _RRFArm(BaseRetriever):
    """Identify the failed RRF algorithm without swallowing its error."""

    def __init__(self, name, retriever):
        super().__init__()
        self._name = name
        self._retriever = retriever

    def _retrieve(self, query_bundle):
        try:
            return self._retriever.retrieve(query_bundle)
        except Exception as error:
            raise RuntimeError(f"RRF {self._name} failed: {error}") from error


class RRFRetriever(QueryFusionRetriever):
    """Reciprocal-rank fusion over the arms' own rankings."""

    def __init__(self, *args, rrf_k: float = 60, **kwargs):
        super().__init__(*args, **kwargs)
        self.rrf_k = rrf_k

    def _reciprocal_rerank_fusion(self, results) -> List[NodeWithScore]:
        scores = defaultdict(float)
        nodes_by_id = {}
        for ranked_nodes in results.values():
            # Preserve the arm's own ranking, including ties and zero scores.
            for rank, node_with_score in enumerate(ranked_nodes):
                node_id = node_with_score.node.node_id
                scores[node_id] += 1.0 / (self.rrf_k + rank + 1)
                nodes_by_id.setdefault(node_id, node_with_score.node)
        # Stable sorting preserves first-seen order for equal fused scores.
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [
            NodeWithScore(node=nodes_by_id[node_id], score=score)
            for node_id, score in ranked
        ]


def build_retriever(projection, retriever_type: str, top_k: int, filters=None, node_filter=None, filter_key=None):
    """A single-algorithm retriever over one vector projection; None for an empty BM25 collection."""
    if retriever_type in ("rrf", "graph"):
        raise ValueError(
            f"Retriever type '{retriever_type}' requires pool context; "
            "use build_pool_retriever"
        )
    if retriever_type == "vectorsimilarity":
        return ProjectionVectorRetriever(projection, top_k, filters, node_filter)
    if retriever_type == "bm25":
        if node_filter is not None:
            return _bm25_retriever(projection, top_k, node_filter, filter_key)
        return _bm25_retriever(projection, top_k)
    if retriever_type == "auto_merge":
        raise ValueError(
            "auto_merge is unavailable for externally backed projections; "
            "use vectorsimilarity, bm25, or pool-level rrf"
        )
    raise ValueError(
        f"Retriever type '{retriever_type}' is not supported over one vector projection; "
        "supported: vectorsimilarity, bm25"
    )


class GraphSearchArmRetriever(BaseRetriever):
    """Adapt a graph-search retriever to llama-index's retriever contract."""

    def __init__(self, graph_search):
        super().__init__()
        self._graph_search = graph_search

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self._graph_search.retrieve(query_bundle.query_str)


def pool_asset_scope(asset_pool) -> Optional[frozenset]:
    asset_ids = getattr(asset_pool, "asset_ids", None)
    if asset_ids is None:
        return None
    ingesting = materialize.ingesting_asset_ids(getattr(asset_pool, "asset_pool_id", None))
    return frozenset(asset_ids) | ingesting


def _scoped_vector_filters(filters, scope):
    if scope is None:
        return filters
    in_pool = MetadataFilter(key="asset_id", value=sorted(scope), operator=FilterOperator.IN)
    if filters is None:
        return MetadataFilters(filters=[in_pool])
    return MetadataFilters(filters=[filters, in_pool])


def _scoped_node_filter(node_filter, scope):
    if scope is None:
        return node_filter
    if node_filter is None:
        return lambda node: (node.metadata or {}).get("asset_id") in scope
    return lambda node: (node.metadata or {}).get("asset_id") in scope and node_filter(node)


def _serving_projections(asset_pool):
    """Snapshot serving projections; disabled sources never answer a query."""
    return tuple(
        projection
        for projection in asset_pool.serving
        if getattr(projection.source, "enabled", True)
    )


def _projection_of_kind(asset_pool, kind: str):
    return next(
        (
            projection for projection in _serving_projections(asset_pool)
            if projection.kind == kind
            and not (kind == "vector" and isinstance(projection, MultimodalIndexer))
        ),
        None,
    )


def _build_graph_arm(asset_library, asset_pool, graph, vector, top_k):
    """A graph arm over persisted Nebula/Milvus data, validated against the vector chunks."""
    from core.graph_search import (
        GraphSearchRetriever,
        InMemoryConceptGraphBackend,
        NebulaConceptGraphBackend,
    )

    for projection in (graph, vector):
        sync_status = asset_pool.source_statuses.get(projection.source.source_id)
        if sync_status is not None and sync_status.status != "ready":
            raise RuntimeError(
                f"Graph retrieval source {projection.source.source_id!r} is "
                f"{sync_status.status}: {sync_status.error or 'finish asset pool sync first'}"
            )
    pool_id = getattr(asset_pool, "asset_pool_id", None)
    cache_key = (graph.projection_id, graph.version, vector.projection_id, vector.version, pool_id)
    backend, concept_indexer = _graph_cache.get(cache_key, (None, None))
    if backend is None:
        # A graph space may be shared by several pools; restrict to this pool's concepts.
        scope_of = getattr(asset_library, "pool_concept_scope", None)
        scope = scope_of(pool_id) if scope_of is not None and pool_id is not None else None
        open_store = getattr(graph._adapter, "existing_store", None)
        if open_store is None:
            raise ValueError("Graph retrieval requires an existing Nebula graph store")
        persisted_backend = NebulaConceptGraphBackend(open_store(graph.collection.space))
        concept_ids = set(persisted_backend.concept_ids())
        if scope is not None:
            concept_ids &= scope
        if not concept_ids:
            raise ValueError("Nebula contains no OKF concepts for this pool; ingest the OKF assets first")
        chunk_ids = {node.node_id for node in vector.load()}
        # Never repair provenance during a query. Re-chunking requires OKF re-ingest.
        sources = persisted_backend.source_chunk_ids(sorted(concept_ids))
        missing = {cid for ids in sources.values() for cid in ids if cid not in chunk_ids}
        if missing:
            raise ValueError(
                f"Nebula references {len(missing)} missing document chunks; "
                "re-ingest the OKF assets into this pool after document re-chunking"
            )
        backend = InMemoryConceptGraphBackend.from_persisted(persisted_backend)
        if scope is not None:
            backend = backend.restricted_to(concept_ids)
        concept_indexer = vector.load_concept_index(backend.concept_ids())
        for key in list(_graph_cache):
            if (key[0], key[2], key[4]) == (cache_key[0], cache_key[2], cache_key[4]):
                _graph_cache.pop(key, None)
        _graph_cache[cache_key] = (backend, concept_indexer)
    chunk_nodes = vector.load()
    search = GraphSearchRetriever(
        chunk_nodes=chunk_nodes,
        concept_indexer=concept_indexer,
        concept_graph_backend=backend,
        similarity_top_k=top_k,
    )
    return GraphSearchArmRetriever(search)


class PoolVectorRetriever(BaseRetriever):
    """Interleave per-source results, each left in its own score scale."""

    def __init__(self, retrievers, top_k: int):
        super().__init__()
        self._retrievers = retrievers
        self._top_k = top_k

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self._merge([
            (source_id, retriever.retrieve(query_bundle))
            for source_id, retriever in self._retrievers
        ])

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self._merge([
            (source_id, await retriever.aretrieve(query_bundle))
            for source_id, retriever in self._retrievers
        ])

    def _handle_recursive_retrieval(self, query_bundle, nodes):
        # Arms already resolved recursion; a node-id-only pass would drop same-id hits from other sources.
        return nodes

    async def _ahandle_recursive_retrieval(self, query_bundle, nodes):
        return nodes

    def _merge(self, source_results) -> List[NodeWithScore]:
        groups = []
        for source_id, hits in source_results:
            group = []
            for scored in hits[:self._top_k]:
                node = scored.node.model_copy(deep=True)
                node.metadata = {**(node.metadata or {}), "source_id": source_id}
                group.append(NodeWithScore(node=node, score=scored.score))
            groups.append(group)
        return [hit for rank in zip_longest(*groups) for hit in rank if hit is not None]


def build_pool_retriever(
    asset_library, asset_pool, retriever_type: str, top_k: int,
    selected_vectors=None, vector_filters=None, node_filter=None, filter_key=None,
):
    """Query the selected serving vector sources; only the first text source gets graph/BM25/RRF arms."""
    if retriever_type not in RETRIEVER_TYPES:
        raise ValueError(f"Retriever type '{retriever_type}' is not supported")
    if retriever_type == "auto_merge":
        raise ValueError(
            "auto_merge is unavailable for externally backed projections; "
            "use vectorsimilarity, bm25, or pool-level rrf"
        )
    scope = pool_asset_scope(asset_pool)
    if scope is not None:
        if not scope:
            return None
        vector_filters = _scoped_vector_filters(vector_filters, scope)
        node_filter = _scoped_node_filter(node_filter, scope)
        filter_key = (filter_key, scope)
    projections = _serving_projections(asset_pool)
    vectors = [p for p in projections if p.kind == "vector"]
    if selected_vectors is not None:
        chosen = {id(projection) for projection in selected_vectors}
        vectors = [projection for projection in vectors if id(projection) in chosen]
    graph = next((p for p in projections if p.kind == "graph"), None)
    text_vectors = [
        p for p in vectors
        if not isinstance(p, MultimodalIndexer)
        and (getattr(p.source, "profile", None) or {}).get("encoder_kind") != "multimodal"
    ]
    graph_vector = text_vectors[0] if text_vectors else None
    # TODO: explicit graph/vector binding and provenance migration when replacing the first text source.
    if retriever_type == "graph":
        if graph is None or not text_vectors:
            raise ValueError("Graph retrieval requires both graph and vector sources")
    if retriever_type == "rrf" and graph is not None and not text_vectors:
        raise RuntimeError("RRF graph initialization failed: text vector source is required")
    retrievers = []
    for vector in vectors:
        if isinstance(vector, MultimodalIndexer) or vector is not graph_vector:
            retriever = ProjectionVectorRetriever(vector, top_k, vector_filters, node_filter)
        elif retriever_type == "rrf" and graph is not None:
            retriever = _fused_pool_retriever(
                asset_library, asset_pool, top_k, vector, graph,
                vector_filters=vector_filters, node_filter=node_filter, filter_key=filter_key,
            )
        elif retriever_type == "graph":
            retriever = _build_graph_arm(asset_library, asset_pool, graph, vector, top_k)
            if node_filter is not None:
                retriever = ScopedRetriever(retriever, node_filter)
        else:
            algorithm = "vectorsimilarity" if retriever_type == "rrf" else retriever_type
            if node_filter is not None:
                retriever = build_retriever(
                    vector, algorithm, top_k, vector_filters, node_filter, filter_key,
                )
            else:
                retriever = build_retriever(vector, algorithm, top_k)
        if retriever is not None:
            retrievers.append((vector.source.source_id, retriever))
    if not retrievers:
        return None
    return PoolVectorRetriever(retrievers, top_k)


def _fused_pool_retriever(
    asset_library, asset_pool, top_k: int, vector, graph,
    vector_filters=None, node_filter=None, filter_key=None,
):
    """An RRF-fused retriever over vector, graph, and BM25 arms; arm order breaks score ties."""
    for projection in (vector, graph):
        source_id = projection.source.source_id
        sync_status = asset_pool.source_statuses.get(source_id)
        if sync_status is not None and sync_status.status == "failed":
            raise RuntimeError(f"RRF source {source_id} sync failed: {sync_status.error}")
    arms = (
        ("vectorsimilarity", lambda: ProjectionVectorRetriever(vector, top_k, vector_filters, node_filter)),
        ("graph", lambda: _build_graph_arm(asset_library, asset_pool, graph, vector, top_k)),
        # None for an empty collection: BM25 has nothing to index.
        ("bm25", lambda: _bm25_retriever(vector, top_k, node_filter, filter_key)
         if node_filter is not None else _bm25_retriever(vector, top_k)),
    )
    retrievers = []
    for name, factory in arms:
        try:
            arm = factory()
        except Exception as error:
            raise RuntimeError(f"RRF {name} initialization failed: {error}") from error
        if arm is not None:
            if name == "graph" and node_filter is not None:
                arm = ScopedRetriever(arm, node_filter)
            retrievers.append(_RRFArm(name, arm))
    return RRFRetriever(
        retrievers=retrievers,
        rrf_k=config.RRF_K,
        llm=MockLLM(),
        mode=FUSION_MODES.RECIPROCAL_RANK,
        similarity_top_k=top_k,
        num_queries=1,
        use_async=False,
    )


def graph_search_of(retriever):
    """The `GraphSearchRetriever` inside a pool retriever, or None."""
    if isinstance(retriever, GraphSearchArmRetriever):
        return retriever._graph_search
    if isinstance(retriever, ScopedRetriever):
        return graph_search_of(retriever._retriever)
    if isinstance(retriever, PoolVectorRetriever):
        for _, inner in retriever._retrievers:
            search = graph_search_of(inner)
            if search is not None:
                return search
    if isinstance(retriever, RRFRetriever):
        for arm in getattr(retriever, "_retrievers", ()):
            inner = getattr(arm, "_retriever", None)
            search = graph_search_of(inner)
            if search is not None:
                return search
    return None


_warm_requests: Dict[str, Optional[tuple]] = {}
_warm_lock = threading.Lock()


def warm_graph_arm(asset_library, asset_pool) -> None:
    pool_id = getattr(asset_pool, "asset_pool_id", None)
    if pool_id is None or _projection_of_kind(asset_pool, "graph") is None:
        return
    with _warm_lock:
        running = pool_id in _warm_requests
        _warm_requests[pool_id] = (asset_library, asset_pool)
    if running:
        return
    try:
        threading.Thread(target=_warm_graph_loop, args=(pool_id,), daemon=True).start()
    except Exception:  # noqa: BLE001
        with _warm_lock:
            _warm_requests.pop(pool_id, None)


def _warm_graph_loop(pool_id: str) -> None:
    while True:
        with _warm_lock:
            request = _warm_requests[pool_id]
            if request is None:
                del _warm_requests[pool_id]
                return
            _warm_requests[pool_id] = None
        try:
            build_pool_retriever(*request, "graph", config.RETRIEVE_TOP_K)
        except Exception:  # noqa: BLE001
            pass


# Display-only graph views, not validated against vector chunks; never use for retrieval.
_graph_view_cache: Dict[tuple, Dict[str, Any]] = {}


def pool_concept_graph(asset_pool, limit: int, concept_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    """The pool's concept graph as ``{nodes, edges, total, truncated}``, keeping the `limit` best-connected."""
    from core.graph_search import NebulaConceptGraphBackend

    graph = _projection_of_kind(asset_pool, "graph")
    if graph is None:
        raise ValueError("This asset pool has no graph source")
    scope = frozenset(concept_ids) if concept_ids is not None else None
    key = (graph.projection_id, graph.version, limit, scope)
    cached = _graph_view_cache.get(key)
    if cached is not None:
        return cached
    open_store = getattr(graph._adapter, "existing_store", None)
    if open_store is None:
        raise ValueError("This graph source cannot be read back")
    backend = NebulaConceptGraphBackend(open_store(graph.collection.space))
    concept_ids = sorted(cid for cid in backend.concept_ids() if scope is None or cid in scope)
    adjacency: Dict[str, List] = {}
    for start in range(0, len(concept_ids), 200):
        adjacency.update(backend.neighbors(concept_ids[start:start + 200]))
    kept = concept_ids
    if len(concept_ids) > limit:
        kept = sorted(concept_ids, key=lambda cid: (-len(adjacency.get(cid, [])), cid))[:limit]
    kept_set = set(kept)
    details = backend.concept_details(kept)
    edges, seen = [], set()
    for source in kept:
        for target, relation in adjacency.get(source, []):
            pair = (min(source, target), max(source, target), relation)
            if target in kept_set and pair not in seen:
                seen.add(pair)
                edges.append({"source": source, "target": target, "relation": relation})
    view = {
        "nodes": [
            {"id": cid, "label": details.get(cid, {}).get("label", ""),
             "title": details.get(cid, {}).get("title", cid), "degree": len(adjacency.get(cid, []))}
            for cid in kept
        ],
        "edges": edges,
        "total": len(concept_ids),
        "truncated": len(concept_ids) > len(kept),
    }
    _graph_view_cache[key] = view
    return view
