# SPDX-License-Identifier: Apache-2.0

"""
System Information API Routes.

Provides a single endpoint that returns hardware and OS details about the
current host machine.  Used by the UI to pre-populate the server
registration dialog.
"""

import logging
import os
import platform
import socket
import subprocess
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas

router = APIRouter()
logger = logging.getLogger("api.routes.sysinfo")


def _get_machine_id() -> str:
    """Get a stable unique ID for this physical machine.

    /etc/machine-id is NOT used because it is baked into the Docker image and
    is therefore identical across all containers. Instead we derive a uuid5
    from HOST_IP + CPU + RAM, which uniquely identifies each physical host.
    """
    host_ip = _get_ip_address()
    cpu = _get_cpu_info()
    ram = str(_get_ram_size())

    fingerprint = f"{host_ip}|{cpu}|{ram}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, fingerprint))


def _get_ip_address() -> str:
    """Get host IP address (not container IP)."""
    host_ip = os.environ.get("HOST_IP")
    if host_ip:
        return host_ip

    try:
        with open("/proc/net/route") as f:
            for line in f:
                fields = line.strip().split()
                if fields[1] == "00000000":  # Default route
                    iface = fields[0]
                    result = subprocess.run(
                        ["ip", "addr", "show", iface],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        for addr_line in result.stdout.split("\n"):
                            if "inet " in addr_line and "127.0.0.1" not in addr_line:
                                ip = addr_line.strip().split()[1].split("/")[0]
                                if not ip.startswith("172."):
                                    return ip
    except Exception as e:
        logger.debug("Failed to get IP from /proc/net/route: %s", e)

    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            for ip in result.stdout.strip().split():
                if not ip.startswith("127.") and not ip.startswith("172."):
                    return ip
    except Exception as e:
        logger.debug("Failed to get IP from hostname -I: %s", e)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("172."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"


def _get_cpu_info() -> str:
    """Get CPU model information."""
    try:
        result = subprocess.run(
            ["lscpu"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "Model name:" in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line.lower():
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass

    return platform.processor() or "Unknown CPU"


def _get_ram_size() -> int:
    """Get total RAM size in GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemTotal:" in line:
                    kb = int(line.split()[1])
                    gb = round(kb / (1024 * 1024))
                    return max(1, gb)
    except Exception:
        pass
    return 1


def _get_kernel_version() -> str:
    """Get kernel version."""
    try:
        return platform.release()
    except Exception:
        return "Unknown"


@router.get(
    "",
    operation_id="get_system_info",
    summary="Get System Information",
    responses={
        200: {
            "description": "System information retrieved successfully",
            "model": schemas.ServerResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def get_system_info():
    """
    **Get current system/machine information.**

    ## Operation
    Automatically collects system information from the current machine:
    1. Stable UUID derived from HOST_IP + CPU + RAM
    2. Primary IP address (respects HOST_IP env var)
    3. CPU model from lscpu or /proc/cpuinfo
    4. Total RAM size from /proc/meminfo
    5. Kernel version from platform.release()

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `ServerResponse` with system information |
    | 500 | `MessageResponse` - Unexpected error |

    ## Examples

    ### Success Response (200)
    ```json
    {
      "uuid": "a3c4f6e8b2d1c5a7b9e0f3a1c2d4e5f6",
      "ip_address": "192.168.1.100",
      "cpu_sku": "Intel(R) Core(TM) i7-12700K CPU @ 3.60GHz",
      "ram_size": 32,
      "kernel_version": "5.15.0-56-generic"
    }
    ```
    """
    try:
        system_info = schemas.ServerResponse(
            uuid=_get_machine_id(),
            ip_address=_get_ip_address(),
            cpu_sku=_get_cpu_info(),
            ram_size=_get_ram_size(),
            kernel_version=_get_kernel_version(),
        )
        return JSONResponse(content=system_info.model_dump(), status_code=200)
    except Exception as e:
        logger.error("Unexpected error while getting system info", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to get system info: {str(e)}"
            ).model_dump(),
            status_code=500,
        )
