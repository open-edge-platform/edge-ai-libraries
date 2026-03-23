import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from graph import Graph
from internal_types import (
    InternalDensityJobStatus,
    InternalDensityJobSummary,
    InternalOptimizationJobStatus,
    InternalOptimizationJobSummary,
    InternalPerformanceJobStatus,
    InternalPerformanceJobSummary,
    InternalPipelineStreamSpec,
    InternalValidationJobStatus,
    InternalValidationJobSummary,
)
from managers.optimization_manager import OptimizationManager
from managers.tests_manager import TestsManager
from managers.validation_manager import ValidationManager

router = APIRouter()
logger = logging.getLogger("api.routes.jobs")


def get_test_job_status(job_id: str, job_type: str):
    internal_status = TestsManager().get_job_status(job_id)
    if internal_status is None:
        logger.warning("%s job %s not found", job_type, job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"{job_type} job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    # Convert internal status to API status
    if isinstance(internal_status, InternalPerformanceJobStatus):
        return _performance_job_to_api_status(internal_status)
    elif isinstance(internal_status, InternalDensityJobStatus):
        return _density_job_to_api_status(internal_status)
    logger.error(
        "Unexpected job status type %s for job %s",
        type(internal_status).__name__,
        job_id,
    )
    return JSONResponse(
        content=schemas.MessageResponse(
            message=f"Unexpected job status type for job {job_id}"
        ).model_dump(),
        status_code=500,
    )


def stop_test_job_handler(job_id: str):
    """
    Common handler for stopping test jobs (performance or density).

    This helper function encapsulates the shared logic for stopping test jobs
    and mapping the outcome to appropriate HTTP status codes.

    Parameters
    ----------
    job_id : str
        Identifier of the test job to stop.

    Returns
    -------
    MessageResponse | JSONResponse
        A :class:`MessageResponse` instance (directly for success; wrapped
        in :class:`JSONResponse` for non-200 cases) describing the result
        of the stop attempt.
    """
    success, message = TestsManager().stop_job(job_id)
    response = schemas.MessageResponse(message=message)
    if success:
        return response
    if "not found" in message.lower() or "no active runner found" in message.lower():
        logger.warning("Failed to stop job %s: %s", job_id, message)
        return JSONResponse(
            content=response.model_dump(),
            status_code=404,
        )
    if "not running" in message.lower():
        logger.warning(
            "Job %s stop requested but job is not running: %s", job_id, message
        )
        return JSONResponse(
            content=response.model_dump(),
            status_code=409,
        )
    logger.error("Unexpected error while stopping job %s: %s", job_id, message)
    return JSONResponse(
        content=response.model_dump(),
        status_code=500,
    )


@router.get(
    "/tests/performance/status",
    operation_id="get_performance_statuses",
    summary="List all performance test jobs",
    response_model=list[schemas.PerformanceJobStatus],
)
def get_performance_statuses():
    """
    **List statuses of all performance test jobs.**

    ## Operation

    Reads current state and metrics for every performance test job created via the performance test API.

    ## Parameters

    None

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of PerformanceJobStatus objects |
    | 500  | Unexpected internal error |

    ## Conditions

    ### ✅ Success
    - TestsManager is initialized
    - Zero or more jobs may be present

    ### ❌ Failure
    - Internal errors → 500

    ## Example Response

    ```json
    [
      {
        "id": "job123",
        "start_time": 1715000000000,
        "elapsed_time": 120000,
        "state": "RUNNING",
        "details": [],
        "total_fps": 480.0,
        "per_stream_fps": 30.0,
        "total_streams": 16,
        "streams_per_pipeline": [
          {"id": "pipeline-1", "streams": 8},
          {"id": "pipeline-2", "streams": 8}
        ],
        "video_output_paths": {
          "pipeline-1": ["/outputs/job123-p1-0.mp4"]
        }
      }
    ]
    ```
    """
    internal_statuses = TestsManager().get_job_statuses_by_type(
        InternalPerformanceJobStatus
    )
    return [
        _performance_job_to_api_status(job)
        for job in internal_statuses
        if isinstance(job, InternalPerformanceJobStatus)
    ]


@router.get(
    "/tests/performance/{job_id}/status",
    operation_id="get_performance_job_status",
    summary="Get performance test job status",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.PerformanceJobStatus,
        },
        404: {"description": "Job not found", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def get_performance_job_status(job_id: str):
    """
    **Get detailed status of a single performance test job.**

    ## Operation

    Retrieves current state, timings, FPS metrics, and output paths for a specific performance test job.

    ## Path Parameters

    - `job_id`: Identifier of the performance job to inspect

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | PerformanceJobStatus with current state, timings, FPS and output paths |
    | 404  | Job with given id does not exist |
    | 500  | Unexpected internal error |

    ## Conditions

    ### ✅ Success
    - Job with given id exists in TestsManager

    ### ❌ Failure
    - Unknown job id → 404
    - Unexpected job status type → 500

    ## Examples

    Success (200):
    ```json
    {
      "id": "job123",
      "start_time": 1715000000000,
      "elapsed_time": 60000,
      "state": "COMPLETED",
      "details": ["Pipeline completed successfully"],
      "total_fps": 480.0,
      "per_stream_fps": 30.0,
      "total_streams": 16,
      "streams_per_pipeline": [
        {"id": "pipeline-1", "streams": 8},
        {"id": "pipeline-2", "streams": 8}
      ],
      "video_output_paths": {
        "pipeline-1": ["/outputs/job123-p1-0.mp4"]
      }
    }
    ```

    Error (404):
    ```json
    {
      "message": "Performance job job123 not found"
    }
    ```

    Error (500):
    ```json
    {
      "message": "Unexpected job status type for job job123"
    }
    ```
    """
    return get_test_job_status(job_id, "Performance")


@router.get(
    "/tests/performance/{job_id}",
    operation_id="get_performance_job_summary",
    summary="Get performance test job summary",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.PerformanceJobSummary,
        },
        404: {"description": "Job not found", "model": schemas.MessageResponse},
    },
)
def get_performance_job_summary(job_id: str):
    """
    **Get a short summary of a performance test job.**

    ## Operation

    Retrieves the job id and original PerformanceTestSpec for a specific job.

    ## Path Parameters

    - `job_id`: Identifier of the performance job created earlier

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | PerformanceJobSummary with job id and original request |
    | 404  | Job does not exist |

    ## Conditions

    ### ✅ Success
    - Job exists in TestsManager

    ### ❌ Failure
    - Unknown job id → 404

    ## Example Response

    ```json
    {
      "id": "job123",
      "request": {
        "pipeline_performance_specs": [
          {"id": "pipeline-1", "streams": 8}
        ],
        "video_output": {
          "enabled": false,
          "encoder_device": {"device_name": "GPU", "gpu_id": 0}
        }
      }
    }
    ```
    """
    internal_summary = TestsManager().get_job_summary(job_id)
    if internal_summary is None:
        logger.warning("Performance job summary requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return _test_summary_to_api(internal_summary)


@router.delete(
    "/tests/performance/{job_id}",
    operation_id="stop_performance_test_job",
    summary="Stop a running performance test job",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Performance test job not found",
            "model": schemas.MessageResponse,
        },
        409: {
            "description": "Performance test job not running",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error",
            "model": schemas.MessageResponse,
        },
    },
)
def stop_performance_test_job(job_id: str):
    """
    **Stop a running performance test job.**

    ## Operation

    Requests cancellation of a RUNNING performance test job.

    ## Path Parameters

    - `job_id`: Identifier of the performance test job to stop

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | Job was RUNNING and cancellation was successfully requested |
    | 404  | Job id is unknown or there is no active runner |
    | 409  | Job exists but is not in RUNNING state |
    | 500  | Unexpected error occurs while stopping |

    ## Conditions

    ### ✅ Success
    - Job exists and state == RUNNING
    - TestsManager.stop_job() returns success

    ### ❌ Failure
    - TestsManager.stop_job() returns "not found" / "no active runner" → 404
    - TestsManager.stop_job() returns "not running" → 409
    - Any other error from stop_job() → 500

    ## Examples

    Success (200):
    ```json
    {
      "message": "Job job123 stopped"
    }
    ```

    Conflict (409):
    ```json
    {
      "message": "Job job123 is not running (state: COMPLETED)"
    }
    ```
    """
    return stop_test_job_handler(job_id)


@router.get(
    "/tests/density/status",
    operation_id="get_density_statuses",
    summary="List all density test jobs",
    response_model=list[schemas.DensityJobStatus],
)
def get_density_statuses():
    """
    **List statuses of all density test jobs.**

    ## Operation

    Reads current state and metrics for every density test job.

    ## Parameters

    None

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of DensityJobStatus objects |

    ## Conditions

    ### ✅ Success
    - TestsManager is initialized

    ## Example Response

    ```json
    [
      {
        "id": "job456",
        "start_time": 1715000000000,
        "elapsed_time": 45000,
        "state": "RUNNING",
        "details": [],
        "total_fps": null,
        "per_stream_fps": 28.5,
        "total_streams": 32,
        "streams_per_pipeline": [
          {"id": "pipeline-1", "streams": 16},
          {"id": "pipeline-2", "streams": 16}
        ],
        "video_output_paths": {
          "pipeline-1": ["/outputs/job456-p1-0.mp4"]
        }
      }
    ]
    ```
    """
    internal_statuses = TestsManager().get_job_statuses_by_type(
        InternalDensityJobStatus
    )
    return [
        _density_job_to_api_status(job)
        for job in internal_statuses
        if isinstance(job, InternalDensityJobStatus)
    ]


@router.get(
    "/tests/density/{job_id}/status",
    operation_id="get_density_job_status",
    summary="Get density test job status",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.DensityJobStatus,
        },
        404: {"description": "Job not found", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def get_density_job_status(job_id: str):
    """
    **Get detailed status of a single density test job.**

    ## Operation

    Retrieves current state, timings, and FPS metrics for a specific density test job.

    ## Path Parameters

    - `job_id`: Identifier of the density job to inspect

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | DensityJobStatus for the given job |
    | 404  | Job id is unknown |
    | 500  | Unexpected internal error |

    ## Conditions

    ### ✅ Success
    - Job with given id exists in TestsManager

    ### ❌ Failure
    - Unknown job id → 404
    - Unexpected job status type → 500

    ## Examples

    Error (404):
    ```json
    {
      "message": "Density job job456 not found"
    }
    ```

    Error (500):
    ```json
    {
      "message": "Unexpected job status type for job job456"
    }
    ```
    """
    return get_test_job_status(job_id, "Density")


@router.get(
    "/tests/density/{job_id}",
    operation_id="get_density_job_summary",
    summary="Get density test job summary",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.DensityJobSummary,
        },
        404: {"description": "Job not found", "model": schemas.MessageResponse},
    },
)
def get_density_job_summary(job_id: str):
    """
    **Get a short summary of a density test job.**

    ## Operation

    Retrieves the job id and original DensityTestSpec for a specific job.

    ## Path Parameters

    - `job_id`: Identifier of the density job created earlier

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | DensityJobSummary with job id and original request |
    | 404  | Job does not exist |

    ## Conditions

    ### ✅ Success
    - Job exists in TestsManager

    ### ❌ Failure
    - Unknown job id → 404

    ## Example Response

    ```json
    {
      "id": "job456",
      "request": {
        "fps_floor": 30,
        "pipeline_density_specs": [
          {"id": "pipeline-1", "stream_rate": 50},
          {"id": "pipeline-2", "stream_rate": 50}
        ],
        "video_output": {
          "enabled": false,
          "encoder_device": {"device_name": "GPU", "gpu_id": 0}
        }
      }
    }
    ```
    """
    internal_summary = TestsManager().get_job_summary(job_id)
    if internal_summary is None:
        logger.warning("Density job summary requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return _test_summary_to_api(internal_summary)


@router.delete(
    "/tests/density/{job_id}",
    operation_id="stop_density_test_job",
    summary="Stop a running density test job",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Density test job not found",
            "model": schemas.MessageResponse,
        },
        409: {
            "description": "Density test job not running",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error",
            "model": schemas.MessageResponse,
        },
    },
)
def stop_density_test_job(job_id: str):
    """
    **Stop a running density test job.**

    ## Operation

    Requests cancellation of a RUNNING density test job.

    ## Path Parameters

    - `job_id`: Identifier of the density test job to stop

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | Job was RUNNING and cancellation was successfully requested |
    | 404  | Job id is unknown or there is no active runner |
    | 409  | Job exists but is not RUNNING |
    | 500  | Unexpected error |

    ## Conditions

    Same status mapping logic as stop_performance_test_job.
    """
    return stop_test_job_handler(job_id)


@router.get(
    "/optimization/status",
    operation_id="get_optimization_statuses",
    summary="List all optimization jobs",
    response_model=list[schemas.OptimizationJobStatus],
)
def get_optimization_statuses():
    """
    **List statuses of all optimization jobs.**

    ## Operation

    Reads current state and results for every optimization job.

    ## Parameters

    None

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of OptimizationJobStatus objects |

    ## Conditions

    ### ✅ Success
    - OptimizationManager is initialized

    ## Example Response

    ```json
    [
      {
        "id": "opt789",
        "type": "OPTIMIZE",
        "start_time": 1715000000000,
        "elapsed_time": 20000,
        "state": "RUNNING",
        "details": [],
        "total_fps": null,
        "original_pipeline_graph": {"nodes": [], "edges": []},
        "optimized_pipeline_graph": null,
        "original_pipeline_description": "videotestsrc ! fakesink",
        "optimized_pipeline_description": null
      }
    ]
    ```
    """
    internal_statuses = OptimizationManager().get_all_job_statuses()
    return [_optimization_job_to_api_status(job) for job in internal_statuses]


@router.get(
    "/optimization/{job_id}",
    operation_id="get_optimization_job_summary",
    summary="Get optimization job summary",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.OptimizationJobSummary,
        },
        404: {
            "description": "Optimization job not found",
            "model": schemas.MessageResponse,
        },
    },
)
def get_optimization_job_summary(job_id: str):
    """
    **Get a short summary of an optimization job.**

    ## Operation

    Retrieves the job id and original optimization request for a specific job.

    ## Path Parameters

    - `job_id`: Identifier of the optimization job created earlier

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | OptimizationJobSummary with job id and original request |
    | 404  | Job does not exist |

    ## Conditions

    ### ✅ Success
    - Job exists in OptimizationManager

    ### ❌ Failure
    - Unknown job id → 404

    ## Error Example

    ```json
    {
      "message": "Optimization job opt789 not found"
    }
    ```
    """
    internal_summary = OptimizationManager().get_job_summary(job_id)
    if internal_summary is None:
        logger.warning("Optimization job summary requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Optimization job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return _optimization_summary_to_api(internal_summary)


@router.get(
    "/optimization/{job_id}/status",
    operation_id="get_optimization_job_status",
    summary="Get optimization job status",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.OptimizationJobStatus,
        },
        404: {
            "description": "Optimization job not found",
            "model": schemas.MessageResponse,
        },
    },
)
def get_optimization_job_status(job_id: str):
    """
    **Get detailed status of a single optimization job.**

    ## Operation

    Retrieves timings, state, graphs, descriptions and total_fps (for OPTIMIZE) for a specific optimization job.

    ## Path Parameters

    - `job_id`: Identifier of the optimization job to inspect

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | OptimizationJobStatus containing timings, state, graphs and descriptions |
    | 404  | Job does not exist |

    ## Conditions

    ### ✅ Success
    - Job with given id exists in OptimizationManager

    ### ❌ Failure
    - Unknown job id → 404
    """
    internal_status = OptimizationManager().get_job_status(job_id)
    if internal_status is None:
        logger.warning("Optimization job status requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Optimization job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return _optimization_job_to_api_status(internal_status)


@router.get(
    "/validation/status",
    operation_id="get_validation_statuses",
    summary="List all validation jobs",
    response_model=list[schemas.ValidationJobStatus],
)
def get_validation_statuses():
    """
    **List statuses of all validation jobs.**

    ## Operation

    Reads current state and validation result for all validation jobs.

    ## Parameters

    None

    ## Response Format

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of ValidationJobStatus objects |

    ## Conditions

    ### ✅ Success
    - ValidationManager is initialized

    ## Example Response

    ```json
    [
      {
        "id": "val001",
        "start_time": 1715000000000,
        "elapsed_time": 10000,
        "state": "RUNNING",
        "details": [],
        "is_valid": null
      }
    ]
    ```
    """
    internal_statuses = ValidationManager().get_all_job_statuses()
    return [_validation_job_to_api_status(s) for s in internal_statuses]


@router.get(
    "/validation/{job_id}",
    operation_id="get_validation_job_summary",
    summary="Get validation job summary",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.ValidationJobSummary,
        },
        404: {
            "description": "Validation job not found",
            "model": schemas.MessageResponse,
        },
    },
)
def get_validation_job_summary(job_id: str):
    """
    **Get a short summary of a validation job.**

    ## Operation

    Retrieves the job id and original validation request for a specific job.

    ## Path Parameters

    - `job_id`: Identifier of the validation job created earlier

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | ValidationJobSummary with job id and original request |
    | 404  | Job does not exist |

    ## Conditions

    ### ✅ Success
    - Job exists in ValidationManager

    ### ❌ Failure
    - Unknown job id → 404
    """
    internal_summary = ValidationManager().get_job_summary(job_id)
    if internal_summary is None:
        logger.warning("Validation job summary requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Validation job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return _validation_summary_to_api(internal_summary)


@router.get(
    "/validation/{job_id}/status",
    operation_id="get_validation_job_status",
    summary="Get validation job status",
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.ValidationJobStatus,
        },
        404: {
            "description": "Validation job not found",
            "model": schemas.MessageResponse,
        },
    },
)
def get_validation_job_status(job_id: str):
    """
    **Get detailed status of a single validation job.**

    ## Operation

    Retrieves timings, state, is_valid flag and details list for a specific validation job.

    ## Path Parameters

    - `job_id`: Identifier of the validation job to inspect

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | ValidationJobStatus with timings, state, is_valid flag and details |
    | 404  | Job does not exist |

    ## Conditions

    ### ✅ Success
    - Job with given id exists in ValidationManager

    ### ❌ Failure
    - Unknown job id → 404

    ## Error Example

    ```json
    {
      "message": "Validation job val001 not found"
    }
    ```
    """
    internal_status = ValidationManager().get_job_status(job_id)
    if internal_status is None:
        logger.warning("Validation job status requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Validation job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return _validation_job_to_api_status(internal_status)


# ------------------------------------------------------------------
# Conversion helpers: internal types -> API types
#
# These functions convert internal types returned by managers into
# API schema types for HTTP responses. Managers work exclusively
# with internal types; conversion to API types happens only here
# in the route layer.
# ------------------------------------------------------------------


def _graph_to_api(graph: Graph) -> schemas.PipelineGraph:
    """
    Convert internal Graph to API PipelineGraph.

    Args:
        graph: Internal Graph object.

    Returns:
        PipelineGraph ready for API response.
    """
    return schemas.PipelineGraph.model_validate(graph.to_dict())


def _convert_streams_per_pipeline(
    internal_specs: list[InternalPipelineStreamSpec] | None,
) -> list[schemas.PipelineStreamSpec] | None:
    """
    Convert internal stream specs to API PipelineStreamSpec for response.

    Args:
        internal_specs: List of InternalPipelineStreamSpec or None.

    Returns:
        List of API PipelineStreamSpec or None if input is None.
    """
    if internal_specs is None:
        return None
    return [
        schemas.PipelineStreamSpec(id=spec.id, streams=spec.streams)
        for spec in internal_specs
    ]


def _performance_job_to_api_status(
    job: InternalPerformanceJobStatus,
) -> schemas.PerformanceJobStatus:
    """
    Convert InternalPerformanceJobStatus to API PerformanceJobStatus.

    Converts internal state enum to API state enum and
    InternalPipelineStreamSpec to API PipelineStreamSpec.

    Args:
        job: Internal performance job status.

    Returns:
        PerformanceJobStatus ready for API response.
    """
    current_time = int(time.time() * 1000)
    elapsed_time = (
        job.end_time - job.start_time if job.end_time else current_time - job.start_time
    )
    return schemas.PerformanceJobStatus(
        id=job.id,
        start_time=job.start_time,
        elapsed_time=elapsed_time,
        state=schemas.TestJobState(job.state.value),
        details=list(job.details),
        total_fps=job.total_fps,
        per_stream_fps=job.per_stream_fps,
        total_streams=job.total_streams,
        streams_per_pipeline=_convert_streams_per_pipeline(job.streams_per_pipeline),
        video_output_paths=job.video_output_paths,
        live_stream_urls=job.live_stream_urls,
    )


def _density_job_to_api_status(
    job: InternalDensityJobStatus,
) -> schemas.DensityJobStatus:
    """
    Convert InternalDensityJobStatus to API DensityJobStatus.

    Converts internal state enum to API state enum and
    InternalPipelineStreamSpec to API PipelineStreamSpec.

    Note: DensityJobStatus does not include live_stream_urls because
    density tests do not support live-streaming output mode.

    Args:
        job: Internal density job status.

    Returns:
        DensityJobStatus ready for API response.
    """
    current_time = int(time.time() * 1000)
    elapsed_time = (
        job.end_time - job.start_time if job.end_time else current_time - job.start_time
    )
    return schemas.DensityJobStatus(
        id=job.id,
        start_time=job.start_time,
        elapsed_time=elapsed_time,
        state=schemas.TestJobState(job.state.value),
        details=list(job.details),
        total_fps=job.total_fps,
        per_stream_fps=job.per_stream_fps,
        total_streams=job.total_streams,
        streams_per_pipeline=_convert_streams_per_pipeline(job.streams_per_pipeline),
        video_output_paths=job.video_output_paths,
    )


def _test_summary_to_api(
    summary: InternalPerformanceJobSummary | InternalDensityJobSummary,
) -> schemas.PerformanceJobSummary | schemas.DensityJobSummary:
    """
    Convert internal test job summary to API summary type.

    Args:
        summary: Internal performance or density job summary.

    Returns:
        PerformanceJobSummary or DensityJobSummary ready for API response.
    """
    if isinstance(summary, InternalPerformanceJobSummary):
        return schemas.PerformanceJobSummary(
            id=summary.id,
            request=summary.request,
        )
    else:
        return schemas.DensityJobSummary(
            id=summary.id,
            request=summary.request,
        )


def _optimization_job_to_api_status(
    job: InternalOptimizationJobStatus,
) -> schemas.OptimizationJobStatus:
    """
    Convert InternalOptimizationJobStatus to API OptimizationJobStatus.

    Converts internal Graph objects to API PipelineGraph, and internal
    state/type enums to API enums.

    Args:
        job: Internal optimization job status.

    Returns:
        OptimizationJobStatus ready for API response.
    """
    current_time = int(time.time() * 1000)
    elapsed_time = (
        job.end_time - job.start_time if job.end_time else current_time - job.start_time
    )
    return schemas.OptimizationJobStatus(
        id=job.id,
        type=schemas.OptimizationType(job.request.type.value),
        start_time=job.start_time,
        elapsed_time=elapsed_time,
        state=schemas.OptimizationJobState(job.state.value),
        details=list(job.details),
        total_fps=job.total_fps,
        original_pipeline_graph=_graph_to_api(job.original_pipeline_graph),
        original_pipeline_graph_simple=_graph_to_api(
            job.original_pipeline_graph_simple
        ),
        optimized_pipeline_graph=(
            _graph_to_api(job.optimized_pipeline_graph)
            if job.optimized_pipeline_graph
            else None
        ),
        optimized_pipeline_graph_simple=(
            _graph_to_api(job.optimized_pipeline_graph_simple)
            if job.optimized_pipeline_graph_simple
            else None
        ),
        original_pipeline_description=job.original_pipeline_description,
        optimized_pipeline_description=job.optimized_pipeline_description,
    )


def _optimization_summary_to_api(
    summary: InternalOptimizationJobSummary,
) -> schemas.OptimizationJobSummary:
    """
    Convert InternalOptimizationJobSummary to API OptimizationJobSummary.

    Converts internal optimization request type back to API type.

    Args:
        summary: Internal optimization job summary.

    Returns:
        OptimizationJobSummary ready for API response.
    """
    return schemas.OptimizationJobSummary(
        id=summary.id,
        request=schemas.PipelineRequestOptimize(
            type=schemas.OptimizationType(summary.request.type.value),
            parameters=summary.request.parameters,
        ),
    )


def _validation_job_to_api_status(
    status: InternalValidationJobStatus,
) -> schemas.ValidationJobStatus:
    """
    Convert InternalValidationJobStatus to API ValidationJobStatus.

    Converts internal state enum to API state enum.

    Args:
        status: Internal validation job status.

    Returns:
        ValidationJobStatus ready for API response.
    """
    return schemas.ValidationJobStatus(
        id=status.id,
        start_time=status.start_time,
        elapsed_time=status.elapsed_time,
        state=schemas.ValidationJobState(status.state.value),
        details=list(status.details),
        is_valid=status.is_valid,
    )


def _validation_summary_to_api(
    summary: InternalValidationJobSummary,
) -> schemas.ValidationJobSummary:
    """
    Convert InternalValidationJobSummary to API ValidationJobSummary.

    Converts internal Graph back to API PipelineGraph for the request field.

    Args:
        summary: Internal validation job summary.

    Returns:
        ValidationJobSummary ready for API response.
    """
    return schemas.ValidationJobSummary(
        id=summary.id,
        request=schemas.PipelineValidation(
            pipeline_graph=schemas.PipelineGraph.model_validate(
                summary.request.pipeline_graph.to_dict()
            ),
            parameters=summary.request.parameters,
        ),
    )
