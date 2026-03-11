"""Internal dataclass types for pipeline test execution.

This module contains internal representations of API request types used by
managers and benchmark components. These types are converted from API schema
types (Pydantic models) in the route layer after validation.

The internal types contain resolved pipeline information (graphs, IDs, names)
rather than references, making them easier to work with in the execution layer.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from graph import Graph


class InternalOutputMode(str, Enum):
    """
    Internal representation of pipeline output mode.

    Values:
        DISABLED: No output generation (default).
        FILE: Save output to file.
        LIVE_STREAM: Stream output live to media server.
    """

    DISABLED = "disabled"
    FILE = "file"
    LIVE_STREAM = "live_stream"


@dataclass
class InternalExecutionConfig:
    """
    Internal representation of execution configuration.

    Attributes:
        output_mode: Mode for pipeline output generation.
        max_runtime: Maximum runtime in seconds (0 = run until EOS).
    """

    output_mode: InternalOutputMode
    max_runtime: float


@dataclass
class InternalPipelineDensitySpec:
    """
    Internal per-pipeline configuration for density tests.

    Contains resolved pipeline information rather than references.

    Attributes:
        pipeline_id: Unique pipeline identifier.
            For VariantReference: "/pipelines/{pid}/variants/{vid}"
            For GraphInline: "__graph-{16-char-hash}"
        pipeline_name: Human-readable pipeline name.
            For VariantReference: pipeline.name from stored pipeline.
            For GraphInline: same as pipeline_id.
        pipeline_graph: Resolved pipeline graph for execution as Graph object.
        stream_rate: Relative share of total streams (percentage).
    """

    pipeline_id: str
    pipeline_name: str
    pipeline_graph: Graph
    stream_rate: int


@dataclass
class InternalPipelinePerformanceSpec:
    """
    Internal per-pipeline configuration for performance tests.

    Contains resolved pipeline information rather than references.

    Attributes:
        pipeline_id: Unique pipeline identifier.
            For VariantReference: "/pipelines/{pid}/variants/{vid}"
            For GraphInline: "__graph-{16-char-hash}"
        pipeline_name: Human-readable pipeline name.
            For VariantReference: pipeline.name from stored pipeline.
            For GraphInline: same as pipeline_id.
        pipeline_graph: Resolved pipeline graph for execution as Graph object.
        streams: Number of parallel streams for this pipeline.
    """

    pipeline_id: str
    pipeline_name: str
    pipeline_graph: Graph
    streams: int


@dataclass
class InternalDensityTestSpec:
    """
    Internal representation of a density test request.

    Contains resolved pipeline information and validated configuration.

    Attributes:
        fps_floor: Minimum acceptable FPS per stream.
        pipeline_density_specs: List of resolved pipeline specs with stream_rate ratios.
        execution_config: Execution configuration for output and runtime.
        original_request: Original API request as serialized dict for summary endpoint.
    """

    fps_floor: int
    pipeline_density_specs: List[InternalPipelineDensitySpec]
    execution_config: InternalExecutionConfig
    original_request: Dict[str, Any]


@dataclass
class InternalPerformanceTestSpec:
    """
    Internal representation of a performance test request.

    Contains resolved pipeline information and validated configuration.

    Attributes:
        pipeline_performance_specs: List of resolved pipeline specs with stream counts.
        execution_config: Execution configuration for output and runtime.
        original_request: Original API request as serialized dict for summary endpoint.
    """

    pipeline_performance_specs: List[InternalPipelinePerformanceSpec]
    execution_config: InternalExecutionConfig
    original_request: Dict[str, Any]
