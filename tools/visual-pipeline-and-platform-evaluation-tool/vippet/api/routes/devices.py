import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from device import DeviceDiscovery

router = APIRouter()
logger = logging.getLogger("api.routes.devices")


@router.get(
    "",
    operation_id="get_devices",
    response_model=List[schemas.Device],
    summary="List available inference devices",
    responses={
        200: {
            "description": "List of devices successfully retrieved.",
            "model": List[schemas.Device],
        },
        500: {
            "description": "Unexpected error when discovering devices.",
            "model": schemas.MessageResponse,
        },
    },
)
def get_devices():
    """
    Return all devices discovered by the OpenVINO runtime.

    This endpoint discovers CPU, GPU and NPU devices available in the system and
    exposes them in a simplified, API-friendly format.

    Returns:
        200 OK:
            List[Device] with one entry per detected device. Each entry contains:
            * device_name – short identifier used by the runtime (e.g. ``"CPU"``,
              ``"GPU"``, ``"GPU.0"``, ``"NPU"``).
            * full_device_name – human-readable name (e.g. CPU / GPU marketing name).
            * device_type – ``INTEGRATED`` or ``DISCRETE``.
            * device_family – ``CPU``, ``GPU`` or ``NPU``.
            * gpu_id – integer index for GPU devices when applicable, otherwise null.
        500 Internal Server Error:
            MessageResponse with a generic error description if device discovery fails
            unexpectedly (for example if OpenVINO cannot be initialized).

    Success conditions:
        * OpenVINO Core initializes correctly.
        * At least zero devices are returned (empty list is still success).

    Failure conditions:
        * 500 – any unhandled exception during device discovery.

    Successful response example (200):
        .. code-block:: json

            [
              {
                "device_name": "CPU",
                "full_device_name": "Intel(R) Core(TM) Ultra 7 155H",
                "device_type": "INTEGRATED",
                "device_family": "CPU",
                "gpu_id": null
              },
              {
                "device_name": "GPU.0",
                "full_device_name": "Intel(R) Arc(TM) Graphics (iGPU) (GPU.0)",
                "device_type": "INTEGRATED",
                "device_family": "GPU",
                "gpu_id": 0
              }
            ]
    """
    try:
        device_list = DeviceDiscovery().list_devices()
        return [
            schemas.Device(
                device_name=device.device_name,
                full_device_name=device.full_device_name,
                device_type=device.device_type,
                device_family=device.device_family,
                gpu_id=getattr(device, "gpu_id", None),
            )
            for device in device_list
        ]
    except Exception:
        logger.error("Failed to discover devices", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error when discovering devices"
            ).model_dump(),
            status_code=500,
        )
