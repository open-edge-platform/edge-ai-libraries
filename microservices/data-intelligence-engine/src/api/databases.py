# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Database connection management.

The engine connects to nothing until something registers a database here. That
used to be an environment decision made at import time, which meant one Milvus
per deployment, a restart to change it, and no way to ask what was configured
or whether it worked. A registration is runtime state now, persisted in the
workspace beside the asset libraries that reference it.

Registering does not dial: the adapter is built on first use, so writing down a
connection whose far end is not up yet succeeds, and `POST /{id}/check` is how
you find out. That is the right way round -- an operator should be able to
configure the engine and the database in either order.

Credentials go out masked (`DatabaseRegistration.redacted`). They are kept, so
a client can GET, edit one field and PATCH the whole object back without
overwriting a password with `***`.
"""

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
    """What would break if this database went away, in human terms.

    Content is not a separate case any more: it lives in a registered source
    like everything else, so the loop below already covers it. All the default
    one earns is a clearer label -- it used to be found through a field beside
    the sources, which missed a content source registered any other way.
    """
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
    """What can be registered, so a caller can offer a choice rather than guess."""
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
    """Repoint a database, closing the connection it currently holds.

    The type is fixed. Sources already reference this id and were created as
    vector or object sources against it; turning one into the other underneath
    them would leave those sources describing something that is not there.
    Delete and re-register to do that deliberately, which the 409 on delete will
    make you confront.
    """
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
    """Forget a database, unless something is still pointing at it.

    Refusing is the point. Deleting one that is in use does not fail loudly at
    delete time -- it fails later, as a pool that cannot sync and an ingest with
    nowhere to put content, a long way from the action that caused it.
    """
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
    """Connect and ask the backend whether it is there.

    200 either way: "this database is unreachable" is the answer to the
    question, not a failure to answer it. Read `reachable`.
    """
    if database_manager.get(database_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database '{database_id}' is not registered",
        )
    reachable, error = database_manager.check(database_id)
    return DatabaseCheck(
        database_id=database_id, reachable=reachable, error=error or None
    )
