# SPDX-License-Identifier: Apache-2.0

"""
Server/Machine Management API Routes.

Provides REST endpoints for managing server/machine records in the database.
"""

import logging
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Path as PathParam
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from database import check_db_connection
from managers.server_manager import ServerManager

router = APIRouter()
logger = logging.getLogger("api.routes.servers")

ADMIN_API_KEY: str = os.environ.get("ADMIN_API_KEY", "").strip()


def _require_admin(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> None:
    """FastAPI dependency — allows access only when the correct ADMIN_API_KEY is provided."""
    if not ADMIN_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Admin API key is not configured on this server",
        )
    if not secrets.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin API key")


@router.get(
    "/db-status",
    operation_id="get_db_status",
    summary="Get Database Status",
    responses={
        200: {"description": "Database is reachable"},
        503: {"description": "Database is not reachable"},
    },
)
async def get_db_status(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    """
    **Check whether the database is reachable and return the caller's role.**

    Returns 200 with ``role`` if DATABASE_URL is set and the database accepts
    connections, or 503 with an error message otherwise.

    The ``role`` field is determined by the optional ``X-Admin-Key`` header:
    - ``vippet_server`` — ``ADMIN_API_KEY`` is configured on this server **and**
      the provided ``X-Admin-Key`` matches; full write access, UI shows the
      server registration dialog.
    - ``vippet_user``   — key absent, incorrect, or ``ADMIN_API_KEY`` not set;
      read-only access, UI hides the server registration dialog.
    """
    available, reason = check_db_connection()
    if available:
        key_valid = (
            bool(ADMIN_API_KEY)
            and x_admin_key is not None
            and secrets.compare_digest(x_admin_key, ADMIN_API_KEY)
        )
        role = "vippet_server" if key_valid else "vippet_user"
        return JSONResponse(
            content={"available": True, "message": reason, "role": role},
            status_code=200,
        )
    return JSONResponse(
        content={"available": False, "message": reason, "role": None},
        status_code=503,
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
async def add_server(body: schemas.ServerCreate, _: None = Depends(_require_admin)):
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
    _: None = Depends(_require_admin),
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
    uuid: str = PathParam(..., description="UUID of the server to delete"),
    _: None = Depends(_require_admin),
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
