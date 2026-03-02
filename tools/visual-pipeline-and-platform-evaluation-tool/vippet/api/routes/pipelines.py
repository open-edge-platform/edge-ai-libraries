import logging
import tempfile
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from managers.optimization_manager import OptimizationManager
from managers.pipeline_manager import PipelineManager
from managers.validation_manager import ValidationManager
from graph import Graph
from internal_types import (
    InternalOptimizationType,
    InternalPipeline,
    InternalPipelineDefinition,
    InternalPipelineRequestOptimize,
    InternalPipelineSource,
    InternalPipelineValidation,
    InternalVariant,
    InternalVariantCreate,
)

TEMP_DIR = tempfile.gettempdir()

router = APIRouter()
logger = logging.getLogger("api.routes.pipelines")


@router.post(
    "",
    operation_id="create_pipeline",
    summary="Create Pipeline",
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
    **Create a new user-defined pipeline.**

    ## Operation
    1. Enforce `USER_CREATED` source
    2. Delegate to `PipelineManager.add_pipeline()`
    3. Return generated pipeline ID

    ## Auto-Generated Fields
    The backend automatically sets:
    - Pipeline ID (generated from name)
    - Timestamps (`created_at` and `modified_at`)
    - Variant IDs (generated from variant names)
    - Variant `read_only=False` for all variants
    - Pipeline `thumbnail=None` (user-created pipelines)

    ## Request Body
    **`PipelineDefinition`** with:
    - `name` *(required)* - Non-empty pipeline name
    - `description` *(required)* - Human-readable description
    - `source` *(ignored)* - Forced to `USER_CREATED`
    - `tags` *(optional)* - List of categorization tags
    - `variants` *(required)* - List of `VariantCreate` objects:
      - `name` - Variant name
      - `pipeline_graph` - Advanced graph representation
      - `pipeline_graph_simple` - Simplified graph representation

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 201 | `PipelineCreationResponse` with generated pipeline `id` |
    | 400 | `MessageResponse` - Invalid pipeline definition |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Valid PipelineDefinition
    - PipelineManager successfully creates pipeline

    ### ❌ Failure
    - Invalid pipeline definition → 400
    - Unhandled error → 500

    ## Examples

    ### Request
    ```json
    {
      "name": "vehicle-detection",
      "description": "Simple vehicle detection pipeline",
      "tags": ["detection", "vehicle"],
      "variants": [
        {
          "name": "CPU",
          "pipeline_graph": {...},
          "pipeline_graph_simple": {...}
        }
      ]
    }
    ```

    ### Success Response (201)
    ```json
    {
      "id": "pipeline-a3f5d9e1"
    }
    ```

    ### Error Response (400)
    ```json
    {
      "message": "Pipeline name cannot be empty"
    }
    ```
    """
    try:
        # Enforce USER_CREATED source for pipelines created via API
        body.source = schemas.PipelineSource.USER_CREATED

        internal_def = _pipeline_definition_to_internal(body)
        pipeline = PipelineManager().add_pipeline(internal_def)

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
    summary="Validate Pipeline",
    status_code=202,
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
    **Start asynchronous validation job for a pipeline graph.**

    ## Operation
    1. Convert PipelineGraph to GStreamer launch string
    2. Extract validation parameters (e.g., `max-runtime`)
    3. Create validation job and run `gst_runner.py` in background
    4. Return generated job ID

    ## Request Body
    **`PipelineValidation`** with:
    - `pipeline_graph` *(required)* - Nodes and edges representation
    - `parameters` *(optional)* - Configuration dict, e.g., `{"max-runtime": 10}`
      - **Note:** `max-runtime` must be > 0 for validation mode

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 202 | `ValidationJobResponse` with `job_id` |
    | 400 | `MessageResponse` - Invalid parameters (e.g., `max-runtime` < 1) |
    | 500 | `MessageResponse` - Unexpected error (e.g., graph conversion) |

    ## Conditions

    ### ✅ Success
    - Graph converts to valid launch string
    - Parameters pass ValidationManager checks
    - Background validation job started

    ### ❌ Failure
    - Parameter validation error → 400
    - Unexpected exception → 500

    ## Examples

    ### Request
    ```json
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
    ```

    ### Success Response (202)
    ```json
    {
      "job_id": "val001"
    }
    ```

    ### Error Response (400)
    ```json
    {
      "message": "Parameter 'max-runtime' must be greater than or equal to 1."
    }
    ```
    """
    try:
        internal_request = _pipeline_validation_to_internal(body)
        job_id = ValidationManager().run_validation(internal_request)
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


@router.get(
    "",
    operation_id="get_pipelines",
    summary="List All Pipelines",
    response_model=List[schemas.Pipeline],
    response_description="List of all pipelines including predefined and user-created",
)
def get_pipelines():
    """
    **List all pipelines currently registered in the system.**

    ## Operation
    Return both predefined pipelines loaded from configuration and
    user-created pipelines added via this API.

    ## Parameters
    - **Path/Query parameters:** None

    ## Response Format

    ### 200 OK
    JSON array of Pipeline objects with all variants.

    **Each pipeline includes:**
    - `id` - Unique pipeline identifier
    - `name` - Pipeline name
    - `description` - Human-readable description
    - `source` - Pipeline source (`PREDEFINED` or `USER_CREATED`)
    - `tags` - List of categorization tags
    - `variants` - List of Variant objects with:
      - Pipeline graphs and timestamps
      - `read_only` flag
    - `thumbnail` - Base64-encoded image for PREDEFINED pipelines, `null` otherwise
      > **Note:** Thumbnail is redacted in logs but returned in full in API response
    - `created_at`, `modified_at` - UTC datetime (ISO 8601 format)

    ## Conditions

    ### ✅ Success
    - PipelineManager is initialized and has pipelines loaded

    ### ❌ Failure
    - Unexpected errors will be propagated as 500 by FastAPI

    ## Example Response

    ```json
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
            "pipeline_graph_simple": {...},
            "created_at": "2026-02-05T14:30:45.123000+00:00",
            "modified_at": "2026-02-05T14:30:45.123000+00:00"
          }
        ],
        "thumbnail": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
        "created_at": "2026-02-05T14:30:45.123000+00:00",
        "modified_at": "2026-02-05T14:30:45.123000+00:00"
      }
    ]
    ```
    """
    internal_pipelines = PipelineManager().get_pipelines()
    return [_internal_pipeline_to_api(p) for p in internal_pipelines]


@router.get(
    "/{pipeline_id}",
    operation_id="get_pipeline",
    summary="Get Pipeline by ID",
    responses={
        200: {
            "description": "Pipeline details retrieved successfully",
            "model": schemas.Pipeline,
        },
        404: {"description": "Pipeline not found", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def get_pipeline(pipeline_id: str):
    """
    **Get details of a single pipeline by its ID.**

    ## Operation
    Retrieve the full pipeline definition including all variants,
    metadata, timestamps, and tags.

    ## Path Parameters
    - `pipeline_id` - Unique identifier of the pipeline (e.g., `"pipeline-a3f5d9e1"`)

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | Complete Pipeline object with all fields |
    | 404 | `MessageResponse` - Pipeline with given ID does not exist |
    | 500 | `MessageResponse` - Unexpected error in manager layer |

    ## Response Fields (200)
    - `id`, `name`, `description`, `source`, `tags`
    - `variants` - Each with `pipeline_graph`, `pipeline_graph_simple`, and timestamps
    - `thumbnail` - Base64-encoded image for PREDEFINED pipelines, `null` otherwise
      > **Note:** Thumbnail is redacted in logs but returned in full in API response
    - `created_at`, `modified_at` - UTC datetime (ISO 8601 format, set by backend only)

    ## Conditions

    ### ✅ Success
    - Pipeline with the given ID is present in PipelineManager
    - All variants are available

    ### ❌ Failure
    - Unknown ID → 404
    - Any other unhandled exception → 500

    ## Examples

    ### Success Response (200)
    ```json
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
          "pipeline_graph_simple": {...},
          "created_at": "2026-02-05T14:30:45.123000+00:00",
          "modified_at": "2026-02-05T14:30:45.123000+00:00"
        }
      ],
      "thumbnail": null,
      "created_at": "2026-02-05T14:30:45.123000+00:00",
      "modified_at": "2026-02-05T14:30:45.123000+00:00"
    }
    ```

    ### Error Response (404)
    ```json
    {
      "message": "Pipeline with id 'pipeline-unknown' not found."
    }
    ```
    """
    try:
        internal_pipeline = PipelineManager().get_pipeline_by_id(pipeline_id)
        return _internal_pipeline_to_api(internal_pipeline)
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
    summary="Update Pipeline",
    responses={
        200: {
            "description": "Pipeline successfully updated",
            "model": schemas.Pipeline,
        },
        404: {"description": "Pipeline not found", "model": schemas.MessageResponse},
        400: {"description": "Invalid request", "model": schemas.MessageResponse},
        422: {"description": "Validation error", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def update_pipeline(pipeline_id: str, body: schemas.PipelineUpdate):
    """
    **Partially update selected fields of an existing pipeline.**

    ## Operation
    1. Validate request body via `PipelineUpdate` model
    2. Delegate to `PipelineManager.update_pipeline()`
    3. Backend automatically updates `modified_at` timestamp

    ## Immutable Fields
    The following fields **cannot** be updated via API:
    - `id` - Immutable identifier
    - `source` - Immutable source type
    - `thumbnail` - Only set for PREDEFINED pipelines from config files
    - `created_at` - Immutable creation timestamp
    - `modified_at` - Automatically updated by backend (UTC datetime)

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline to update

    ## Request Body
    **`PipelineUpdate`** (validated by Pydantic) - any combination of:
    - `name` *(optional)* - New pipeline name (non-empty after trim)
    - `description` *(optional)* - New description (non-empty after trim)
    - `tags` *(optional)* - List of tags (can be empty)

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | Updated Pipeline object with new `modified_at` |
    | 400 | `MessageResponse` - Manager-level validation fails |
    | 404 | `MessageResponse` - Pipeline ID does not exist |
    | 422 | Pydantic validation error (no fields or empty values) |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Pipeline with the given ID exists
    - At least one valid field is provided and passes validation

    ### ❌ Failure
    - No fields provided → 422 (Pydantic validation)
    - Empty name or description after trim → 422 (Pydantic validation)
    - Unknown ID → 404
    - Any other exception → 500

    ## Examples

    ### Request
    ```json
    {
      "name": "vehicle-detection-v2",
      "description": "Updated pipeline with better preprocessing",
      "tags": ["updated", "v2"]
    }
    ```

    ### Success Response (200)
    ```json
    {
      "id": "pipeline-a3f5d9e1",
      "name": "vehicle-detection-v2",
      "description": "Updated pipeline with better preprocessing",
      "source": "USER_CREATED",
      "tags": ["updated", "v2"],
      "variants": [...],
      "thumbnail": null,
      "created_at": "2026-02-05T14:30:45.123000+00:00",
      "modified_at": "2026-02-05T15:45:00.456000+00:00"
    }
    ```

    ### Error Response (422)
    ```json
    {
      "detail": [
        {
          "type": "value_error",
          "msg": "Value error, At least one of 'name', 'description', or 'tags' must be provided."
        }
      ]
    }
    ```
    """
    try:
        updated_pipeline = PipelineManager().update_pipeline(
            pipeline_id=pipeline_id,
            name=body.name,
            description=body.description,
            tags=body.tags,
        )
        return _internal_pipeline_to_api(updated_pipeline)
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
    summary="Optimize Variant",
    status_code=202,
    responses={
        202: {
            "description": "Optimization job successfully started",
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
    **Start asynchronous optimization job for a pipeline variant.**

    ## Operation
    1. Validate that pipeline and variant exist
    2. Delegate to `OptimizationManager.run_optimization()` with variant
    3. Return generated job ID

    > **Note:** Optimization works with both read-only (PREDEFINED) and user-created variants.
    > The optimization job uses the variant's graphs as input but does not modify the original variant.

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline containing the variant
    - `variant_id` - ID of the variant to optimize

    ## Request Body
    **`PipelineRequestOptimize`** with:
    - `type` *(required)* - Optimization type: `"preprocess"` or `"optimize"`
    - `parameters` *(optional)* - Optimizer-specific options, e.g.:
      ```json
      {
        "search_duration": 300,
        "sample_duration": 10
      }
      ```

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 202 | `OptimizationJobResponse` with `job_id` of created job |
    | 404 | `MessageResponse` - Pipeline or variant with given IDs do not exist |
    | 500 | `MessageResponse` - Unexpected error (e.g., graph conversion) |

    ## Conditions

    ### ✅ Success
    - Pipeline and variant exist
    - Variant's graph can be converted to a launch string
    - OptimizationManager starts a background job

    ### ❌ Failure
    - Unknown pipeline or variant ID → 404
    - Unhandled exception in pipeline/variant lookup or job creation → 500

    ## Examples

    ### Request
    ```json
    {
      "type": "optimize",
      "parameters": {
        "search_duration": 300,
        "sample_duration": 10
      }
    }
    ```

    ### Success Response (202)
    ```json
    {
      "job_id": "opt789"
    }
    ```
    """
    try:
        # Use get_variant_by_ids to validate both pipeline and variant exist
        internal_variant = PipelineManager().get_variant_by_ids(pipeline_id, variant_id)

        # Convert API request to internal type at the route boundary
        internal_request = _optimize_request_to_internal(body)

        job_id = OptimizationManager().run_optimization(
            internal_variant, internal_request
        )
        return JSONResponse(
            content=schemas.OptimizationJobResponse(job_id=job_id).model_dump(),
            status_code=202,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            logger.warning(
                "Pipeline or variant not found for optimization request: %s",
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
    summary="Delete Pipeline",
    responses={
        200: {
            "description": "Pipeline successfully deleted",
            "model": schemas.MessageResponse,
        },
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
    **Delete a pipeline by its ID.**

    ## Operation
    1. Validate that pipeline exists
    2. Validate that pipeline is not PREDEFINED
    3. Delegate to `PipelineManager.delete_pipeline_by_id()`

    > **Note:** PREDEFINED pipelines cannot be deleted. They are loaded from
    > configuration files and include thumbnail images.

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline to delete

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `MessageResponse` confirming deletion |
    | 400 | `MessageResponse` - Trying to delete PREDEFINED pipeline |
    | 404 | `MessageResponse` - Pipeline with given ID does not exist |

    ## Conditions

    ### ✅ Success
    - Pipeline with the given ID is found
    - Pipeline is USER_CREATED (not PREDEFINED)
    - Pipeline is removed from manager

    ### ❌ Failure
    - Pipeline is PREDEFINED → 400
    - Unknown ID → 404

    ## Examples

    ### Success Response (200)
    ```json
    {
      "message": "Pipeline deleted"
    }
    ```

    ### Error Response (400)
    ```json
    {
      "message": "Cannot delete PREDEFINED pipeline 'pipeline-a3f5d9e1'."
    }
    ```

    ### Error Response (404)
    ```json
    {
      "message": "Pipeline with id 'pipeline-unknown' not found."
    }
    ```
    """
    try:
        PipelineManager().delete_pipeline_by_id(pipeline_id)
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
    summary="Create Variant",
    status_code=201,
    responses={
        201: {
            "description": "Variant successfully created",
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
    **Create a new variant for an existing pipeline.**

    ## Operation
    1. Validate that pipeline exists
    2. Delegate to `PipelineManager.add_variant()`
    3. Return created variant with generated ID and timestamps

    ## Auto-Generated Fields
    The backend automatically sets:
    - Variant ID (generated from variant name)
    - `read_only=false` (user-created variants are never read-only)
    - `created_at` timestamp (current UTC time)
    - `modified_at` timestamp (same as `created_at` initially)
    - Pipeline's `modified_at` timestamp is also updated

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline to add variant to

    ## Request Body
    **`VariantCreate`** with:
    - `name` *(required)* - Variant name (non-empty)
    - `pipeline_graph` *(required)* - Advanced graph representation
    - `pipeline_graph_simple` *(required)* - Simplified graph representation

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 201 | Complete Variant object with generated `id`, `read_only=false`, and timestamps |
    | 400 | `MessageResponse` - Invalid variant definition |
    | 404 | `MessageResponse` - Pipeline does not exist |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Pipeline exists
    - Variant definition is valid
    - Variant is successfully added

    ### ❌ Failure
    - Pipeline not found → 404
    - Invalid variant definition → 400
    - Any other exception → 500

    ## Examples

    ### Request
    ```json
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
    ```

    ### Success Response (201)
    ```json
    {
      "id": "gpu",
      "name": "GPU",
      "read_only": false,
      "pipeline_graph": {...},
      "pipeline_graph_simple": {...},
      "created_at": "2026-02-05T14:30:45.123000+00:00",
      "modified_at": "2026-02-05T14:30:45.123000+00:00"
    }
    ```
    """
    try:
        # Convert API PipelineGraph to Graph objects
        graph = Graph.from_dict(body.pipeline_graph.model_dump())
        graph_simple = Graph.from_dict(body.pipeline_graph_simple.model_dump())

        new_variant = PipelineManager().add_variant(
            pipeline_id=pipeline_id,
            name=body.name,
            pipeline_graph=graph,
            pipeline_graph_simple=graph_simple,
        )

        api_variant = _internal_variant_to_api(new_variant)

        logger.info(f"Created variant {new_variant.id} for pipeline {pipeline_id}")
        return JSONResponse(
            content=api_variant.model_dump(mode="json"),
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
    summary="Delete Variant",
    responses={
        200: {
            "description": "Variant successfully deleted",
            "model": schemas.MessageResponse,
        },
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
    **Delete a variant from a pipeline.**

    ## Operation
    1. Validate that pipeline and variant exist
    2. Check that variant is not read-only
    3. Check that variant is not the last one
    4. Delegate to `PipelineManager.delete_variant()`
    5. Pipeline's `modified_at` timestamp is updated

    ## Restrictions
    **Cannot delete:**
    - Read-only variants (from PREDEFINED pipelines)
    - The last remaining variant of a pipeline

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline containing the variant
    - `variant_id` - ID of the variant to delete

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `MessageResponse` confirming deletion |
    | 400 | `MessageResponse` - Trying to delete read-only or last variant |
    | 404 | `MessageResponse` - Pipeline or variant not found |

    ## Conditions

    ### ✅ Success
    - Pipeline and variant exist
    - Variant is not read-only
    - Variant is not the last one
    - Variant is successfully deleted
    - Pipeline's `modified_at` is updated

    ### ❌ Failure
    - Pipeline or variant not found → 404
    - Variant is read-only → 400
    - Variant is last one → 400

    ## Examples

    ### Success Response (200)
    ```json
    {
      "message": "Variant deleted"
    }
    ```

    ### Error Response (400 - Read-only)
    ```json
    {
      "message": "Cannot delete read-only variant 'variant-1'."
    }
    ```

    ### Error Response (400 - Last Variant)
    ```json
    {
      "message": "Cannot delete variant 'variant-1' as it is the last variant in pipeline 'pipeline-a3f5d9e1'."
    }
    ```
    """
    try:
        PipelineManager().delete_variant(pipeline_id, variant_id)
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
    summary="Update Variant",
    responses={
        200: {"description": "Variant successfully updated", "model": schemas.Variant},
        400: {
            "description": "Invalid request or cannot update read-only variant",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Pipeline or variant not found",
            "model": schemas.MessageResponse,
        },
        422: {"description": "Validation error", "model": schemas.MessageResponse},
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
    },
)
def update_variant(pipeline_id: str, variant_id: str, body: schemas.VariantUpdate):
    """
    **Update an existing variant.**

    ## Operation
    1. Validate request body via `VariantUpdate` model
    2. Validate that pipeline and variant exist
    3. Check that variant is not read-only
    4. Delegate to `PipelineManager.update_variant()`
    5. Backend automatically updates variant's and pipeline's `modified_at` timestamps

    ## Immutable Fields
    The following fields **cannot** be updated via API:
    - `id` - Immutable identifier
    - `read_only` - Immutable flag
    - `created_at` - Immutable creation timestamp
    - `modified_at` - Automatically updated by backend

    ## Restrictions
    - Only one of `pipeline_graph` or `pipeline_graph_simple` can be provided per request
    - Cannot update read-only variants (from PREDEFINED pipelines)

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline containing the variant
    - `variant_id` - ID of the variant to update

    ## Request Body
    **`VariantUpdate`** (validated by Pydantic) - any combination of:
    - `name` *(optional)* - Variant name (non-empty after trim)
    - `pipeline_graph` *(optional)* - Advanced graph (mutually exclusive with `pipeline_graph_simple`)
    - `pipeline_graph_simple` *(optional)* - Simplified graph (mutually exclusive with `pipeline_graph`)

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | Updated Variant object with new `modified_at` |
    | 400 | `MessageResponse` - Variant is read-only |
    | 404 | `MessageResponse` - Pipeline or variant not found |
    | 422 | Pydantic validation error (no fields, both graphs, or empty name) |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Pipeline and variant exist
    - Variant is not read-only
    - At least one field provided
    - At most one graph field provided
    - Name is non-empty after trim (if provided)
    - Variant is successfully updated
    - Variant's and pipeline's `modified_at` are updated

    ### ❌ Failure
    - Pipeline or variant not found → 404
    - Variant is read-only → 400
    - Invalid request (no fields, both graphs, empty name) → 422 (Pydantic validation)
    - Any other exception → 500

    ## Examples

    ### Request (Update Name)
    ```json
    {
      "name": "GPU-optimized"
    }
    ```

    ### Request (Update Advanced Graph)
    ```json
    {
      "pipeline_graph": {
        "nodes": [...],
        "edges": [...]
      }
    }
    ```

    ### Success Response (200)
    ```json
    {
      "id": "variant-1",
      "name": "GPU-optimized",
      "read_only": false,
      "pipeline_graph": {...},
      "pipeline_graph_simple": {...},
      "created_at": "2026-02-05T14:30:45.123000+00:00",
      "modified_at": "2026-02-05T15:45:00.456000+00:00"
    }
    ```

    ### Error Response (400 - Read-only)
    ```json
    {
      "message": "Cannot update read-only variant 'variant-1'."
    }
    ```

    ### Error Response (422 - Empty Name)
    ```json
    {
      "detail": [
        {
          "type": "value_error",
          "msg": "Value error, Field 'name' must not be empty."
        }
      ]
    }
    ```
    """
    try:
        # Convert API PipelineGraph to Graph objects if provided
        graph = (
            Graph.from_dict(body.pipeline_graph.model_dump())
            if body.pipeline_graph is not None
            else None
        )
        graph_simple = (
            Graph.from_dict(body.pipeline_graph_simple.model_dump())
            if body.pipeline_graph_simple is not None
            else None
        )

        updated_variant = PipelineManager().update_variant(
            pipeline_id=pipeline_id,
            variant_id=variant_id,
            name=body.name,
            pipeline_graph=graph,
            pipeline_graph_simple=graph_simple,
        )

        api_variant = _internal_variant_to_api(updated_variant)

        logger.info(f"Updated variant {variant_id} in pipeline {pipeline_id}")
        return api_variant

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


@router.post(
    "/{pipeline_id}/variants/{variant_id}/convert-to-simple",
    operation_id="convert_advanced_to_simple",
    summary="Convert to Simple Graph",
    responses={
        200: {
            "description": "Successfully converted to simplified graph",
            "model": schemas.PipelineGraph,
        },
        400: {
            "description": "Invalid graph or conversion failed",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Pipeline or variant not found",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Internal server error", "model": schemas.MessageResponse},
    },
)
def convert_advanced_to_simple(
    pipeline_id: str, variant_id: str, body: schemas.PipelineGraph
):
    """
    **Convert advanced pipeline graph to simplified view (read-only operation).**

    ## Operation
    1. Validate that pipeline and variant exist
    2. Convert provided advanced graph (PipelineGraph) to Graph object
    3. Validate advanced graph and generate simplified view
    4. Return simplified graph **without modifying the variant**

    > **Note:** This is a read-only conversion. To save changes, use
    > `PATCH /{pipeline_id}/variants/{variant_id}` with `pipeline_graph`.

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline containing the variant
    - `variant_id` - ID of the variant (used for context/validation)

    ## Request Body
    **`PipelineGraph`** - Advanced graph with all pipeline elements to convert

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `PipelineGraph` representing the simplified view |
    | 400 | `MessageResponse` - Invalid graph or conversion failed |
    | 404 | `MessageResponse` - Pipeline or variant not found |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Pipeline and variant exist
    - Advanced graph is valid and can be converted to GStreamer pipeline
    - Simplified view is generated successfully

    ### ❌ Failure
    - Pipeline or variant not found → 404
    - Invalid graph structure → 400
    - Conversion error → 400
    - Any other exception → 500

    ## Examples

    ### Request
    ```json
    {
      "nodes": [
        {"id": "0", "type": "filesrc", "data": {"location": "video.mp4"}},
        {"id": "1", "type": "queue", "data": {}},
        {"id": "2", "type": "gvadetect", "data": {"model": "detection"}},
        {"id": "3", "type": "fakesink", "data": {}}
      ],
      "edges": [
        {"id": "0", "source": "0", "target": "1"},
        {"id": "1", "source": "1", "target": "2"},
        {"id": "2", "source": "2", "target": "3"}
      ]
    }
    ```

    ### Success Response (200)
    ```json
    {
      "nodes": [
        {"id": "0", "type": "filesrc", "data": {"location": "video.mp4"}},
        {"id": "2", "type": "gvadetect", "data": {"model": "detection"}},
        {"id": "3", "type": "fakesink", "data": {}}
      ],
      "edges": [
        {"id": "0", "source": "0", "target": "2"},
        {"id": "1", "source": "2", "target": "3"}
      ]
    }
    ```
    """
    try:
        # Validate pipeline and variant exist
        manager = PipelineManager()

        # Convert PipelineGraph to Graph object
        advanced_graph = Graph.from_dict(body.model_dump())

        # Validate and convert to simple view
        simple_graph = manager.validate_and_convert_advanced_to_simple(advanced_graph)

        # Convert back to PipelineGraph for response
        result = schemas.PipelineGraph.model_validate(simple_graph.to_dict())

        logger.info(
            f"Converted advanced graph to simple for variant {variant_id} in pipeline {pipeline_id}"
        )
        return result

    except ValueError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning("Pipeline or variant not found: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=404,
            )
        else:
            logger.error("Invalid graph for conversion: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=400,
            )
    except Exception as e:
        logger.debug(
            "Unexpected error while converting advanced to simple graph",
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to convert graph: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/{pipeline_id}/variants/{variant_id}/convert-to-advanced",
    operation_id="convert_simple_to_advanced",
    summary="Convert to Advanced Graph",
    responses={
        200: {
            "description": "Successfully converted to advanced graph",
            "model": schemas.PipelineGraph,
        },
        400: {
            "description": "Invalid graph or conversion failed",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Pipeline or variant not found",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Internal server error", "model": schemas.MessageResponse},
    },
)
def convert_simple_to_advanced(
    pipeline_id: str, variant_id: str, body: schemas.PipelineGraph
):
    """
    **Convert simplified pipeline graph to advanced view (read-only operation).**

    ## Operation
    1. Validate that pipeline and variant exist
    2. Convert provided simple graph (PipelineGraph) to Graph object
    3. Validate simple graph changes and merge into advanced view
    4. Return updated advanced graph **without modifying the variant**

    > **Note:** This is a read-only conversion. The conversion uses the variant's current
    > advanced graph as base and applies property changes from the simple graph.
    >
    > To save changes, use `PATCH /{pipeline_id}/variants/{variant_id}` with `pipeline_graph_simple`.
    >
    > **Only property modifications are allowed.** Structural changes (adding/removing
    > nodes or edges) will be rejected.

    ## Path Parameters
    - `pipeline_id` - ID of the pipeline containing the variant
    - `variant_id` - ID of the variant whose advanced graph is used as base

    ## Request Body
    **`PipelineGraph`** - Simplified graph with property changes to apply

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `PipelineGraph` representing the updated advanced view |
    | 400 | `MessageResponse` - Invalid graph, structural changes, or merge failed |
    | 404 | `MessageResponse` - Pipeline or variant not found |
    | 500 | `MessageResponse` - Unexpected error |

    ## Conditions

    ### ✅ Success
    - Pipeline and variant exist
    - Simple graph contains **only property changes** (no structural changes)
    - Changes can be merged into advanced graph
    - Resulting advanced graph is valid

    ### ❌ Failure
    - Pipeline or variant not found → 404
    - Structural changes detected (nodes/edges added/removed) → 400
    - Invalid resulting graph → 400
    - Any other exception → 500

    ## Examples

    ### Request
    ```json
    {
      "nodes": [
        {"id": "0", "type": "filesrc", "data": {"location": "new_video.mp4"}},
        {"id": "2", "type": "gvadetect", "data": {"model": "new_model"}},
        {"id": "3", "type": "fakesink", "data": {}}
      ],
      "edges": [
        {"id": "0", "source": "0", "target": "2"},
        {"id": "1", "source": "2", "target": "3"}
      ]
    }
    ```

    ### Success Response (200)
    ```json
    {
      "nodes": [
        {"id": "0", "type": "filesrc", "data": {"location": "new_video.mp4"}},
        {"id": "1", "type": "queue", "data": {}},
        {"id": "2", "type": "gvadetect", "data": {"model": "new_model"}},
        {"id": "3", "type": "fakesink", "data": {}}
      ],
      "edges": [
        {"id": "0", "source": "0", "target": "1"},
        {"id": "1", "source": "1", "target": "2"},
        {"id": "2", "source": "2", "target": "3"}
      ]
    }
    ```

    ### Error Response (400 - Structural Change)
    ```json
    {
      "message": "Invalid pipeline_graph_simple: Node additions are not supported in simple view. Added nodes: 4. Please use advanced view to add new nodes."
    }
    ```
    """
    try:
        # Validate pipeline and variant exist
        manager = PipelineManager()
        variant = manager.get_variant_by_ids(pipeline_id, variant_id)

        # Convert PipelineGraph to Graph object
        simple_graph = Graph.from_dict(body.model_dump())

        # Validate and convert to advanced view
        advanced_graph = manager.validate_and_convert_simple_to_advanced(
            variant, simple_graph
        )

        # Convert back to PipelineGraph for response
        result = schemas.PipelineGraph.model_validate(advanced_graph.to_dict())

        logger.debug(
            f"Converted simple graph to advanced for variant {variant_id} in pipeline {pipeline_id}"
        )
        return result

    except ValueError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning("Pipeline or variant not found: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=404,
            )
        else:
            logger.error("Invalid graph for conversion: %s", e)
            return JSONResponse(
                content=schemas.MessageResponse(message=error_message).model_dump(),
                status_code=400,
            )
    except Exception as e:
        logger.error(
            "Unexpected error while converting simple to advanced graph",
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message=f"Failed to convert graph: {str(e)}"
            ).model_dump(),
            status_code=500,
        )


# ------------------------------------------------------------------
# Conversion helpers: API types <-> internal types
#
# These functions are used at the route boundary to convert between
# API schema types (Pydantic models from api.api_schemas) and internal
# types (dataclasses from internal_types). Managers work exclusively
# with internal types.
# ------------------------------------------------------------------


def _internal_variant_to_api(variant: InternalVariant) -> schemas.Variant:
    """
    Convert InternalVariant to API Variant.

    Converts Graph objects to PipelineGraph Pydantic models.

    Args:
        variant: InternalVariant from PipelineManager.

    Returns:
        API Variant Pydantic model.
    """
    return schemas.Variant(
        id=variant.id,
        name=variant.name,
        read_only=variant.read_only,
        pipeline_graph=schemas.PipelineGraph.model_validate(
            variant.pipeline_graph.to_dict()
        ),
        pipeline_graph_simple=schemas.PipelineGraph.model_validate(
            variant.pipeline_graph_simple.to_dict()
        ),
        created_at=variant.created_at,
        modified_at=variant.modified_at,
    )


def _internal_pipeline_to_api(pipeline: InternalPipeline) -> schemas.Pipeline:
    """
    Convert InternalPipeline to API Pipeline.

    Converts all variants and maps InternalPipelineSource to API PipelineSource.

    Args:
        pipeline: InternalPipeline from PipelineManager.

    Returns:
        API Pipeline Pydantic model.
    """
    return schemas.Pipeline(
        id=pipeline.id,
        name=pipeline.name,
        description=pipeline.description,
        source=schemas.PipelineSource(pipeline.source.value),
        tags=pipeline.tags,
        variants=[_internal_variant_to_api(v) for v in pipeline.variants],
        thumbnail=pipeline.thumbnail,
        created_at=pipeline.created_at,
        modified_at=pipeline.modified_at,
    )


def _pipeline_definition_to_internal(
    api_def: schemas.PipelineDefinition,
) -> InternalPipelineDefinition:
    """
    Convert API PipelineDefinition to internal representation.

    Converts PipelineGraph fields in each VariantCreate to Graph objects.

    Args:
        api_def: API PipelineDefinition from request body.

    Returns:
        InternalPipelineDefinition with Graph objects.
    """
    internal_variants = []
    for vc in api_def.variants:
        internal_variants.append(
            InternalVariantCreate(
                name=vc.name,
                pipeline_graph=Graph.from_dict(vc.pipeline_graph.model_dump()),
                pipeline_graph_simple=Graph.from_dict(
                    vc.pipeline_graph_simple.model_dump()
                ),
            )
        )

    return InternalPipelineDefinition(
        name=api_def.name,
        description=api_def.description,
        source=InternalPipelineSource(api_def.source.value),
        tags=api_def.tags,
        variants=internal_variants,
    )


def _optimize_request_to_internal(
    api_request: schemas.PipelineRequestOptimize,
) -> InternalPipelineRequestOptimize:
    """
    Convert API PipelineRequestOptimize to internal representation.

    Args:
        api_request: API optimization request.

    Returns:
        InternalPipelineRequestOptimize with mapped type and parameters.
    """
    return InternalPipelineRequestOptimize(
        type=InternalOptimizationType(api_request.type.value),
        parameters=api_request.parameters,
    )


def _pipeline_validation_to_internal(
    api_request: schemas.PipelineValidation,
) -> InternalPipelineValidation:
    """
    Convert API PipelineValidation to internal representation.

    Converts the API PipelineGraph to internal Graph object.

    Args:
        api_request: API validation request.

    Returns:
        InternalPipelineValidation with Graph object and parameters.
    """
    graph = Graph.from_dict(api_request.pipeline_graph.model_dump())
    return InternalPipelineValidation(
        pipeline_graph=graph,
        parameters=api_request.parameters,
    )
