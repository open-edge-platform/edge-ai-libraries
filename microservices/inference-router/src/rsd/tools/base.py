"""Query classifier abstraction.

A classifier maps a piece of query text to a discrete label plus a confidence.
For this tool the labels are the E/H intelligent-routing classes (E -> local,
H -> cloud), but the interface is label-agnostic so the router can map labels
to route targets however it likes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Protocol, runtime_checkable


@dataclass
class ClassifyResult:
    """Outcome of classifying a single query.

    Attributes:
        label: The winning label (e.g. ``"E"`` or ``"H"``).
        confidence: Probability of ``label`` after softmax over the candidate
            label logits. In ``[0, 1]``.
        scores: Probability for every candidate label, e.g. ``{"E": .., "H": ..}``.
            Kept for debugging / thresholding.
    """

    label: str
    confidence: float
    scores: Dict[str, float] = field(default_factory=dict)


@runtime_checkable
class QueryClassifier(Protocol):
    """Anything that turns query text into a :class:`ClassifyResult`.

    Implementations may be a real model (see :mod:`.ov_qwen`) or a stub for
    testing. Keeping this a ``Protocol`` lets the OpenVINO backend be swapped
    (e.g. for a native ``openvino.Core`` implementation) without touching the
    router.
    """

    def classify(self, text: str) -> ClassifyResult:
        """Classify ``text`` and return the label, confidence and per-label scores."""
        ...
