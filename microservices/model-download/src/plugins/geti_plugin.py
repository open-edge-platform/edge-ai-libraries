# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import json
import zipfile
import subprocess
from io import BytesIO
from enum import Enum, auto
from typing import Dict, Any, List, Optional

from pydantic import TypeAdapter

from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.utils.logging import logger


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
        self.model_id = None

        if isinstance(self._server_url, str):
            self._server_url = self._server_url + f"/api/{self._server_api_ver}"

        self._geti_req_headers = {
            "x-api-key": self._server_api_token,
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

    async def _validate_env_vars(self) -> None:
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

    async def _send_request_via_curl(self, method: str, url: str, data: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> "_CurlResponse":
        """Send HTTP request to Geti server using curl"""
        await self._validate_env_vars()

        try:
            # Merge default headers with any overrides
            req_headers = dict(self._geti_req_headers)
            if headers:
                req_headers.update(headers)
            
            # For POST requests with data, ensure Content-Type is set
            if method == "POST" and data and "Content-Type" not in req_headers:
                req_headers["Content-Type"] = "application/json"
            
            logger.info(f"Sending {method} request to Geti server via curl: {url}")
            logger.info(f"Request headers: {req_headers}")
            if data:
                logger.debug(f"Request body: {data}")
            
            # Build curl command
            curl_cmd = ["curl", "--location", "--silent", "--show-error"]
            
            # Add SSL verification flag
            if not self._verify_server_ssl_cert:
                curl_cmd.append("--insecure")
            
            # Add timeout
            curl_cmd.extend(["--max-time", str(self._req_timeout)])
            
            # Add headers
            for header_key, header_value in req_headers.items():
                curl_cmd.extend(["--header", f"{header_key}: {header_value}"])
            
            # Add method and data
            if method == "GET":
                curl_cmd.append("--request")
                curl_cmd.append("GET")
            elif method == "POST":
                curl_cmd.append("--request")
                curl_cmd.append("POST")
                if data:
                    curl_cmd.extend(["--data", data])
            
            # Add URL
            curl_cmd.append(url)
            
            logger.debug(f"Curl command: {' '.join(curl_cmd)}")
            
            # Execute curl command
            # Use binary mode (text=False) to properly capture binary ZIP data
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                text=False,  # Keep as binary to preserve ZIP file data
                timeout=self._req_timeout + 5
            )
            
            logger.debug(f"Curl exit code: {result.returncode}")
            if result.stdout:
                logger.debug(f"Curl stdout length: {len(result.stdout)}")
            if result.stderr:
                stderr_text = result.stderr.decode('utf-8', errors='replace') if isinstance(result.stderr, bytes) else result.stderr
                logger.debug(f"Curl stderr: {stderr_text}")
            
            if result.returncode != 0:
                error_msg = f"Curl failed with exit code {result.returncode}"
                if result.stderr:
                    stderr_text = result.stderr.decode('utf-8', errors='replace') if isinstance(result.stderr, bytes) else result.stderr
                    error_msg += f": {stderr_text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            return _CurlResponse(result.stdout)
            
        except subprocess.TimeoutExpired as e:
            logger.error(f"Curl request timed out: {e}")
            raise RuntimeError(f"Request timed out: {e}") from e
        except Exception as e:
            logger.error(f"Failed to send request via curl: {e}")
            raise RuntimeError(f"Failed to communicate with Geti server: {e}") from e

    async def get_resources(
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
            response = await self._send_request_via_curl(method="GET", url=url)

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

    async def post_resources(self, url_path: str, data, resource_id: Optional[str] = None):
        """
        Send a POST request regarding a specific resource.

        Args:
            url_path (str): The path to the resource
            data: The data to post
            resource_id (str, optional): The ID of a specific resource. Defaults to None.

        Returns:
            Response-like object from the Geti server
        """
        if resource_id:
            url_path = f"{url_path}/{resource_id}"

        url = f"{self._server_url}{url_path}"

        try:
            response = await self._send_request_via_curl(method="POST", url=url, data=data)

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

    async def get_projects(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all projects or a specific project.

        Args:
            project_id (str, optional): The ID of a specific project. Defaults to None.

        Returns:
            List[Dict[str, Any]]: List of projects
        """
        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects"

        try:
            projects = await self.get_resources(
                url_path=url_path,
                resource_prop_key=GetiResourceProperty.PROJECTS,
                resource_id=project_id,
            )
            logger.info(f"Retrieved {len(projects)} project(s) from Geti server")
            return projects
        except Exception as e:
            logger.error(f"Error retrieving projects: {e}")
            raise

    async def get_model_id_by_name(self, project_id: str, model_group_id: str, model_name: str) -> Optional[str]:
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
            model_group = await self.get_model_group(project_id=project_id, model_group_id=model_group_id)
            if not model_group:
                logger.error(
                    f"Model group '{model_group_id}' not found in project '{project_id}'"
                )
                return None
            logger.info(f"Searching for model name '{model_name}' in model group {model_group}") 
            models = model_group.get("models", [])
            for model in models:
                if model.get("name").lower() == model_name.lower():
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

    async def get_model_group(self, project_id: str, model_group_id: str) -> Optional[Dict[str, Any]]:
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
            resp = await self._send_request_via_curl(method="GET", url=url)
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

    async def _download_model_from_geti(
        self, model_id: str, output_dir: str, model_name: str = None, **kwargs
    ) -> Optional[str]:
        """
        Download model files from a Geti server using the deployment package download API.

        Uses POST endpoint: /projects/{project_id}/deployment_package:download

        Args:
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
        project_id = kwargs.get("project_id")
        
        try:
            # Build the POST endpoint URL
            url_path = (
                f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}"
                f"/projects/{project_id}/deployment_package:download"
            )
            url = f"{self._server_url}{url_path}"
            
            # Prepare the model object
            model_obj = {
                "model_group_id": model_group_id,
                "model_id": model_id,
            }
            
            # Prepare the request body with correct structure
            request_body = {
                "package_type": "ovms",
                "models": [model_obj]
            }
                       
            if export_type == "optimized":
                optimized_model_id = kwargs.get("optimized_model_id")
                if not optimized_model_id:
                    logger.error("optimized_model_id is required for optimized model export")
                    return None
                
                model_obj["optimized_model_id"] = optimized_model_id
                model_obj["model_only"] = kwargs.get("model_only", True)
                
                logger.info(f"Downloading optimized model: {optimized_model_id}, model_only={model_obj['model_only']}")
            else:
                logger.info(f"Downloading base model: {model_id}")

            # Make the POST request to download the model
            data = json.dumps(request_body)
            logger.info(f"Request body: {data}")

            # Create hub-specific directory
            hub_dir = os.path.join(output_dir, "geti")
            model_dir_name = f"{export_type}_{model_id}".replace("/", "_")
            model_dir = os.path.join(hub_dir, model_dir_name)
            os.makedirs(model_dir, exist_ok=True)

            resp = await self._send_request_via_curl(method="POST", url=url, data=data)

            if resp.status_code in (200, 201):
                logger.debug(f"Model ({model_id}) downloaded successfully")

                # Store the POST request result (ZIP file) in the model directory
                zip_file_path = os.path.join(model_dir, f"{model_name}.zip")
                with open(zip_file_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"Model ZIP file saved to {zip_file_path}")

                # Extract zip file
                with BytesIO(resp.content) as zip_buffer:
                    with zipfile.ZipFile(zip_buffer, "r") as zip_ref:
                        zip_ref.extractall(model_dir)

                logger.debug(f"Files extracted to {model_dir}")

                # Create archive
                archive_path = shutil.make_archive(
                    base_name=os.path.join(model_dir, model_dir_name), format="zip", base_dir=model_dir
                )
                logger.debug(f"Archive created: {archive_path}")

                return model_dir
            else:
                error_msg = f"Failed to download model - Status code: {resp.status_code}"
                try:
                    error_detail = resp.text[:500] if resp.text else "No response body"
                except:
                    error_detail = "Could not read response"
                logger.error(f"{error_msg}. Response: {error_detail}")
                return None
        except Exception as e:
            logger.error(f"Error downloading model from Geti: {e}")
            raise

        return None

    async def _prepare_deployment(self, project_id: str, model_info: Dict[str, Any]) -> Optional[str]:
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
            resp = await self.post_resources(url_path=url_path, data=data)

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

    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
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
            project_id = kwargs.get("project_id")
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
                model_id = await self.get_model_id_by_name(project_id, model_group_id, model_name)
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
            model_path = await self._download_model_from_geti(
                model_id, output_dir, model_name, **kwargs
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

    async def post_process(
        self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs
    ) -> Dict[str, Any]:
        """Post-process downloaded Geti models"""
        return {
            "model_name": model_name,
            "source": "geti",
            "download_path": output_dir,
            "success": True,
        }


class _CurlResponse:
    """
    Wrapper for curl response to provide a requests-like interface.
    This maintains backward compatibility with existing code.
    """
    
    def __init__(self, response_data):
        # Handle both binary and text responses
        if isinstance(response_data, bytes):
            self._content_bytes = response_data
            try:
                self._content_str = response_data.decode('utf-8')
            except UnicodeDecodeError:
                self._content_str = response_data.decode('utf-8', errors='replace')
        else:
            # Text response
            self._content_str = response_data
            self._content_bytes = response_data.encode('utf-8') if isinstance(response_data, str) else response_data
        
        # Parse status code from curl output if available
        # For now, assume success if we got content
        self.status_code = 200
        self.url = ""

    @property
    def content(self) -> bytes:
        """Return response content as bytes"""
        return self._content_bytes

    @property
    def text(self) -> str:
        """Return response content as text"""
        return self._content_str

    def json(self) -> Dict[str, Any]:
        """Parse response content as JSON"""
        return json.loads(self._content_str)
