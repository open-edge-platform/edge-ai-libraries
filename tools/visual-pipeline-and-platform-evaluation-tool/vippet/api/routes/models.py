import logging
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from models import SupportedModelsManager

router = APIRouter()
logger = logging.getLogger("api.routes.models")


@router.get(
    "",
    operation_id="get_models",
    summary="List All Models",
    response_model=List[schemas.Model],
    response_description="List of all installed and available models",
)
def get_models():
    """
    **List all installed and available models.**

    ## Operation
    Read the supported models configuration, filter out models that are not
    present on disk, and expose the remaining models in an API-friendly format.

    ## Parameters
    - **Path/Query parameters:** None

    ## Response Format

    ### 200 OK
    JSON array of Model objects.

    **Each model includes:**
    - `name` - Internal model identifier
    - `display_name` - Human-readable model name
    - `category` - Logical model category (`classification`, `detection`) or `null` when type is unknown
    - `precision` - Model precision (e.g., `"FP32"`, `"INT8"`) if available

    ## Conditions

    ### ✅ Success
    - `supported_models.yaml` is loaded correctly by SupportedModelsManager
    - At least zero models are installed on disk (empty list is valid)

    ### ❌ Failure
    - If SupportedModelsManager cannot be initialized (e.g., file missing, invalid YAML),
      the application exits at startup and this endpoint will not be available

    ## Example Response

    ```json
    [
      {
        "name": "vehicle-detection-0202",
        "display_name": "Vehicle Detection",
        "category": "detection",
        "precision": "FP32"
      },
      {
        "name": "person-reidentification-0200",
        "display_name": "Person Reidentification",
        "category": "classification",
        "precision": "INT8"
      }
    ]
    ```
    """
    try:
        models = SupportedModelsManager().get_all_installed_models()

        def to_model_category(model_type: str) -> schemas.ModelCategory | None:
            """
            Convert a string model_type to ModelCategory enum if possible.
            Returns None if the string does not match any ModelCategory value.
            """
            try:
                return schemas.ModelCategory(model_type)
            except ValueError:
                return None

        return [
            schemas.Model(
                name=m.name,
                display_name=m.display_name,
                category=to_model_category(m.model_type),
                precision=m.precision,
            )
            for m in models
        ]
    except Exception:
        logger.error("Failed to list models", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing models"
            ).model_dump(),
            status_code=500,
        )
