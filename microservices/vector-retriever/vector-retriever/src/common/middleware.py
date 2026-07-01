# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from uuid import uuid4

from fastapi import Request

from src.common.logger import get_logger


logger = get_logger()


async def request_id_middleware(request: Request, call_next):
    """Attach a request ID to request state and response headers.

    Uses an incoming `x-request-id` header when provided, otherwise generates
    a UUID so logs and responses can be correlated for each request.
    """
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    logger.info(
        "Received request request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response
