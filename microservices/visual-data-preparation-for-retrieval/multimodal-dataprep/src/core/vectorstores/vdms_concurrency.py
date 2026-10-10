# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Serialize access to the shared, non-thread-safe VDMS client connection.

VDMS's Python client (``VDMS_Client``) wraps a single TCP socket and performs an
unlocked ``send`` then ``recv`` per query. The process-wide ``VDMSVectorStore``
singleton shares one such connection across every caller -- the per-stream live
ingestion store workers and the retention sweeper's deletes among them. When two
threads issue a query concurrently their ``send``/``recv`` pairs interleave on
that one socket, desynchronizing the request/response framing so both block
forever in ``recv`` (observed in production as a full-pipeline stall: an insert
``add_from`` and a retention ``FindDescriptor _deletion`` wedged on the same
socket, back-pressuring the entire decode -> detect -> embed -> store pipeline).

A single process-wide re-entrant lock serializes all VDMS calls so the framing
stays intact. VDMS processes requests serially anyway, so the throughput cost is
negligible. This mirrors the fix already shipped in the vector-retriever
microservice.
"""

from __future__ import annotations

import threading
from functools import wraps
from typing import Any, Callable, TypeVar, cast

# Re-entrant so nested VDMS calls on the same thread do not self-deadlock, e.g.
# ``add_embeddings`` -> ``check_and_update_properties`` or
# ``_delete_by_constraints`` -> ``update_index``.
_VDMS_CONNECTION_LOCK = threading.RLock()

F = TypeVar("F", bound=Callable[..., Any])


def serialize_vdms_calls(func: F) -> F:
    """Hold the process-wide VDMS connection lock for the duration of ``func``."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with _VDMS_CONNECTION_LOCK:
            return func(*args, **kwargs)

    return cast(F, wrapper)
