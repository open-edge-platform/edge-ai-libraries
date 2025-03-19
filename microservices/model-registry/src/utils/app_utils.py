"""Module containing functions used across the project"""
import os
import re
from enum import Enum
from typing import Tuple, List
from fastapi import Response, status, HTTPException, Path
from utils.logging_config import logger

class ResourceType(Enum):
    """Enum to represent the types of resources that can be created."""
    PROJECT = "project"
    MODEL = "model"

def get_version_info():
    """Get the version of the microservice
    Raises:
        ValueError: If the contents of the VERSION file is not in the expected format.
        FileNotFoundError: If the VERSION file does not exist in the project root directory.
    Returns:
        str: The version of the SDK
    """
    app_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    version_file_path = os.path.join(app_root_dir, "VERSION")

    if os.path.isfile(version_file_path):
        with open(version_file_path, "r", encoding="utf-8") as version_file:
            file_contents = version_file.read()
            # Check if the contents of the file is the expected x.y.z form
            reg_ex_pattern = "^[0-9]+\\.[0-9]+\\.[0-9]+$"
            match = re.match(reg_ex_pattern, file_contents)
            if match:
                is_file_contents_valid = len(match.regs) == 1
                if is_file_contents_valid:
                    return match.group()

            raise ValueError("The contents of the VERSION file appears to be invalid.")
    else:
        raise FileNotFoundError(f"File not found: {version_file_path}.")


def check_required_env_vars() -> Tuple[bool, List[str]]: # pragma: no cover
    """Checks if the required environment variables are set.

    Returns:
        A tuple containing a boolean indicating where all required variables are set (True) or not (False) and a list with the names of variable that are not set.
    """
    required_vars = ["MLFLOW_S3_ENDPOINT_URL", "MINIO_HOSTNAME",
                     "MINIO_SERVER_PORT", "MINIO_ACCESS_KEY",
                     "MINIO_SECRET_KEY", "MINIO_BUCKET_NAME",
                     "SERVER_PORT"
                     ]

    is_https_mode_enabled = get_bool(os.getenv("ENABLE_HTTPS_MODE", "True"), ignore_empty=True)
    if is_https_mode_enabled:
        required_vars = required_vars + ["SERVER_CERT",
                                         "CA_CERT",
                                         "SERVER_PRIVATE_KEY"
                                         ]

    missing_vars = [var for var in required_vars if var not in os.environ]

    is_required_env_vars_set = len(missing_vars) == 0

    return is_required_env_vars_set, missing_vars

def get_bool(string: str, var_name: str = None, ignore_empty=False) -> bool:
    """Return a Boolean value corresponding to the provided case-insensitive string.\n
    For example, "yes", "y", "true",  "t", and "1" will return True.\n
    If `ignore_empty=True` and `string` is empty, `True` will be returned.\n
    "no",  "n", "false", "f", "0" and "" will return False.

    Args:
        value (str): A string
        var_name (str, optional): The name of the variable or entity the string is associated with. Defaults to None.
        ignore_empty: If True, empty strings will return True.
    Raises:
        ValueError: If the string doesn't correspond with a Boolean value.
    Returns:
        bool: A Boolean value based on the provided string.
    """

    val = None
    if (string.lower() in ("yes", "y", "true",  "t", "1")) or (ignore_empty and string == ""):
        val =  True
    elif string.lower() in ("no",  "n", "false", "f", "0", ""):
        val =  False

    else:
        if var_name:
            msg = f"Invalid string for Boolean conversion for {var_name}"
        else:
            msg = f"Invalid string for boolean conversion: {string}"

        raise ValueError(msg)

    return val

def validate_id(id: str, resource_type: ResourceType):
    """Check if the given string matches the expected format of an ID.

    Args:
        id_string (str): The string to check.
        resource_type (ResourceType): The type of resource the ID is associated with.

    Raises:
        HTTPException: If the string does not match the expected format.

    Returns:
        str: The ID string if it matches the expected format. 
    """
    id_pattern = re.compile(r'^[a-zA-Z0-9_-]{16,}$')
    is_id_valid = bool(id_pattern.match(id))

    if not is_id_valid:
        raise HTTPException(status_code=400, detail=f"Invalid format for {resource_type.value} ID.")
    return id

def validate_resource_id(resource_type: ResourceType):
    """Factory function to create a dependency function for
    validating the id of a resource in the URL path.

    Args:
        resource_type (ResourceType): The type of resource the ID is associated with.
    """
    def model_id_dependency(model_id: str = Path(...)) -> str:
        """Dependency function to validate the ID of a model in the URL path.

        Args:
            model_id (str): The ID of the model in the URL path.

        Returns:
            str: The ID string if it matches the expected format.
        """
        return validate_id(model_id, resource_type)

    def project_id_dependency(project_id: str = Path(...)) -> str:
        """Dependency function to validate the ID of a project in the URL path.

        Args:
            project_id (str): The ID of the project in the URL path.

        Returns:
            str: The ID string if it matches the expected format.
        """
        return validate_id(project_id, resource_type)

    dependency = model_id_dependency if resource_type == ResourceType.MODEL else project_id_dependency

    return dependency

def get_exception_response(log_msg_prefix: str, e: Exception):
    """Reusable function to handle exceptions and return the appropriate responses.

    Args:
        log_msg_prefix: The HTTP request verb and resource path
        e: The exception raised during the endpoint execution.
        response_content: The content to be sent if value is set
        response_s_code: The response code to be sent if set

    Returns:
        A Response object with the appropriate status code and error message details.
    """
    s_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_class_name = e.__class__.__name__

    if isinstance(e, (UnboundLocalError)):
        error_class_name = "ConnectionError"

    component_names = ("mlflow", "postgres", "minio")
    if any(name in error_class_name.lower() for name in component_names):
        error_class_name = ""

    logger.error(f"{log_msg_prefix} failed with status code: {s_code}. {error_class_name}: {e}")

    if isinstance(e, HTTPException):
        return Response(f"{e.detail}", status_code=status.HTTP_400_BAD_REQUEST)

    return Response(f"{error_class_name}\n\n{e}", status_code=s_code)
