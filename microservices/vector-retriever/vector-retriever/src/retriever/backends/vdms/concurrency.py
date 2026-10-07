# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from functools import wraps
import threading
from typing import Any, Callable

from src.common.settings import settings


_VDMS_CONNECTION_LOCK = threading.RLock()


def serialize_vdms_calls(func: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize calls that share the process-wide VDMS connection.

    Only VDMS needs this; the pooled backends (Milvus, PGVector) are already
    safe for concurrent use and are left untouched.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if settings.RETRIEVER_BACKEND == "vdms":
            with _VDMS_CONNECTION_LOCK:
                return func(*args, **kwargs)
        return func(*args, **kwargs)

    return wrapper
