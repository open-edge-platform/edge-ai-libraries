import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from cpu_topology import TopologySource, get_cpu_topology
from device import DeviceDiscovery, DeviceDiscoveryError, DeviceFamily

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
        503: {
            "description": "Device list not available from DL Streamer Pipeline Server 2.0.",
            "model": schemas.MessageResponse,
        },
    },
)
def get_devices():
    """
    **Return the inference devices of DL Streamer Pipeline Server 2.0.**

    ## Operation
    Pipelines run on DL Streamer Pipeline Server 2.0, so the devices listed are
    the CPU, GPU, and NPU devices its OpenVINO runtime discovers. They are
    exposed in a simplified, API-friendly format.

    1. Read the device list from the server's `GET /devices` (once; later
       requests reuse the first list read)
    2. Extract device properties and metadata
    3. Attach the core type of every online logical CPU to the CPU device
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
    - `cpu_topology` - For the CPU device, the core type (`P`, `E`, `LPE` or `UNIFORM`)
      of every online logical CPU, read from Linux sysfs. `null` for other devices, or
      when the core types cannot be determined

    ## Conditions

    ### ✅ Success
    - DL Streamer Pipeline Server 2.0 returns its device list
    - At least zero devices are returned (empty list is valid)
    - A failure to read the CPU topology does not fail the request; `cpu_topology` is `null`

    ### ❌ Failure
    - DL Streamer Pipeline Server 2.0 is unreachable, or cannot list its devices → 503
    - Unhandled exception during device discovery → 500

    ## Example Response

    ```json
    [
      {
        "device_name": "CPU",
        "full_device_name": "Intel(R) Core(TM) Ultra 7 155H",
        "device_type": "INTEGRATED",
        "device_family": "CPU",
        "gpu_id": null,
        "cpu_topology": {
          "is_hybrid": true,
          "source": "sysfs_pmu",
          "cores": [
            {"cpu": 0, "core_type": "P", "core_id": 0},
            {"cpu": 6, "core_type": "E", "core_id": 6},
            {"cpu": 14, "core_type": "LPE", "core_id": 14}
          ]
        }
      },
      {
        "device_name": "GPU.0",
        "full_device_name": "Intel(R) Arc(TM) Graphics (iGPU) (GPU.0)",
        "device_type": "INTEGRATED",
        "device_family": "GPU",
        "gpu_id": 0,
        "cpu_topology": null
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
                device_type=schemas.DeviceType(device.device_type.value),
                device_family=schemas.DeviceFamily(device.device_family.value),
                gpu_id=getattr(device, "gpu_id", None),
                cpu_topology=(
                    _cpu_topology()
                    if device.device_family.value == DeviceFamily.CPU.value
                    else None
                ),
            )
            for device in device_list
        ]
    except DeviceDiscoveryError as e:
        logger.error("Failed to discover devices: %s", e)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Device list not available from DL Streamer Pipeline Server 2.0"
            ).model_dump(),
            status_code=503,
        )
    except Exception:
        logger.error("Failed to discover devices", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error when discovering devices"
            ).model_dump(),
            status_code=500,
        )


def _cpu_topology() -> schemas.CpuTopology | None:
    """
    Return the host CPU topology in API form.

    Returns:
        schemas.CpuTopology | None: Core types of all online CPUs, or None when
            they cannot be determined. Never raises, so a topology problem does
            not fail device discovery.
    """
    try:
        topology = get_cpu_topology()
        if topology.source is TopologySource.UNAVAILABLE:
            return None
        return schemas.CpuTopology(
            is_hybrid=topology.is_hybrid,
            source=schemas.CpuTopologySource(topology.source.value),
            cores=[
                schemas.CpuCore(
                    cpu=c.cpu,
                    core_type=schemas.CpuCoreType(c.core_type.value),
                    core_id=c.core_id,
                )
                for c in topology.cpus
            ],
        )
    except Exception:
        logger.error("Failed to report CPU topology", exc_info=True)
        return None
