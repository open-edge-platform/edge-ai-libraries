# pylint: disable=import-error
"""Module for managing the use of MLflow"""
import ast
import uuid
from ast import literal_eval
from enum import Enum
from datetime import datetime
from typing import List, Dict, Any
from fastapi import HTTPException
import mlflow
from mlflow.utils.logging_utils import disable_logging
from managers.minio_manager import MinioManager
from models.registered_model import RegisteredModel
from models.project import OptimizedModel
from utils.logging_config import logger, configure_alembic_logger

class Operation(Enum):
    """An enumeration representing operations related to models.

    Members:
        REGISTER_MODEL: Signifies that a model is being registered
        UPDATE_TAGS: Signifies that a model's tags are being updated
    """
    REGISTER_MODEL = 1
    UPDATE_MODEL = 2

class MLflowManager():
    """A class for managing MLflow interactions"""
    _client = None

    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(MLflowManager, cls).__new__(cls)
        return cls.instance

    def init_client(self):
        """Initialize MLflow client
        """
        if self._client is None:
            # Note: psycopg2.OperationalError can happen from connection issue
            # This doesn't raise an exception that can be caught
            disable_logging()
            logger.debug("Instantiating MLflowClient object.....")
            self._client = mlflow.MlflowClient()
            configure_alembic_logger()
            logger.debug("Created a new MLflowClient object")


    def register_model(self, metadata: Dict[str, str], file_content, file_name: str) -> str:
        """Store the model's metadata and file

        Args:
            model_metadata (Dict[str, str]): _description_

        Returns:
            str: The id for the model registered
        """
        new_model_id = ""
        is_duplicate_model = False
        msg = ""
        metadata_keys = metadata.keys()

        self.init_client()

        # Set default values if field is not provided
        # Note: MLFlow doesn't create UUID for models
        default_values = {"id": str(uuid.uuid4()), "target_device": "CPU", "score": "0.0", "precision": "fp32"}
        for key, val in default_values.items():
            if not key in metadata_keys or metadata.get(key) == "":
                metadata[key] = val

        # Make the `precision` value consistent with models imported from Geti
        metadata["precision"] = [metadata["precision"]]

        # Delete key:value pair that has a value of ""
        attrs = dict(metadata)
        for k, v in attrs.items():
            if v == "":
                del metadata[k]

        is_duplicate_model, msg = self.duplicate_model_check(new_model_metadata=metadata,
                                                             mode=Operation.REGISTER_MODEL)

        if not is_duplicate_model:
            # store the file in minio
            minio_manager = MinioManager()
            model_file_url = minio_manager.store_data(
                                prefix_dir=metadata["id"],
                                file_object=file_content,
                                file_name=file_name)

            # register the model metadata using mlflow
            # model_uri = f"models:/{metadata['id']}/{metadata['name']}"

            metadata["file_url"] = model_file_url

            registered_model = self._client.create_registered_model(name=metadata['id'], tags=metadata)

            new_model_id = registered_model.tags["id"]

        return new_model_id, is_duplicate_model, msg


    def register_geti_model(self, model: OptimizedModel, model_file_url: str) -> bool:
        """
        Save model metadata
        Args:
            model: A Geti `Model`
            model_file_url: The url where the model is stored
        Returns:
            True: if the model was registered successfully
            False: Otherwise
        """
        is_model_registered = False

        self.init_client()

        # Prevent registering models that already exist in the registry id (Geti) -> name (MLflow)
        # Return False if the model is already stored in the registry
        registered_models = self._client.search_registered_models(
            filter_string=f"name='{model.id}'")

        if len(registered_models) > 0:
            return False

        model_tags = {
            "target_device": model.target_device,
            "created_date": model.created_date,
            "precision": model.precision,
            "project_id": model.project_id,
            "size": model.size,
            "id": model.id,
            "name": model.name,
            "version": model.version,
            "format": model.model_format.lower(),
            "origin": "Geti",
            "file_url": model_file_url,
            "project_name": model.project_name,
            "category": model.category.title(),
            "target_device_type": model.target_device_type,
            "score": model.score,
            "overview": model.overview,
            "optimization_capabilities": model.optimization_capabilities,
            "labels": model.labels,
            "architecture": model.architecture
        }

        registered_model = self._client.create_registered_model(name=model.id, tags=model_tags)

        if registered_model is not None:
            is_model_registered = registered_model.name == model.id

        return is_model_registered

    def update_model(self, model_id, metadata: Dict[str, Any]) -> bool:
        """Update the metadata for a model

        Args:
            model_metadata (Dict[str, Any]): The metadata to be updated for an registered model

        Returns:
            A tuple containing a boolean (True if the properties were updated, Otherwise, false)
            another boolean (True if update will result in match with a registered model, False otherwise)
            and a message.
        """
        is_metadata_updated = None
        try:
            self.init_client()

            model = self._client.get_registered_model(model_id)
            new_metadata = model.tags.copy()

            if metadata.get("precision"):
                metadata["precision"] = str([metadata["precision"]])

            new_metadata.update(metadata)

            is_duplicate_model, msg = self.duplicate_model_check(new_model_metadata=new_metadata,
                                                                 mode=Operation.UPDATE_MODEL)

            if not is_duplicate_model:
                for k, v in metadata.items():
                    self._client.set_registered_model_tag(name=model_id, key=k, value=v)

                last_updated_date = str(datetime.now()) + " UTC"
                self._client.set_registered_model_tag(name=model_id, key="last_updated_date", value=last_updated_date)
                is_metadata_updated = True
        except Exception as exc:
            logger.debug("Exception occured while updating model metadata: %s", exc)
            msg = f"Error: {exc}"
            is_metadata_updated = False

        return is_metadata_updated, is_duplicate_model, msg

    def get_models(self, model_id=None, keys=None, values=None) -> List[RegisteredModel]:
        """
        Get model(s) based on id or other criteria
        Args:
            model_id: The id for a model
            keys: the metadata attributes to search for models by
            values: the values associated to the keys
        Returns:
            A list of models based on the search criteria
        """
        registered_models: List[RegisteredModel] = []
        comparator = "="
        f_string = ""

        self.init_client()

        if model_id is None and keys is None:
            mlflow_registered_models = self._client.search_registered_models()
        else:
            if model_id:
                attr = "name"
                value = model_id
                f_string = f"{attr} {comparator} '{value}'"
            else:
                # Iterate over the keys and values lists at the same time to construct filter string
                for key, value in zip(keys, values):
                    if value is None:
                        continue

                    if f_string:
                        f_string = f_string + " AND "

                    attr = "tags."+key

                    special_characters = ("<", "%", "'")
                    if self._string_contains_any_char(input_string=value, char_tuple=special_characters):
                        sc_string = ", ".join(special_characters)
                        raise HTTPException(status_code=400, detail=f"The value provided for '{key}' must not contain special characters like {sc_string}.")

                    if attr in ["tags.name", "tags.project_name", "tags.category", "tags.architecture", "tags.precision"]:
                        comparator = "ILIKE"
                        value = "%"+str(value)+"%"
                    else:
                        comparator = "="

                    f_string = f_string + \
                        f"{attr} {comparator} '{value}'"
            mlflow_registered_models = self._client.search_registered_models(
                filter_string=f_string)

        # create a list consisting of model metadata
        for m in mlflow_registered_models:
            p = m.tags.get("precision", "[]")
            o = m.tags.get("overview", "{}")
            oc = m.tags.get("optimization_capabilities", "{}")
            l = m.tags.get("labels", "[]")
            created_date = str(datetime.fromtimestamp(m.last_updated_timestamp/1000)) + " UTC"
            registered_model = RegisteredModel(id=m.tags.get("id"),
                                               name=m.tags.get("name"),
                                               target_device=m.tags.get("target_device"),
                                               created_date=m.tags.get("created_date", created_date),
                                               last_updated_date=m.tags.get("last_updated_date", created_date),
                                               precision=literal_eval(p) if isinstance(p, str) else [],
                                               size=m.tags.get("size"),
                                               version=m.tags.get("version"),
                                               format=m.tags.get("format"),
                                               origin=m.tags.get("origin"),
                                               file_url=m.tags.get("file_url"),
                                               project_id=m.tags.get("project_id"),
                                               project_name=m.tags.get("project_name"),
                                               category=m.tags.get("category"),
                                               target_device_type=m.tags.get("target_device_type"),
                                               score=literal_eval(m.tags.get("score", "0.0")),
                                               overview=literal_eval(o) if isinstance(o, str) else {},
                                               optimization_capabilities= literal_eval(oc) if isinstance(oc, str) else {},
                                               labels=ast.literal_eval(l) if isinstance(l, str) else [],
                                               architecture=m.tags.get("architecture"))
            registered_models.append(registered_model)

        return registered_models

    def duplicate_model_check(self, new_model_metadata: Dict[str, Any], mode: Operation) -> bool:
        """Check if any existing registered models share properties with a new model

        Args:
            new_model_metadata (Dict[str, Any]): The metadata for a new model to compare against
            existing registered models
        
        Returns:
            A tuple containing a boolean (True if a match is found, False otherwise) and a string
            describing the items that match
        """
        id_already_exists = False
        name_ver_prec_already_exists = False
        match_msg = ""
        registered_models = self.get_models()

        try:
            self.init_client()

            for registered_model in registered_models:
                id_ = registered_model.id
                name = registered_model.name
                ver = registered_model.version
                precision = registered_model.precision if mode == Operation.REGISTER_MODEL else str(registered_model.precision)
                project_name = registered_model.project_name
                project_id = registered_model.project_id

                if mode == Operation.REGISTER_MODEL:
                    id_already_exists = id_ == new_model_metadata.get("id", "")

                name_ver_prec_already_exists = (project_name == new_model_metadata.get("project_name") and
                                                project_id == new_model_metadata.get("project_id") and
                                                name == new_model_metadata.get("name") and
                                                ver == new_model_metadata.get("version") and
                                                precision == new_model_metadata.get("precision"))

                if id_already_exists or name_ver_prec_already_exists:
                    if mode == Operation.UPDATE_MODEL and \
                        id_ == new_model_metadata.get("id"):
                        break
                    match_msg = f"'{id_}'."
                    return True, match_msg

        except Exception as exc:
            logger.debug("Exception occured during duplicate model check: %s", exc)
            return None, "Unknown Error"

        return False, match_msg


    def delete_model(self, m_id) -> bool:
        """
        Delete a model associated to id
        Args:
            id: The identifier for a model
        Returns:
            True: Successfully deleted model
            False: Otherwise
        """
        is_model_deletion_complete = False

        self.init_client()

        registered_models = self._client.search_registered_models(
            filter_string=f"name='{m_id}'")

        if len(registered_models) > 0:
            minio_manager = MinioManager()
            for rm in registered_models:
                file_name = rm.tags["file_url"].split("/")[-1]
                # Delete object in object storage
                minio_manager.delete_data(
                    prefix_dir=rm.tags["id"], file_name=file_name)
                self._client.delete_registered_model(name=rm.name)
                is_model_deletion_complete = True

        return is_model_deletion_complete

    def _string_contains_any_char(self, input_string: str, char_tuple: tuple) -> bool:
        """
        Checks if a string contains any characters from a given tuple.

        Args:
            input_string: The string to check.
            char_tuple: A tuple of characters to search for.

        Returns:
            True if the string contains at least one character from the tuple,
            False otherwise.
        """

        for char in char_tuple:
            if char in input_string:
                return True

        return False
