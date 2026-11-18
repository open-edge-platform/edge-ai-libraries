# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Dict, List


class ConceptSeeder:
    """Seeds query -> OKF concepts through the persisted Milvus concept index."""

    def __init__(self, vector_indexer):
        if vector_indexer is None:
            raise ValueError("Graph seeding requires an existing Milvus concept index")
        self._retriever = vector_indexer.as_retriever()

    @staticmethod
    def _split(query: str, k: int, overlap: int, min_win: int) -> List[str]:
        """Tile `query` into ~k overlapping character windows of length >= min_win."""
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
        """Union of `_split` at every level 1..k; level 1 is the whole query."""
        seen: set = set()
        out: List[str] = []
        for level in range(1, max(1, k) + 1):
            for win in self._split(query, level, overlap, min_win):
                if win not in seen:
                    seen.add(win)
                    out.append(win)
        return out

    def seed(self, query: str, count: int, windows: int = 1, overlap: int = 0, min_win: int = 6) -> List[str]:
        """Top-`count` concept ids, scored by max similarity over the query window pyramid."""
        chunks = self._windows(query, windows, overlap, min_win)
        # Assumes cosine/IP scores (higher is better), not L2 distance.
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
