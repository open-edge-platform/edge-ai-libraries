# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import json
import zipfile
from io import BytesIO
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Union, Type

import requests
from requests.exceptions import RequestException
from pydantic import TypeAdapter

from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.utils.logging import logger


class HTTPMethod(Enum):
    """Enum for HTTP methods"""
    GET = auto()
    POST = auto()


class GetiResourceProperty(Enum):
    """Enum for Geti resource properties"""
    PROJECTS = "projects"
    MODEL_GROUPS = "model_groups"
    MODELS = "models"
    OPTIMIZED_MODELS = "optimized_models"


class GetiPlugin(ModelDownloadPlugin):
    """
    Plugin for downloading OpenVINO models from Intel Geti Server.
    Interacts with Geti REST API to retrieve and manage models.
    """

    def __init__(self):
        """Initialize the Geti plugin with environment variables"""
        self._server_url = os.environ.get("GETI_HOST")
        self._organization_id = os.environ.get("GETI_ORGANIZATION_ID")
        self._workspace_id = os.environ.get("GETI_WORKSPACE_ID")
        self._server_api_token = os.environ.get("GETI_TOKEN")
        self._server_api_ver = os.environ.get("GETI_SERVER_API_VERSION", "v1")
        self._verify_server_ssl_cert = self._parse_bool(
            os.getenv("GETI_SERVER_SSL_VERIFY", "False"), ignore_empty=True
        )
        self.model_id=None

        if isinstance(self._server_url, str):
            self._server_url = self._server_url + f"/api/{self._server_api_ver}"

        self._geti_req_headers = {
            #"Accept": "application/json",
            "x-api-key": f"{self._server_api_token}",
        }
        self._req_timeout = 30

    @staticmethod
    def _parse_bool(value: str, ignore_empty: bool = False) -> bool:
        """Parse a string value to boolean"""
        if ignore_empty and not value:
            return True
        return value.lower() in ("true", "1", "yes", "on")

    @property
    def plugin_name(self) -> str:
        return "geti"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        """
        Check if this plugin can handle the given model.
        Returns True if hub is 'geti' and all required environment variables are set.
        """
        if hub.lower() != "geti":
            return False

        required_vars = [
            self._server_url,
            self._organization_id,
            self._workspace_id,
            self._server_api_token,
            self._server_api_ver,
        ]

        if any(var is None for var in required_vars):
            logger.warning(
                "One or more Geti environment variables are not set. "
                "Required: GETI_HOST, GETI_ORGANIZATION_ID, GETI_WORKSPACE_ID, "
                "GETI_TOKEN, GETI_SERVER_API_VERSION"
            )
            return False

        return True

    def _validate_env_vars(self) -> None:
        """Validate that all required environment variables are set"""
        if any(
            [
                self._server_url is None,
                self._organization_id is None,
                self._workspace_id is None,
                self._server_api_token is None,
                self._server_api_ver is None,
            ]
        ):
            err_msg = (
                "One or more required environment variables are not set: "
                "GETI_HOST, GETI_ORGANIZATION_ID, GETI_WORKSPACE_ID, "
                "GETI_TOKEN, GETI_SERVER_API_VERSION"
            )
            raise ValueError(err_msg)

    def _send_request(self, method: HTTPMethod, url: str, data=None, headers: Optional[Dict[str, str]] = None):
        """Send HTTP request to Geti server"""
        self._validate_env_vars()

        try:
            # Merge default headers with any overrides (override takes precedence)
            req_headers = dict(self._geti_req_headers)
            if headers:
                req_headers.update(headers)
            
            logger.info(f"Sending {method.name} request to Geti server: {url}")
            logger.info(f"Request headers: {req_headers}")

            if method == HTTPMethod.GET:
                response = requests.get(
                    url, 
                    headers=req_headers, 
                    proxies={'no_proxy': '10.223.22.123'}, 
                    timeout=self._req_timeout, 
                    verify=self._verify_server_ssl_cert
                )
            elif method == HTTPMethod.POST:
                response = requests.post(
                    url, 
                    headers=req_headers, 
                    data=data,
                    proxies={'no_proxy': self._server_url.split('/')[2] if self._server_url else ''}, 
                    timeout=self._req_timeout, 
                    verify=self._verify_server_ssl_cert
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            logger.info(f"Geti {method.name} Response Status Code: {response.status_code}")
            response.raise_for_status()
            return response
            
            
        except RequestException as e:
            logger.error(f"Failed to communicate with Geti server: {e}")
            raise RequestException(f"Failed to get resource from the Geti server: {e}") from e

    def get_resources(
        self,
        url_path: str,
        resource_prop_key: GetiResourceProperty,
        resource_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all resources or a specific resource associated to the resource_id.

        Args:
            url_path (str): The path to the resource
            resource_prop_key (GetiResourceProperty): The property key within a resource
            resource_id (str, optional): The ID of a specific resource. Defaults to None.

        Returns:
            List[Dict[str, Any]]: List of resources
        """
        resources = []
        limit = 100

        if resource_id:
            url_path = f"{url_path}/{resource_id}"

        url_query_str = f"?limit={limit}"
        url = f"{self._server_url}{url_path}{url_query_str}"

        try:
            response = self._send_request(method=HTTPMethod.GET, url=url)

            if response.status_code == 200:
                if resource_id:
                    if resource_prop_key == GetiResourceProperty.OPTIMIZED_MODELS:
                        resources_json_list = response.json()[resource_prop_key.value]
                    else:
                        resources_json_list = [response.json()]
                else:
                    resources_json_list = response.json()[resource_prop_key.value]

                resources = resources_json_list
            else:
                logger.error(
                    f"Geti Server Response - Status code: {response.status_code}, {response.text}"
                )
        except Exception as e:
            logger.error(f"Error getting resources: {e}")
            raise

        return resources

    def post_resources(self, url_path: str, data, resource_id: Optional[str] = None):
        """
        Send a POST request regarding a specific resource.

        Args:
            url_path (str): The path to the resource
            data: The data to post
            resource_id (str, optional): The ID of a specific resource. Defaults to None.

        Returns:
            requests.Response: Response from the Geti server
        """
        if resource_id:
            url_path = f"{url_path}/{resource_id}"

        url = f"{self._server_url}{url_path}"

        try:
            response = self._send_request(method=HTTPMethod.POST, url=url, data=data)

            if response.status_code in (200, 201):
                return response
            else:
                logger.error(
                    f"Geti Server Response - Status code: {response.status_code}, {response.text}"
                )
        except Exception as e:
            logger.error(f"Error posting resources: {e}")
            raise

        return None

    def get_projects(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all projects or a specific project.

        Args:
            project_id (str, optional): The ID of a specific project. Defaults to None.

        Returns:
            List[Dict[str, Any]]: List of projects
        """
        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects"

        try:
            projects = self.get_resources(
                url_path=url_path,
                resource_prop_key=GetiResourceProperty.PROJECTS,
                resource_id=project_id,
            )
            logger.info(f"Retrieved {len(projects)} project(s) from Geti server")
            return projects
        except Exception as e:
            logger.error(f"Error retrieving projects: {e}")
            raise

    def get_model_id_by_name(self, project_id: str, model_group_id: str, model_name: str) -> Optional[str]:
        """
        Fetch model_id from Geti server by looking up the model name.

        Args:
            project_id (str): The ID of the project
            model_group_id (str): The ID of the model group
            model_name (str): The name of the model to search for

        Returns:
            Optional[str]: The model_id if found, None otherwise
        """
        # Per REST API spec, models are returned within the model group object
        # at GET /projects/{project_id}/model_groups/{model_group_id}
        try:
            model_group = self.get_model_group(project_id=project_id, model_group_id=model_group_id)
            if not model_group:
                logger.error(
                    f"Model group '{model_group_id}' not found in project '{project_id}'"
                )
                return None
            logger.info(f"Searching for model name '{model_name}' in model group {model_group}") 
            models = model_group.get("models", [])
            for model in models:
                if model.get("name") == model_name:
                    model_id = model.get("id")
                    logger.info(
                        f"Found model ID '{model_id}' for model name '{model_name}'"
                    )
                    return model_id

            logger.warning(
                f"Model with name '{model_name}' not found in model group {model_group_id}"
            )
            return None

        except Exception as e:
            logger.error(f"Error fetching model ID by name: {e}")
            return None

    def get_model_group(self, project_id: str, model_group_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific model group, which includes its models list, per REST API spec:
        GET /organizations/{organization_id}/workspaces/{workspace_id}/projects/{project_id}/model_groups/{model_group_id}
        """
        url_path = (
            f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}"
            f"/projects/{project_id}/model_groups/{model_group_id}"
        )
        url = f"{self._server_url}{url_path}"
        try:
            # Expecting a ZIP archive, adjust Accept header accordingly
            resp = self._send_request(method=HTTPMethod.GET, url=url)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(
                    f"Failed to get model group - Status code: {resp.status_code}, {resp.text}"
                )
                return None
        except Exception as e:
            logger.error(f"Error retrieving model group: {e}")
            return None

    def _download_model_from_geti(
        self, project_id: str, model_id: str, output_dir: str, **kwargs
    ) -> Optional[str]:
        """
        Download model files from a Geti server using the export API endpoints.

        Supports both base model and optimized model exports as per the API specification.

        Args:
            project_id (str): The ID of the project
            model_group_id (str): The ID of the model group
            model_id (str): The ID of the model
            output_dir (str): Output directory for downloaded files
            **kwargs: Additional arguments:
                - export_type: "base" (default) or "optimized"
                - optimized_model_id: Required if export_type is "optimized"
                - model_only: Optional for optimized models, True to exclude code (default: True)

        Returns:
            Optional[str]: Path to the downloaded model file, or None if failed
        """
        export_type = (kwargs.get("export_type") or "base").lower()
        model_group_id = kwargs.get("model_group_id")
        
        try:
            if export_type == "optimized":
                # Export optimized model
                optimized_model_id = kwargs.get("optimized_model_id")
                if not optimized_model_id:
                    logger.error("optimized_model_id is required for optimized model export")
                    return None
                
                model_only = kwargs.get("model_only", True)
                url_path = (
                    f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}"
                    f"/projects/{project_id}/model_groups/{model_group_id}/models/{model_id}"
                    f"/optimized_models/{optimized_model_id}/export"
                )
                
                # Add query parameter for model_only
                url_query_str = f"?model_only={str(model_only).lower()}"
                url = f"{self._server_url}{url_path}{url_query_str}"
                
                logger.info(f"Downloading optimized model: {optimized_model_id}, model_only={model_only}")
            else:
                # Export base model
                url_path = (
                    f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}"
                    f"/projects/{project_id}/model_groups/{model_group_id}/models/{model_id}/export"
                )
                url = f"{self._server_url}{url_path}"
                
                logger.info(f"Downloading base model: {model_id}")

            # Make the GET request to download the model
            resp = self._send_request(method=HTTPMethod.GET, url=url)

            if resp.status_code == 200:
                logger.debug(f"Model ({model_id}) downloaded successfully")

                # Create hub-specific directory
                hub_dir = os.path.join(output_dir, "geti")
                model_dir_name = f"{export_type}_{model_id}".replace("/", "_")
                model_dir = os.path.join(hub_dir, model_dir_name)

                os.makedirs(model_dir, exist_ok=True)

                # Extract zip file
                zip_file_path = os.path.join(model_dir, f"{model_dir_name}.zip")
                with BytesIO(resp.content) as zip_buffer:
                    with zipfile.ZipFile(zip_buffer, "r") as zip_ref:
                        zip_ref.extractall(model_dir)

                logger.debug(f"Files extracted to {model_dir}")

                # Create archive
                archive_path = shutil.make_archive(
                    base_name=os.path.join(model_dir, model_dir_name), format="zip", base_dir=model_dir
                )
                logger.debug(f"Archive created: {archive_path}")

                return archive_path
            else:
                logger.error(
                    f"Failed to download model - Status code: {resp.status_code}, {resp.text}"
                )
        except Exception as e:
            logger.error(f"Error downloading model from Geti: {e}")
            raise

        return None

    def _prepare_deployment(self, project_id: str, model_info: Dict[str, Any]) -> Optional[str]:
        """
        Prepare a deployment for model download.

        Args:
            project_id (str): The ID of the project
            model_info (Dict[str, Any]): Model information

        Returns:
            Optional[str]: Deployment ID if successful, None otherwise
        """
        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects/{project_id}/code_deployments:prepare"

        try:
            data = json.dumps({"models": [model_info]})
            resp = self.post_resources(url_path=url_path, data=data)

            if resp and resp.status_code in (200, 201):
                deployment_id = resp.json().get("id")
                logger.debug(f"Deployment prepared with ID: {deployment_id}")
                return deployment_id
            else:
                logger.error(f"Failed to prepare deployment: {resp.text if resp else 'No response'}")
        except Exception as e:
            logger.error(f"Error preparing deployment: {e}")
            raise

        return None

    def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        """
        Download OpenVINO models from Geti server.

        Uses the export endpoints which are the standard APIs for downloading models from Geti.
        Supports both base model and optimized model exports.

        Can fetch model_id at runtime based on model name if not provided explicitly.

        Args:
            model_name (str): The model name (can be project_id:model_id or just the model name)
            output_dir (str): Output directory for downloaded files
            **kwargs: Additional arguments:
                - project_id: Project ID (required)
                - model_id: Model ID (optional - will be fetched by name if not provided)
                - model_group_id: Model group ID (required)
                - export_type: "base" (default) or "optimized"
                - optimized_model_id: Required if export_type is "optimized"
                - model_only: Optional for optimized models (default: True to exclude code)

        Returns:
            Dict[str, Any]: Download result information
        """
        try:
            project_id = (kwargs.get("project_id") or "691bfa6c0a9b332eadf1d28c").lower()
            model_group_id = kwargs.get("model_group_id")
            export_type = (kwargs.get("export_type") or "base").lower()
            model_only = kwargs.get("model_only", True)  # Default to True to exclude code

            logger.info(f"Starting Geti model download: model_name={model_name}, export_type={export_type}, model_only={model_only}")

            if not project_id:
                logger.error("project_id is required for Geti model downloads")
                return {"success": False, "error": "project_id is required"}

            if not model_group_id:
                logger.error("model_group_id is required for Geti model downloads")
                return {"success": False, "error": "model_group_id is required"}

            # Try to get model_id from kwargs, otherwise fetch it by name at runtime
            model_id = kwargs.get("model_id")
            if not model_id:
                logger.info(f"Model ID not provided, fetching model_id for model name '{model_name}' from Geti server")
                model_id = self.get_model_id_by_name(project_id, model_group_id, model_name)
                if not model_id:
                    logger.error(f"Failed to fetch model_id for model name '{model_name}'")
                    return {"success": False, "error": f"Model '{model_name}' not found in Geti server"}
            else:
                logger.info(f"Using provided model_id: {model_id}")

            if export_type == "optimized" and not kwargs.get("optimized_model_id"):
                logger.error("optimized_model_id is required when export_type is 'optimized'")
                return {"success": False, "error": "optimized_model_id is required for optimized exports"}

            # Update kwargs with model_only to ensure it's passed to _download_model_from_geti
            kwargs["model_only"] = model_only
            logger.info(f"Downloading model_id '{model_id}' from Geti server of project '{project_id}' and model group '{model_group_id}' in the directory '{output_dir}' with kwargs: {kwargs}")
            # Download model files using the export API
            model_path = self._download_model_from_geti(
                project_id=project_id, model_id=model_id, output_dir=output_dir, **kwargs
            )

            if not model_path:
                return {"success": False, "error": "Failed to download model files"}

            hub_dir = os.path.join(output_dir, "geti")
            host_path = hub_dir
            if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
                host_prefix = os.getenv("MODEL_PATH", "models")
                host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

            logger.info(f"Successfully downloaded Geti model to {host_path}")

            return {
                "model_name": model_name,
                "source": "geti",
                "download_path": host_path,
                "success": True,
                "model_id": model_id,
                "model_group_id": model_group_id,
                "export_type": export_type,
                "model_only": model_only,
                "model_format": "OpenVINO" if export_type == "optimized" else "Base",
            }

        except Exception as e:
            logger.error(f"Error downloading Geti model: {e}")
            return {"success": False, "error": str(e)}

    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """Geti plugin does not support task-based downloading"""
        raise NotImplementedError("Geti plugin does not support task-based downloading")

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """Geti plugin does not support task-based downloading"""
        raise NotImplementedError("Geti plugin does not support task-based downloading")

    def post_process(
        self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs
    ) -> Dict[str, Any]:
        """Post-process downloaded Geti models"""
        return {
            "model_name": model_name,
            "source": "geti",
            "download_path": output_dir,
            "success": True,
        }
