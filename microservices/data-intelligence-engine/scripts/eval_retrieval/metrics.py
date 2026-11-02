# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Text-to-media retrieval metrics, reported under both usual conventions.

A dataset gives several captions per item, and the literature scores that two
ways: treat each caption as its own query, or count an item found if any of its
captions finds it. The numbers differ by several points and papers are not
always explicit about which they used, so both are reported rather than one
being picked and later mistaken for the other.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

RECALL_AT = (1, 5, 10)


@dataclass
class Scores:
    """One scoring convention's results."""

    queries: int = 0
    recall: Dict[int, float] = field(default_factory=dict)
    median_rank: float = 0.0
    mean_rank: float = 0.0

    def as_row(self, label: str) -> str:
        cells = "  ".join(f"{self.recall.get(k, 0.0) * 100:6.2f}" for k in RECALL_AT)
        return (
            f"| {label:<22} | {self.queries:>6} | {cells} | "
            f"{self.median_rank:>6.1f} | {self.mean_rank:>7.1f} |"
        )


def _from_ranks(ranks: Sequence[int]) -> Scores:
    """Scores from one rank per query, where rank 1 is a correct top hit."""
    if not ranks:
        return Scores()
    ordered = sorted(ranks)
    middle = len(ordered) // 2
    median = (
        float(ordered[middle])
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    return Scores(
        queries=len(ranks),
        recall={k: sum(r <= k for r in ranks) / len(ranks) for k in RECALL_AT},
        median_rank=median,
        mean_rank=sum(ranks) / len(ranks),
    )


def rank_of(similarities: Sequence[float], target: int) -> int:
    """Where `target` lands, counting from 1.

    Ties are broken against the target -- anything scoring equal is counted as
    ahead of it. A model that returns one constant for everything then scores
    like the worst case rather than the average, which is the honest reading.
    """
    score = similarities[target]
    return 1 + sum(1 for index, other in enumerate(similarities)
                   if index != target and other >= score)


def score(ranks_per_item: Sequence[Sequence[int]]) -> Dict[str, Scores]:
    """Both conventions, from the per-caption ranks grouped by item.

    `ranks_per_item[i]` holds one rank for each caption of item `i`.
    """
    per_caption: List[int] = [rank for ranks in ranks_per_item for rank in ranks]
    per_item: List[int] = [min(ranks) for ranks in ranks_per_item if ranks]
    return {"per_caption": _from_ranks(per_caption), "per_item": _from_ranks(per_item)}


def table(results: Dict[str, Dict[str, Scores]]) -> str:
    """Every run's scores as one markdown table."""
    header = (
        "| run                    | queries |    R@1     R@5    R@10 | MedR |   MeanR |\n"
        "|------------------------|---------|------------------------|------|---------|"
    )
    rows = [
        scores.as_row(f"{run}/{convention.replace('per_', '')}")
        for run, conventions in results.items()
        for convention, scores in conventions.items()
    ]
    return "\n".join([header, *rows])


__all__ = ["RECALL_AT", "Scores", "rank_of", "score", "table"]
