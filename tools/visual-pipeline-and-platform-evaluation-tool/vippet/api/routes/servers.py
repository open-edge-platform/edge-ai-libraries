# SPDX-License-Identifier: Apache-2.0

"""
Server/Machine Management API Routes.

Provides REST endpoints for managing server/machine records in the database.
"""

import logging
import os
import platform
import socket
import subprocess
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Path as PathParam
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from database import check_db_connection
from managers.server_manager import ServerManager

router = APIRouter()
logger = logging.getLogger("api.routes.servers")


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
    # First, try to get from environment variable (if passed from host)
    host_ip = os.environ.get("HOST_IP")
    if host_ip:
        return host_ip
    
    try:
        # Try to get the default gateway IP from /proc/net/route
        with open("/proc/net/route", "r") as f:
            for line in f:
                fields = line.strip().split()
                if fields[1] == "00000000":  # Default route
                    # Get interface name
                    iface = fields[0]
                    # Read IP address from that interface
                    result = subprocess.run(
                        ["ip", "addr", "show", iface],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split("\n"):
                            if "inet " in line and "127.0.0.1" not in line:
                                # Extract IP address
                                ip = line.strip().split()[1].split("/")[0]
                                # Filter out Docker bridge IPs (172.x.x.x)
                                if not ip.startswith("172."):
                                    return ip
    except Exception as e:
        logger.debug(f"Failed to get IP from /proc/net/route: {e}")
    
    try:
        # Fallback: try hostname -I to get all IPs
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            ips = result.stdout.strip().split()
            # Filter out localhost and Docker IPs
            for ip in ips:
                if not ip.startswith("127.") and not ip.startswith("172."):
                    return ip
    except Exception as e:
        logger.debug(f"Failed to get IP from hostname -I: {e}")
    
    try:
        # Last resort: connect to external server to determine interface IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        # Only return if it's not a Docker bridge IP
        if not ip.startswith("172."):
            return ip
    except Exception:
        pass
    
    return "127.0.0.1"


def _get_cpu_info() -> str:
    """Get CPU model information."""
    try:
        # Try lscpu first
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
        # Fallback to /proc/cpuinfo
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line.lower():
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass

    return platform.processor() or "Unknown CPU"


def _get_ram_size() -> int:
    """Get total RAM size in GB."""
    try:
        # Read from /proc/meminfo
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemTotal:" in line:
                    # MemTotal is in kB
                    kb = int(line.split()[1])
                    gb = round(kb / (1024 * 1024))
                    return max(1, gb)  # At least 1 GB
    except Exception:
        pass
    return 1  # Default fallback


def _get_kernel_version() -> str:
    """Get kernel version."""
    try:
        return platform.release()
    except Exception:
        return "Unknown"


@router.get(
    "/db-status",
    operation_id="get_db_status",
    summary="Get Database Status",
    responses={
        200: {"description": "Database is reachable"},
        503: {"description": "Database is not reachable"},
    },
)
async def get_db_status():
    """
    **Check whether the database is reachable and return the connected role.**

    Returns 200 with ``role`` if DATABASE_URL is set and the database accepts
    connections, or 503 with an error message otherwise.

    The ``role`` field reflects the PostgreSQL ``current_user``:
    - ``vippet_server`` — full access; UI shows server registration dialog.
    - ``vippet_user``   — read-only access; UI hides server registration dialog.
    """
    available, reason, db_role = check_db_connection()
    if available:
        return JSONResponse(
            content={"available": True, "message": reason, "role": db_role},
            status_code=200,
        )
    return JSONResponse(
        content={"available": False, "message": reason, "role": None},
        status_code=503,
    )


@router.get(
    "/system-info",
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
    1. Machine ID from /etc/machine-id
    2. Primary IP address
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

        return JSONResponse(
            content=system_info.model_dump(),
            status_code=200,
        )
    except Exception as e:
        logger.error("Unexpected error while getting system info", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to get system info: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "",
    operation_id="add_server",
    summary="Add Server",
    status_code=201,
    responses={
        201: {
            "description": "Server created successfully",
            "model": schemas.ServerResponse,
        },
        400: {
            "description": "Invalid server data or server already exists",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def add_server(body: schemas.ServerCreate):
    """
    **Add a new server/machine to the database.**

    ## Operation
    1. Validate server data (all fields required and non-empty)
    2. Delegate to `ServerManager.add_server()`
    3. Return created server details

    ## Request Body
    **`ServerCreate`** with:
    - `uuid` *(required)* - Unique identifier for the server
    - `ip_address` *(required)* - IP address of the server
    - `cpu_sku` *(required)* - CPU SKU/model identifier
    - `ram_size` *(required)* - RAM size in GB (must be positive)
    - `kernel_version` *(required)* - Ubuntu kernel version

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 201 | `ServerResponse` with server details |
    | 400 | `MessageResponse` - Invalid data or UUID already exists |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - All required fields provided and valid
    - UUID is unique (not already in database)
    - RAM size is positive

    ### ❌ Failure
    - Missing or empty required fields → 400
    - UUID already exists → 400
    - RAM size is not positive → 400
    - Database error → 500

    ## Examples

    ### Request
    ```json
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "ip_address": "192.168.1.100",
      "cpu_sku": "Intel Core i7-12700K",
      "ram_size": 32,
      "kernel_version": "5.15.0-56-generic"
    }
    ```

    ### Success Response (201)
    ```json
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "ip_address": "192.168.1.100",
      "cpu_sku": "Intel Core i7-12700K",
      "ram_size": 32,
      "kernel_version": "5.15.0-56-generic"
    }
    ```

    ### Error Response (400)
    ```json
    {
      "message": "Server with UUID 550e8400-e29b-41d4-a716-446655440000 already exists"
    }
    ```
    """
    try:
        server = ServerManager().add_server(
            uuid=body.uuid,
            ip_address=body.ip_address,
            cpu_sku=body.cpu_sku,
            ram_size=body.ram_size,
            kernel_version=body.kernel_version,
        )

        return JSONResponse(
            content=schemas.ServerResponse(
                uuid=server.uuid,
                ip_address=server.ip_address,
                cpu_sku=server.cpu_sku,
                ram_size=server.ram_size,
                kernel_version=server.kernel_version,
            ).model_dump(),
            status_code=201,
        )
    except ValueError as e:
        logger.error("Failed to add server due to invalid input: %s", e)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=400,
        )
    except Exception as e:
        logger.error("Unexpected error while adding server", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to add server: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "",
    operation_id="list_servers",
    summary="List Servers",
    responses={
        200: {
            "description": "List of all servers",
            "model": schemas.ServerListResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def list_servers():
    """
    **List all servers/machines in the database.**

    ## Operation
    1. Retrieve all server records from database
    2. Return list of server details

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `ServerListResponse` with list of all servers |
    | 500 | `MessageResponse` - Unexpected error |

    ## Examples

    ### Success Response (200)
    ```json
    {
      "servers": [
        {
          "uuid": "550e8400-e29b-41d4-a716-446655440000",
          "ip_address": "192.168.1.100",
          "cpu_sku": "Intel Core i7-12700K",
          "ram_size": 32,
          "kernel_version": "5.15.0-56-generic"
        },
        {
          "uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
          "ip_address": "192.168.1.101",
          "cpu_sku": "Intel Core i9-12900K",
          "ram_size": 64,
          "kernel_version": "5.19.0-50-generic"
        }
      ]
    }
    ```
    """
    try:
        servers = ServerManager().list_servers()

        return JSONResponse(
            content=schemas.ServerListResponse(
                servers=[
                    schemas.ServerResponse(
                        uuid=server.uuid,
                        ip_address=server.ip_address,
                        cpu_sku=server.cpu_sku,
                        ram_size=server.ram_size,
                        kernel_version=server.kernel_version,
                    )
                    for server in servers
                ]
            ).model_dump(),
            status_code=200,
        )
    except Exception as e:
        logger.error("Unexpected error while listing servers", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to list servers: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.patch(
    "/{uuid}",
    operation_id="update_server",
    summary="Update Server",
    responses={
        200: {
            "description": "Server updated successfully",
            "model": schemas.ServerResponse,
        },
        400: {
            "description": "Invalid update data",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Server not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def update_server(
    uuid: str = PathParam(..., description="UUID of the server to update"),
    body: schemas.ServerUpdate = ...,
):
    """
    **Update server/machine details in the database.**

    ## Operation
    1. Validate that server exists
    2. Update provided fields only (partial update)
    3. Return updated server details

    ## Path Parameters
    - `uuid` - Unique identifier of the server to update

    ## Request Body
    **`ServerUpdate`** with optional fields:
    - `ip_address` *(optional)* - New IP address
    - `cpu_sku` *(optional)* - New CPU SKU
    - `ram_size` *(optional)* - New RAM size in GB (must be positive)
    - `kernel_version` *(optional)* - New kernel version

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `ServerResponse` with updated server details |
    | 400 | `MessageResponse` - Invalid update data |
    | 404 | `MessageResponse` - Server not found |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Server exists
    - All provided fields are valid
    - At least one field provided for update

    ### ❌ Failure
    - Server not found → 404
    - Invalid field values → 400
    - Database error → 500

    ## Examples

    ### Request
    ```json
    {
      "ip_address": "192.168.1.101",
      "ram_size": 64
    }
    ```

    ### Success Response (200)
    ```json
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "ip_address": "192.168.1.101",
      "cpu_sku": "Intel Core i7-12700K",
      "ram_size": 64,
      "kernel_version": "5.15.0-56-generic"
    }
    ```

    ### Error Response (404)
    ```json
    {
      "message": "Server with UUID 550e8400-e29b-41d4-a716-446655440000 not found"
    }
    ```
    """
    try:
        server = ServerManager().update_server(
            uuid=uuid,
            ip_address=body.ip_address,
            cpu_sku=body.cpu_sku,
            ram_size=body.ram_size,
            kernel_version=body.kernel_version,
        )

        return JSONResponse(
            content=schemas.ServerResponse(
                uuid=server.uuid,
                ip_address=server.ip_address,
                cpu_sku=server.cpu_sku,
                ram_size=server.ram_size,
                kernel_version=server.kernel_version,
            ).model_dump(),
            status_code=200,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            logger.warning("Server not found: %s", error_msg)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_msg).model_dump(),
                status_code=404,
            )
        else:
            logger.error("Failed to update server due to invalid input: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_msg).model_dump(),
                status_code=400,
            )
    except Exception as e:
        logger.error("Unexpected error while updating server", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to update server: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.delete(
    "/{uuid}",
    operation_id="delete_server",
    summary="Delete Server",
    responses={
        200: {
            "description": "Server deleted successfully",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Server not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
async def delete_server(
    uuid: str = PathParam(..., description="UUID of the server to delete")
):
    """
    **Delete a server/machine from the database.**

    ## Operation
    1. Validate that server exists
    2. Delete server record from database
    3. Return confirmation message

    ## Path Parameters
    - `uuid` - Unique identifier of the server to delete

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `MessageResponse` - Server deleted successfully |
    | 404 | `MessageResponse` - Server not found |
    | 500 | `MessageResponse` - Unexpected error |

    ## Examples

    ### Success Response (200)
    ```json
    {
      "message": "Server deleted successfully"
    }
    ```

    ### Error Response (404)
    ```json
    {
      "message": "Server with UUID 550e8400-e29b-41d4-a716-446655440000 not found"
    }
    ```
    """
    try:
        deleted = ServerManager().delete_server(uuid)

        if not deleted:
            logger.warning("Server not found for deletion: %s", uuid)
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=f"Server with UUID {uuid} not found"
                ).model_dump(),
                status_code=404,
            )

        return JSONResponse(
            content=schemas.MessageResponse(
                message="Server deleted successfully"
            ).model_dump(),
            status_code=200,
        )
    except Exception as e:
        logger.error("Unexpected error while deleting server", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to delete server: {str(e)}"
            ).model_dump(),
            status_code=500,
        )
