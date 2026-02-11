import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from managers.tests_manager import TestsManager

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
              streams per pipeline.
            * execution_config – configuration for output mode and runtime limits:
              - output_mode: disabled (default), file, or live_stream
              - max_runtime: maximum runtime in seconds (0 = run until EOS)

    Returns:
        202 Accepted:
            TestJobResponse with job_id of the created performance job.
        400 Bad Request:
            MessageResponse if the request is invalid at manager level, for
            example:
            * all stream counts are zero,
            * pipeline ids do not exist (if validated up front in future),
            * output_mode=file combined with max_runtime > 0.
        500 Internal Server Error:
            MessageResponse if an unexpected error occurs when creating the
            job or starting the background thread.

    Success conditions:
        * At least one stream is requested across all pipelines.
        * TestsManager.test_performance() successfully enqueues the job.

    Failure conditions (high level):
        * Validation or configuration error inside TestsManager → 400.
        * Any unhandled exception in job creation → 500.

    Request example:
        .. code-block:: json

            {
              "pipeline_performance_specs": [
                {"id": "pipeline-a3f5d9e1", "streams": 8},
                {"id": "pipeline-b7c2e114", "streams": 4}
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
        pipeline_ids = [spec.id for spec in body.pipeline_performance_specs]
        if len(pipeline_ids) != len(set(pipeline_ids)):
            raise ValueError(
                "Duplicate pipeline IDs found in pipeline_performance_specs"
            )

        job_id = TestsManager().test_performance(body)
        return schemas.TestJobResponse(job_id=job_id)
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
              percentages that must sum to 100.
            * execution_config – configuration for output mode and runtime limits:
              - output_mode: disabled (default) or file (live_stream not supported)
              - max_runtime: maximum runtime in seconds (0 = run until EOS)

    Returns:
        202 Accepted:
            TestJobResponse with job_id of the created density job.
        400 Bad Request:
            MessageResponse when:
            * pipeline_density_specs.stream_rate values do not sum to 100,
            * output_mode is live_stream (not supported for density tests),
            * output_mode=file combined with max_runtime > 0,
            * other validation errors raised by Benchmark or TestsManager.
        500 Internal Server Error:
            MessageResponse for unexpected errors when creating or starting
            the job.

    Success conditions:
        * stream_rate ratios sum to 100%.
        * DensityTestSpec is valid and Benchmark.run() can be started in a
          background thread.

    Failure conditions:
        * Validation errors in Benchmark._calculate_streams_per_pipeline() or
          TestsManager.test_density() → 400.
        * Any other unhandled exception → 500.

    Request example:
        .. code-block:: json

            {
              "fps_floor": 30,
              "pipeline_density_specs": [
                {"id": "pipeline-a3f5d9e1", "stream_rate": 50},
                {"id": "pipeline-b7c2e114", "stream_rate": 50}
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
        pipeline_ids = [spec.id for spec in body.pipeline_density_specs]
        if len(pipeline_ids) != len(set(pipeline_ids)):
            raise ValueError("Duplicate pipeline IDs found in pipeline_density_specs")

        job_id = TestsManager().test_density(body)
        return schemas.TestJobResponse(job_id=job_id)
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
