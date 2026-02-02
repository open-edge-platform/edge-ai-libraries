import logging
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
logger = logging.getLogger("api.routes.pipelines")


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
            "description": "Invalid pipeline definition",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Internal server error", "model": schemas.MessageResponse},
    },
)
def create_pipeline(body: schemas.PipelineDefinition):
    """
    Create a new user-defined pipeline.

    Operation:
        * Enforce USER_CREATED source
        * Validate that no variant has read_only=true
        * Delegate to PipelineManager.add_pipeline()
        * Return generated pipeline ID

    Request body:
        body: PipelineDefinition
            * name – non-empty pipeline name.
            * description – non-empty human-readable text describing what the pipeline does.
            * source – ignored and forced to USER_CREATED by this endpoint.
            * tags – list of tags for categorizing the pipeline.
            * variants – list of pipeline variants with their graphs.
                Note: read_only field in variants will be set to false and cannot be changed.

    Returns:
        201 Created:
            PipelineCreationResponse with generated pipeline id.
        400 Bad Request:
            MessageResponse when pipeline definition is invalid or when
            attempting to set read_only=true.
        500 Internal Server Error:
            MessageResponse when an unexpected error occurs.

    Success conditions:
        * PipelineDefinition is structurally valid
        * No variant has read_only=true
        * PipelineManager successfully creates pipeline

    Failure conditions:
        * Any variant has read_only=true → 400
        * Invalid pipeline definition at manager level → 400
        * Any other unhandled error → 500

    Request example:
        .. code-block:: json

            {
              "name": "vehicle-detection",
              "description": "Simple vehicle detection pipeline",
              "tags": ["detection", "vehicle"],
              "variants": [
                {
                  "id": "variant-1",
                  "name": "CPU",
                  "read_only": false,
                  "pipeline_graph": {...},
                  "pipeline_graph_simple": {...}
                }
              ]
            }

    Successful response example (201):
        .. code-block:: json

            {
              "id": "pipeline-a3f5d9e1"
            }

    Error response example (400):
        .. code-block:: json

            {
              "message": "Cannot set read_only=true for user-created pipeline variants. This field is reserved for PREDEFINED pipelines only."
            }
    """
    try:
        # Enforce USER_CREATED source for pipelines created via API
        body.source = schemas.PipelineSource.USER_CREATED

        # Reject any attempt to set read_only=true for user-created pipelines
        for variant in body.variants:
            if variant.read_only:
                return JSONResponse(
                    content=schemas.MessageResponse(
                        message="Cannot set read_only=true for user-created pipeline variants. "
                        "This field is reserved for PREDEFINED pipelines only."
                    ).model_dump(),
                    status_code=400,
                )
            # Ensure read_only is false
            variant.read_only = False

        pipeline = pipeline_manager.add_pipeline(body)

        return JSONResponse(
            content=schemas.PipelineCreationResponse(id=pipeline.id).model_dump(),
            status_code=201,
        )
    except ValueError as e:
        logger.error("Failed to create pipeline due to invalid input: %s", e)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=400,
        )
    except Exception as e:
        logger.error("Unexpected error while creating pipeline", exc_info=True)
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
        * Create a new validation job and run ``gst_runner.py`` in validation
          mode in a background thread.
        * Return the generated job id.

    Request body:
        body: PipelineValidation
            * pipeline_graph – nodes and edges representation of the pipeline.
            * parameters – optional dict, e.g. ``{"max-runtime": 10}``.
              Note: max-runtime must be greater than 0 for validation mode.

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
        logger.error("Invalid pipeline validation request: %s", e)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=400,
        )
    except Exception as e:
        logger.error(
            "Unexpected error while starting pipeline validation", exc_info=True
        )
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
            JSON array of Pipeline objects with all variants.

    Success conditions:
        * PipelineManager is initialized and has pipelines loaded.

    Failure conditions:
        * Unexpected errors will be propagated as 500 by FastAPI.

    Response example (200):
        .. code-block:: json

            [
              {
                "id": "pipeline-a3f5d9e1",
                "name": "vehicle-detection",
                "description": "Simple vehicle detection pipeline",
                "source": "PREDEFINED",
                "tags": ["detection"],
                "variants": [
                  {
                    "id": "variant-1",
                    "name": "CPU",
                    "read_only": true,
                    "pipeline_graph": {...},
                    "pipeline_graph_simple": {...}
                  }
                ]
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

    Operation:
        Retrieve the full pipeline definition including all variants,
        metadata, and tags.

    Path parameters:
        pipeline_id: Unique identifier of the pipeline (for example
            ``"pipeline-a3f5d9e1"``).

    Returns:
        200 OK:
            Pipeline object with all variants:
            - Each variant contains both pipeline_graph and pipeline_graph_simple
        404 Not Found:
            MessageResponse if pipeline with given id does not exist.
        500 Internal Server Error:
            MessageResponse for unexpected errors in the manager layer.

    Success conditions:
        * Pipeline with the given id is present in PipelineManager.
        * All variants are available.

    Failure conditions:
        * Unknown id → 404.
        * Any other unhandled exception → 500.

    Successful response example (200):
        .. code-block:: json

            {
              "id": "pipeline-a3f5d9e1",
              "name": "vehicle-detection",
              "description": "Simple vehicle detection pipeline",
              "source": "USER_CREATED",
              "tags": ["detection", "vehicle"],
              "variants": [
                {
                  "id": "variant-1",
                  "name": "CPU",
                  "read_only": false,
                  "pipeline_graph": {...},
                  "pipeline_graph_simple": {...}
                }
              ]
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
        logger.warning("Pipeline %s not found: %s", pipeline_id, e)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(e)).model_dump(),
            status_code=404,
        )
    except Exception as e:
        logger.error(
            "Unexpected error while retrieving pipeline %s", pipeline_id, exc_info=True
        )
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

    Operation:
        * Validate that at least one field is provided
        * Validate field values if provided
        * Delegate to PipelineManager.update_pipeline()

    Path parameters:
        pipeline_id: ID of the pipeline to update.

    Request body:
        body: PipelineUpdate
            Any combination of:
            * name – new pipeline name (non-empty string).
            * description – new human-readable text (non-empty string).
            * tags – list of tags (can be empty).

    Returns:
        200 OK:
            Updated Pipeline object with all fields.
        400 Bad Request:
            MessageResponse when:
            * none of the updatable fields is provided,
            * provided name or description is empty.
        404 Not Found:
            MessageResponse when pipeline id does not exist.
        500 Internal Server Error:
            MessageResponse for unexpected errors.

    Success conditions:
        * Pipeline with the given id exists.
        * At least one valid field is provided and passes validation.

    Failure conditions:
        * No fields provided → 400
        * Empty name or description → 400
        * Unknown id → 404
        * Any other exception → 500

    Request example:
        .. code-block:: json

            {
              "name": "vehicle-detection-v2",
              "description": "Updated pipeline with better preprocessing",
              "tags": ["updated", "v2"]
            }

    Successful response example (200):
        .. code-block:: json

            {
              "id": "pipeline-a3f5d9e1",
              "name": "vehicle-detection-v2",
              "description": "Updated pipeline with better preprocessing",
              "source": "USER_CREATED",
              "tags": ["updated", "v2"],
              "variants": [...]
            }

    Error response example (400):
        .. code-block:: json

            {
              "message": "At least one of 'name', 'description', or 'tags' must be provided."
            }
    """
    if body.name is None and body.description is None and body.tags is None:
        message = "At least one of 'name', 'description', or 'tags' must be provided."
        logger.error(
            "Invalid update request for pipeline %s: %s",
            pipeline_id,
            message,
        )
        return JSONResponse(
            content=schemas.MessageResponse(message=message).model_dump(),
            status_code=400,
        )

    if body.name is not None and body.name.strip() == "":
        message = "Field 'name' must not be empty."
        logger.error(
            "Invalid update request for pipeline %s: %s",
            pipeline_id,
            message,
        )
        return JSONResponse(
            content=schemas.MessageResponse(message=message).model_dump(),
            status_code=400,
        )

    if body.description is not None and body.description.strip() == "":
        message = "Field 'description' must not be empty."
        logger.error(
            "Invalid update request for pipeline %s: %s",
            pipeline_id,
            message,
        )
        return JSONResponse(
            content=schemas.MessageResponse(message=message).model_dump(),
            status_code=400,
        )

    try:
        updated_pipeline = pipeline_manager.update_pipeline(
            pipeline_id=pipeline_id,
            name=body.name,
            description=body.description,
            tags=body.tags,
        )
        return updated_pipeline
    except ValueError as e:
        # ValueError is used both for "not found" and validation errors.
        # Check message to determine appropriate status code.
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning(
                "Failed to update pipeline %s - not found: %s",
                pipeline_id,
                e,
            )
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=404,
            )
        else:
            logger.warning(
                "Failed to update pipeline %s due to invalid input: %s",
                pipeline_id,
                e,
            )
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=400,
            )
    except Exception as e:
        logger.error(
            "Unexpected error while updating pipeline %s", pipeline_id, exc_info=True
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Unexpected error: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/{pipeline_id}/variants/{variant_id}/optimize",
    operation_id="optimize_variant",
    responses={
        202: {
            "description": "Variant optimization started",
            "model": schemas.OptimizationJobResponse,
        },
        404: {
            "description": "Pipeline or variant not found",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def optimize_variant(
    pipeline_id: str, variant_id: str, body: schemas.PipelineRequestOptimize
):
    """
    Start an asynchronous optimization job for a specific pipeline variant.

    Operation:
        * Validate that pipeline and variant exist
        * Delegate to OptimizationManager.run_optimization() with variant
        * Return generated job ID

    Path parameters:
        pipeline_id: ID of the pipeline containing the variant.
        variant_id: ID of the variant to optimize.

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
            MessageResponse if pipeline or variant with given IDs do not exist.
        500 Internal Server Error:
            MessageResponse for unexpected errors when starting optimization
            (e.g. Graph conversion, external optimizer issues thrown early).

    Success conditions:
        * Pipeline and variant exist
        * Variant's graph can be converted to a launch string
        * OptimizationManager.run_optimization() starts a background job

    Failure conditions:
        * Unknown pipeline or variant ID → 404
        * Any unhandled exception in pipeline/variant lookup or job creation → 500

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

        # Find the variant
        variant_to_optimize = None
        for variant in pipeline.variants:
            if variant.id == variant_id:
                variant_to_optimize = variant
                break

        if variant_to_optimize is None:
            return JSONResponse(
                content=schemas.MessageResponse(
                    message=f"Variant '{variant_id}' not found in pipeline '{pipeline_id}'."
                ).model_dump(),
                status_code=404,
            )

        job_id = optimization_manager.run_optimization(variant_to_optimize, body)
        return schemas.OptimizationJobResponse(job_id=job_id)

    except ValueError as e:
        if "not found" in str(e).lower():
            logger.warning(
                "Pipeline %s not found for optimization request: %s",
                pipeline_id,
                e,
            )
            return JSONResponse(
                content=schemas.MessageResponse(message=str(e)).model_dump(),
                status_code=404,
            )
        else:
            logger.error("Optimization request validation failed: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=str(e)).model_dump(),
                status_code=400,
            )
    except Exception as e:
        logger.error(
            "Unexpected error while starting optimization for variant %s in pipeline %s",
            variant_id,
            pipeline_id,
            exc_info=True,
        )
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
        400: {
            "description": "Cannot delete PREDEFINED pipeline",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Pipeline not found",
            "model": schemas.MessageResponse,
        },
    },
)
def delete_pipeline(pipeline_id: str):
    """
    Delete a pipeline by its id.

    Operation:
        * Validate that pipeline exists
        * Validate that pipeline is not PREDEFINED
        * Delegate to PipelineManager.delete_pipeline_by_id()

    Path parameters:
        pipeline_id: ID of the pipeline to delete.

    Returns:
        200 OK:
            MessageResponse when the pipeline was successfully deleted.
        400 Bad Request:
            MessageResponse when trying to delete PREDEFINED pipeline.
        404 Not Found:
            MessageResponse when a pipeline with given id does not exist.

    Success conditions:
        * Pipeline with the given id is found
        * Pipeline is USER_CREATED (not PREDEFINED)
        * Pipeline is removed from manager

    Failure conditions:
        * Pipeline is PREDEFINED → 400
        * Unknown id → 404

    Note: PREDEFINED pipelines cannot be deleted.

    Successful response example (200):
        .. code-block:: json

            {
              "message": "Pipeline deleted"
            }

    Error response example (400):
        .. code-block:: json

            {
              "message": "Cannot delete PREDEFINED pipeline 'pipeline-a3f5d9e1'."
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
        error_message = str(e)
        if "PREDEFINED" in error_message:
            logger.warning("Cannot delete PREDEFINED pipeline %s: %s", pipeline_id, e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=400,
            )
        else:
            logger.warning("Pipeline %s not found for deletion: %s", pipeline_id, e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=404,
            )
    return schemas.MessageResponse(message="Pipeline deleted")


@router.post(
    "/{pipeline_id}/variants",
    operation_id="create_variant",
    status_code=201,
    responses={
        201: {
            "description": "Variant created",
            "model": schemas.Variant,
        },
        400: {
            "description": "Invalid variant definition",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Pipeline not found",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Internal server error", "model": schemas.MessageResponse},
    },
)
def create_variant(pipeline_id: str, body: schemas.VariantCreate):
    """
    Create a new variant for an existing pipeline.

    Operation:
        * Validate that pipeline exists
        * Delegate to PipelineManager.add_variant()
        * Return created variant with generated ID

    The backend automatically generates the variant ID and sets read_only=false.
    These fields must not be included in the request.

    Path parameters:
        pipeline_id: ID of the pipeline to add variant to.

    Request body:
        body: VariantCreate
            * name – variant name (required, non-empty).
            * pipeline_graph – advanced graph representation (required).
            * pipeline_graph_simple – simplified graph representation (required).

    Returns:
        201 Created:
            Complete Variant object with generated id and read_only=false.
        400 Bad Request:
            MessageResponse when variant definition is invalid.
        404 Not Found:
            MessageResponse when pipeline does not exist.
        500 Internal Server Error:
            MessageResponse for unexpected errors.

    Success conditions:
        * Pipeline exists
        * Variant definition is valid
        * Variant is successfully added

    Failure conditions:
        * Pipeline not found → 404
        * Invalid variant definition → 400
        * Any other exception → 500

    Request example:
        .. code-block:: json

            {
              "name": "GPU",
              "pipeline_graph": {
                "nodes": [...],
                "edges": [...]
              },
              "pipeline_graph_simple": {
                "nodes": [...],
                "edges": [...]
              }
            }

    Successful response example (201):
        .. code-block:: json

            {
              "id": "variant-abc123",
              "name": "GPU",
              "read_only": false,
              "pipeline_graph": {...},
              "pipeline_graph_simple": {...}
            }
    """
    try:
        new_variant = pipeline_manager.add_variant(
            pipeline_id=pipeline_id,
            name=body.name,
            pipeline_graph=body.pipeline_graph,
            pipeline_graph_simple=body.pipeline_graph_simple,
        )

        logger.info(f"Created variant {new_variant.id} for pipeline {pipeline_id}")
        return JSONResponse(
            content=new_variant.model_dump(),
            status_code=201,
        )

    except ValueError as e:
        if "not found" in str(e).lower():
            logger.warning("Pipeline %s not found for variant creation", pipeline_id)
            return JSONResponse(
                content=schemas.MessageResponse(message=str(e)).model_dump(),
                status_code=404,
            )
        else:
            logger.error("Invalid variant definition: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=str(e)).model_dump(),
                status_code=400,
            )
    except Exception as e:
        logger.error("Unexpected error while creating variant", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to create variant: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.delete(
    "/{pipeline_id}/variants/{variant_id}",
    operation_id="delete_variant",
    responses={
        200: {"description": "Variant deleted", "model": schemas.MessageResponse},
        400: {
            "description": "Cannot delete read-only variant or last variant",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Pipeline or variant not found",
            "model": schemas.MessageResponse,
        },
    },
)
def delete_variant(pipeline_id: str, variant_id: str):
    """
    Delete a variant from a pipeline.

    Operation:
        * Validate that pipeline and variant exist
        * Check that variant is not read-only
        * Check that variant is not the last one
        * Delegate to PipelineManager.delete_variant()

    Path parameters:
        pipeline_id: ID of the pipeline containing the variant.
        variant_id: ID of the variant to delete.

    Cannot delete:
    * Read-only variants (from PREDEFINED pipelines)
    * The last remaining variant of a pipeline

    Returns:
        200 OK:
            MessageResponse confirming deletion.
        400 Bad Request:
            MessageResponse when trying to delete read-only variant or last variant.
        404 Not Found:
            MessageResponse when pipeline or variant not found.

    Success conditions:
        * Pipeline and variant exist
        * Variant is not read-only
        * Variant is not the last one
        * Variant is successfully deleted

    Failure conditions:
        * Pipeline or variant not found → 404
        * Variant is read-only → 400
        * Variant is last one → 400

    Successful response example (200):
        .. code-block:: json

            {
              "message": "Variant deleted"
            }

    Error response example (400, read-only):
        .. code-block:: json

            {
              "message": "Cannot delete read-only variant 'variant-1'."
            }

    Error response example (400, last variant):
        .. code-block:: json

            {
              "message": "Cannot delete variant 'variant-1' as it is the last variant in pipeline 'pipeline-a3f5d9e1'."
            }
    """
    try:
        pipeline_manager.delete_variant(pipeline_id, variant_id)
        logger.info(f"Deleted variant {variant_id} from pipeline {pipeline_id}")
        return schemas.MessageResponse(message="Variant deleted")

    except ValueError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning("Pipeline or variant not found for deletion: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=404,
            )
        else:
            logger.warning("Cannot delete variant: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=400,
            )


@router.patch(
    "/{pipeline_id}/variants/{variant_id}",
    operation_id="update_variant",
    responses={
        200: {"description": "Variant updated", "model": schemas.Variant},
        400: {
            "description": "Invalid request or cannot update read-only variant",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Pipeline or variant not found",
            "model": schemas.MessageResponse,
        },
    },
)
def update_variant(pipeline_id: str, variant_id: str, body: schemas.VariantUpdate):
    """
    Update an existing variant.

    Operation:
        * Validate that pipeline and variant exist
        * Check that variant is not read-only
        * Validate request body (checked by VariantUpdate model)
        * Delegate to PipelineManager.update_variant()

    Path parameters:
        pipeline_id: ID of the pipeline containing the variant.
        variant_id: ID of the variant to update.

    Request body:
        body: VariantUpdate (validated by Pydantic)
            * name: Optional variant name
            * pipeline_graph: Optional advanced graph (mutually exclusive with pipeline_graph_simple)
            * pipeline_graph_simple: Optional simplified graph (mutually exclusive with pipeline_graph)

    Allowed fields:
    * name: Variant name
    * pipeline_graph: Advanced graph (mutually exclusive with pipeline_graph_simple)
    * pipeline_graph_simple: Simplified graph (mutually exclusive with pipeline_graph)

    Only one of pipeline_graph or pipeline_graph_simple can be provided per request.
    Cannot update read-only variants.

    Returns:
        200 OK:
            Updated Variant object.
        400 Bad Request:
            MessageResponse when request is invalid, variant is read-only, or
            both graphs are provided (validated by VariantUpdate model).
        404 Not Found:
            MessageResponse when pipeline or variant not found.

    Success conditions:
        * Pipeline and variant exist
        * Variant is not read-only
        * At least one field provided
        * At most one graph field provided
        * Variant is successfully updated

    Failure conditions:
        * Pipeline or variant not found → 404
        * Variant is read-only → 400
        * Invalid request (no fields or both graphs) → 400
        * Any other exception → 500

    Request example (update name):
        .. code-block:: json

            {
              "name": "GPU-optimized"
            }

    Request example (update advanced graph):
        .. code-block:: json

            {
              "pipeline_graph": {
                "nodes": [...],
                "edges": [...]
              }
            }

    Successful response example (200):
        .. code-block:: json

            {
              "id": "variant-1",
              "name": "GPU-optimized",
              "read_only": false,
              "pipeline_graph": {...},
              "pipeline_graph_simple": {...}
            }

    Error response example (400, read-only):
        .. code-block:: json

            {
              "message": "Cannot update read-only variant 'variant-1'."
            }
    """
    try:
        updated_variant = pipeline_manager.update_variant(
            pipeline_id=pipeline_id,
            variant_id=variant_id,
            name=body.name,
            pipeline_graph=body.pipeline_graph,
            pipeline_graph_simple=body.pipeline_graph_simple,
        )

        logger.info(f"Updated variant {variant_id} in pipeline {pipeline_id}")
        return updated_variant

    except ValueError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning("Pipeline or variant not found for update: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=404,
            )
        else:
            logger.error("Invalid variant update: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=400,
            )
    except Exception as e:
        logger.error("Unexpected error while updating variant", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to update variant: {str(e)}"
            ).model_dump(),
            status_code=500,
        )
