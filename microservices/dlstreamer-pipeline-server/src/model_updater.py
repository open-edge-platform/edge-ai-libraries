#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""This file contains the classes, variables and methods for connecting
 and interacting with the model registry microservice."""
# pylint: disable=broad-exception-caught
import os
import io
from typing import Union
import threading
import json
import zipfile
from enum import Enum
import requests
from requests import Response
from pydantic import BaseModel
from pydantic import field_validator
from src.common.log import get_logger

class RequestMethod(Enum):
    """Request Method Enum"""
    GET = "get"
    POST = "post"

class ModelQueryParams(BaseModel):
    """Model Query Params class"""
    name: str = None
    category: str = None
    architecture: str = None
    precision: str = None
    project_name: str = None
    version: str = None
    origin: str = None
    deploy: bool = False
    pipeline_element_name: str = None

    @field_validator('*')
    def validate_params_not_empty(cls, value, info):
        if value is not None and value == '':
            raise ValueError(f'{info.field_name} cannot be empty')
        return value

class ModelRegistryClient:
    """Model Registry Client class"""
    _pipelines_cfg = None
    # _auth_header = {}
    # _is_connected = False
    _verify_cert = False

    _logger = get_logger(__name__)

    def __init__(self, model_registry_cfg: dict) -> None:
        """Create an instance of the Model Registry Client for connecting and 
        interacting with the Model Registry microservice

        Args:
            model_registry_cfg (dict): The properties for connecting and storing models locally
              from the model_registry such as the `url`, `saved_models_dir`
              and `request_timeout`.
            pipelines_cfg (list): A list of configurations associated to each pipeline
        """
        try:
            self._url = model_registry_cfg["url"]

            if self._url.startswith("https://"):
                self._verify_cert = ModelRegistryClient._get_verify_cert(os.getenv("MR_VERIFY_CERT",
                                                                                   "/run/secrets/ModelRegistry_Server/ca-bundle.crt"))

            # self._user_password = os.getenv("MR_USER_PASSWORD")
            self._saved_models_dir = model_registry_cfg["saved_models_dir"]
            self._request_timeout = model_registry_cfg["request_timeout"]
            if not isinstance(self._request_timeout, int):
                raise ValueError("request_timeout must be an integer")          
            # if not self._url or not self._user_password:
            #     raise ValueError(
            #         "URL and/or User Password cannot be an empty string or None.")

            # self._login_to_mr_microservice()
        except Exception as e:
            self._logger.error("Exception occurred while initializing Model "
                                "Registry Client: %s", e)
    @classmethod
    def _get_verify_cert(cls, string: str) -> Union[str, bool]:
        """Return a file path or boolean to be used for enabling or disabling SSL certificate verification

        Args:
            string (str): A string used for enabling or disabling SSL certification verification

        Raises:
            ValueError: Unsupported value provided for MR_VERIFY_CERT environment variable: <string>

        Returns:
            Union[str, bool]: If the provided string is a truthy or falsy value, return a boolean. 
            If the provided string is a valid file path, return a string.
        """
        val = None
        if string.lower() in ("yes", "y", "true",  "t", "1"):
            val =  True
        elif string.lower() in ("no",  "n", "false", "f", "0", ""):
            val =  False
        elif os.path.exists(string):
            val = string
        else:
            msg = f"Unsupported value provided for MR_VERIFY_CERT environment variable: {string}"

            raise ValueError(msg)

        return val

    # def _login_to_mr_microservice(self):
    #     """Connect to a running model registry microservice
    #     """
    #     try:
    #         login_form_data = {"username": "admin", "password": self._user_password}
    #         self._logger.debug(
    #             "Connection to the model registry microservice requested.")
    #         resp = requests.post(
    #             url=self._url+"/login", data=login_form_data, verify=self._verify_cert,
    #             timeout=self._request_timeout)
    #         self._auth_header = {
    #             "Authorization": "Bearer "+resp.json()["access_token"]}
    #         self._logger.info(
    #             "Connection to the model registry microservice successful.")
    #         self._is_connected = True
    #     except Exception as e:
    #         self._logger.error("Exception occurred while connecting to the"
    #                            " model registry microservice: %s", e)

    def _send_request(self, url: str, method: RequestMethod = RequestMethod.GET,
                       params=None, data=None, stream: bool=False) -> Response:
        """Sends a HTTP/HTTPS request and retries the request 2 times while attempting
        to obtain a new JWT if the response's status code is 401

        Args:
            url: The URL to send the request to.
            params: A dictionary, list of tuples or bytes to send as a query string.
            data: A dictionary, list of tuples, bytes or a file object to send to the specified url
            stream: A Boolean indication if the response should be immediately downloaded (False)
            or streamed (True).
        """
        resp_s_code = None
        num_retries = 0
        max_retries = 2
        response = None
        try:
            while (resp_s_code is None or resp_s_code == 401) and num_retries < max_retries:
                response = requests.request(method=method.value, url=url,
                                            params=params, data=data,
                                            # headers=self._auth_header,
                                            verify=self._verify_cert,
                                            timeout=self._request_timeout,
                                            stream=stream)

                resp_s_code = response.status_code

                # if resp_s_code == 401:
                #     self._login_to_mr_microservice()

                num_retries = num_retries + 1

            if resp_s_code == 401:
                self._logger.error("%s Request to %s failed with status code %s after"
                                    " %s attempt(s) to the model registry microservice",
                                    method.value.upper(), url, resp_s_code, max_retries)
        except Exception as e:
            self._logger.error("Exception occurred while sending a request"
                                   " to the model registry microservice: %s", e)

        return response

    def _get_model(self, params: ModelQueryParams) -> dict:
        """Get a model that has properties matching the model query parameters

        Args:
            params (ModelQueryParams): The model query parameters used to search for a model

        Raises:
            ValueError: Expected a single model response with properties

        Returns:
            dict: The metadata for a model
        """
        # if not self._is_connected:
        #     self._logger.error("Failed to get model: Not connected to the " \
        #                        "model registry microservice.")
        #     return None

        model = None
        try:
            params_dict = {k: v for k,
                           v in params.model_dump().items() if v is not None}
            params_dict.pop("deploy", None)
            params_dict.pop("pipeline_element_name", None)
            params_dict.pop("origin", None)
            params_dict_str = json.dumps(params_dict)
            self._logger.debug(
                "Metadata for a model with the specified properties (%s) requested.",
                params_dict_str)

            if params_dict == {}:
                raise ValueError("A valid JSON object with at least one supported " \
                                 "property is required.")

            resp = self._send_request(url=self._url+"/models", method=RequestMethod.GET,
                                      params=params_dict)
            json_obj = resp.json()
            if resp.status_code == 200:
                if isinstance(json_obj, list) and (len(json_obj) > 1 or len(json_obj) == 0):
                    raise ValueError(
                        f"Received 0 or more than 1 model. " \
                        f"Expected a single model with properties: " \
                            f"{params_dict_str}")

                model = json_obj[0]
                self._logger.debug(
                    "Metadata for a model with the specified properties (%s) returned.",
                    params_dict_str)
            else:
                raise ValueError(
                    f"Status Code: {resp.status_code}; {resp.content}")
        except Exception as e:
            self._logger.error("Exception occurred while getting metadata for model: "
                               "%s", e)

        return model

    def _get_model_artifacts_zip_file_data(self, model_id: str):
        """Get the zip file data for a model using its id

        Args:
            model_id (str): The id of the model

        Raises:
            ValueError: The content type is not application/zip.
            ValueError: The received file \"{filename}\" is not a ZIP file.

        Returns:
            bytes | None: The zip file data. Otherwise, None
        """
        # if not self._is_connected:
        #     self._logger.error("Failed to get model artifacts: Not connected to the " \
        #                        "model registry microservice.")
        #     return None

        zip_file_data = None
        try:
            self._logger.debug(
                "Zip file containing artifacts for a model with ID: %s requested.",
                model_id)

            resp = self._send_request(url=self._url+"/models/"+model_id+"/files",
                                      method=RequestMethod.GET, stream=True)

            content_type = resp.headers.get("Content-Type")
            if content_type != "application/zip":
                raise ValueError("The content type is not application/zip.")

            zip_file_data = resp.content
            self._logger.debug(
                "Zip file containing artifacts for a model with ID: %s returned.",
                model_id)
        except Exception as e:
            self._logger.error("Exception occurred while getting artifacts for model:"
                               "%s", e)

        return zip_file_data

    def get_model_path(self, pipelines_cfg: list) -> dict:
        """
        Constructs and returns the model path based on the provided pipeline configuration.

        Args:
            pipeline_cfg (list): A list of pipeline configurations, where each configuration
                 is expected to contain model parameters.

        Returns:
            dict: A dictionary mapping pipeline names to their constructed model paths.

        Raises:
            Exception: Logs an error message if an exception occurs during the construction
               of the model path.

        The function iterates through the provided pipeline configurations to extract model
        parameters and constructs the model path based on these parameters. The path format
        differs depending on the origin of the model (e.g., "geti" or other origins).
        """
        try:
            model_path_dict = {}
            for pipeline in pipelines_cfg:
                list_pipeline_model_params = pipeline.get("model_params")
                if list_pipeline_model_params:
                    for pipeline_model_params in list_pipeline_model_params:
                        model_params = ModelQueryParams(**pipeline_model_params)      
                        model_params = {k: v for k,
                                    v in model_params.model_dump().items() if v is not None}
                        if model_params.get("deploy", False):
                            models_pipeline_dirpath = (self._saved_models_dir + \
                                    "/" + "_".join((model_params["name"],
                                    "m-"+model_params["version"],
                                    model_params["precision"]))).lower()
                            if model_params.get("origin", None) == "Geti":
                                model_path = models_pipeline_dirpath + "/deployment" + "/" + model_params["category"] + "/model/model.xml"
                                self._logger.debug("Model origin is GETI. Model path is %s", model_path)
                            else:
                                model_path = models_pipeline_dirpath + "/" + model_params["precision"].upper() + "/" + model_params["name"] + ".xml"
                                self._logger.debug("Model origin is not GETI. Model path is %s", model_path)
                            model_path_dict.update({model_params["pipeline_element_name"]: model_path})
            return model_path_dict
        except Exception as e:
            self._logger.error("Exception occurred while constructing model path: %s", e)
            return None

    def start_download_models(self, pipelines_cfg: list): # pragma: no cover
        """Start a thread to download the artifacts for models described in the model params 
        in the provided `pipelines_cfg` parameter.

        Args:
            pipelines_cfg (list): A list of configurations associated to each pipeline

        Returns:
            bool: True if the artifacts for the model(s) as saved locally. Otherwise, False.
        """
        # if not self._is_connected:
        #     self._logger.error("Failed to start model download process: Not connected to the " \
        #                        "model registry microservice.")
        #     return

        self._logger.debug("Start _download_models thread")
        thread = threading.Thread(target=self.download_models,
                                  args=(pipelines_cfg,), daemon=True)
        thread.start()

    def download_models(self, pipelines_cfg: list):
        """Download and save the artifacts for models locally based on the 
        `model_params` in the provided  `pipelines_cfg` parameter.

        Args:
            pipelines_cfg (list): A list of configurations associated to each pipeline
        
        Returns:
            tuple: The flag where the model(s) artifacts was saved successfully, error_message
        """
        is_artifacts_saved = False
        deployment_dirpath = None
        msg = None

        # if not self._is_connected:
        #     msg = "Failed to save model artifacts: Not connected to the " \
        #         "model registry microservice."
        #     self._logger.error(msg)
        #     return is_artifacts_saved, msg, deployment_dirpath


        if pipelines_cfg:
            self._pipelines_cfg = pipelines_cfg

        try:
            for pipeline in self._pipelines_cfg:
                list_pipeline_model_params = pipeline.get("model_params")
                if list_pipeline_model_params:
                    for pipeline_model_params in list_pipeline_model_params:
                            msg = None
                            params = ModelQueryParams(**pipeline_model_params)
                            model = self._get_model(params)
                            if not model:
                                msg = "Model is not found."
                                raise ValueError(msg)

                            model_id = model["id"]

                            models_pipeline_dirpath = (self._saved_models_dir + \
                                "/" + "_".join((model["name"],
                                                "m-"+model["version"],
                                                model["precision"][0]))).lower()

                            deployment_dirpath = (
                                models_pipeline_dirpath + "/deployment").lower()

                            dir_info = ("Directory", models_pipeline_dirpath)
                            is_already_saved = False

                            if not (os.path.exists(deployment_dirpath) or \
                                    os.path.exists(models_pipeline_dirpath)):

                                self._logger.info("Downloading model files...")
                                zip_file_data = self._get_model_artifacts_zip_file_data(
                                    model_id)

                                if zip_file_data:
                                    if not os.path.exists(models_pipeline_dirpath):
                                        os.makedirs(models_pipeline_dirpath)

                                    with zipfile.ZipFile(io.BytesIO(zip_file_data), 'r') as zip_ref:
                                        ignored_filenames = (".DS_Store", "__MACOSX")
                                        for file_info in zip_ref.infolist():
                                            file_root_dirname = zip_ref.filelist[0].filename
                                            fname = file_info.filename
                                            if not "deployment" in file_root_dirname:
                                                fname = fname.replace(
                                                    file_root_dirname, "")
                                            if fname and \
                                                not file_info.is_dir() and \
                                                    not any(name in fname for name in ignored_filenames):
                                                extract_path = os.path.join(models_pipeline_dirpath, fname)
                                                os.makedirs(os.path.dirname(extract_path), exist_ok=True)
                                                file_info.filename = os.path.basename(file_info.filename)
                                                zip_ref.extract(file_info, os.path.dirname(extract_path))

                                    is_artifacts_saved = True
                                else:
                                    msg = "Model artifacts are not found."
                            else:
                                is_already_saved = True
                                is_artifacts_saved = True

                            if os.path.exists(deployment_dirpath):
                                dir_info = ("Deployment directory", deployment_dirpath)

                            if msg is None:
                                verb_phrase = "already exists " if is_already_saved else "was created "
                                msg = f"{dir_info[0]} ({dir_info[1]}) {verb_phrase}" \
                                    f"for the {pipeline['name']} pipeline."
                                self._logger.info(msg)

        except Exception as e:
            if isinstance(e, PermissionError):
                msg = f"Insufficient permissions to access or create "\
                    f"file(s) in the {self._saved_models_dir} directory."
            elif not isinstance(e, ValueError):
                msg = "Failed to download or save artifacts."

            self._logger.error("Exception occurred while saving artifacts for model: " \
                               "%s", e)

        return is_artifacts_saved, msg
