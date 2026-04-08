"""API routes."""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_comparison_engine
from app.api.models import (
    HealthResponse,
    InventoryValidationRequest,
    InventoryValidationResponse,
    OrderValidationRequest,
    OrderValidationResponse,
    SemanticMatchRequest,
    SemanticMatchResponse,
)
from app.core.config import settings
from app.core.metrics import api_requests_total, request_duration_seconds
from app.services.comparison_engine import ComparisonEngine
from app.services.vlm.factory import VLMBackendFactory

logger = logging.getLogger(__name__)

router = APIRouter()

# Service start time for uptime calculation
_start_time = time.time()


@router.post(
    "/compare/order",
    response_model=OrderValidationResponse,
    summary="Validate order",
    description="Compare expected items vs detected items and identify missing/extra/quantity mismatches",
)
async def validate_order(
    request: OrderValidationRequest,
    engine: Annotated[ComparisonEngine, Depends(get_comparison_engine)],
):
    """Validate order by comparing expected vs detected items."""
    start_time = time.time()
    
    try:
        logger.info(f"Order validation request: {len(request.expected_items)} expected items")
        
        options = request.options or {}
        
        result = await engine.validate_order(
            expected_items=[item.model_dump() for item in request.expected_items],
            detected_items=[item.model_dump() for item in request.detected_items],
            use_semantic=options.use_semantic if hasattr(options, "use_semantic") else True,
            exact_match_first=options.exact_match_first if hasattr(options, "exact_match_first") else True,
        )
        
        # Update metrics
        duration = time.time() - start_time
        request_duration_seconds.labels(endpoint="/compare/order", method="POST").observe(duration)
        api_requests_total.labels(endpoint="/compare/order", method="POST", status="200").inc()
        
        return result
    
    except Exception as e:
        logger.error(f"Order validation failed: {e}", exc_info=True)
        api_requests_total.labels(endpoint="/compare/order", method="POST", status="500").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Order validation failed: {str(e)}",
        )


@router.post(
    "/compare/inventory",
    response_model=InventoryValidationResponse,
    summary="Validate inventory",
    description="Check if items exist in inventory using exact or semantic matching",
)
async def validate_inventory(
    request: InventoryValidationRequest,
    engine: Annotated[ComparisonEngine, Depends(get_comparison_engine)],
):
    """Validate if items exist in inventory."""
    start_time = time.time()
    
    try:
        logger.info(f"Inventory validation request: {len(request.items)} items")
        
        options = request.options or {}
        
        result = await engine.validate_inventory(
            items=request.items,
            inventory=request.inventory,
            use_semantic=options.use_semantic if hasattr(options, "use_semantic") else True,
        )
        
        # Update metrics
        duration = time.time() - start_time
        request_duration_seconds.labels(endpoint="/compare/inventory", method="POST").observe(duration)
        api_requests_total.labels(endpoint="/compare/inventory", method="POST", status="200").inc()
        
        return result
    
    except Exception as e:
        logger.error(f"Inventory validation failed: {e}", exc_info=True)
        api_requests_total.labels(endpoint="/compare/inventory", method="POST", status="500").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inventory validation failed: {str(e)}",
        )


@router.post(
    "/compare/semantic",
    response_model=SemanticMatchResponse,
    summary="Semantic match",
    description="Perform generic semantic comparison between two text strings",
)
async def semantic_match(
    request: SemanticMatchRequest,
    engine: Annotated[ComparisonEngine, Depends(get_comparison_engine)],
):
    """Perform semantic matching between two texts."""
    start_time = time.time()
    
    try:
        logger.info(f"Semantic match request: '{request.text1}' vs '{request.text2}'")
        
        result = await engine.semantic_match(
            text1=request.text1,
            text2=request.text2,
            context=request.context,
        )
        
        # Update metrics
        duration = time.time() - start_time
        request_duration_seconds.labels(endpoint="/compare/semantic", method="POST").observe(duration)
        api_requests_total.labels(endpoint="/compare/semantic", method="POST", status="200").inc()
        
        return result
    
    except Exception as e:
        logger.error(f"Semantic match failed: {e}", exc_info=True)
        api_requests_total.labels(endpoint="/compare/semantic", method="POST", status="500").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic match failed: {str(e)}",
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check service health and VLM backend status",
)
async def health_check():
    """Health check endpoint."""
    try:
        vlm_backend = VLMBackendFactory.create(settings.vlm_backend)
        vlm_status = "connected" if vlm_backend.is_available() else "unavailable"
        
        api_requests_total.labels(endpoint="/health", method="GET", status="200").inc()
        
        return HealthResponse(
            status="healthy",
            service=settings.service_name,
            version=settings.service_version,
            vlm_backend=settings.vlm_backend,
            vlm_status=vlm_status,
            uptime_seconds=round(time.time() - _start_time, 2),
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        api_requests_total.labels(endpoint="/health", method="GET", status="500").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )
