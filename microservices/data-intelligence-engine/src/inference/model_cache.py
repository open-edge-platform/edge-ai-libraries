# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Loaded models, shared while something uses them and released after.

Loading an embedding model is expensive and several sources usually share one,
so the factories cache by configuration. The cache used to hold every model
forever: detaching a source, deleting a pool or deprecating a source left its
model resident until the process exited.

Entries are now held weakly. A projection owns its model; while any projection
does, every other source with the same configuration gets the same instance,
and when the last one is dropped -- a source frozen, detached or replaced --
the model goes with it. An object that cannot be weakly referenced is cached
strongly, as before.
"""

import gc
import threading
import weakref
from typing import Any, Callable, Dict, Hashable


class ModelCache:
    """`get_or_build(key, factory)`, at most one live instance per key."""

    def __init__(self) -> None:
        self._weak: "weakref.WeakValueDictionary[Hashable, Any]" = (
            weakref.WeakValueDictionary()
        )
        self._strong: Dict[Hashable, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any:
        found = self._strong.get(key)
        return found if found is not None else self._weak.get(key)

    def get_or_build(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        with self._lock:
            # Re-check: another thread may have built it while we waited.
            cached = self.get(key)
            if cached is None:
                cached = factory()
                try:
                    self._weak[key] = cached
                except TypeError:
                    self._strong[key] = cached
        return cached

    def __contains__(self, key: Hashable) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        return len(self._strong) + len(self._weak)

    @staticmethod
    def collect() -> None:
        """Run the collector, so a model dropped in a reference cycle goes now."""
        gc.collect()


__all__ = ["ModelCache"]
