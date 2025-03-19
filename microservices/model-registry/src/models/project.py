# pylint: disable=redefined-builtin

"""Project class module"""
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

class OptimizedModel(BaseModel):
    """
    OptimizedModel class
    """
    model_config = ConfigDict(coerce_numbers_to_str=True)
    model_config['protected_namespaces'] = ()

    id: str
    name: str
    model_format: str = Field(exclude=True, default=None)
    target_device: str = Field(exclude=True, default=None)
    created_date: str = Field(exclude=True, alias="creation_date", default=None)
    precision: List[str] = Field(exclude=True, default=None)
    project_id: str = Field(exclude=True, default=None)
    size: Optional[int] = Field(exclude=True, default=None)
    version: str = Field(exclude=True, alias="version", default=None)
    origin: str = Field(exclude=True, default=None)
    file_url: str = Field(exclude=True, default=None)
    project_name: str = Field(exclude=True, default=None)
    category: str = Field(exclude=True, default=None)
    target_device_type: Optional[str] = Field(exclude=True, default=None)
    score: float = Field(exclude=True, default=0.0)
    overview: Union[str, Dict[str, Any], None] = Field(exclude=True, default=None)
    optimization_capabilities: Union[str, Dict[str, Any], None] = Field(exclude=True, default=None)
    labels: Optional[List[Dict[str, Any]]] = Field(exclude=True, default=None)
    architecture: str = Field(exclude=True, default=None)

class ModelVersion(BaseModel):
    """
    ModelVersion class
    """
    id: str
    name: str
    version: int
    openvino_models: List[OptimizedModel] = Field(default=[])

class ModelGroup(BaseModel):
    """
    ModelGroup class
    """
    model_config = ConfigDict(protected_namespaces=())
    id: str
    name: str
    model_versions: List[ModelVersion] = Field(alias="models",serialization_alias="model_versions")

class ProjectOut (BaseModel):
    """Project class representation for HTTP Response"""
    model_config = ConfigDict(protected_namespaces=())
    id: str
    name: str
    creation_time: str
    model_groups: List[ModelGroup] = Field(default=[])
    pipeline: Union[Dict[Any, Any], None] = Field(exclude=True, default=None)
