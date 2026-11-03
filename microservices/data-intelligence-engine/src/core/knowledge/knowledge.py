# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Knowledge: from assets to concepts, and from concepts to a graph.

A vector source answers "what text is like this query"; a graph source answers
"what is connected to what". A graph source's `Knowledge` decides which assets
become graph content and how, from the source's `operator_options.asset_types`:

- ``okf`` (the default): OKF bundles, built directly (`build`). The only format
  a graph is built from today.
- ``document``: ordinary documents, turned into OKF bundles first (`extract`) by
  the source's external extractor service (`core/knowledge/extractor.py`),
  then built like any bundle. Needs ``okf`` too, since that is what extraction
  produces, and an ``external_extractor`` with the service's access parameters.
    All documents in an extraction call form one task: corpus-specific instruction
    planning runs before the service extracts the OKF bundle.

`build` turns a bundle's concepts into vertices (keyed by concept id, labelled by
concept type) and their links into edges, keeping each concept's provenance --
the document chunks it was drawn from -- so graph retrieval can walk from
concepts back to text. Concepts several bundles define become one vertex.

`GraphIndexer` (one per graph source) holds a `Knowledge` and materializes what
`build` returns into its graph database. Document chunks live in vector sources,
where concepts cite them.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.knowledge.extractor import EXTERNAL_EXTRACTOR, ExternalExtractor, ExternalExtractorConfig

#: Max characters of an OKF concept's summary kept as its graph-vertex gloss.
GLOSS_MAX_CHARS = 50


@dataclass
class KnowledgeGraph:
    """Vertices and edges, keyed by vertex id so a merge cannot duplicate.

    Edges are deduplicated on `(source, label, target)`: the same relation
    stated twice in one document is one edge, and re-extracting an asset after
    its content changed writes over what was there rather than beside it.
    """

    vertices: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: Dict[tuple, Dict[str, Any]] = field(default_factory=dict)

    def add_vertex(
        self, vertex_id: str, label: str, properties: Optional[Mapping[str, Any]] = None
    ) -> str:
        existing = self.vertices.get(vertex_id)
        if existing is None:
            self.vertices[vertex_id] = {
                "id": vertex_id,
                "label": label,
                "properties": dict(properties or {}),
            }
        else:
            # A second mention of the same entity fills in what the first left
            # blank without overwriting what it established.
            for key, value in (properties or {}).items():
                existing["properties"].setdefault(key, value)
        return vertex_id

    def add_edge(
        self,
        source: str,
        label: str,
        target: str,
        properties: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.edges.setdefault(
            (source, label, target),
            {
                "source": source,
                "label": label,
                "target": target,
                "properties": dict(properties or {}),
            },
        )

    def merge(self, other: "KnowledgeGraph") -> "KnowledgeGraph":
        for vertex in other.vertices.values():
            self.add_vertex(vertex["id"], vertex["label"], vertex["properties"])
        for edge in other.edges.values():
            self.add_edge(
                edge["source"], edge["label"], edge["target"], edge["properties"]
            )
        return self

    def as_request(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "vertices": list(self.vertices.values()),
            "edges": list(self.edges.values()),
        }


def _origin_path(asset: Any) -> str:
    """The filesystem path inside an asset's provenance URI.

    OKF assets are provenance-only (their ``origin`` is the bundle directory), so
    the graph extractor reads the concepts from disk rather than from a content
    stream. Kept local to avoid importing ``core.file_asset_library`` (which
    imports ``core.indexer``, and this module is imported by ``core.indexer``).
    """
    origin = str(getattr(asset, "origin", "") or "")
    if origin.startswith("file://"):
        return origin[len("file://"):]
    return origin


def okf_nodes_to_graph(nodes) -> KnowledgeGraph:
    """OKF concepts as graph vertices and edges (the pure nodes -> graph step).

    ``resolve_source_chunk_ids`` must already have run, so each node's
    ``source_chunk_ids`` holds the provenance chunk ids before this is called.
    """
    graph = KnowledgeGraph()
    for node in nodes:
        gloss = ""
        if node.summaries:
            summary = max((text for text, _ in node.summaries), key=len, default="")
            summary = " ".join(summary.split())
            gloss = summary[:GLOSS_MAX_CHARS] + (
                "..." if len(summary) > GLOSS_MAX_CHARS else ""
            )
        concept_properties = {
            "title": node.title,
            "gloss": gloss,
            "okf_file_path": node.okf_file_path,
            "n_sources": len(node.source_chunk_ids),
            "source_chunk_ids": json.dumps(node.source_chunk_ids, ensure_ascii=False),
        }
        if node.status:
            concept_properties["status"] = node.status
        graph.add_vertex(
            node.cid,
            node.ctype,
            {
                "ref_doc_id": node.cid,
                "_node_content": json.dumps(concept_properties, ensure_ascii=False),
                "_node_type": "OKFConcept",
            },
        )
        for target, relation in node.links:
            graph.add_edge(node.cid, relation, target)
    return graph


#: Formats a graph can be built from. ``okf`` is built directly; ``document``
#: goes through the external extractor to become ``okf`` first.
OKF = "okf"
DOCUMENT = "document"
FORMATS: Tuple[str, ...] = (OKF, DOCUMENT)
DEFAULT_FORMATS: Tuple[str, ...] = (OKF,)


def _is_okf(asset: Any) -> bool:
    return getattr(asset, "asset_kind", "document") == OKF


def asset_format(asset: Any) -> str:
    """The knowledge format an asset is: an OKF bundle, or a document."""
    return OKF if _is_okf(asset) else DOCUMENT


class Knowledge:
    """Assets to OKF bundles (`extract`) and bundles to a graph (`build`).

    Configured from a graph source's `operator_options` (see the module
    docstring); an unusable configuration raises ValueError here, so a bad
    source is refused when it is created rather than when it first syncs.

    Writing the graph to a database is not this class's job: the graph source's
    `GraphIndexer` owns the connection and materializes what `build` returns.
    One `Knowledge` per graph source -- it is the single recipe for how that
    source's space is built, so vertex ids from different recipes never meet.

    Concept vertices follow edgecraftrag's OKFNodePathExtractor: keyed by
    ``cid``, labelled by ``ctype``, one edge per link, and a ``_node_content``
    JSON the graph-search backend parses for provenance chunk ids.
    """

    def __init__(self, configuration: Optional[Mapping[str, Any]] = None):
        configuration = configuration or {}
        misplaced = set(configuration) & {
            "url", "api_key", "timeout", "options", "trigger",
            "debounce_seconds", "cron", "timezone",
        }
        if misplaced:
            raise ValueError(
                "Extractor fields " + ", ".join(sorted(misplaced))
                + " belong inside operator_options.external_extractor, not directly "
                'in operator_options. Set operator_options.asset_types to ["okf", "document"] '
                "to enable document extraction."
            )
        raw = configuration.get("asset_types")
        if raw is None or raw == []:
            formats = list(DEFAULT_FORMATS)
        elif isinstance(raw, (list, tuple)) and all(isinstance(f, str) for f in raw):
            formats = list(dict.fromkeys(f.strip().lower() for f in raw))
        else:
            raise ValueError("asset_types must be a list of knowledge formats, e.g. [\"okf\"]")
        unknown = [f for f in formats if f not in FORMATS]
        if unknown:
            raise ValueError(
                f"Unsupported knowledge format(s) for a graph source: {', '.join(unknown)}; "
                f"supported: {', '.join(FORMATS)}"
            )
        self.extractor: Optional[ExternalExtractor] = None
        if DOCUMENT in formats:
            if OKF not in formats:
                raise ValueError(
                    "asset_types with \"document\" needs \"okf\" too: documents are "
                    "extracted into OKF bundles and built from those"
                )
            self.extractor = ExternalExtractor(
                ExternalExtractorConfig.from_options(configuration.get(EXTERNAL_EXTRACTOR))
            )
        elif configuration.get(EXTERNAL_EXTRACTOR) is not None:
            raise ValueError(
                f"{EXTERNAL_EXTRACTOR} is only used when asset_types includes \"document\""
            )
        self.formats: Tuple[str, ...] = tuple(formats)

    def accepts(self, asset: Any) -> bool:
        """Whether this knowledge takes `asset`: its format is configured."""
        return asset_format(asset) in self.formats

    def extract(self, assets: Sequence[Any], output_dir: Optional[Path] = None) -> List[Path]:
        """Turn documents into OKF bundles through the external extractor;
        return the bundle folders written under `output_dir`.

        Each bundle is a folder with an ``index.md`` and one markdown file per
        concept, citing the documents it came from in ``source_files`` -- the
        shape `build` (via ``core.knowledge.okf``) reads -- so it can be
        ingested as an ``okf`` asset into the same pool as its documents.
        """
        bundles = [asset for asset in assets if _is_okf(asset)]
        if bundles:
            raise ValueError(
                "OKF assets are already bundles: "
                + ", ".join(str(asset.asset_id) for asset in bundles)
            )
        if not assets:
            return []
        if self.extractor is None:
            raise ValueError(
                "This knowledge does not take documents; add \"document\" to asset_types "
                f"and configure {EXTERNAL_EXTRACTOR}"
            )
        return self.extractor.extract(assets, output_dir)

    def build(
        self,
        bundles: Sequence[Any],
        okf_context: Optional[Mapping[str, List[Any]]] = None,
    ) -> KnowledgeGraph:
        """The graph of every concept in `bundles` (``okf`` assets), merged.

        ``okf_context`` maps an asset id to its concepts (``[OKFNode, ...]``),
        already parsed and provenance-resolved by the library so the graph
        write and the concept vector index share one parse. A bundle without an
        entry is parsed from disk here instead, in which case ``source_files``
        cannot be resolved and must be absent. Retrieval reads persisted graph
        data, not parsed nodes in memory.
        """
        context = okf_context or {}
        graph = KnowledgeGraph()
        for bundle in bundles:
            if not _is_okf(bundle):
                # Documents are extracted into bundles first (`extract`); one
                # reaching here unextracted is a caller bug.
                raise ValueError(
                    f"Only OKF assets can be built into a graph; {bundle.asset_id!r} "
                    f"is {getattr(bundle, 'asset_kind', 'document')!r}"
                )
            nodes = context.get(bundle.asset_id)
            if nodes is None:
                from core.knowledge.okf import parse_okf_bundle

                nodes = parse_okf_bundle(_origin_path(bundle))
                if any(node.source_files for node in nodes):
                    raise ValueError(
                        "OKF source_files require indexed document files in the same "
                        "pool to resolve source_chunk_ids before writing to Nebula"
                    )
            graph.merge(okf_nodes_to_graph(nodes))
        return graph


__all__ = [
    "DEFAULT_FORMATS",
    "DOCUMENT",
    "FORMATS",
    "GLOSS_MAX_CHARS",
    "Knowledge",
    "KnowledgeGraph",
    "OKF",
    "asset_format",
    "okf_nodes_to_graph",
]
