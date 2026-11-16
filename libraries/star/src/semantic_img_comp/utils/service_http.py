# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/service_http.py
Description: Small FastAPI helpers shared by the encoder and decoder REST
services (semantic_img_comp.encoder.service / semantic_img_comp.decoder.service)
so the identical exception handling, request-body-size limiting, and health
check wiring isn't duplicated in both places.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# SDL425/T-002: both services use this to constrain path stream_id tokens --
# they are used as dict keys and, depending on the service, to build
# filesystem paths (decoder) or outgoing decoder-service URLs (encoder).
STREAM_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,128}$"


def install_common_endpoints(app: FastAPI, logger: logging.Logger, *, max_body_bytes: int) -> None:
    """Register the exception handler, body-size middleware, and `/healthz`
    route shared by the encoder and decoder services.

    :param max_body_bytes: per-service cap (SDL443/T-004) checked against the
        request's Content-Length header; each service's `/v1/streams/*` body
        endpoint still separately re-checks the actual body length as a
        safety net for chunked bodies with no/incorrect Content-Length header.
    """

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # SDL423: log full detail server-side only; never leak internals to the client
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "An internal error occurred. Please try again."})

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        # SDL443/T-004: reject oversized bodies before they are buffered/processed
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_body_bytes:
                    return JSONResponse(status_code=413, content={"detail": "request body too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "invalid content-length header"})
        return await call_next(request)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}
