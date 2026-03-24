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
    **Return all devices discovered by the OpenVINO runtime.**

    ## Operation
    Discovers CPU, GPU, and NPU devices available in the system and exposes
    them in a simplified, API-friendly format.

    1. Initialize OpenVINO Core
    2. Discover all available inference devices
    3. Extract device properties and metadata
    4. Return formatted device list

    ## Parameters
    - **Path/Query parameters:** None

    ## Response Format

    ### 200 OK
    JSON array of Device objects.

    **Each device includes:**
    - `device_name` - Short identifier used by runtime (e.g., `"CPU"`, `"GPU"`, `"GPU.0"`, `"NPU"`)
    - `full_device_name` - Human-readable name (e.g., CPU/GPU marketing name)
    - `device_type` - `INTEGRATED` or `DISCRETE`
    - `device_family` - `CPU`, `GPU`, or `NPU`
    - `gpu_id` - Integer index for GPU devices (when applicable), otherwise `null`

    ## Conditions

    ### ✅ Success
    - OpenVINO Core initializes correctly
    - At least zero devices are returned (empty list is valid)

    ### ❌ Failure
    - Unhandled exception during device discovery → 500
    - OpenVINO cannot be initialized → 500

    ## Example Response

    ```json
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
    ```
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
