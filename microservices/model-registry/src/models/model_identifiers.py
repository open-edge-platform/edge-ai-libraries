"""Module"""
from typing import List
from pydantic import BaseModel, ConfigDict, Field

class ModelIdentifier(BaseModel):
    """
    ModelIdentifier class
    """
    id: str = Field(serialization_alias="model_id")
    group_id: str = Field(serialization_alias="model_group_id")

class ModelIdentifiersIn(BaseModel):
    """
    Class used to capture active model ids sent in a HTTP request
    """
    models: List[ModelIdentifier]
    __config__ = ConfigDict(extra="ignore")
