# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
API response models for type-safe responses and OpenAPI documentation.

Provides Pydantic models for all API responses, ensuring consistent
response structure and automatic OpenAPI schema generation.
"""

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(
        ...,
        description="Health status",
        examples=["healthy", "degraded", "unhealthy"],
    )
    version: str = Field(..., description="Service version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    checks: dict[str, bool] = Field(default_factory=dict, description="Individual health checks")


class DetailedHealthResponse(HealthResponse):
    """Detailed health check response with service statistics."""

    metrics_store: dict[str, Any] = Field(..., description="Metrics store statistics")


class MetricsAcceptedResponse(BaseModel):
    """Response for metrics ingestion endpoints."""

    accepted: int = Field(..., ge=0, description="Number of metrics accepted")
    message: str = Field(..., description="Status message")
    errors: list[str] = Field(default_factory=list, description="Any parsing errors")


class MetricData(BaseModel):
    """Metric data in response format."""

    name: str = Field(..., description="Metric name")
    tags: dict[str, str] = Field(default_factory=dict, description="Metric tags")
    fields: dict[str, Any] = Field(..., description="Metric field values")
    timestamp: int = Field(..., description="Unix timestamp")


class MetricsListResponse(BaseModel):
    """Response containing a list of metrics."""

    metrics: list[MetricData] = Field(..., description="List of metrics")
    count: int = Field(..., ge=0, description="Number of metrics returned")


class MetricsLatestResponse(BaseModel):
    """Response containing latest metrics by name."""

    metrics: dict[str, MetricData] = Field(..., description="Latest metric for each name")


class MetricNamesResponse(BaseModel):
    """Response containing metric names."""

    names: list[str] = Field(..., description="List of metric names")
    count: int = Field(..., ge=0, description="Number of metric names")


class MetricsClearedResponse(BaseModel):
    """Response for metrics deletion."""

    cleared: int = Field(..., ge=0, description="Number of metrics cleared")
    message: str = Field(..., description="Status message")


class ServiceInfoResponse(BaseModel):
    """Service information response."""

    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    description: str = Field(..., description="Service description")
    endpoints: dict[str, dict[str, str]] = Field(..., description="Available endpoints")
