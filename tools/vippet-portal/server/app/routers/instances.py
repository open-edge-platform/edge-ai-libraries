"""Registration and health of the aggregated ViPPET instances."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import aggregator, schemas
from ..db import Instance, get_session

router = APIRouter(prefix="/instances", tags=["instances"])


def _to_schema(instance: Instance) -> schemas.Instance:
    return schemas.Instance.model_validate(instance, from_attributes=True)


@router.get("", response_model=list[schemas.InstanceHealth], operation_id="get_instances")
async def get_instances(session: AsyncSession = Depends(get_session)):
    """List every registered instance together with its live reachability."""
    return await aggregator.instance_health(session)


@router.post("", response_model=schemas.Instance, status_code=201, operation_id="add_instance")
async def add_instance(
    payload: schemas.InstanceCreate, session: AsyncSession = Depends(get_session)
):
    existing = await session.scalar(select(Instance).where(Instance.url == payload.url))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Instance with this URL already exists")

    instance = Instance(name=payload.name or payload.url, url=payload.url, notes=payload.notes)
    session.add(instance)
    await session.commit()
    aggregator.invalidate_cache()
    return _to_schema(instance)


@router.patch(
    "/{instance_id}", response_model=schemas.Instance, operation_id="update_instance"
)
async def update_instance(
    instance_id: int,
    payload: schemas.InstanceUpdate,
    session: AsyncSession = Depends(get_session),
):
    instance = await session.get(Instance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    for attribute, value in payload.model_dump(exclude_none=True).items():
        setattr(instance, attribute, value)
    await session.commit()
    aggregator.invalidate_cache()
    return _to_schema(instance)


@router.delete("/{instance_id}", status_code=204, operation_id="delete_instance")
async def delete_instance(instance_id: int, session: AsyncSession = Depends(get_session)):
    instance = await session.get(Instance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    await session.delete(instance)
    await session.commit()
    aggregator.invalidate_cache()
