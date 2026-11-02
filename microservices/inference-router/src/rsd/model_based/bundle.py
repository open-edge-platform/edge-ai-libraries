# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Immutable in-memory form of one classifier version (one ``.rcv`` file).

A bundle is just data: the prompt (soft vectors or hard prompt text), the head,
the backbone fingerprint and the metadata. It holds no backbone and runs no
inference; :mod:`.format` reads and writes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, List, Mapping, Optional, Sequence, Union

import numpy as np

KIND_SOFT = "soft"
KIND_HARD = "hard"
KINDS = (KIND_SOFT, KIND_HARD)


def _frozen(array: np.ndarray) -> np.ndarray:
    array = np.ascontiguousarray(array)
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class ClassifierBundle:
    """One classifier version.

    Attributes:
        kind: ``"soft"`` or ``"hard"`` (stored in the ``.rcv`` header).
        prompt: Slot 0. Soft prompt vectors ``[k, hidden]`` (float32) for
            ``soft``; the system-prompt text for ``hard``.
        head_weight: Slot 1, ``[num_classes, hidden]``.
        head_bias: Slot 2, ``[num_classes]``.
        fp_hidden: Slot 3, backbone fingerprint ``[n_probes, hidden]``.
        meta: Metadata key/values (read-only), e.g. ``model_name``, ``threshold``.
    """

    kind: str
    prompt: Union[np.ndarray, str]
    head_weight: np.ndarray
    head_bias: np.ndarray
    fp_hidden: np.ndarray
    meta: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")
        if self.kind == KIND_SOFT:
            object.__setattr__(self, "prompt", _frozen(np.asarray(self.prompt, dtype=np.float32)))
        elif not isinstance(self.prompt, str):
            raise TypeError("a hard bundle's prompt must be text")
        for name in ("head_weight", "head_bias", "fp_hidden"):
            object.__setattr__(self, name, _frozen(np.asarray(getattr(self, name), dtype=np.float32)))
        object.__setattr__(self, "meta", MappingProxyType(dict(self.meta)))

    # -- frequently used metadata -------------------------------------------

    @property
    def model_name(self) -> str:
        return self.meta["model_name"]

    @property
    def version(self) -> str:
        return self.meta["version"]

    @property
    def hidden(self) -> int:
        return int(self.meta["hidden"])

    @property
    def num_classes(self) -> int:
        return int(self.meta["num_classes"])

    @property
    def class_labels(self) -> Sequence[int]:
        labels: Optional[Sequence[int]] = self.meta.get("class_labels")
        return list(labels) if labels is not None else list(range(self.num_classes))

    @property
    def class_zones(self) -> Optional[List[int]]:
        """Zone of each class, or ``None`` for one zone per class."""
        zones: Optional[Sequence[int]] = self.meta.get("class_zones")
        return list(zones) if zones is not None else None

    @property
    def zone_names(self) -> List[str]:
        """Name of each routing zone: ``zone_names``, else the class names."""
        names = self.meta.get("zone_names")
        return list(names if names is not None else self.meta["class_semantics"])

    @property
    def threshold(self) -> float:
        return float(self.meta["threshold"])

    # -- token form (soft prompt and class head live in the vocabulary) ------

    @property
    def soft_token_ids(self) -> Optional[List[int]]:
        """Token-form soft version: the vocabulary ids of its soft-prompt rows."""
        ids: Optional[Sequence[int]] = self.meta.get("soft_token_ids")
        return list(ids) if ids is not None else None

    @property
    def label_token_ids(self) -> Optional[List[int]]:
        """Token-form soft version: the vocabulary ids of its class rows."""
        ids: Optional[Sequence[int]] = self.meta.get("label_token_ids")
        return list(ids) if ids is not None else None

    @property
    def token_form(self) -> bool:
        """True for a soft version: its soft prompt and head are vocabulary rows.

        Every soft version is token form (the format requires the id fields;
        see :mod:`.vocab_tokens`).
        """
        return self.kind == KIND_SOFT and "soft_token_ids" in self.meta
