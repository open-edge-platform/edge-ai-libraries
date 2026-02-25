import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
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
        return PipelineTemplateManager().get_templates()
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
        return PipelineTemplateManager().get_template_by_id(template_id)
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
