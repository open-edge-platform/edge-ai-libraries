"""Query classifier abstraction and the routing decision.

A classifier scores C classes, merges them into routing zones (a version's
``class_zones``; one zone per class unless stated) and decides on one zone or
abstains. The rule returns the zone index. Zone names come from the classifier
configuration: for example local/cloud for the shipped soft versions or a
multi-class rule's user-defined labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Sequence, runtime_checkable

import numpy as np


def zone_probs(
    class_probs: Sequence[float], class_zones: Optional[Sequence[int]] = None
) -> np.ndarray:
    """Sum class probabilities into their zones (``class_zones=None``: one zone per class)."""
    probs = np.asarray(class_probs, dtype=np.float64)
    if class_zones is None:
        return probs
    return np.bincount(np.asarray(class_zones), weights=probs)


def decide(zone_probs: Sequence[float], threshold: float) -> Optional[int]:
    """The most likely zone, or ``None`` (abstain) when its probability is below ``threshold``."""
    index = max(range(len(zone_probs)), key=zone_probs.__getitem__)
    return None if zone_probs[index] < threshold else index


@dataclass
class ClassifyResult:
    """Outcome of classifying a single query.

    Attributes:
        label: Name of the decided zone (for example ``"local"``, ``"cloud"``
            or ``"planning"``), or ``None`` when the classifier abstains.
        confidence: Probability of the most likely zone (also when abstaining).
            Informational only -- :func:`decide` compares it with ``threshold``.
        scores: Probability of every zone, by name, in zone order.
        index: Index of the decided zone -- what the rule returns -- or
            ``None`` when abstaining.
        threshold: Confidence floor that was applied (see :func:`decide`).
        kind: Classifier kind (``"hard"`` / ``"soft"``), when known.
        version: Classifier version that produced the result, when known.
        raw: Pre-decision outputs kept for data collection (e.g. label logits,
            per-class probabilities before merging into zones).
    """

    label: Optional[str]
    confidence: float
    scores: Dict[str, float] = field(default_factory=dict)
    index: Optional[int] = None
    threshold: Optional[float] = None
    kind: Optional[str] = None
    version: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class QueryClassifier(Protocol):
    """Anything that turns query text into a :class:`ClassifyResult`.

    Implementations may be a real model (see :mod:`.classifier`) or a stub for
    testing. Keeping this a ``Protocol`` lets the OpenVINO backend be swapped
    (e.g. for a native ``openvino.Core`` implementation) without touching the
    router.
    """

    def classify(self, text: str) -> ClassifyResult:
        """Classify ``text`` and return the label, confidence and per-label scores."""
        ...
