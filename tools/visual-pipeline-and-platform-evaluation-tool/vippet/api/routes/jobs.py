import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from managers.optimization_manager import OptimizationManager
from managers.tests_manager import DensityJob, PerformanceJob, TestsManager
from managers.validation_manager import ValidationManager

router = APIRouter()
logger = logging.getLogger("api.routes.jobs")


def get_job_status_or_404(job_id: str, job_type: str):
    status = TestsManager().get_job_status(job_id)
    if status is None:
        logger.warning("%s job %s not found", job_type, job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"{job_type} job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return status


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
    response_model=List[schemas.PerformanceJobStatus],
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
        "total_fps": 480.0,
        "per_stream_fps": 30.0,
        "total_streams": 16,
        "streams_per_pipeline": [
          {"id": "pipeline-1", "streams": 8},
          {"id": "pipeline-2", "streams": 8}
        ],
        "video_output_paths": {
          "pipeline-1": ["/outputs/job123-p1-0.mp4"]
        },
        "error_message": null
      }
    ]
    ```
    """
    return TestsManager().get_job_statuses_by_type(PerformanceJob)


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

    ## Conditions

    ### ✅ Success
    - Job with given id exists in TestsManager

    ### ❌ Failure
    - Unknown job id → 404

    ## Examples

    Success (200):
    ```json
    {
      "id": "job123",
      "start_time": 1715000000000,
      "elapsed_time": 60000,
      "state": "COMPLETED",
      "total_fps": 480.0,
      "per_stream_fps": 30.0,
      "total_streams": 16,
      "streams_per_pipeline": [
        {"id": "pipeline-1", "streams": 8},
        {"id": "pipeline-2", "streams": 8}
      ],
      "video_output_paths": {
        "pipeline-1": ["/outputs/job123-p1-0.mp4"]
      },
      "error_message": null
    }
    ```

    Error (404):
    ```json
    {
      "message": "Performance job job123 not found"
    }
    ```
    """
    return get_job_status_or_404(job_id, "Performance")


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
    summary = TestsManager().get_job_summary(job_id)
    if summary is None:
        logger.warning("Performance job summary requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return summary


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
    response_model=List[schemas.DensityJobStatus],
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
        "total_fps": null,
        "per_stream_fps": 28.5,
        "total_streams": 32,
        "streams_per_pipeline": [
          {"id": "pipeline-1", "streams": 16},
          {"id": "pipeline-2", "streams": 16}
        ],
        "video_output_paths": {
          "pipeline-1": ["/outputs/job456-p1-0.mp4"]
        },
        "error_message": null
      }
    ]
    ```
    """
    return TestsManager().get_job_statuses_by_type(DensityJob)


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

    ## Conditions

    ### ✅ Success
    - Job with given id exists in TestsManager

    ### ❌ Failure
    - Unknown job id → 404

    ## Error Example

    ```json
    {
      "message": "Density job job456 not found"
    }
    ```
    """
    return get_job_status_or_404(job_id, "Density")


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
    summary = TestsManager().get_job_summary(job_id)
    if summary is None:
        logger.warning("Density job summary requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return summary


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
    response_model=List[schemas.OptimizationJobStatus],
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
        "total_fps": null,
        "original_pipeline_graph": {"nodes": [], "edges": []},
        "optimized_pipeline_graph": null,
        "original_pipeline_description": "videotestsrc ! fakesink",
        "optimized_pipeline_description": null,
        "error_message": null
      }
    ]
    ```
    """
    # Delegate to the manager; FastAPI takes care of serializing the
    # resulting Pydantic models into JSON.
    return OptimizationManager().get_all_job_statuses()


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
    # Ask the manager for the summary.  It returns None when the job id
    # is unknown, which we map to a 404 HTTP response.
    summary = OptimizationManager().get_job_summary(job_id)
    if summary is None:
        logger.warning("Optimization job summary requested for unknown job %s", job_id)
        # The explicit JSONResponse is used instead of raising HTTPException
        # to mirror the style used by other routes (e.g. pipelines.py) and
        # to fully control the response payload.
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Optimization job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return summary


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
    # Query the manager for the job status.  Unknown job ids are mapped
    # to a 404 response, mirroring the behaviour of the summary endpoint.
    status = OptimizationManager().get_job_status(job_id)
    if status is None:
        logger.warning("Optimization job status requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Optimization job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return status


@router.get(
    "/validation/status",
    operation_id="get_validation_statuses",
    summary="List all validation jobs",
    response_model=List[schemas.ValidationJobStatus],
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
        "is_valid": null,
        "error_message": null
      }
    ]
    ```
    """
    return ValidationManager().get_all_job_statuses()


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
    summary = ValidationManager().get_job_summary(job_id)
    if summary is None:
        logger.warning("Validation job summary requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Validation job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return summary


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

    Retrieves timings, state, is_valid flag and error_message list for a specific validation job.

    ## Path Parameters

    - `job_id`: Identifier of the validation job to inspect

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200  | ValidationJobStatus with timings, state, is_valid flag and error_message |
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
    status = ValidationManager().get_job_status(job_id)
    if status is None:
        logger.warning("Validation job status requested for unknown job %s", job_id)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Validation job {job_id} not found"
            ).model_dump(),
            status_code=404,
        )
    return status
