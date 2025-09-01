#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""
MR Interface Module.

This module provides functionality for interacting with the Model Registry service
to fetch and download models.
"""
import os
from pathlib import Path
from zipfile import ZipFile
import uuid
import requests


UDF_API_ENDPOINT = "/models"
UDF_GET_FILES = "files"

class MRHandler:
    """
    MRHandler is a class responsible for handling interactions with a Model Registry service. 
    It facilitates fetching model information and downloading model files based on the 
    provided configuration.
    Attributes:
        tasks (dict): Configuration dictionary containing task-related information.
        base_url (str): Base URL for the Model Registry service, fetched from the 
        environment variable "MODEL_REGISTRY_URL".
        logger (object): Logger instance for logging messages.
        fetch_from_model_registry (bool): Flag indicating whether the model was 
        successfully fetched from the Model Registry.
    Methods:
        __init__(config, logger):
            Initializes the MRHandler instance with the given configuration and logger.
            If the configuration specifies fetching a model from the registry, it 
            attempts to retrieve and download the model.
        get_model_info(model_name, model_version):
            Fetches model information from the Model Registry service based on the 
            model name and version.
            Args:
                model_name (str): Name of the model to fetch.
                model_version (str): Version of the model to fetch.
            Returns:
                list or None: A list of model information if successful, or None if an 
                error occurs.
        download_udf_model_by_id(name, id):
            Downloads the model files from the Model Registry service using the model's ID.
            Args:
                name (str): Name of the model.
                id (str): ID of the model to download.
            Raises:
                Exception: If the model files cannot be retrieved or downloaded.
    """
    def __init__(self, config, logger) -> None:
        self.config = config
        self.base_url = os.getenv("MODEL_REGISTRY_URL")
        self.logger = logger
        self.fetch_from_model_registry = False
        self.unique_id = None
        os.environ["REQUESTS_CA_BUNDLE"] = "/run/secrets/server-ca.crt"
        if "model_registry" in self.config and self.config["model_registry"]["enable"] is True:
            logger.info("Fetching model from Model Registry: %s"
                        " version: %s", self.config["udfs"]["name"],
                        self.config["model_registry"]["version"])
            data = self.get_model_info(self.config["udfs"]["name"],
                                       self.config["model_registry"]["version"])
            if data is not None and (len(data))>0:
                mr_id = data[0]["id"]
                self.logger.debug("Model id: %s", mr_id)
                self.unique_id = str(uuid.uuid4())
                self.download_udf_model_by_id(mr_id)
                self.fetch_from_model_registry = True
            else:
                self.logger.error("Error: Invalid Model name/version or Model Registry" \
                " service is not reachable")
                self.fetch_from_model_registry = True
                return
        os.environ["REQUESTS_CA_BUNDLE"] = ""

    def get_model_info(self, model_name, model_version):
        """
        Retrieves information about a specific model from the server.
        Args:
            model_name (str): The name of the model to retrieve information for.
            model_version (str): The version of the model to retrieve information for.
        Returns:
            dict: A dictionary containing the model information if the request is successful.
            None: If the request fails or an error occurs.
        Logs:
            Logs an error message if the request fails or an exception is raised.
        Notes:
            - The method constructs a URL using the base URL, model name, and model version.
            - A GET request is sent to the constructed URL with a timeout of 10 seconds.
            - SSL certificate verification is disabled (verify=False).
        """
        # Construct the URL with the given parameters
        url = f"{self.base_url}/models?name={model_name}&version={model_version}"
        try:
            # Make the GET request
            response = requests.get(url, timeout=10, verify=True)

            # Check if the request was successful
            if response.status_code == 200:
                # Parse the JSON response
                model_info = response.json()
                return model_info
            self.logger.error("Failed to retrieve model info. Status code: %s",
                              response.status_code)
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error("An error occurred: %s", e)
            return None

    def download_udf_model_by_id(self, mr_id): #pragma: no cover
        """
        Downloads a UDF (User-Defined Function) model by its ID, saves it as a zip file, 
        and extracts its contents to a specified directory.

        Args:
            mr_id (str): The ID of the model resource to be downloaded.

        Raises:
            requests.exceptions.RequestException: If the model zip file cannot be retrieved 
                or if any error occurs during the download or extraction process.

        Notes:
            - The downloaded zip file is temporarily stored in the `/tmp` directory.
            - The extracted contents are placed in a subdirectory under `/tmp` named after 
              the `name` argument.
            - SSL verification is disabled for the HTTP request (`verify=False`).
            - Logs errors using the `self.logger` instance.
        """
        try:
            data_headers = {}
            data_headers["Accept"] = "*/*"

            url = f"{self.base_url}{UDF_API_ENDPOINT}/{mr_id}/{UDF_GET_FILES}"
            response2 = requests.get(
                url,
                timeout=30,
                verify=True,
                headers=data_headers
            )
            if response2.status_code == 200:
                file_path = os.path.join("/tmp", "temp.zip")
                with open(file_path, 'wb') as f:
                    f.write(response2.content)
                    f.close()
                model_dir = os.path.join("/tmp", f"{self.unique_id}")
                Path(model_dir).mkdir(parents=True, exist_ok=True)
                with ZipFile(file_path, 'r') as zobj:
                    zobj.extractall(path=model_dir)
            else:
                self.logger.error("Failed to Retrieve model zip file")
                raise Exception("Failed to Retrieve model zip file")
        except Exception as exc:
            self.logger.error("Failed to Retrieve model: %s", exc)
            raise RuntimeError("Failed to Retrieve model") from exc
