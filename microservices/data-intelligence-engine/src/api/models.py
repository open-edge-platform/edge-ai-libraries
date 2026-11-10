# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List, Union

from inference import models
from schemas import EmbeddingModelOptions, ModelOptions
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/v1/models", tags=["models"])


@router.get("/devices", response_model=List[str])
async def list_devices():
    """Inference devices the engine can run on (OpenVINO's devices + AUTO)."""
    import openvino as ov

    return ov.Core().available_devices + ["AUTO"]


@router.get("", response_model=dict[str, Union[ModelOptions, EmbeddingModelOptions]])
async def list_models():
    """Backend, device and models for embedding, reranker, layout and ASR."""
    return models.all_model_options()


@router.get("/{model_type}", response_model=Union[ModelOptions, EmbeddingModelOptions])
async def list_models_of_type(model_type: str):
    """One type: `embedding`, `reranker`, `layout`, `asr`; `multimodal` aliases media embeddings."""
    try:
        return models.model_options(model_type)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get("/{model_type}/names", response_model=List[str])
async def list_model_names(model_type: str):
    """Names for one type or the `multimodal` compatibility alias."""
    options = await list_models_of_type(model_type)
    return [model["name"] for model in options["models"]]
