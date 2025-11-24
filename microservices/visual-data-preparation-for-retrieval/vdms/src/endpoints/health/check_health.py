# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter
from src.common import settings

router = APIRouter(tags=["Status APIs"])


@router.get("/health", summary="Check the health of the API service")
async def check_health():
    """Health API endpoint to check whether API Server is reachable and responding."""
    
    # Basic health status
    health_status = {"status": "ok", "embedding_mode": settings.EMBEDDING_PROCESSING_MODE}
    
    # If in SDK mode, check if client is preloaded
    if settings.EMBEDDING_PROCESSING_MODE.lower() == "sdk":
        try:
            from src.core.embedding.sdk_embedding_helper import _sdk_client
            
            if _sdk_client is not None:
                health_status["sdk_client_status"] = "preloaded"
                health_status["model_name"] = settings.MULTIMODAL_EMBEDDING_MODEL_NAME
                health_status["processing_device"] = settings.PROCESSING_DEVICE
                health_status["sdk_use_openvino"] = settings.SDK_USE_OPENVINO
            else:
                health_status["sdk_client_status"] = "not_loaded"
                
        except Exception as e:
            health_status["sdk_client_status"] = "error"
            health_status["sdk_client_error"] = str(e)
    
    return health_status
