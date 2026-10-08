# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

import src.api.schemas as schemas

router = APIRouter()


@router.get(
    "/health",
    operation_id="get_health",
    response_model=schemas.HealthResponse,
    summary="Service health",
)
def get_health() -> schemas.HealthResponse:
    return schemas.HealthResponse(healthy=True)
