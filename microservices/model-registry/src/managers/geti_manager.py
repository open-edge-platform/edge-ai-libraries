
# pylint: disable=import-error,
# type: ignore
"""Module providing a class for managing interaction with Geti projects and models"""
import os
import shutil
import json
from enum import Enum, auto
from typing import List, Optional, Union, Type
import zipfile
from io import BytesIO
import requests
from requests.exceptions import RequestException
from pydantic import TypeAdapter
from models.model_identifiers import ModelIdentifiersIn
from models.project import ProjectOut, ModelVersion, ModelGroup, OptimizedModel
from managers.minio_manager import MinioManager
from managers.mlflow_manager import MLflowManager
from utils.logging_config import logger
from utils.app_utils import get_bool


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


class GetiManager():
    """
    A class for an Intel Geti project
    """
    _geti_client = None
    _project_client = None
    _server_url = os.environ.get("GETI_HOST")
    _organization_id = os.environ.get("GETI_ORGANIZATION_ID")
    _workspace_id = os.environ.get("GETI_WORKSPACE_ID")
    _server_api_token = os.environ.get("GETI_TOKEN")
    _server_api_ver = os.environ.get("GETI_SERVER_API_VERSION")
    _verify_server_ssl_cert = get_bool(os.getenv("GETI_SERVER_SSL_VERIFY", "True"), ignore_empty=True)

    if isinstance(_server_url, str):
        _server_url = _server_url + f"/api/{_server_api_ver}"

    _geti_req_headers = {
        "Content-Type": "application/json",
        "x-api-key": _server_api_token
    }

    _req_timeout = 30

    def __new__(cls):
        if not hasattr(cls, 'instance'):
            if any([cls._server_url is None,
                    cls._organization_id is None,
                    cls._workspace_id is None,
                    cls._server_api_token is None,
                    cls._server_api_ver is None]):
                logger.warning("One or more environment variables required to communicate with a Geti Server are not set."
                             " Please restart the service and set the following environment variables: GETI_HOST,"
                             " GETI_ORGANIZATION_ID, GETI_WORKSPACE_ID, GETI_TOKEN, and GETI_SERVER_API_VERSION."
                             " Subsequent Geti related requests will fail.")

            cls.instance = super(GetiManager, cls).__new__(cls)
        return cls.instance

    def _send_request(self, method: HTTPMethod, url: str, data = None):
        if any([self._server_url is None,
                self._organization_id is None,
                self._workspace_id is None,
                self._server_api_token is None,
                self._server_api_ver is None]):
            err_msg = "One or more of the following environment variables are not set: " \
                "GETI_HOST, GETI_ORGANIZATION_ID, GETI_WORKSPACE_ID, GETI_TOKEN, and/or GETI_SERVER_API_VERSION."
            raise ValueError(err_msg)

        try:
            response = None
            if method == HTTPMethod.GET:
                response = requests.get(
                    url=url, headers=self._geti_req_headers, timeout=self._req_timeout, verify=self._verify_server_ssl_cert)
            elif method == HTTPMethod.POST:
                response = requests.post(
                    url=url, headers=self._geti_req_headers, timeout=self._req_timeout, data=data, verify=self._verify_server_ssl_cert)

            return response
        except Exception as e:
            logger.error(e)
            raise RequestException(
                f"Failed to get resource from the Geti server: {e}") from e

    def get_projects(self, project_id: str = None) -> [ProjectOut]:
        """Get all projects or a specific project associated to the project_id.

        Args:
            project_id (str, optional): The ID of a specfic project. Defaults to None.

        Raises:
            e: Exception

        Returns:
            List[ProjectOut]: List of projects
        """
        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects"

        try:
            projects = self.get_resources(
                url_path=url_path, cls=ProjectOut, resource_prop_key=GetiResourceProperty.PROJECTS, resource_id=project_id)
            for project in projects:
                url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects/{project.id}/model_groups"
                model_groups = self.get_resources(
                    url_path=url_path, cls=ModelGroup, resource_prop_key=GetiResourceProperty.MODEL_GROUPS)
                project.model_groups = model_groups
                for model_group in project.model_groups:
                    for mv in model_group.model_versions:
                        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects/{project.id}/model_groups/{model_group.id}/models"
                        optimized_models = self.get_resources(url_path=url_path, cls=OptimizedModel,
                                                              resource_prop_key=GetiResourceProperty.OPTIMIZED_MODELS, resource_id=mv.id)
                        optimized_models = [
                            om for om in optimized_models if om.model_format.lower() == "openvino"]
                        mv.openvino_models = optimized_models

        except Exception as e:
            raise e

        return projects

    def get_resources(self, url_path: str,
                      cls: Type[Union[ModelGroup, ModelVersion]],
                      resource_prop_key: GetiResourceProperty, resource_id: str = None):
        """Get all resources or a specific resource associated to the resource_id.

        Args:
            url_path (str): The path to the resource.
            cls (Type[Union[ModelGroup, ModelVersion]]): The class type of the returned resource.
            resource_prop_key (GetiResourceProperty): The property key within a resource.
            resource_id (str, optional): The ID of a specfic resource. Defaults to None.

        Raises:
            e: Exception

        Returns:
            List: List of resources
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
                    if cls == OptimizedModel:
                        resources_json_list = response.json()[
                                                            resource_prop_key.value]
                    else:
                        resources_json_list = [response.json()]
                else:
                    resources_json_list = response.json()[
                                                        resource_prop_key.value]

                resources = TypeAdapter(
                    list[cls]).validate_python(resources_json_list)
            else:
                logger.error(
                    f"Geti Server Response - Status code: {response.status_code}, {response.text}")
        except Exception as e:
            raise e

        return resources

    def post_resources(self, url_path: str, data, resource_id: str = None) -> requests.Response:
        """Send a request regarding a specific group of resources or a specific resource associated to the resource_id.

        Args:
            url_path (str): The path to the resource.
            resource_id (str, optional): The ID of a specfic resource. Defaults to None.

        Raises:
            e: Exception

        Returns:
            response: Response from the Geti server
        """
        resp = None
        if resource_id:
            url_path = f"{url_path}/{resource_id}"

        url = f"{self._server_url}{url_path}"

        try:
            response = self._send_request(method=HTTPMethod.POST, url=url, data=data)

            if response.status_code in (200, 201):
                resp = response
            else:
                logger.error(
                    f"Geti Server Response - Status code: {response.status_code}, {response.text}")
        except Exception as e:
            raise e

        return resp

    def _store_model_from_geti(self, project_id: str, deployment_id: str, model: OptimizedModel) -> bool:
        """Download model(s) from a Geti server.

        Args:
            project_id (str): _description_
            deployment_id (str): _description_
        """
        is_models_registered = False
        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}" \
            f"/projects/{project_id}/code_deployments/{deployment_id}/download"

        try:
            url = f"{self._server_url}{url_path}"
            resp = self._send_request(method=HTTPMethod.GET, url=url)

            if resp.status_code == 200:
                logger.debug(f"Model ({model.id}) is downloaded.")

                project = self.get_projects(project_id=project_id)[0]
                base_dir_name = project.name.lower().replace(" ", "-").replace(".", "")
                current_dir_path = "./"
                base_dir = current_dir_path + base_dir_name
                zip_file_path = base_dir + ".zip"

                if not os.path.exists(base_dir):
                    os.makedirs(base_dir)

                with BytesIO(resp.content) as zip_buffer:
                    with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                        zip_ref.extractall(base_dir)
                logger.debug(f"Files extracted to {base_dir}")

                shutil.make_archive(base_name=base_dir_name,
                                    format='zip', base_dir=base_dir)
                logger.debug(f"{base_dir_name}.zip file created")

                minio_manager = MinioManager()
                mlflow_manager = MLflowManager()

                model_file_url = minio_manager.store_data(
                    prefix_dir=model.id,
                    file_path=zip_file_path,
                    file_name=base_dir_name+".zip")

                model.project_id = project.id
                model.project_name = project.name

                geti_model_supported_tasks = ("detection", "classification", "segmentation", "anomaly")
                for task in project.pipeline["tasks"]:
                    task_type = task["task_type"]
                    if task_type.lower() in geti_model_supported_tasks:
                        if model.category is None:
                            model.category = task_type.lower()
                        else:
                            model.category = model.category + "_" + task_type.lower()

                _ = mlflow_manager.register_geti_model(model=model, model_file_url=model_file_url)

                shutil.rmtree(base_dir)
                logger.debug(f"{base_dir} deleted")
                os.remove(zip_file_path)
                is_models_registered = True

        except Exception as e:
            raise e

        return is_models_registered

    def save_models(self, project_id: str, model_identifiers_in: ModelIdentifiersIn) -> Optional[List[str]]:
        """
        Download specified OpenVINO models in a project.

        Save the model files in object storage.

        Save the models' metadata in the database.

        Args:
            project_id: The id for a Intel Geti project
            desired_model_ids: The ids for the models to be stored in object storage

        Returns:
            List[str]: List of 1 or more ids for models registered
            None: if something went wrong
        """
        registered_model_ids = []
        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects/{project_id}/code_deployments:prepare"

        try:
            for model_identifiers in model_identifiers_in.models:
                data = model_identifiers.model_dump(by_alias=True)
                data = {
                    "models": [data]
                }
                data = json.dumps(data)
                resp = self.post_resources(url_path=url_path, data=data)

                if resp.status_code in (200, 201):
                    json_data = resp.json()
                    deployment_id = json_data['id']

                    model_group_id = json_data["models"][0]['model_group_id']
                    model_id = json_data["models"][0]['model_id']

                    url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}/projects/{project_id}/model_groups/{model_group_id}/models/{model_id}"
                    url = f"{self._server_url}{url_path}"
                    resp = self._send_request(method=HTTPMethod.GET, url=url)
                    json_data = resp.json()
                    o_model = OptimizedModel(**json_data)
                    o_model.score = json_data["performance"]["score"]
                    o_model.model_format = "OpenVINO"

                    logger.debug(f"Model ({o_model.id}) is being prepared for deployment.")

                    deployment_prep_state = "NONE"
                    while deployment_prep_state.lower() != "done":
                        url_path = f"/organizations/{self._organization_id}/workspaces/{self._workspace_id}" \
                            f"/projects/{project_id}/code_deployments/{deployment_id}"

                        url = f"{self._server_url}{url_path}"
                        resp = self._send_request(method=HTTPMethod.GET, url=url)

                        deployment_prep_state = resp.json()["state"]

                    logger.debug(f"Model ({o_model.id}) is ready to be downloaded.")
                    is_model_registered = self._store_model_from_geti(project_id, deployment_id, o_model)

                    if is_model_registered:
                        registered_model_ids.append(o_model.id)

                else:
                    logger.error(
                        f"Geti Server Response (Code Deployment:Prepare) - Status code: {resp.status_code}, {resp.text}")   
        except Exception as e:
            raise e

        return registered_model_ids

