import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from internal_types import InternalPipeline, InternalVariant
from managers.pipeline_template_manager import PipelineTemplateManager

router = APIRouter()
logger = logging.getLogger("api.routes.pipeline_templates")


@router.get(
    "",
    operation_id="get_pipeline_templates",
    response_model=List[schemas.Pipeline],
    responses={
        200: {
            "description": "List of all available pipeline templates",
            "model": List[schemas.Pipeline],
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
def get_pipeline_templates():
    """
    List all available pipeline templates.

    Operation:
        Return all read-only pipeline templates loaded from configuration.
        Properties that require user-supplied values (e.g. input source URI, model paths)
        are stored as empty strings. Use templates as a starting point.

    Path / query parameters:
        None.

    Returns:
        200 OK:
            JSON array of Pipeline objects with ``source=TEMPLATE``.
            Each pipeline includes:
            * id, name, description, source, tags
            * variants (list of Variant objects with graphs and timestamps),
              all variants have ``read_only=True``
            * thumbnail (always null for templates)
            * created_at, modified_at (UTC datetime, serialized as ISO 8601 strings)

    Success conditions:
        * PipelineTemplateManager is initialized (even if no templates are loaded,
          an empty array is returned).

    Failure conditions:
        * Unexpected errors will be returned as 500 Internal Server Error.

    Response example (200):
        .. code-block:: json

            [
              {
                "id": "detect-only",
                "name": "Detect Only",
                "description": "Template pipeline with a single object detection model.",
                "source": "TEMPLATE",
                "tags": ["template", "detection"],
                "variants": [
                  {
                    "id": "cpu",
                    "name": "CPU",
                    "read_only": true,
                    "pipeline_graph": {},
                    "pipeline_graph_simple": {},
                    "created_at": "2026-02-05T14:30:45.123000+00:00",
                    "modified_at": "2026-02-05T14:30:45.123000+00:00"
                  }
                ],
                "thumbnail": null,
                "created_at": "2026-02-05T14:30:45.123000+00:00",
                "modified_at": "2026-02-05T14:30:45.123000+00:00"
              }
            ]
    """
    try:
        internal_templates = PipelineTemplateManager().get_templates()
        return [_internal_pipeline_to_api(t) for t in internal_templates]
    except Exception:
        logger.error("Unexpected error while listing pipeline templates", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing pipeline templates."
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{template_id}",
    operation_id="get_pipeline_template",
    response_model=schemas.Pipeline,
    responses={
        200: {
            "description": "Successful Response",
            "model": schemas.Pipeline,
        },
        404: {
            "description": "Template not found",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Internal server error",
            "model": schemas.MessageResponse,
        },
    },
)
def get_pipeline_template(template_id: str):
    """
    Get a single pipeline template by its ID.

    Operation:
        Look up a template by its unique identifier and return it.

    Path / query parameters:
        template_id: Unique identifier of the template.

    Returns:
        200 OK:
            Pipeline object with ``source=TEMPLATE``.
            Includes:
            * id, name, description, source, tags
            * variants (list of Variant objects with graphs and timestamps),
              all variants have ``read_only=True``
            * thumbnail (always null for templates)
            * created_at, modified_at (UTC datetime, serialized as ISO 8601 strings)
        404 Not Found:
            MessageResponse if a template with the given ID does not exist.
        500 Internal Server Error:
            MessageResponse when an unexpected error occurs.

    Success conditions:
        * Template with the given ID exists.

    Failure conditions:
        * Template with the given ID does not exist – 404 Not Found.
        * Unexpected errors will be returned as 500 Internal Server Error.

    Response example (200):
        .. code-block:: json

            {
              "id": "detect-only",
              "name": "Detect Only",
              "description": "Template pipeline with a single object detection model.",
              "source": "TEMPLATE",
              "tags": ["template", "detection"],
              "variants": [
                {
                  "id": "cpu",
                  "name": "CPU",
                  "read_only": true,
                  "pipeline_graph": {},
                  "pipeline_graph_simple": {},
                  "created_at": "2026-02-05T14:30:45.123000+00:00",
                  "modified_at": "2026-02-05T14:30:45.123000+00:00"
                }
              ],
              "thumbnail": null,
              "created_at": "2026-02-05T14:30:45.123000+00:00",
              "modified_at": "2026-02-05T14:30:45.123000+00:00"
            }
    """
    try:
        internal_template = PipelineTemplateManager().get_template_by_id(template_id)
        return _internal_pipeline_to_api(internal_template)
    except ValueError as exc:
        logger.warning("Pipeline template '%s' not found: %s", template_id, exc)
        return JSONResponse(
            content=schemas.MessageResponse(message=str(exc)).model_dump(),
            status_code=404,
        )
    except Exception:
        logger.error(
            "Unexpected error while retrieving template '%s'",
            template_id,
            exc_info=True,
        )
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while retrieving pipeline template."
            ).model_dump(),
            status_code=500,
        )


# ------------------------------------------------------------------
# Conversion helpers: internal types -> API types
#
# These functions convert InternalPipeline/InternalVariant (from
# internal_types) to API Pipeline/Variant (from api.api_schemas).
# Managers work exclusively with internal types; conversion happens
# at the route boundary.
# ------------------------------------------------------------------


def _internal_variant_to_api(variant: InternalVariant) -> schemas.Variant:
    """
    Convert InternalVariant to API Variant.

    Converts Graph objects to PipelineGraph Pydantic models.

    Args:
        variant: InternalVariant from PipelineTemplateManager.

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
        pipeline: InternalPipeline from PipelineTemplateManager.

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
