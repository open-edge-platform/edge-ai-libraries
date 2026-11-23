# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import math
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import config
from core.seeder import ConceptSeeder
from llama_index.core.graph_stores.types import EntityNode
from llama_index.core.schema import NodeWithScore

#: Max ids per Nebula get()/neighbors() request.
_NEBULA_FETCH_BATCH = config.NEBULA_FETCH_BATCH_SIZE


class ConceptGraphBackend(ABC):
    """Graph access primitives for concept-graph search; one implementation per graph db."""

    @abstractmethod
    def neighbors(self, node_ids: List[str]) -> Dict[str, List[Tuple[str, str]]]:
        # One-hop undirected neighbors: {node: [(neighbor_id, rel_label), ...]}.
        pass

    @abstractmethod
    def source_chunk_ids(self, concept_ids: List[str]) -> Dict[str, List[str]]:
        # Provenance chunk ids for each concept.
        pass

    @abstractmethod
    def chunk_density(self) -> Dict[str, int]:
        # How many concepts reference each chunk.
        pass


class NebulaConceptGraphBackend(ConceptGraphBackend):
    """Backed by llama-index's NebulaPropertyGraphStore."""

    def __init__(self, graph_store):
        self._store = graph_store
        self._density_cache: Optional[Dict[str, int]] = None

    def concept_ids(self) -> set[str]:
        """Read persisted OKF IDs, excluding document/structural graph vertices."""
        return {
            node.id
            for node in self._store.get(properties={"_node_type": "OKFConcept"})
            if isinstance(node, EntityNode)
            and node.properties.get("_node_type") == "OKFConcept"
        }

    def concept_details(self, concept_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """``{id: {"label", "title"}}`` for drawing concepts, read from Nebula."""
        unique_ids = list(dict.fromkeys(concept_ids))
        details = {}
        for start in range(0, len(unique_ids), _NEBULA_FETCH_BATCH):
            for node in self._store.get(ids=unique_ids[start:start + _NEBULA_FETCH_BATCH]):
                try:
                    content = json.loads((node.properties or {}).get("_node_content") or "{}")
                except ValueError:
                    content = {}
                details[node.id] = {
                    "label": getattr(node, "label", "") or "",
                    "title": str(content.get("title") or node.id),
                }
        return details

    def neighbors(self, node_ids: List[str]) -> Dict[str, List[Tuple[str, str]]]:
        unique_ids = list(dict.fromkeys(node_ids))
        if not unique_ids:
            return {}
        requested_ids = set(unique_ids)
        adjacency: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        # get_triplets matches either endpoint; fold both directions into undirected neighbors.
        for source, relation, target in self._store.get_triplets(ids=unique_ids):
            if any(
                node.properties.get("_node_type") != "OKFConcept"
                for node in (source, target)
            ):
                continue
            if source.name in requested_ids:
                adjacency[source.name].append((target.name, relation.label))
            if target.name in requested_ids:
                adjacency[target.name].append((source.name, relation.label))
        return dict(adjacency)

    def source_chunk_ids(self, concept_ids: List[str]) -> Dict[str, List[str]]:
        unique_ids = list(dict.fromkeys(concept_ids))
        if not unique_ids:
            return {}
        result = {}
        for start in range(0, len(unique_ids), _NEBULA_FETCH_BATCH):
            for node in self._store.get(ids=unique_ids[start:start + _NEBULA_FETCH_BATCH]):
                if node.properties.get("_node_type") == "OKFConcept":
                    result[node.id] = self._parse_source_chunks(node.properties)
        missing = set(unique_ids) - result.keys()
        if missing:
            raise ValueError(f"Nebula OKF concepts are missing: {sorted(missing)[:5]}")
        return result

    def chunk_density(self) -> Dict[str, int]:
        if self._density_cache is None:
            density: Dict[str, int] = defaultdict(int)
            for chunks in self.source_chunk_ids(sorted(self.concept_ids())).values():
                for chunk_id in set(chunks):
                    density[chunk_id] += 1
            self._density_cache = dict(density)
        return self._density_cache

    @staticmethod
    def _parse_source_chunks(properties: Optional[Dict[str, Any]]) -> List[str]:
        try:
            content = json.loads((properties or {}).get("_node_content") or "{}")
            raw_sources = content["source_chunk_ids"]
            sources = json.loads(raw_sources) if isinstance(raw_sources, str) else raw_sources
            if not isinstance(sources, list) or any(not isinstance(cid, str) or not cid for cid in sources):
                raise ValueError("source_chunk_ids must be a list of nonempty strings")
            return sources
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError(
                "Nebula OKF concept has invalid source_chunk_ids; re-ingest the OKF assets"
            ) from error


class InMemoryConceptGraphBackend(ConceptGraphBackend):
    """An immutable query cache built from a persisted concept graph."""

    def __init__(
        self,
        adjacency: Dict[str, List[Tuple[str, str]]],
        source_chunks: Dict[str, List[str]],
    ):
        self._adjacency = adjacency
        self._source_chunks = source_chunks
        density: Dict[str, int] = defaultdict(int)
        for chunk_ids in source_chunks.values():
            for chunk_id in set(chunk_ids):
                density[chunk_id] += 1
        self._density = dict(density)

    @classmethod
    def from_persisted(cls, backend: NebulaConceptGraphBackend):
        """Snapshot only data already materialized in Nebula."""
        concept_ids = sorted(backend.concept_ids())
        source_chunks = backend.source_chunk_ids(concept_ids)
        adjacency: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for start in range(0, len(concept_ids), _NEBULA_FETCH_BATCH):
            for concept_id, neighbors in backend.neighbors(
                concept_ids[start:start + _NEBULA_FETCH_BATCH]
            ).items():
                adjacency[concept_id].extend(neighbors)
        return cls(
            {
                concept_id: list(dict.fromkeys(neighbors))
                for concept_id, neighbors in adjacency.items()
            },
            source_chunks,
        )

    def restricted_to(self, concept_ids: Set[str]) -> "InMemoryConceptGraphBackend":
        """Subgraph of `concept_ids` and the edges between them."""
        return InMemoryConceptGraphBackend(
            {
                concept_id: [(target, relation) for target, relation in neighbors if target in concept_ids]
                for concept_id, neighbors in self._adjacency.items() if concept_id in concept_ids
            },
            {concept_id: chunks for concept_id, chunks in self._source_chunks.items() if concept_id in concept_ids},
        )

    def neighbors(self, node_ids: List[str]) -> Dict[str, List[Tuple[str, str]]]:
        return {
            node_id: list(self._adjacency.get(node_id, []))
            for node_id in dict.fromkeys(node_ids)
        }

    def source_chunk_ids(self, concept_ids: List[str]) -> Dict[str, List[str]]:
        return {
            concept_id: list(self._source_chunks.get(concept_id, []))
            for concept_id in dict.fromkeys(concept_ids)
        }

    def concept_ids(self) -> set[str]:
        return set(self._source_chunks)

    def chunk_density(self) -> Dict[str, int]:
        return self._density


class GraphSearchRetriever:
    """Embedding-seeded concept-graph search, returning chunks."""

    def __init__(
        self,
        chunk_nodes: List[Any],
        concept_indexer,
        concept_graph_backend: ConceptGraphBackend,
        **kwargs,
    ):
        options = {**config.GRAPH_SEARCH_DEFAULTS, **kwargs}
        self.topk = options["similarity_top_k"]
        self.seeder = ConceptSeeder(vector_indexer=concept_indexer)
        self.backend = concept_graph_backend
        self._known: Optional[Set[str]] = None

        self.seed_m = options["seed_m"]
        self.seed_windows = options["seed_windows"]
        self.seed_overlap = options["seed_overlap"]
        self.seed_min_win = options["seed_min_win"]
        self.hops = options["hops"]
        self.decay = options["decay"]
        self.coreach_coef = options["coreach_coef"]
        self.coreach_mode = options["coreach_mode"]
        self.inverse_freq = options["inverse_freq"]
        self.breadth_mode = options["breadth_mode"]
        self.file_density_coef = options["file_density_coef"]
        self.hub_gate = options["hub_gate"]
        self.hub_gate_mu = options["hub_gate_mu"]
        self.hub_gate_sigma = (
            options["hub_gate_sigma"] or config.GRAPH_HUB_GATE_FALLBACK_SIGMA
        )

        self._nodes_by_id = {node.node_id: node for node in chunk_nodes}
        # What the last `custom_retrieve` walked; one retriever serves one request.
        self.last_trace: Optional[Dict[str, Any]] = None
        if self.inverse_freq:
            self.backend.chunk_density()

    def _expand_multi(self, seed_ids: List[str]) -> Tuple[Dict[str, float], Dict[str, int]]:
        seeds = list(dict.fromkeys(seed_ids))
        best_by_seed: Dict[str, Dict[str, int]] = {seed: {seed: 0} for seed in seeds}
        frontier_by_seed: Dict[str, List[str]] = {seed: [seed] for seed in seeds}
        # BFS tree edges: the first edge that reached each concept from each seed.
        walked: Dict[Tuple[str, str], str] = {}
        for hop in range(1, self.hops + 1):
            union_frontier = list(
                {node for frontier in frontier_by_seed.values() for node in frontier}
            )
            if not union_frontier:
                break
            adjacency = self.backend.neighbors(union_frontier)
            for seed in seeds:
                best = best_by_seed[seed]
                next_frontier: List[str] = []
                for node_id in frontier_by_seed[seed]:
                    for neighbor_id, _relation in adjacency.get(node_id, []):
                        if neighbor_id not in best:
                            best[neighbor_id] = hop
                            next_frontier.append(neighbor_id)
                            walked.setdefault((node_id, neighbor_id), _relation)
                frontier_by_seed[seed] = next_frontier
        weights: Dict[str, float] = {}
        coreach: Dict[str, int] = defaultdict(int)
        for seed in seeds:
            for concept_id, hop in best_by_seed[seed].items():
                graph_weight = self.decay ** hop
                if graph_weight > weights.get(concept_id, 0.0):
                    weights[concept_id] = graph_weight
                coreach[concept_id] += 1
        self._walked = walked
        self._hops = {
            concept_id: min(best[concept_id] for best in best_by_seed.values() if concept_id in best)
            for concept_id in weights
        }
        return weights, dict(coreach)

    def _score_reached(self, reached: Dict[str, float]) -> List[Tuple[str, float]]:
        scores: Dict[str, float] = defaultdict(float)
        density = self.backend.chunk_density() if self.inverse_freq else {}
        degrees = self.backend.neighbors(list(reached)) if self.hub_gate else {}
        source_chunks = self.backend.source_chunk_ids(list(reached))
        self._source_chunks = source_chunks
        for concept_id, graph_weight in reached.items():
            chunk_ids = source_chunks.get(concept_id, [])
            weight = graph_weight
            if self.inverse_freq:
                breadth = max(1, len(chunk_ids))
                if self.breadth_mode == "linear":
                    weight /= breadth
                elif self.breadth_mode == "sqrt":
                    weight /= math.sqrt(breadth)
                else:
                    weight /= 1.0 + math.log(breadth)
            if self.hub_gate:
                degree = len(degrees.get(concept_id, []))
                weight /= 1.0 + math.exp(
                    (degree - self.hub_gate_mu) / self.hub_gate_sigma
                )
            for chunk_id in chunk_ids:
                if chunk_id not in self._nodes_by_id:
                    raise ValueError(
                        f"Nebula references missing document chunk {chunk_id!r}; "
                        "re-ingest the OKF assets after document re-chunking"
                    )
                if self.inverse_freq:
                    density_val = max(1, density.get(chunk_id, 1))
                    contribution = weight / (
                        1.0 + self.file_density_coef * math.log(density_val)
                    )
                else:
                    contribution = weight
                scores[chunk_id] += contribution
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    def _search_from_concepts(self, seed_ids: List[str]) -> List[Tuple[str, float]]:
        weights, coreach = self._expand_multi(seed_ids)
        reached = {}
        for concept_id, graph_weight in weights.items():
            n = coreach.get(concept_id, 1)
            if self.coreach_mode == "log":
                multiplier = 1.0 + self.coreach_coef * math.log(n) if n >= 1 else 1.0
            else:  # "linear"
                multiplier = 1.0 + self.coreach_coef * (n - 1)
            reached[concept_id] = graph_weight * multiplier
        self._last_weights = reached
        return self._score_reached(reached)

    def _known_concepts(self) -> Set[str]:
        if self._known is None:
            self._known = set(self.backend.concept_ids())
        return self._known

    def custom_retrieve(self, query_str: str) -> List[NodeWithScore]:
        seed_ids = self.seeder.seed(
            query_str,
            self.seed_m,
            windows=self.seed_windows,
            overlap=self.seed_overlap,
            min_win=self.seed_min_win,
        )
        self.last_trace = None
        # The concept index may be shared across pools: seed only from this graph's concepts.
        known = self._known_concepts()
        seed_ids = [seed for seed in seed_ids if seed in known]
        if not seed_ids:
            self.last_trace = {"seeds": [], "concepts": [], "edges": []}
            return []
        pairs = self._search_from_concepts(seed_ids)
        self.last_trace = self._trace(seed_ids)
        results = []
        for chunk_id, score in pairs:
            node = self._nodes_by_id.get(chunk_id)
            if node is not None:
                results.append(NodeWithScore(node=node, score=score))
        return results

    def _trace(self, seed_ids: List[str]) -> Dict[str, Any]:
        weights = getattr(self, "_last_weights", {})
        return {
            "seeds": list(dict.fromkeys(seed_ids)),
            "concepts": [
                {
                    "id": concept_id,
                    "hop": hop,
                    "weight": weights.get(concept_id, 0.0),
                    "chunk_ids": list(self._source_chunks.get(concept_id, [])),
                }
                for concept_id, hop in sorted(self._hops.items(), key=lambda item: (item[1], item[0]))
            ],
            "edges": [
                {"source": source, "target": target, "relation": relation}
                for (source, target), relation in self._walked.items()
            ],
        }

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[NodeWithScore]:
        return self.custom_retrieve(query)[: top_k or self.topk]
