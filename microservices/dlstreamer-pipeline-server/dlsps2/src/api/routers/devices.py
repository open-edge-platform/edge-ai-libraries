# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging

from fastapi import APIRouter, HTTPException

from api.schema import DeviceInfo
from core.openvino_devices import get_cached_devices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceInfo])
async def list_devices():
    """List OpenVINO inference devices available in the DLSPS runtime.

    Returns the device list cached at server startup, with each device's
    read-only OpenVINO properties.

    ### Example
    `GET /devices` – Returns list of OpenVINO devices
    """
    devices = get_cached_devices()
    if devices is None:
        raise HTTPException(status_code=503, detail="OpenVINO device discovery unavailable")
    return devices
