# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Available embedding, rerank, and layout models.

What the engine can actually run, so a caller (a UI's model pickers, for example)
offers the models that are in the workspace rather than a typed-in name.
See data-intelligence-engine/src/inference/models.py for how they are found and classified.
"""

from typing import List

from inference import models
from schemas import ModelOptions
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/models", tags=["models"])


@router.get("/devices", response_model=List[str])
async def list_devices():
    """Inference devices the engine can run on (OpenVINO's devices + AUTO)."""
    import openvino as ov

    return ov.Core().available_devices + ["AUTO"]


@router.get("", response_model=dict[str, ModelOptions])
async def list_models():
    """Backend, device, and available models for every model capability."""
    return models.all_model_options()


@router.get("/{model_type}", response_model=ModelOptions)
async def list_models_of_type(model_type: str):
    """One kind: `embedding`, `reranker`, or `layout`."""
    try:
        return models.model_options(model_type)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get("/{model_type}/names", response_model=List[str])
async def list_model_names(model_type: str):
    """Just the names, for a plain select."""
    options = await list_models_of_type(model_type)
    return [model["name"] for model in options["models"]]
