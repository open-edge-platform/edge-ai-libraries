import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from graph import Graph
from internal_types import (
    InternalExecutionConfig,
    InternalOutputMode,
    InternalPipelineDensitySpec,
    InternalPipelinePerformanceSpec,
    InternalDensityTestSpec,
    InternalPerformanceTestSpec,
)
from managers.pipeline_manager import PipelineManager
from managers.tests_manager import TestsManager
from utils import (
    generate_pipeline_graph_id,
    generate_pipeline_description_id,
    slugify_text,
)

router = APIRouter()
logger = logging.getLogger("api.routes.tests")


@router.post(
    "/performance",
    operation_id="run_performance_test",
    status_code=202,
    response_model=schemas.TestJobResponse,
    responses={
        202: {
            "description": "Performance test job created",
            "model": schemas.TestJobResponse,
        },
        400: {
            "description": "Invalid performance test request",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error while starting performance test",
            "model": schemas.MessageResponse,
        },
    },
)
def run_performance_test(body: schemas.PerformanceTestSpec):
    """
    Start an asynchronous performance test job.

    Operation:
        * Validate the performance test request.
        * Create a PerformanceJob with RUNNING state.
        * Spawn a background thread that runs the pipelines using
          a GStreamer-based runner.
        * Return the job identifier so the caller can poll status endpoints.

    Request body:
        body: PerformanceTestSpec
            * pipeline_performance_specs – list of pipelines and number of
              streams per pipeline. Each pipeline can be specified as:
              - variant reference: {"source": "variant", "pipeline_id": "...", "variant_id": "..."}
              - inline graph: {"source": "graph", "pipeline_graph": {...}}
            * execution_config – configuration for output mode and runtime limits:
              - output_mode: disabled (default), file, or live_stream
              - max_runtime: maximum runtime in seconds (0 = run until EOS)

    Returns:
        202 Accepted:
            TestJobResponse with job_id of the created performance job.
        400 Bad Request:
            MessageResponse if the request is invalid, for example:
            * pipeline_performance_specs is empty,
            * duplicate pipeline_ids in request,
            * all stream counts are zero,
            * referenced variant does not exist,
            * output_mode=file combined with max_runtime > 0.
        500 Internal Server Error:
            MessageResponse if an unexpected error occurs when creating the
            job or starting the background thread.

    Success conditions:
        * At least one stream is requested across all pipelines.
        * All referenced variants exist.
        * No duplicate pipeline_ids in request.
        * TestsManager.test_performance() successfully enqueues the job.

    Failure conditions (high level):
        * Validation or configuration error → 400.
        * Any unhandled exception in job creation → 500.

    Request example (variant reference):
        .. code-block:: json

            {
              "pipeline_performance_specs": [
                {
                  "pipeline": {
                    "source": "variant",
                    "pipeline_id": "pipeline-a3f5d9e1",
                    "variant_id": "variant-abc123"
                  },
                  "streams": 8
                }
              ],
              "execution_config": {
                "output_mode": "disabled",
                "max_runtime": 0
              }
            }

    Request example (inline graph):
        .. code-block:: json

            {
              "pipeline_performance_specs": [
                {
                  "pipeline": {
                    "source": "graph",
                    "pipeline_graph": {
                      "nodes": [...],
                      "edges": [...]
                    }
                  },
                  "streams": 4
                }
              ],
              "execution_config": {
                "output_mode": "disabled",
                "max_runtime": 0
              }
            }

    Successful response example (202):
        .. code-block:: json

            {
              "job_id": "job123"
            }

    Error response example (400, invalid request):
        .. code-block:: json

            {
              "message": "At least one stream must be specified to run the pipeline."
            }
    """
    try:
        # Convert and validate API types to internal types
        internal_spec = _convert_performance_test_spec(body)

        job_id = TestsManager().test_performance(internal_spec)
        return JSONResponse(
            content=schemas.TestJobResponse(job_id=job_id).model_dump(),
            status_code=202,
        )
    except ValueError as e:
        logger.error("Invalid performance test request: %s", e)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=400,
        )
    except Exception as e:
        logger.error("Unexpected error while starting performance test", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error while starting performance test: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/density",
    operation_id="run_density_test",
    status_code=202,
    response_model=schemas.TestJobResponse,
    responses={
        202: {
            "description": "Density test job created",
            "model": schemas.TestJobResponse,
        },
        400: {
            "description": "Invalid density test request",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error while starting density test",
            "model": schemas.MessageResponse,
        },
    },
)
def run_density_test(body: schemas.DensityTestSpec):
    """
    Start an asynchronous density test job.

    Operation:
        * Validate the density test request.
        * Use requested fps_floor and per‑pipeline stream_rate ratios.
        * Create a DensityJob with RUNNING state.
        * Spawn a background thread that runs a Benchmark to determine the
          maximum number of streams that still meets fps_floor.
        * Return the job identifier so the caller can poll status endpoints.

    Request body:
        body: DensityTestSpec
            * fps_floor – minimum acceptable FPS per stream.
            * pipeline_density_specs – list of pipelines with stream_rate
              percentages that must sum to 100. Each pipeline can be specified as:
              - variant reference: {"source": "variant", "pipeline_id": "...", "variant_id": "..."}
              - inline graph: {"source": "graph", "pipeline_graph": {...}}
            * execution_config – configuration for output mode and runtime limits:
              - output_mode: disabled (default) or file (live_stream not supported)
              - max_runtime: maximum runtime in seconds (0 = run until EOS)

    Returns:
        202 Accepted:
            TestJobResponse with job_id of the created density job.
        400 Bad Request:
            MessageResponse when:
            * pipeline_density_specs is empty,
            * duplicate pipeline_ids in request,
            * pipeline_density_specs.stream_rate values do not sum to 100,
            * referenced variant does not exist,
            * output_mode is live_stream (not supported for density tests),
            * output_mode=file combined with max_runtime > 0,
            * other validation errors raised by Benchmark or TestsManager.
        500 Internal Server Error:
            MessageResponse for unexpected errors when creating or starting
            the job.

    Success conditions:
        * pipeline_density_specs is not empty.
        * All referenced variants exist.
        * No duplicate pipeline_ids in request.
        * stream_rate ratios sum to 100%.
        * DensityTestSpec is valid and Benchmark.run() can be started in a
          background thread.

    Failure conditions:
        * Validation errors → 400.
        * Any other unhandled exception → 500.

    Request example (variant reference):
        .. code-block:: json

            {
              "fps_floor": 30,
              "pipeline_density_specs": [
                {
                  "pipeline": {
                    "source": "variant",
                    "pipeline_id": "pipeline-a3f5d9e1",
                    "variant_id": "variant-abc123"
                  },
                  "stream_rate": 50
                },
                {
                  "pipeline": {
                    "source": "variant",
                    "pipeline_id": "pipeline-b7c2e114",
                    "variant_id": "variant-def456"
                  },
                  "stream_rate": 50
                }
              ],
              "execution_config": {
                "output_mode": "disabled",
                "max_runtime": 0
              }
            }

    Request example (inline graph):
        .. code-block:: json

            {
              "fps_floor": 30,
              "pipeline_density_specs": [
                {
                  "pipeline": {
                    "source": "graph",
                    "pipeline_graph": {
                      "nodes": [...],
                      "edges": [...]
                    }
                  },
                  "stream_rate": 100
                }
              ],
              "execution_config": {
                "output_mode": "disabled",
                "max_runtime": 0
              }
            }

    Successful response example (202):
        .. code-block:: json

            {
              "job_id": "job456"
            }

    Error response example (400, bad ratios):
        .. code-block:: json

            {
              "message": "Pipeline stream_rate ratios must sum to 100%, got 110%"
            }
    """
    try:
        # Convert and validate API types to internal types
        internal_spec = _convert_density_test_spec(body)

        job_id = TestsManager().test_density(internal_spec)
        return JSONResponse(
            content=schemas.TestJobResponse(job_id=job_id).model_dump(),
            status_code=202,
        )
    except ValueError as e:
        logger.error("Invalid density test request: %s", e)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=400,
        )
    except Exception as e:
        logger.error("Unexpected error while starting density test", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error while starting density test: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


def _validate_and_get_graph_id(graph_inline: schemas.GraphInline) -> str:
    """
    Validate and return pipeline ID for inline graph.

    If graph_id is provided, validates it:
    - Trims whitespace
    - Checks if empty after trim (raises ValueError)
    - Validates URL-safety using slugify (raises ValueError if different)

    If graph_id is not provided, generates ID from graph content hash.

    Args:
        graph_inline: GraphInline object with optional graph_id.

    Returns:
        Validated graph_id or generated hash-based ID.

    Raises:
        ValueError: If graph_id is empty after trim or contains invalid characters.
    """
    if graph_inline.graph_id is not None:
        # Trim whitespace
        trimmed_id = graph_inline.graph_id.strip()

        # Check if empty after trim
        if not trimmed_id:
            raise ValueError("graph_id cannot be empty or contain only whitespace.")

        # Validate URL-safety using slugify
        slugified_id = slugify_text(trimmed_id, 64)
        if slugified_id != trimmed_id:
            raise ValueError(
                f"graph_id '{trimmed_id}' contains characters that cannot be used in URL. "
                f"Use only lowercase letters, numbers, and dashes. "
                f"Suggested: '{slugified_id}'"
            )

        return trimmed_id
    else:
        # Generate hash-based ID
        return generate_pipeline_graph_id(graph_inline.pipeline_graph.model_dump())


def _validate_and_get_description_id(
    description_source: schemas.PipelineDescriptionSource,
) -> str:
    """
    Validate and return pipeline ID for pipeline description source.

    If description_id is provided, validates it:
    - Trims whitespace
    - Checks if empty after trim (raises ValueError)
    - Validates URL-safety using slugify (raises ValueError if different)

    If description_id is not provided, generates ID from description content hash.

    Args:
        description_source: PipelineDescriptionSource object with optional description_id.

    Returns:
        Validated description_id or generated hash-based ID.

    Raises:
        ValueError: If description_id is empty after trim or contains invalid characters.
    """
    if description_source.description_id is not None:
        # Trim whitespace
        trimmed_id = description_source.description_id.strip()

        # Check if empty after trim
        if not trimmed_id:
            raise ValueError(
                "description_id cannot be empty or contain only whitespace."
            )

        # Validate URL-safety using slugify
        slugified_id = slugify_text(trimmed_id, 64)
        if slugified_id != trimmed_id:
            raise ValueError(
                f"description_id '{trimmed_id}' contains characters that cannot be used in URL. "
                f"Use only lowercase letters, numbers, and dashes. "
                f"Suggested: '{slugified_id}'"
            )

        return trimmed_id
    else:
        # Generate hash-based ID
        return generate_pipeline_description_id(description_source.pipeline_description)


def _convert_output_mode(mode: schemas.OutputMode) -> InternalOutputMode:
    """
    Convert API OutputMode to internal representation.

    Args:
        mode: API OutputMode enum value.

    Returns:
        InternalOutputMode with equivalent value.
    """
    mode_mapping = {
        schemas.OutputMode.DISABLED: InternalOutputMode.DISABLED,
        schemas.OutputMode.FILE: InternalOutputMode.FILE,
        schemas.OutputMode.LIVE_STREAM: InternalOutputMode.LIVE_STREAM,
    }
    return mode_mapping[mode]


def _convert_execution_config(
    config: schemas.ExecutionConfig,
) -> InternalExecutionConfig:
    """
    Convert API ExecutionConfig to internal representation.

    Args:
        config: API ExecutionConfig from request.

    Returns:
        InternalExecutionConfig with converted field values.
    """
    return InternalExecutionConfig(
        output_mode=_convert_output_mode(config.output_mode),
        max_runtime=config.max_runtime,
    )


def _convert_pipeline_density_spec(
    spec: schemas.PipelineDensitySpec,
    pipeline_manager: PipelineManager,
) -> InternalPipelineDensitySpec:
    """
    Convert API PipelineDensitySpec to internal representation.

    Resolves pipeline references to actual pipeline graphs and generates
    appropriate pipeline IDs. Converts PipelineGraph to Graph object.

    For GraphInline with graph_id: validates and uses the provided ID.
    For GraphInline without graph_id: generates hash-based synthetic ID.
    For PipelineDescriptionSource: parses description into graph using
        Graph.from_pipeline_description().

    Args:
        spec: API PipelineDensitySpec from request.
        pipeline_manager: PipelineManager instance to resolve variant references.

    Returns:
        InternalPipelineDensitySpec with resolved pipeline information.

    Raises:
        ValueError: If referenced pipeline or variant does not exist,
            if graph_id/description_id validation fails, or if pipeline
            description parsing fails.
    """
    match spec.pipeline:
        case schemas.VariantReference(pipeline_id=pid, variant_id=vid):
            # Resolve variant reference - this raises ValueError if not found
            pipeline = pipeline_manager.get_pipeline_by_id(pid)
            variant = pipeline_manager.get_variant_by_ids(pid, vid)

            # Convert PipelineGraph to Graph
            graph = Graph.from_dict(variant.pipeline_graph.model_dump())

            return InternalPipelineDensitySpec(
                pipeline_id=f"/pipelines/{pid}/variants/{vid}",
                pipeline_name=pipeline.name,
                pipeline_graph=graph,
                stream_rate=spec.stream_rate,
            )
        case schemas.GraphInline() as graph_inline:
            # Validate and get pipeline ID
            pipeline_id = _validate_and_get_graph_id(graph_inline)

            # Convert PipelineGraph to Graph
            graph = Graph.from_dict(graph_inline.pipeline_graph.model_dump())

            return InternalPipelineDensitySpec(
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_id,
                pipeline_graph=graph,
                stream_rate=spec.stream_rate,
            )
        case schemas.PipelineDescriptionSource() as description_source:
            # Validate and get pipeline ID
            pipeline_id = _validate_and_get_description_id(description_source)

            # Parse pipeline description into Graph
            graph = Graph.from_pipeline_description(
                description_source.pipeline_description
            )

            return InternalPipelineDensitySpec(
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_id,
                pipeline_graph=graph,
                stream_rate=spec.stream_rate,
            )
        case _:
            raise ValueError("Invalid pipeline source type in density spec")


def _convert_pipeline_performance_spec(
    spec: schemas.PipelinePerformanceSpec,
    pipeline_manager: PipelineManager,
) -> InternalPipelinePerformanceSpec:
    """
    Convert API PipelinePerformanceSpec to internal representation.

    Resolves pipeline references to actual pipeline graphs and generates
    appropriate pipeline IDs. Converts PipelineGraph to Graph object.

    For GraphInline with graph_id: validates and uses the provided ID.
    For GraphInline without graph_id: generates hash-based synthetic ID.
    For PipelineDescriptionSource: parses description into graph using
        Graph.from_pipeline_description().

    Args:
        spec: API PipelinePerformanceSpec from request.
        pipeline_manager: PipelineManager instance to resolve variant references.

    Returns:
        InternalPipelinePerformanceSpec with resolved pipeline information.

    Raises:
        ValueError: If referenced pipeline or variant does not exist,
            if graph_id/description_id validation fails, or if pipeline
            description parsing fails.
    """
    match spec.pipeline:
        case schemas.VariantReference(pipeline_id=pid, variant_id=vid):
            # Resolve variant reference - this raises ValueError if not found
            pipeline = pipeline_manager.get_pipeline_by_id(pid)
            variant = pipeline_manager.get_variant_by_ids(pid, vid)

            # Convert PipelineGraph to Graph
            graph = Graph.from_dict(variant.pipeline_graph.model_dump())

            return InternalPipelinePerformanceSpec(
                pipeline_id=f"/pipelines/{pid}/variants/{vid}",
                pipeline_name=pipeline.name,
                pipeline_graph=graph,
                streams=spec.streams,
            )
        case schemas.GraphInline() as graph_inline:
            # Validate and get pipeline ID
            pipeline_id = _validate_and_get_graph_id(graph_inline)

            # Convert PipelineGraph to Graph
            graph = Graph.from_dict(graph_inline.pipeline_graph.model_dump())

            return InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_id,
                pipeline_graph=graph,
                streams=spec.streams,
            )
        case schemas.PipelineDescriptionSource() as description_source:
            # Validate and get pipeline ID
            pipeline_id = _validate_and_get_description_id(description_source)

            # Parse pipeline description into Graph
            graph = Graph.from_pipeline_description(
                description_source.pipeline_description
            )

            return InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_id,
                pipeline_graph=graph,
                streams=spec.streams,
            )
        case _:
            raise ValueError("Invalid pipeline source type in performance spec")


def _convert_density_test_spec(
    spec: schemas.DensityTestSpec,
) -> InternalDensityTestSpec:
    """
    Convert and validate API DensityTestSpec to internal representation.

    Performs the following validations:
    - pipeline_density_specs list cannot be empty
    - All pipeline_ids must be unique (no duplicates after resolution)

    Args:
        spec: API DensityTestSpec from request.

    Returns:
        InternalDensityTestSpec with resolved pipeline information and
        original request stored as dict.

    Raises:
        ValueError: If validation fails or referenced pipeline/variant does not exist.
    """
    # Validate non-empty list
    if not spec.pipeline_density_specs:
        raise ValueError("pipeline_density_specs cannot be empty")

    # Convert all pipeline specs
    internal_specs: List[InternalPipelineDensitySpec] = []
    seen_pipeline_ids: set[str] = set()

    for pipeline_spec in spec.pipeline_density_specs:
        internal_spec = _convert_pipeline_density_spec(pipeline_spec, PipelineManager())

        # Check for duplicate pipeline_id
        if internal_spec.pipeline_id in seen_pipeline_ids:
            raise ValueError(
                f"Duplicate pipeline_id found: '{internal_spec.pipeline_id}'. "
                "Each pipeline must be unique in the request."
            )
        seen_pipeline_ids.add(internal_spec.pipeline_id)

        internal_specs.append(internal_spec)

    # Serialize original request to dict for storage in job
    original_request_dict = spec.model_dump(mode="json")

    return InternalDensityTestSpec(
        fps_floor=spec.fps_floor,
        pipeline_density_specs=internal_specs,
        execution_config=_convert_execution_config(spec.execution_config),
        original_request=original_request_dict,
    )


def _convert_performance_test_spec(
    spec: schemas.PerformanceTestSpec,
) -> InternalPerformanceTestSpec:
    """
    Convert and validate API PerformanceTestSpec to internal representation.

    Performs the following validations:
    - pipeline_performance_specs list cannot be empty
    - All pipeline_ids must be unique (no duplicates after resolution)

    Args:
        spec: API PerformanceTestSpec from request.

    Returns:
        InternalPerformanceTestSpec with resolved pipeline information and
        original request stored as dict.

    Raises:
        ValueError: If validation fails or referenced pipeline/variant does not exist.
    """
    # Validate non-empty list
    if not spec.pipeline_performance_specs:
        raise ValueError("pipeline_performance_specs cannot be empty")

    # Convert all pipeline specs
    internal_specs: List[InternalPipelinePerformanceSpec] = []
    seen_pipeline_ids: set[str] = set()

    for pipeline_spec in spec.pipeline_performance_specs:
        internal_spec = _convert_pipeline_performance_spec(
            pipeline_spec, PipelineManager()
        )

        # Check for duplicate pipeline_id
        if internal_spec.pipeline_id in seen_pipeline_ids:
            raise ValueError(
                f"Duplicate pipeline_id found: '{internal_spec.pipeline_id}'. "
                "Each pipeline must be unique in the request."
            )
        seen_pipeline_ids.add(internal_spec.pipeline_id)

        internal_specs.append(internal_spec)

    # Serialize original request to dict for storage in job
    original_request_dict = spec.model_dump(mode="json")

    return InternalPerformanceTestSpec(
        pipeline_performance_specs=internal_specs,
        execution_config=_convert_execution_config(spec.execution_config),
        original_request=original_request_dict,
    )
