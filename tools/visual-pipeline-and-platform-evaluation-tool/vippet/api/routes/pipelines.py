import tempfile
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from managers.optimization_manager import get_optimization_manager
from managers.pipeline_manager import get_pipeline_manager
from managers.validation_manager import get_validation_manager

TEMP_DIR = tempfile.gettempdir()

router = APIRouter()
pipeline_manager = get_pipeline_manager()
optimization_manager = get_optimization_manager()
validation_manager = get_validation_manager()


@router.post(
    "",
    operation_id="create_pipeline",
    status_code=201,
    responses={
        201: {
            "description": "Pipeline created",
            "model": schemas.PipelineCreationResponse,
        },
        400: {
            "description": "Invalid pipeline definition or version conflict",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Internal server error", "model": schemas.MessageResponse},
    },
)
def create_pipeline(body: schemas.PipelineDefinition):
    """
    Create a new user-defined pipeline from a GStreamer launch string.

    Request body:
        body: PipelineDefinition
            * name – non-empty pipeline name.
            * version – positive integer. Must be exactly 1 for a new name,
              or "last_version + 1" for an existing name.
            * description – non-empty human-readable description.
            * source – ignored and forced to USER_CREATED by this endpoint.
            * type – pipeline type (currently GStreamer is used).
            * pipeline_description – full GStreamer launch string.
            * parameters – optional default parameters for this pipeline.

    Returns:
        201 Created:
            PipelineCreationResponse with generated pipeline id.
        400 Bad Request:
            MessageResponse when:
            * versioning rules are violated (e.g. version not next in sequence),
            * pipeline name or definition is invalid at manager level.
        500 Internal Server Error:
            MessageResponse when an unexpected error occurs while creating
            the pipeline.

    Success conditions:
        * PipelineDefinition is structurally valid.
        * PipelineManager successfully adds the pipeline and converts the
          launch string to a graph.

    Failure conditions (high level):
        * Version conflicts or invalid name → 400.
        * Any other unhandled error in PipelineManager / Graph → 500.

    Request example:
        .. code-block:: json

            {
              "name": "vehicle-detection",
              "version": 1,
              "description": "Simple vehicle detection pipeline",
              "type": "GStreamer",
              "pipeline_description": "filesrc location=input.mp4 ! decodebin ! videoconvert ! fakesink",
              "parameters": {
                "default": {
                  "max-runtime": 60
                }
              }
            }

    Successful response example (201):
        .. code-block:: json

            {
              "id": "pipeline-a3f5d9e1"
            }

    Error response example (400):
        .. code-block:: json

            {
              "message": "Invalid version '2' for pipeline 'vehicle-detection'. Expected version '1' for a new pipeline."
            }
    """
    try:
        # Enforce USER_CREATED source for pipelines created via API
        body.source = schemas.PipelineSource.USER_CREATED
        pipeline = pipeline_manager.add_pipeline(body)

        return JSONResponse(
            content=schemas.PipelineCreationResponse(id=pipeline.id).model_dump(),
            status_code=201,
        )
    except ValueError as e:
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=400,
        )
    except Exception as e:
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to create pipeline: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/validate",
    operation_id="validate_pipeline",
    responses={
        202: {
            "description": "Pipeline validation started",
            "model": schemas.ValidationJobResponse,
        },
        400: {
            "description": "Invalid validation request",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Internal server error", "model": schemas.MessageResponse},
    },
)
def validate_pipeline(body: schemas.PipelineValidation):
    """
    Start an asynchronous validation job for an ad-hoc pipeline graph.

    Operation:
        * Convert the provided PipelineGraph to a GStreamer launch string.
        * Extract validation parameters (for example ``max-runtime``).
        * Create a new validation job and run ``validator.py`` in a
          background thread.
        * Return the generated job id.

    Request body:
        body: PipelineValidation
            * type – pipeline type (currently GStreamer).
            * pipeline_graph – nodes and edges representation of the pipeline.
            * parameters – optional dict, e.g. ``{"max-runtime": 10}``.

    Returns:
        202 Accepted:
            ValidationJobResponse with job_id of created validation job.
        400 Bad Request:
            MessageResponse when request parameters are invalid, e.g.:
            * ``max-runtime`` is not an integer,
            * ``max-runtime`` is < 1.
        500 Internal Server Error:
            MessageResponse for unexpected errors (e.g. Graph conversion).

    Success conditions:
        * Graph can be converted to a valid launch string.
        * Parameters pass ValidationManager checks.
        * Background validation job is successfully started.

    Failure conditions:
        * Parameter validation error (ValueError) → 400.
        * Any other unexpected exception → 500.

    Request example:
        .. code-block:: json

            {
              "type": "GStreamer",
              "pipeline_graph": {
                "nodes": [
                  {"id": "0", "type": "filesrc", "data": {"location": "/videos/input.mp4"}},
                  {"id": "1", "type": "decodebin", "data": {}},
                  {"id": "2", "type": "fakesink", "data": {}}
                ],
                "edges": [
                  {"id": "0", "source": "0", "target": "1"},
                  {"id": "1", "source": "1", "target": "2"}
                ]
              },
              "parameters": {
                "max-runtime": 10
              }
            }

    Successful response example (202):
        .. code-block:: json

            {
              "job_id": "val001"
            }

    Error response example (400):
        .. code-block:: json

            {
              "message": "Parameter 'max-runtime' must be greater than or equal to 1."
            }
    """
    try:
        job_id = validation_manager.run_validation(body)
        return JSONResponse(
            content=schemas.ValidationJobResponse(job_id=job_id).model_dump(),
            status_code=202,
        )
    except ValueError as e:
        # ValidationManager uses ValueError for user-level input problems.
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=400,
        )
    except Exception as e:
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.get("", operation_id="get_pipelines", response_model=List[schemas.Pipeline])
def get_pipelines():
    """
    List all pipelines currently registered in the system.

    Operation:
        Return both predefined pipelines loaded from configuration and
        user-created pipelines added via this API.

    Path / query parameters:
        None.

    Returns:
        200 OK:
            JSON array of Pipeline objects.

    Success conditions:
        * PipelineManager is initialized.

    Failure conditions:
        * Unexpected errors will be propagated as 500 by FastAPI.

    Response example (200):
        .. code-block:: json

            [
              {
                "id": "pipeline-a3f5d9e1",
                "name": "vehicle-detection",
                "version": 1,
                "description": "Simple vehicle detection pipeline",
                "source": "PREDEFINED",
                "type": "GStreamer",
                "pipeline_graph": {
                  "nodes": [...],
                  "edges": [...]
                },
                "parameters": null
              }
            ]
    """
    return pipeline_manager.get_pipelines()


@router.get(
    "/{pipeline_id}",
    operation_id="get_pipeline",
    responses={
        200: {"description": "Successful Response", "model": schemas.Pipeline},
        404: {"description": "Pipeline not found", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def get_pipeline(pipeline_id: str):
    """
    Get details of a single pipeline by its id.

    Path parameters:
        pipeline_id: Unique identifier of the pipeline (for example
            ``"pipeline-a3f5d9e1"``).

    Returns:
        200 OK:
            Pipeline object with full graph and metadata.
        404 Not Found:
            MessageResponse if pipeline with given id does not exist.
        500 Internal Server Error:
            MessageResponse for unexpected errors in the manager layer.

    Success conditions:
        * Pipeline with the given id is present in PipelineManager.

    Failure conditions:
        * Unknown id → 404.
        * Any other unhandled exception → 500.

    Successful response example (200):
        .. code-block:: json

            {
              "id": "pipeline-a3f5d9e1",
              "name": "vehicle-detection",
              "version": 1,
              "description": "Simple vehicle detection pipeline",
              "source": "USER_CREATED",
              "type": "GStreamer",
              "pipeline_graph": {
                "nodes": [...],
                "edges": [...]
              },
              "parameters": {
                "default": {
                  "max-runtime": 60
                }
              }
            }

    Error response example (404):
        .. code-block:: json

            {
              "message": "Pipeline with id 'pipeline-unknown' not found."
            }
    """
    try:
        return pipeline_manager.get_pipeline_by_id(pipeline_id)
    except ValueError as e:
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=404,
        )
    except Exception as e:
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.patch(
    "/{pipeline_id}",
    operation_id="update_pipeline",
    responses={
        200: {"description": "Pipeline updated", "model": schemas.Pipeline},
        404: {"description": "Pipeline not found", "model": schemas.MessageResponse},
        400: {"description": "Invalid request", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def update_pipeline(pipeline_id: str, body: schemas.PipelineUpdate):
    """
    Partially update selected fields of an existing pipeline.

    Path parameters:
        pipeline_id: ID of the pipeline to update.

    Request body:
        body: PipelineUpdate
            Any combination of:
            * name – new pipeline name (non-empty string).
            * description – new human-readable description (non-empty string).
            * pipeline_graph – new graph representation. It must contain at
              least one node and one edge and must be convertible to a valid
              pipeline description string.
            * parameters – new pipeline parameters.

    Returns:
        200 OK:
            Updated Pipeline object.
        400 Bad Request:
            MessageResponse when:
            * none of the updatable fields is provided,
            * provided name or description is empty,
            * provided pipeline_graph has no nodes/edges or cannot be
              converted to a valid pipeline description.
        404 Not Found:
            MessageResponse when pipeline id does not exist.
        500 Internal Server Error:
            MessageResponse for unexpected errors.

    Success conditions:
        * Pipeline with the given id exists.
        * At least one valid field is provided and passes validation.
        * For pipeline_graph, Graph.to_pipeline_description() succeeds.

    Failure conditions:
        * Validation failures in this handler or PipelineManager.update_pipeline.
        * Unknown id → 404.
        * Any other exception → 500.

    Request example:
        .. code-block:: json

            {
              "name": "vehicle-detection-v2",
              "description": "Updated pipeline with better preprocessing",
              "parameters": {
                "default": {
                  "max-runtime": 120
                }
              }
            }

    Error response example (400, empty body):
        .. code-block:: json

            {
              "message": "At least one of 'name', 'description', 'parameters' or 'pipeline_graph' must be provided."
            }
    """
    if (
        body.name is None
        and body.description is None
        and body.parameters is None
        and body.pipeline_graph is None
    ):
        return JSONResponse(
            content=schemas.MessageResponse(
                message="At least one of 'name', 'description', 'parameters' or 'pipeline_graph' must be provided."
            ).model_dump(),
            status_code=400,
        )

    # Additional lightweight validation to avoid accepting empty values.
    if body.name is not None and body.name.strip() == "":
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Field 'name' must not be empty."
            ).model_dump(),
            status_code=400,
        )

    if body.description is not None and body.description.strip() == "":
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Field 'description' must not be empty."
            ).model_dump(),
            status_code=400,
        )

    if body.pipeline_graph is not None:
        if not body.pipeline_graph.nodes or not body.pipeline_graph.edges:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message="Field 'pipeline_graph' must contain at least one node and one edge."
                ).model_dump(),
                status_code=400,
            )

    try:
        updated_pipeline = pipeline_manager.update_pipeline(
            pipeline_id=pipeline_id,
            name=body.name,
            description=body.description,
            pipeline_graph=body.pipeline_graph,
            parameters=body.parameters,
        )
        return updated_pipeline
    except ValueError as e:
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=404,
        )
    except Exception as e:
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/{pipeline_id}/optimize",
    operation_id="optimize_pipeline",
    responses={
        202: {
            "description": "Pipeline optimization started",
            "model": schemas.OptimizationJobResponse,
        },
        404: {"description": "Pipeline not found", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def optimize_pipeline(pipeline_id: str, body: schemas.PipelineRequestOptimize):
    """
    Start an asynchronous optimization job for a given pipeline.

    Path parameters:
        pipeline_id: ID of the pipeline to optimize.

    Request body:
        body: PipelineRequestOptimize
            * type – optimization type: ``"preprocess"`` or ``"optimize"``.
            * parameters – optional dict with optimizer-specific options,
              for example:

              .. code-block:: json

                  {
                    "search_duration": 300,
                    "sample_duration": 10
                  }

    Returns:
        202 Accepted:
            OptimizationJobResponse with job_id of the created optimization job.
        404 Not Found:
            MessageResponse if pipeline with given id does not exist.
        500 Internal Server Error:
            MessageResponse for unexpected errors when starting optimization
            (e.g. Graph conversion, external optimizer issues thrown early).

    Success conditions:
        * Pipeline exists and its graph can be converted to a launch string.
        * OptimizationManager.run_optimization() starts a background job.

    Failure conditions:
        * Unknown pipeline id → 404.
        * Any unhandled exception in pipeline lookup or job creation → 500.

    Request example:
        .. code-block:: json

            {
              "type": "optimize",
              "parameters": {
                "search_duration": 300,
                "sample_duration": 10
              }
            }

    Successful response example (202):
        .. code-block:: json

            {
              "job_id": "opt789"
            }
    """
    try:
        pipeline = pipeline_manager.get_pipeline_by_id(pipeline_id)
        job_id = optimization_manager.run_optimization(pipeline, body)
        return schemas.OptimizationJobResponse(job_id=job_id)
    except ValueError as e:
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=404,
        )
    except Exception as e:
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.delete(
    "/{pipeline_id}",
    operation_id="delete_pipeline",
    responses={
        200: {"description": "Pipeline deleted", "model": schemas.MessageResponse},
        404: {
            "description": "Pipeline not found",
            "model": schemas.MessageResponse,
        },
    },
)
def delete_pipeline(pipeline_id: str):
    """
    Delete a pipeline by its id.

    Path parameters:
        pipeline_id: ID of the pipeline to delete.

    Returns:
        200 OK:
            MessageResponse when the pipeline was successfully deleted.
        404 Not Found:
            MessageResponse when a pipeline with given id does not exist.

    Success conditions:
        * Pipeline with the given id is found and removed from manager.

    Failure conditions:
        * Unknown id → 404.

    Successful response example (200):
        .. code-block:: json

            {
              "message": "Pipeline deleted"
            }

    Error response example (404):
        .. code-block:: json

            {
              "message": "Pipeline with id 'pipeline-unknown' not found."
            }
    """
    try:
        pipeline_manager.delete_pipeline_by_id(pipeline_id)
    except ValueError as e:
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=404,
        )
    return schemas.MessageResponse(message="Pipeline deleted")
