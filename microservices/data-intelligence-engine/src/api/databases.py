# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List

from core.manager import registry
from databasehub import repository as database_repository
from databasehub.manager import BACKENDS, database_manager
from schemas import (
    BackendOption,
    DatabaseCheck,
    DatabaseIn,
    DatabaseOut,
    DatabaseUpdate,
)
from fastapi import APIRouter, HTTPException, status

DATABASE_API_PREFIX = "/v1/databases"

router = APIRouter(prefix=DATABASE_API_PREFIX, tags=["databases"])


def _users_of(database_id: str) -> List[str]:
    """Human-readable labels of the sources that use this database."""
    used = []
    for library in registry.list():
        default_content = getattr(library, "default_content_source_id", "")
        for source in library.sources.values():
            if source.database_id != database_id:
                continue
            if source.source_id == default_content:
                used.append(f"{library.name} (content)")
            else:
                used.append(f"{library.name}/sources/{source.name or source.source_id}")
    return used


def _out(registration) -> DatabaseOut:
    redacted = registration.redacted()
    return DatabaseOut(
        id=registration.database_id,
        type=registration.database_type,
        backend=registration.backend,
        options=redacted["options"],
        description=registration.description,
        in_use_by=_users_of(registration.database_id),
    )


def _save() -> None:
    database_repository.save(database_manager)


@router.get("", response_model=List[DatabaseOut])
async def list_databases():
    return [_out(item) for item in database_manager.list_databases()]


@router.get("/backends", response_model=List[BackendOption])
async def list_backends():
    """List registrable backends per database type."""
    by_type: dict = {}
    for database_type, backend in BACKENDS:
        by_type.setdefault(database_type, []).append(backend)
    return [
        BackendOption(
            database_type=database_type,
            backends=sorted(backends),
        )
        for database_type, backends in sorted(by_type.items())
    ]


@router.get("/{database_id}", response_model=DatabaseOut)
async def get_database(database_id: str):
    registration = database_manager.get(database_id)
    if registration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database '{database_id}' is not registered",
        )
    return _out(registration)


@router.post("", response_model=DatabaseOut, status_code=status.HTTP_201_CREATED)
async def register_database(body: DatabaseIn):
    try:
        registration = database_manager.register(
            body.id,
            database_type=body.type,
            backend=body.backend,
            options=body.options,
            description=body.description,
        )
    except ValueError as error:
        code = (
            status.HTTP_409_CONFLICT
            if "already exists" in str(error)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(error))
    _save()
    return _out(registration)


@router.patch("/{database_id}", response_model=DatabaseOut)
async def update_database(database_id: str, body: DatabaseUpdate):
    """Repoint a database, closing its current connection; the type cannot change."""
    try:
        registration = database_manager.update(
            database_id,
            backend=body.backend,
            options=body.options,
            description=body.description,
        )
    except ValueError as error:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not registered" in str(error)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(error))
    _save()
    return _out(registration)


@router.delete("/{database_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_database(database_id: str):
    """Remove a database registration; 409 if any source still uses it."""
    if database_manager.get(database_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database '{database_id}' is not registered",
        )
    used_by = _users_of(database_id)
    if used_by:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Database '{database_id}' is still in use by: "
                + ", ".join(used_by)
                + ". Remove or repoint them first."
            ),
        )
    database_manager.remove(database_id)
    _save()


@router.post("/{database_id}/check", response_model=DatabaseCheck)
async def check_database(database_id: str):
    """Check connectivity; returns 200 with `reachable` set either way."""
    if database_manager.get(database_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database '{database_id}' is not registered",
        )
    reachable, error = database_manager.check(database_id)
    return DatabaseCheck(
        database_id=database_id, reachable=reachable, error=error or None
    )
