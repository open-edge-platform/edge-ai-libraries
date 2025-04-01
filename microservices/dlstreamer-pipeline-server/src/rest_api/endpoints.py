#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import connexion
import requests
import time
import os
from pydantic import ValidationError
from http import HTTPStatus
from src.common.log import get_logger
from src.model_updater import ModelRegistryClient, ModelQueryParams
from src.server.pipeline import Pipeline

logger = get_logger('REST API Endpoints')

BAD_REQUEST_RESPONSE = 'Invalid pipeline, version or instance'
NOT_IMPLEMENTED = 'Unsupported endpoint'

class Endpoints:

    pipeline_server_manager = None
    model_registry_client: ModelRegistryClient = None

    def models_get():  # noqa: E501
        """models_get

        Return supported models # noqa: E501


        :rtype: List[ModelVersion]
        """
        return (NOT_IMPLEMENTED, HTTPStatus.BAD_REQUEST)


    def pipelines_get():  # noqa: E501
        """pipelines_get

        Return supported pipelines # noqa: E501


        :rtype: List[Pipeline]
        """
        try:
            logger.debug("GET on /pipelines")
            return Endpoints.pipeline_server_manager.get_loaded_pipelines()
        except Exception as error:
            logger.error('pipelines_name_version_get %s', error)
            return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)


    def pipelines_name_version_get(name, version):  # noqa: E501
        """pipelines_name_version_get

        Return pipeline description and parameters # noqa: E501

        :param name:
        :type name: str
        :param version:
        :type version: str

        :rtype: None
        """
        return (NOT_IMPLEMENTED, HTTPStatus.BAD_REQUEST)


    def pipelines_name_version_instance_id_delete(name, version, instance_id):  # noqa: E501
        """pipelines_name_version_instance_id_delete

        Stop and remove an instance of the customized pipeline # noqa: E501

        :param name:
        :type name: str
        :param version:
        :type version: str
        :param instance_id:
        :type instance_id: int

        :rtype: None
        """
        return (NOT_IMPLEMENTED, HTTPStatus.BAD_REQUEST)

    def pipelines_instance_id_delete(instance_id):  # noqa: E501
        """pipelines_instance_id_delete

        Stop and remove an instance of the customized pipeline # noqa: E501

        :param instance_id:
        :type instance_id: int

        :rtype: None
        """
        try:
            logger.debug("DELETE on /pipelines/{id}".format(id=instance_id))
            result = Endpoints.pipeline_server_manager.stop_instance(instance_id)
            if result:
                result['state'] = result['state'].name
                return result
            return (BAD_REQUEST_RESPONSE, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            logger.error('pipelines_instance_id_delete %s', error)
            return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)


    def pipelines_name_version_instance_id_get(name, version, instance_id):  # noqa: E501
        """pipelines_name_version_instance_id_get

        Return instance summary # noqa: E501

        :param instance_id:
        :type instance_id: int
        :param name:
        :type name: str
        :param version:
        :type version: str

        :rtype: object
        """
        return (NOT_IMPLEMENTED, HTTPStatus.BAD_REQUEST)


    def pipelines_instance_id_get(instance_id):  # noqa: E501
        """pipelines_instance_id_get

        Return instance summary # noqa: E501

        :param instance_id:
        :type instance_id: int

        :rtype: object
        """
        try:
            logger.debug("GET on /pipelines/{id}".format(id=instance_id))
            result, err = Endpoints.pipeline_server_manager.get_pipeline_instance_summary(instance_id)
            if result is not None:
                return result
            return (err, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            logger.error('pipelines_instance_id_get %s', error)
            return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)


    def pipelines_name_version_instance_id_status_get(name, version, instance_id):  # noqa: E501
        """pipelines_name_version_instance_id_status_get

        Return instance status summary # noqa: E501

        :param name:
        :type name: str
        :param version:
        :type version: str
        :param instance_id:
        :type instance_id: int

        :rtype: object
        """
        return (NOT_IMPLEMENTED, HTTPStatus.BAD_REQUEST)

    def pipelines_status_get_all():  # noqa: E501
        """pipelines_status_get_all

        Returns all instance status summary # noqa: E501

        :rtype: object
        """
        try:
            logger.debug("GET on /pipelines/status")
            results = Endpoints.pipeline_server_manager.get_all_instance_status()
            for result in results:
                result['state'] = result['state'].name
            return results
        except Exception as error:
            logger.error('pipelines_status_get %s', error)
            return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)


    def pipelines_instance_id_status_get(instance_id):  # noqa: E501
        """pipelines_instance_id_status_get

        Return instance status summary # noqa: E501

        :param instance_id:
        :type instance_id: int

        :rtype: object
        """
        try:
            logger.debug("GET on /pipelines/{id}/status".format(id=instance_id))
            result = Endpoints.pipeline_server_manager.get_instance_status(instance_id)
            if result:
                result['state'] = result['state'].name
                return result
            return ('Invalid instance', HTTPStatus.BAD_REQUEST)
        except Exception as error:
            logger.error('pipelines_instance_id_status_get %s', error)
            return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)

    def pipelines_name_version_post(name, version):  # noqa: E501
        """pipelines_name_version_post

        Start new instance of pipeline.
        Specify the source and destination parameters as URIs # noqa: E501

        :param name:
        :type name: str
        :param version:
        :type version: str
        :param pipeline_request:
        :type pipeline_request: dict | bytes

        :rtype: None
        """

        logger.debug(
            "POST on /pipelines/{name}/{version}".format(name=name, version=str(version)))
        if connexion.request.is_json:
            try:
                pipeline_id, err = Endpoints.pipeline_server_manager.start_instance(
                    name, version, connexion.request.get_json())
                if pipeline_id is not None:
                    return pipeline_id
                return (err, HTTPStatus.BAD_REQUEST)
            except Exception as error:
                logger.exception('Exception in pipelines_name_version_post %s', error)
                return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)

        return('Invalid Request, Body must be valid JSON', HTTPStatus.BAD_REQUEST)
    

    def pipelines_name_version_instance_id_post(name, version, instance_id):  # noqa: E501
        """pipelines_name_version_instance_id_post

        Send a new request to pipeline instance.
        Specify the source and destination parameters as URIs # noqa: E501

        :param name:
        :type name: str
        :param version:
        :type version: str
        :param instance_id:
        :type instance_id: int
        :param pipeline_request:
        :type pipeline_request: dict | bytes

        :rtype: None
        """

        logger.debug(
            "POST on /pipelines/{name}/{version}/{instance_id}".format(name=name, version=str(version), instance_id=instance_id))
        if connexion.request.is_json:
            try:
                pipeline_id, err = Endpoints.pipeline_server_manager.execute_request_on_instance(
                    name, version, instance_id, connexion.request.get_json())
                if pipeline_id is not None:
                    return pipeline_id
                return (err, HTTPStatus.BAD_REQUEST)
            except Exception as error:
                logger.error('Exception in pipelines_name_version_instance_id_post %s', error)
                return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)

        return('Invalid Request, Body must be valid JSON', HTTPStatus.BAD_REQUEST)

    def pipelines_name_version_instance_id_models_files_post(name,
                                                             version,
                                                             instance_id):  # noqa: E501
        """pipelines_name_version_get

        Save model(s) from the model registry microservice # noqa: E501

        :param name:
        :type name: str
        :param version:
        :type version: str
        :param instance_id:
        :type instance_id: str
        :param model_query_params:
        :type model_query_params: dict | bytes

        :rtype: None
        """
        logger.debug(
            "POST on /pipelines/%s/%s/%s/models", name, version, instance_id)
        resp_body = {"status": "error", "message": ""}

        if not Endpoints.model_registry_client:
            resp_body["message"] = "Connection to the model registry "\
                "microservice is not established."
            return (resp_body, HTTPStatus.INTERNAL_SERVER_ERROR)

        if connexion.request.is_json:
            try:
                model_query_params = connexion.request.get_json()
                try:
                    _ = ModelQueryParams(**model_query_params)
                except ValidationError as e:
                    resp_body["message"] = "Invalid model query parameters"
                    for error in e.errors():
                        logger.error("Invalid model query parameters: %s", str(error['msg']))
                        resp_body["message"] = resp_body["message"] + ", " + str(error['msg'])
                    return (resp_body, HTTPStatus.BAD_REQUEST)

                pipelines_cfg = [{"name":version, "model_params": [model_query_params]}]

                is_model_files_downloaded, msg = \
                    Endpoints.model_registry_client.download_models(pipelines_cfg)

                is_success_criteria_met = is_model_files_downloaded
                resp_body["message"] = msg

                restart_pipeline = model_query_params.get("deploy", False)

                model_path = None
                if restart_pipeline:
                    model_path_dict = Endpoints.model_registry_client.get_model_path(pipelines_cfg)
                    if model_path_dict:
                        model_path = next(iter(Endpoints.model_registry_client.get_model_path(pipelines_cfg).values()))
                    if is_model_files_downloaded and model_path is None:
                        resp_body["message"] = (
                            "Model(s) downloaded, but failed to get model path."
                        )
                        return (resp_body, HTTPStatus.INTERNAL_SERVER_ERROR)
                    if is_model_files_downloaded and not os.path.exists(model_path):
                        resp_body["message"] = f"Model(s) downloaded, but model path {model_path} does not exist."
                        return (resp_body, HTTPStatus.INTERNAL_SERVER_ERROR)

                new_pipeline_instance_id = None
                if restart_pipeline:
                    resp = Endpoints.pipeline_server_manager.get_pipeline_instance_summary(instance_id)
                    p_summary = resp[0]
                    p_instance_state = p_summary.get("state") if p_summary else None
                    if isinstance(p_summary, dict):
                        p_params = p_summary["params"]
                        prev_request = p_params.get("request", None)
                        if None not in (p_params.get("source"),
                                        prev_request.get("destination"),
                                        prev_request.get("parameters")):
                            pipeline_cfg = {"source": p_params["source"],
                                            "destination": prev_request["destination"],
                                            "parameters": prev_request["parameters"]
                                            }
                            resp = Endpoints.pipelines_instance_id_delete(instance_id)
                        else:
                            resp = None
           
                        # Get parameter name from the pipeline definition
                        # that corresponds to the pipeline element name
                        pipeline_param_name = None
                        pipelines = Endpoints.pipeline_server_manager.app_config['pipelines']
                        pipeline_dfn = [param for param in pipelines if param.get("name") == p_params.get("version")]
                        pipeline_dfn_params = pipeline_dfn[0].get("parameters", None)
                        if pipeline_dfn_params:
                            pipeline_properties = pipeline_dfn_params.get("properties", None)
                            for key, value in pipeline_properties.items():
                                if isinstance(value.get('element', None), dict):
                                    if value.get('element', {}).get('name') != model_query_params.get(
                                        'pipeline_element_name'):
                                        continue
                                else:
                                    if value.get('element', None) != model_query_params.get(
                                        'pipeline_element_name'):
                                        continue
                                if (key == "udfloader"or key == "model" or 
                                    value.get('element',{}).get('format', None) == "element-properties" or
                                    value.get('element', {}).get('property') == "model"):
                                    pipeline_param_name = key

                        if not pipeline_param_name:
                            resp_body["message"] = (
                                f"Unable to find the pipeline parameters for "
                                f"pipeline element '{model_query_params.get('pipeline_element_name')}'"
                            )
                            return (resp_body, HTTPStatus.BAD_REQUEST)

                        # Update the model in the pipeline configuration
                        if isinstance(pipeline_cfg["parameters"][pipeline_param_name], dict):
                            if pipeline_cfg["parameters"][pipeline_param_name].get("udfs", None):
                                pipeline_cfg["parameters"][pipeline_param_name].get("udfs", None)[0]["deployment"] = \
                                    model_path.split('/deployment', 1)[0] + '/deployment'

                            if pipeline_cfg["parameters"][pipeline_param_name].get("model", None):
                                pipeline_cfg["parameters"][pipeline_param_name]["model"] = \
                                    model_path                           
                        else:
                            pipeline_cfg["parameters"][pipeline_param_name] = model_path

                        while p_instance_state in (Pipeline.State.QUEUED.name,
                                                   Pipeline.State.RUNNING.name):
                            p = Endpoints.pipeline_server_manager.get_pipeline_instance_summary(instance_id)[0]
                            p_instance_state = p.get("state")
                            logger.debug("Pipeline instance (%s) state: %s", p.get('id'),
                                         p_instance_state)
                            time.sleep(1)

                        new_pipeline_instance_id, _ = \
                            Endpoints.pipeline_server_manager.start_instance(name,
                                                                            version,
                                                                            pipeline_cfg)

                    is_success_criteria_met = is_model_files_downloaded and \
                        (restart_pipeline and new_pipeline_instance_id)

                if is_model_files_downloaded and new_pipeline_instance_id is None and \
                    restart_pipeline:
                    if msg.endswith("."):
                        msg = msg[:-1]

                    error_msg = resp[1]
                    resp_body["message"] = msg + \
                        ", but failed to restart the pipeline. " + error_msg

                resp_body["status"] = "success" if is_success_criteria_met else "error"

                if is_success_criteria_met:
                    status_code = HTTPStatus.OK

                    if new_pipeline_instance_id:
                        resp_body["message"] = msg + \
                        " Pipeline instance was restarted."
                        resp_body["new_instance_id"] = new_pipeline_instance_id
                elif "not found" in resp_body["message"].lower():
                    status_code = HTTPStatus.BAD_REQUEST
                else:
                    status_code = HTTPStatus.INTERNAL_SERVER_ERROR

                return (resp_body, status_code)

            except Exception as exc:
                logger.error("Exception in " \
                             "pipelines_name_version_instance_id_models_files_post: %s", exc)
                resp_body["message"] = "Unexpected error"
                return (resp_body, HTTPStatus.INTERNAL_SERVER_ERROR)

        return ('Invalid Request, Body must be valid JSON', HTTPStatus.BAD_REQUEST)
