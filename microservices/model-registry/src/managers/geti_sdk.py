import os
import shutil
import zipfile
from pydantic import TypeAdapter
from typing import List, Optional

from geti_sdk import Geti
from geti_sdk.rest_clients import ProjectClient
from geti_sdk.data_models import Project
from geti_sdk.rest_clients.model_client import ModelClient

from models.project import ProjectOut, ModelVersion, ModelGroup, OptimizedModel
from models.model_identifiers import ModelIdentifiersIn
from managers.mlflow_manager import MLflowManager
from managers.minio_manager import MinioManager
from utils.logging_config import logger
from utils.app_utils import get_bool

class GetiSdk():
    """
    A class for an Intel Geti SDK project
    """
    _server_url = os.environ.get("GETI_HOST")
    _server_api_token = os.environ.get("GETI_TOKEN")
    _verify_server_ssl_cert = get_bool(os.getenv("GETI_SERVER_SSL_VERIFY", "True"), ignore_empty=True)

    def __new__(cls):
        if not hasattr(cls, 'instance'):
            if any([cls._server_url is None,
                    cls._server_api_token is None]):
                logger.warning("One or more environment variables required to communicate with a Geti Server are not set."
                             " Please restart the service and set the following environment variables: GETI_HOST and GETI_TOKEN."
                             " Subsequent Geti related requests will fail.")

            cls.instance = super(GetiSdk, cls).__new__(cls)
        return cls.instance

    def get_projects(self, project_id: str = None) -> [ProjectOut]:
        """Get all projects or a specific project associated to the project_id.

        Returns:
            List[ProjectOut]: List of projects
        """
        geti = Geti(
            host=f"{self._server_url}",
            token=f"{self._server_api_token}",
            verify_certificate=self._verify_server_ssl_cert
        )
        project_client = ProjectClient(session=geti.session, workspace_id=geti.workspace_id)
        project_list = project_client.list_projects()

        # Only interest on specific project id
        target_projects = []
        if project_id:
            for proj_item in project_list:
                if proj_item.id == project_id:
                    target_projects = [ proj_item ]
                    break
        else:
            target_projects = project_list

        rsc_projects = []
        for project in target_projects:
            model_client = ModelClient(workspace_id=geti.workspace_id, project=project, session=geti.session)
            # Get Geti Server model groups and all latest model
            geti_model_groups = model_client.get_all_model_groups()
            geti_models = model_client.get_latest_model_for_all_model_groups()

            # Mapping Model Registry <-> Geti
            # model_groups <--> geti_model_groups
            # model_versions <--> geti_models
            # openvino_models <--> geti_model.optimized_models
            rsc_model_groups = []
            for geti_model_group in geti_model_groups:
                rsc_model_versions = []
                for geti_model in geti_models:
                    json_labels = []
                    for label in geti_model.labels:
                        json_label = { "name": label.name,
                                       "color": label.color,
                                       "group": label.group,
                                       "is_empty": label.is_empty,
                                       "hotkey": label.hotkey,
                                       "domain": label.domain,
                                       "id": label.id,
                                       "parent_id": label.parent_id,
                                       "is_anomalous": label.is_anomalous,
                                       "is_background": label.is_background }
                        json_labels.append(json_label)

                    if geti_model_group.name == geti_model.name:
                        # openvino_models <--> geti_model.optimized_models
                        rsc_openvino_models = []
                        for optimized_model in geti_model.optimized_models:

                            json_openvino_model = { "id": optimized_model.id,
                                                    "name": optimized_model.name,
                                                    "model_format": optimized_model.model_format,
                                                    "target_device": optimized_model.target_device,
                                                    "creation_date": optimized_model.creation_date.isoformat(),
                                                    "precision": optimized_model.precision,
                                                    "size": optimized_model.size,
                                                    "version": str(optimized_model.version),
                                                    "target_device_type": optimized_model.target_device_type,
                                                    "score": optimized_model.performance.score,
                                                    "labels": json_labels }
                            rsc_optimized_model = TypeAdapter(OptimizedModel).validate_python(json_openvino_model)
                            rsc_openvino_models.append(rsc_optimized_model)

                        # model_versions <--> geti_models
                        json_model_version = { "id": geti_model.id,
                                                "name": geti_model.name,
                                                "version": geti_model.version,
                                                "openvino_models": rsc_openvino_models }
                        rsc_model_version = TypeAdapter(ModelVersion).validate_python(json_model_version)
                        rsc_model_versions.append(rsc_model_version)

                # model_groups <--> geti_model_groups
                json_model_group = { 'id': geti_model_group.id,
                                     'name': geti_model_group.name,
                                     'models': rsc_model_versions }
                rsc_model_group = TypeAdapter(ModelGroup).validate_python(json_model_group)
                rsc_model_groups.append(rsc_model_group)

            json_project = { 'id': project.id,
                             'name': project.name,
                             'creation_time': project.creation_time.isoformat(),
                             'model_groups': rsc_model_groups }
            rsc_project = TypeAdapter(ProjectOut).validate_python(json_project)
            rsc_projects.append(rsc_project)

        return rsc_projects

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

        geti = Geti(
            host=f"{self._server_url}",
            token=f"{self._server_api_token}",
            verify_certificate=self._verify_server_ssl_cert
        )
        registered_model_ids = []
        try:
            project_client = ProjectClient(session=geti.session, workspace_id=geti.workspace_id)
            project_list = project_client.list_projects()

            # Only interest on specific project id
            project = None
            if project_id:
                for proj_item in project_list:
                    if proj_item.id == project_id:
                        project = proj_item
                        break

            if project:
                model_client = ModelClient(workspace_id=geti.workspace_id, project=project, session=geti.session)
                for model_identifiers in model_identifiers_in.models:
                    model = model_client._get_model_detail(model_identifiers.group_id, model_identifiers.id)
                    # Extract labels
                    json_labels = []
                    for label in model.labels:
                        json_label = { "name": label.name,
                                       "color": label.color,
                                       "group": label.group,
                                       "is_empty": label.is_empty,
                                       "hotkey": label.hotkey,
                                       "domain": label.domain,
                                       "id": label.id,
                                       "parent_id": label.parent_id,
                                       "is_anomalous": label.is_anomalous,
                                       "is_background": label.is_background }
                        json_labels.append(json_label)

                    for optimized_model in model.optimized_models:
                        if optimized_model.id == model_identifiers.id:
                            # project = self.get_projects(project_id=project_id)[0]

                            base_dir_name = project.name.lower().replace(" ", "-").replace(".", "")
                            current_dir_path = "./"
                            base_dir = current_dir_path + base_dir_name
                            zip_file_path = base_dir + ".zip"

                            if not os.path.exists(base_dir):
                                os.makedirs(base_dir)

                            model_client._download_model(optimized_model, path_to_folder=base_dir)
                            geti_zipfilename = f"{optimized_model.name}_{optimized_model.optimization_type}_optimized.zip"
                            geti_zipfile_path = base_dir + "/models/" + geti_zipfilename
                            with zipfile.ZipFile(geti_zipfile_path, 'r') as zip_ref:
                                zip_ref.extractall(base_dir)

                            logger.debug(f"Remove zip file {geti_zipfile_path}")
                            os.remove(geti_zipfile_path)

                            geti_model_dir = base_dir + "/models"
                            logger.debug(f"Remove directory {geti_model_dir}")
                            shutil.rmtree(geti_model_dir)

                            logger.debug(f"Files extracted to {base_dir}")
                            shutil.make_archive(base_name=base_dir_name,
                                                format='zip', base_dir=base_dir)
                            logger.debug(f"{base_dir_name}.zip file created")

                            minio_manager = MinioManager()
                            mlflow_manager = MLflowManager()
                            model_file_url = minio_manager.store_data(
                                prefix_dir=optimized_model.id ,
                                file_path=zip_file_path,
                                file_name=base_dir_name+".zip")

                            model_category = "undefined"
                            geti_model_supported_tasks = ("detection", "classification", "segmentation", "anomaly")
                            for task in project.pipeline.tasks:
                                task_type = str(task.task_type)
                                if task_type.lower() in geti_model_supported_tasks:
                                    model_category = task_type.lower()
                                    break

                            # mlflow_manager.register_geti_model() uses model registry OptimizedModel, we need
                            # to construct it from Geti SDK OptimizedModel. Also,
                            # Also, the format should match m.tags in MLflowManager->get_models()
                            json_optimized_model = {
                                    "target_device": optimized_model.target_device,
                                    "creation_date": optimized_model.creation_date.isoformat(),
                                    "precision": optimized_model.precision,
                                    "project_id": project.id,
                                    "size": optimized_model.size,
                                    "id": optimized_model.id,
                                    "name": optimized_model.name,
                                    "version": optimized_model.version,
                                    "model_format": optimized_model.model_format,
                                    "origin": "Geti",
                                    "file_url": model_file_url,
                                    "project_name": project.name,
                                    "category": model_category,
                                    "target_device_type": optimized_model.target_device_type,
                                    "score": optimized_model.performance.score,
                                    "overview": optimized_model.overview,
                                    "optimization_capabilities": optimized_model.optimization_objectives,
                                    "labels": json_labels,
                                }
                            rsc_optimized_model = TypeAdapter(OptimizedModel).validate_python(json_optimized_model)
                            _ = mlflow_manager.register_geti_model(model=rsc_optimized_model, model_file_url=model_file_url)

                            shutil.rmtree(base_dir)
                            logger.info(f"{base_dir} deleted")
                            os.remove(zip_file_path)
                            logger.info(f"{zip_file_path} deleted")
                            registered_model_ids.append(optimized_model.id)
            else:
                logger.error(f"Geti Server: Invalid project ID {project_id}")

        except Exception as e:
            raise e

        return registered_model_ids
