from typing import List
from fastapi import APIRouter

import api.api_schemas as schemas
from models import get_supported_models_manager

router = APIRouter()


@router.get("", operation_id="get_models", response_model=List[schemas.Model])
def get_models():
    supported_models_manager = get_supported_models_manager()
    models = supported_models_manager.get_all_installed_models()

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
