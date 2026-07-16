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
        "embedding_mode": settings.EMBEDDING_PROCESSING_MODE,
        "embedding_device": settings.DEVICE,
    }

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

    # If in SDK mode, check if client is preloaded
    if settings.EMBEDDING_PROCESSING_MODE.lower() == "sdk":
        try:
            from src.core.embedding.sdk_embedding_helper import _sdk_client

            if _sdk_client is not None:
                health_status["sdk_client_status"] = "preloaded"
                health_status["model_name"] = settings.MULTIMODAL_EMBEDDING_MODEL_NAME
                health_status["embedding_device"] = settings.DEVICE
                health_status["sdk_use_openvino"] = settings.SDK_USE_OPENVINO
            else:
                health_status["sdk_client_status"] = "not_loaded"

        except Exception as e:
            health_status["sdk_client_status"] = "error"
            health_status["sdk_client_error"] = str(e)

    return HealthResponse.model_validate(health_status)
