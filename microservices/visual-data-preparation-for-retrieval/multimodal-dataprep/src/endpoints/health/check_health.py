# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter
from src.common import settings
from src.common.schema import HealthResponse

router = APIRouter(tags=["Status APIs"])


@router.get(
    "/health",
    summary="Check service health",
    operation_id="getServiceHealth",
    response_model=HealthResponse,
)
async def check_health() -> HealthResponse:
    """Health API endpoint to check whether API Server is reachable and responding."""

    # Basic health status
    health_status = {
        "status": "ok",
        "embedding_device": settings.DEVICE,
    }

    # Report the active vector store backend health (backend-agnostic).
    try:
        from src.core.vectorstores import get_vector_store

        vector_health = get_vector_store().health()
        health_status["vectordb_backend"] = settings.VECTORDB_BACKEND
        health_status["vectordb_status"] = vector_health.get("status", "unknown")
        if vector_health.get("error"):
            health_status["vectordb_error"] = vector_health["error"]
    except Exception as e:
        health_status["vectordb_backend"] = settings.VECTORDB_BACKEND
        health_status["vectordb_status"] = "error"
        health_status["vectordb_error"] = str(e)

    # Report the active storage backend.
    health_status["storage_backend"] = settings.STORAGE_BACKEND

    try:
        from src.core.utils.config_utils import get_config

        detection_config = get_config().get("object_detection", {})
        health_status["detection_model"] = detection_config.get("model_name") or "yolox_s"
        health_status["detection_device"] = (
            detection_config.get("device") or settings.DETECTION_DEVICE or "CPU"
        )
    except Exception:
        health_status["detection_model"] = "yolox_s"
        health_status["detection_device"] = settings.DETECTION_DEVICE or "CPU"

    # Check whether the embedding client is preloaded
    try:
        from src.core.embedding.embedding_helper import _embedding_client

        if _embedding_client is not None:
            health_status["embedding_client_status"] = "preloaded"
            health_status["model_name"] = settings.MULTIMODAL_EMBEDDING_MODEL_NAME
            health_status["embedding_device"] = settings.DEVICE
            health_status["use_openvino"] = settings.USE_OPENVINO
        else:
            health_status["embedding_client_status"] = "not_loaded"

    except Exception as e:
        health_status["embedding_client_status"] = "error"
        health_status["embedding_client_error"] = str(e)

    return HealthResponse.model_validate(health_status)
