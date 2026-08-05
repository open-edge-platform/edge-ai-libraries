# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Reusable OpenAPI ``responses`` fragments for the DataPrep REST API.

Every failure raised by the service is normalised into a
:class:`~src.common.schema.DataPrepResponse` body by the global exception
handler in :mod:`src.main`, so a single response shape describes them all.
Declaring the codes here keeps the generated specification exhaustive, which is
what lets generated clients handle failures instead of only the happy path.

Descriptions are deliberately written against the *configured* storage and
vector database backends rather than any concrete product: the same endpoints
serve object storage or a local filesystem (``STORAGE_BACKEND``) and VDMS or
Milvus (``VECTORDB_BACKEND``).
"""

from http import HTTPStatus
from typing import Any, Dict, Iterable

from src.common.schema import DataPrepResponse

#: Canonical description for each error status the API can return.
_ERROR_DESCRIPTIONS: Dict[int, str] = {
    HTTPStatus.BAD_REQUEST: (
        "Required parameters are missing, malformed, or fail validation "
        "(for example an unsupported media type or an out-of-range value)."
    ),
    HTTPStatus.NOT_FOUND: (
        "The requested media, bucket, or job does not exist in the configured "
        "storage backend."
    ),
    HTTPStatus.CONFLICT: (
        "The upload duplicates media that is already stored. Returned only when "
        "duplicate uploads are disabled (``ALLOW_DUPLICATE_UPLOADS=false``); the "
        "message carries the existing ``video_id``."
    ),
    HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE: (
        "The requested byte range lies outside the stored object."
    ),
    HTTPStatus.INTERNAL_SERVER_ERROR: (
        "An unexpected error occurred inside the DataPrep service."
    ),
    HTTPStatus.BAD_GATEWAY: (
        "The configured storage backend or vector database could not be reached "
        "or returned an error."
    ),
}


def error_responses(*codes: int) -> Dict[int | str, Dict[str, Any]]:
    """Build an OpenAPI ``responses`` mapping for the given error codes.

    Args:
        *codes: HTTP status codes the operation can return. Each must have a
            canonical description registered above, so that a typo surfaces at
            import time rather than as a silently undocumented response.

    Returns:
        A mapping suitable for the ``responses`` argument of a FastAPI route
        decorator, with every entry documenting a ``DataPrepResponse`` body.

    Raises:
        KeyError: If a code has no canonical description.
    """

    responses: Dict[int | str, Dict[str, Any]] = {}
    for code in _dedupe(codes):
        responses[int(code)] = {
            "description": _ERROR_DESCRIPTIONS[code],
            "model": DataPrepResponse,
        }
    return responses


def _dedupe(codes: Iterable[int]) -> list[int]:
    """Return ``codes`` without duplicates, preserving the declared order."""

    seen: set[int] = set()
    ordered: list[int] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


# Frequently reused groupings, named for the behaviour they describe.

#: Endpoints that validate input and talk to storage plus the vector database.
INGEST_ERRORS = (
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.CONFLICT,
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.INTERNAL_SERVER_ERROR,
)

#: Ingestion endpoints that skip duplicates instead of rejecting them.
INGEST_ERRORS_NO_CONFLICT = (
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.INTERNAL_SERVER_ERROR,
)

#: Read-only endpoints over stored media and jobs.
READ_ERRORS = (
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.INTERNAL_SERVER_ERROR,
)
