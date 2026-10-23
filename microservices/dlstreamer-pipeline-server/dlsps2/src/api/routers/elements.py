# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging

from fastapi import APIRouter, HTTPException

from api.schema import ElementDetailResponse, ElementInfo
from core.gst_elements import get_available_elements, get_element_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/elements", tags=["elements"])


@router.get("", response_model=list[ElementInfo])
async def list_elements():
    """List all available GStreamer elements.

    Returns all available GStreamer elements on the system.

    ### Example
    `GET /elements` – Returns list of all elements
    """
    elements = get_available_elements()
    return elements


@router.get("/{element_name}", response_model=ElementDetailResponse)
async def get_element_details(element_name: str):
    """Get detailed information about a specific GStreamer element.

    Returns full `gst-inspect` output for the element.

    ### Example
    `GET /elements/videotestsrc` – Details about videotestsrc element
    """
    element = get_element_info(element_name)
    if not element:
        raise HTTPException(
            status_code=404,
            detail=f"GStreamer element {element_name!r} not found",
        )
    return element
