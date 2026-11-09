# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concept seeder (query -> seed OKF concepts), extracted from retriever.py so both the fused
graph arm and a graph-only retriever can build/reuse it. ConceptSeeder = embedding-cosine seeds."""

from typing import Dict, List


class ConceptSeeder:
    """Seed concepts through the persisted Milvus index, never local embeddings."""

    def __init__(self, vector_indexer):
        if vector_indexer is None:
            raise ValueError("Graph seeding requires an existing Milvus concept index")
        # top_k is set per call in seed() (to `count`), so no fixed value here.
        self._retriever = vector_indexer.as_retriever()

    @staticmethod
    def _split(query: str, k: int, overlap: int, min_win: int) -> List[str]:
        """Tile `query` into ~k overlapping character windows at ONE granularity.

        Window length W and step S are derived from the window COUNT k and overlap O:
            W = ceil((L + (k-1)*O) / k),  S = W - O
        A floor min_win keeps windows meaningful on a short query (W clamped up, which
        may yield fewer than k windows). k<=1, or a query short enough that one window
        already covers it, returns [query]. (Ported from POC hsgm concept_link._split.)"""
        length = len(query)
        if k <= 1 or length <= min_win:
            return [query]
        window = max(min_win, -(-(length + (k - 1) * overlap) // k))  # ceil division
        if window >= length:
            return [query]
        step = max(1, window - overlap)
        windows, start = [], 0
        while start < length:
            windows.append(query[start:start + window])
            if start + window >= length:
                break
            start += step
        return windows

    def _windows(self, query: str, k: int, overlap: int, min_win: int) -> List[str]:
        """Multi-granularity PYRAMID of windows for MaxSim: the union of `_split` at every
        level 1..k. Level 1 is the whole query; level j tiles it into ~j windows. So k=2
        yields the whole query + a 2-way split. MaxSim over the pyramid lets each concept
        match the query at WHATEVER granularity fits it best (a salient entity diluted in
        the full vector is rescued by a finer level). k=1 == whole-query only (no change)."""
        seen: set = set()
        out: List[str] = []
        for level in range(1, max(1, k) + 1):
            for win in self._split(query, level, overlap, min_win):
                if win not in seen:
                    seen.add(win)
                    out.append(win)
        return out

    def seed(self, query: str, count: int, windows: int = 1, overlap: int = 0, min_win: int = 6) -> List[str]:
        """Top-`count` concepts as graph seeds by MaxSim (ColBERT-style late interaction) over a
        pyramid of `windows` overlapping query windows: each concept's score is the MAX of its
        similarity to any window. Splitting the query dilutes semantically-empty spans that drag a
        single whole-query vector off the salient entities. windows=1 == whole-query (original)."""
        chunks = self._windows(query, windows, overlap, min_win)
        # Similarity search runs in Milvus. Only window-score aggregation is local.
        # Assumes cosine/IP (higher scores are better), not raw L2 distance.
        self._retriever.similarity_top_k = count
        if len(chunks) == 1:
            return [nws.node.metadata.get("cid", nws.node.node_id) for nws in self._retriever.retrieve(chunks[0])]
        best: Dict[str, float] = {}
        for win in chunks:
            for nws in self._retriever.retrieve(win):
                cid = nws.node.metadata.get("cid", nws.node.node_id)
                score = nws.score if nws.score is not None else 0.0
                if cid not in best or score > best[cid]:
                    best[cid] = score
        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)[:count]
        return [cid for cid, _ in ranked]
