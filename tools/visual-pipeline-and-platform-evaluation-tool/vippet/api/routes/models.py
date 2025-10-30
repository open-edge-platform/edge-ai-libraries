from typing import List
from fastapi import APIRouter

import api.api_schemas as schemas
from models import SupportedModelsManager

router = APIRouter()


@router.get("", operation_id="get_models", response_model=List[schemas.Model])
def get_models():
    models = SupportedModelsManager().get_all_available_models()
    return [
        schemas.Model(
            name=m.name,
            display_name=m.display_name,
            category=m.model_type,
            precision=m.display_name.split(" ")[-1].strip("()")
            if "(" in m.display_name
            else None,
        )
        for m in models
    ]
