# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

router = APIRouter(tags=["Status APIs"])


@router.get("/health", summary="Check the health of the API service")
async def check_health():
    """Health API endpoint to check whether API Server is reachable and responding."""
    return {"status": "ok"}
