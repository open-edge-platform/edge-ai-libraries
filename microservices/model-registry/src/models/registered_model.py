# pylint: disable=redefined-builtin
"""Module for Registered model class"""
import json
import ast
from typing import Dict, List, Union, Any, Optional
from pydantic import BaseModel, ConfigDict
from fastapi import Form, File, UploadFile, HTTPException, status


class RegisteredModel:
    """RegisteredModel class"""
    id: str
    name: str
    target_device: str
    created_date: str
    last_updated_date: str
    size: int
    version: str
    format: str
    origin: str
    file_url: str
    project_id: str
    project_name: str
    category: str
    fps_throughput: str
    latency: str
    target_device_type: str
    previous_revision_id: str
    previous_trained_revision_id: str
    score: float
    score_up_to_date: bool
    performance: Dict[str, str]
    precision: List[str]
    label_schema_in_sync: bool
    overview: Dict[str, str]
    optimization_capabilities: Dict[str, str]
    model_group_id: str
    labels: List[Dict[str, str]]
    architecture: str

    def __init__(self, id: str = None, name: str = None, target_device: str = None, created_date: str = None, last_updated_date: str = None, size: int = None, version: str = None, format: str = None, origin: str = None, file_url: str = None, project_id: str = None, project_name: str = None, category: str = None, fps_throughput: str = None, latency: str = None, target_device_type: str = None, previous_revision_id: str = None, previous_trained_revision_id: str = None, score: float = None, score_up_to_date: bool = None, performance: Dict[str, str] = None, precision: List[str] = None, label_schema_in_sync: bool = None, overview: Dict[str, str] = None, optimization_capabilities: Dict[str, str] = None, model_group_id: str = None, labels: List[Dict[str, str]] = None, architecture: str = None):
        self.id = id
        self.name = name
        self.target_device = target_device
        self.created_date = created_date
        self.last_updated_date = last_updated_date
        self.size = size
        self.version = version
        self.format = format
        self.origin = origin
        self.file_url = file_url
        self.project_id = project_id
        self.project_name = project_name
        self.category = category
        self.fps_throughput = fps_throughput
        self.latency = latency
        self.target_device_type = target_device_type
        self.previous_revision_id = previous_revision_id
        self.previous_trained_revision_id = previous_trained_revision_id
        self.score = score
        self.score_up_to_date = score_up_to_date
        self.performance = performance
        self.precision = precision
        self.label_schema_in_sync = label_schema_in_sync
        self.overview = overview
        self.optimization_capabilities = optimization_capabilities
        self.model_group_id = model_group_id
        self.labels = labels
        self.architecture = architecture


class ModelIn:
    """RegisteredModel class representation for HTTP Request"""

    def __init__(self,
                 file: UploadFile = File(
                     ..., description="The ZIP file containing model files and related artifacts."),
                 name: str = Form(..., description="The human-readable name of the model.",
                                  examples=["Sample Model Name"]),
                 version: str = Form(..., description="The version of the model (e.g., 1.0, 1A, v2).", examples=[
                                     "1.0"]),
                 target_device: str = Form(
                     None, description="The hardware platform the model is designed to run on (e.g., CPU, GPU, FPGA).", examples=[""]),
                 precision: str = Form(
                     None, description="The precision of the model (e.g., FP32, FP16, INT8, INT4). Defaults to FP32.", examples=[""]),
                 format: str = Form(
                     None, description="The format of the model (e.g. openvino, pytorch).", examples=[""]),
                 score: float = Form(
                     None, description="A metric that represents the model's performance.", examples=["0.0"]),
                 id: str = Form(
                     None, description="A unique identifier for the model.", examples=[""]),
                 created_date: str = Form(
                     None, description="The date and time the model was first created or trained. If empty, this will be the date and time the model was registered.(e.g. 2024-02-28 15:39:07.054000)", examples=[""]),
                 size: int = Form(
                     None, description="The storage space occupied by the model files (e.g., in bytes).", examples=["0"]),
                 origin: str = Form(
                     None, description="The source of the model (e.g., geti), or where it was obtained from.", examples=[""]),
                 project_id: str = Form(
                     None, description="The unique identifier of the project the model belongs to, if applicable.", examples=[""]),
                 project_name: str = Form(
                     None, description="The human-readable name of the project the model belongs to, if applicable.", examples=[""]),
                 category: str = Form(
                     None, description="The category associated to the labels used by the model (e.g. Detection, Classification, etc.).", examples=[""]),
                 target_device_type: str = Form(
                     None, description="A more specific categorization of the target device (e.g., client, edge, cloud).", examples=[""]),
                 overview: Union[str, dict[str, str], None] = Form(None, description="A general description of the model's purpose, function, and intended use cases. (e.g. {\"description\":\"The description of the model\"})", examples=[
                                                                   "{\"description\":\"The description of the model\"}"]),
                 optimization_capabilities: Union[str, dict[str, str], None] = Form(
                     None, description="If applicable, information about any specific optimizations made to the model, such as for speed, accuracy, or size reduction.", examples=["{\"optimization\":\"accuracy\"}"]),
                 labels: Union[str, List[Any]] = Form(None, description="A list of categories or classes the model can predict, if applicable.", examples=[
                                                      "\"[" + "\\" + "\"" + "class A" + "\\" + "\"" + "," + "\\" + "\"" + "class B" + "\\" + "\"" + "]" + "\""]),
                 architecture: str = Form(None, description="The type of machine learning architecture used.", examples=[""])):
        self.file = file
        self.name = name
        self.target_device = target_device
        self.precision = precision
        self.version = version
        self.format = format
        self.score = score
        self.id = id
        self.created_date = created_date
        self.size = size
        self.origin = origin
        self.project_id = project_id
        self.project_name = project_name
        self.category = category
        self.target_device_type = target_device_type
        self.overview = ModelIn.val_to_correct_type("overview", overview)
        self.optimization_capabilities = ModelIn.val_to_correct_type(
            "optimization_capabilities", optimization_capabilities)
        self.labels = ModelIn.val_to_correct_type("labels", labels)
        self.architecture = architecture

    @classmethod
    def val_to_correct_type(cls, var_name, val):
        """Convert the provided value to the expected type and verify

        Args:
            var_name: The name of the variable
            val: The provided value to be convert to the expected type if possible

        Returns:
            dict | list | None: The dictionary or list representation of the provided value or None
        """
        v = val
        msg = ""
        try:
            if isinstance(val, str):
                if var_name in ("overview", "optimization_capabilities"):
                    msg = f"{var_name} is not a valid JSON object."
                    v = json.loads(val)
                elif var_name == "labels":
                    msg = f"{var_name} is not a valid list."
                    v = ast.literal_eval(val)

                    if not isinstance(v, list):
                        raise ValueError()

        except Exception as exc:
            s_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            raise HTTPException(status_code=s_code, detail=msg) from exc

        return v


class UpdateModelIn:
    """RegisteredModel class representation for HTTP Request"""

    def __init__(self,
                 name: str = Form(
                     None, description="The human-readable name of the model.", examples=[""]),
                 version: str = Form(
                     None, description="The version of the model (e.g., 1.0, 1A, v2).", examples=[""]),
                 target_device: str = Form(
                     None, description="The hardware platform the model is designed to run on (e.g., CPU, GPU, FPGA).", examples=[""]),
                 precision: str = Form(
                     None, description="The precision of the model (e.g., FP32, FP16, INT8, INT4).", examples=[""]),
                 format: str = Form(
                     None, description="The format of the model (e.g. openvino, pytorch).", examples=[""]),
                 score: float = Form(
                     None, description="A metric that represents the model's performance.", examples=[""]),
                 created_date: str = Form(
                     None, description="The date and time the model was first created or trained. If empty, this will be the date and time the model was registered.(e.g. 2024-02-28 15:39:07.054000)", examples=[""]),
                 size: int = Form(
                     None, description="The storage space occupied by the model files (e.g., in bytes).", examples=[""]),
                 origin: str = Form(
                     None, description="The source of the model (e.g., geti), or where it was obtained from.", examples=[""]),
                 project_id: str = Form(
                     None, description="The unique identifier of the project the model belongs to, if applicable.", examples=[""]),
                 project_name: str = Form(
                     None, description="The human-readable name of the project the model belongs to, if applicable.", examples=[""]),
                 category: str = Form(
                     None, description="The category associated to the labels used by the model (e.g. Detection, Classification, etc.).", examples=[""]),
                 target_device_type: str = Form(
                     None, description="A more specific categorization of the target device (e.g., client, edge, cloud).", examples=[""]),
                 overview: Union[str, dict[str, str], None] = Form(
                     None, description="A general description of the model's purpose, function, and intended use cases. (e.g. {\"description\":\"The description of the model\"})", examples=[""]),
                 optimization_capabilities: Union[str, dict[str, str], None] = Form(
                     None, description="If applicable, information about any specific optimizations made to the model, such as for speed, accuracy, or size reduction.", examples=[""]),
                 labels: Union[str, List[Any]] = Form(
                     None, description="A list of categories or classes the model can predict, if applicable.", examples=[""]),
                 architecture: str = Form(None, description="The type of machine learning architecture used.", examples=[""])):
        self.name = name
        self.target_device = target_device
        self.precision = precision
        self.version = version
        self.format = format
        self.score = score
        self.created_date = created_date
        self.size = size
        self.origin = origin
        self.project_id = project_id
        self.project_name = project_name
        self.category = category
        self.target_device_type = target_device_type
        self.overview = UpdateModelIn.val_to_correct_type("overview", overview)
        self.optimization_capabilities = UpdateModelIn.val_to_correct_type(
            "optimization_capabilities", optimization_capabilities)
        self.labels = UpdateModelIn.val_to_correct_type("labels", labels)
        self.architecture = architecture

    @classmethod
    def val_to_correct_type(cls, var_name, val):
        """Convert the provided value to the expected type and verify

        Args:
            var_name: The name of the variable
            val: The provided value to be convert to the expected type if possible

        Returns:
            dict | list | None: The dictionary or list representation of the provided value or None
        """
        v = val
        msg = ""
        try:
            if isinstance(val, str):
                if var_name in ("overview", "optimization_capabilities"):
                    msg = f"{var_name} is not a valid JSON object."
                    v = json.loads(val)
                elif var_name == "labels":
                    msg = f"{var_name} is not a valid list."
                    v = ast.literal_eval(val)

                    if not isinstance(v, list):
                        raise ValueError()

        except Exception as exc:
            s_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            raise HTTPException(status_code=s_code, detail=msg) from exc

        return v


class RegisteredModelOut(BaseModel):
    """RegisteredModel class representation for HTTP Response"""
    id: str
    name: str
    target_device: str
    created_date: str
    last_updated_date: str
    precision: Optional[List[str]]
    size: Optional[int]
    version: str
    format: Optional[str]
    origin: Optional[str]
    file_url: str
    project_id: Optional[str]
    project_name: Optional[str]
    category: Optional[str]
    target_device_type: Optional[str]
    score: Optional[float]
    overview: Union[str, Dict[str, Any], None]
    optimization_capabilities: Union[str, Dict[str, Any], None]
    labels: Union[List[str], List[Dict[str, Any]], None]
    architecture: Optional[str]

    model_config = ConfigDict(protected_namespaces=())
