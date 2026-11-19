#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import connexion
import requests
import time
import os
import json
import datetime
from pydantic import ValidationError
from http import HTTPStatus
from src.common.log import get_logger, get_audit_logger
from src.server.pipeline import Pipeline

logger = get_logger('REST API Endpoints')
audit_logger = get_audit_logger()

BAD_REQUEST_RESPONSE = 'Invalid pipeline, version or instance'
NOT_IMPLEMENTED = 'Unsupported endpoint'


def _client_ip():
    """Best-effort client IP for SDL423/T-005 audit logging."""
    try:
        return connexion.request.remote_addr
    except Exception:
        return 'unknown'


def _audit_log(action, name=None, version=None, instance_id=None):
    """SDL423/T-005: structured, persistent audit entry for a pipeline lifecycle action."""
    audit_logger.info(json.dumps({
        'audit': True,
        'action': action,
        'name': name,
        'version': version,
        'instance_id': instance_id,
        'client_ip': _client_ip(),
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }))

class Endpoints:

    pipeline_server_manager = None

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
                _audit_log('pipeline_stop', instance_id=instance_id)
                return result
            return (BAD_REQUEST_RESPONSE, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            logger.error('pipelines_instance_id_delete %s (client %s)', error, _client_ip())
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
                    _audit_log('pipeline_start', name=name, version=version, instance_id=pipeline_id)
                    return pipeline_id
                return (err, HTTPStatus.BAD_REQUEST)
            except Exception as error:
                logger.exception('Exception in pipelines_name_version_post %s (client %s)', error, _client_ip())
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
                    _audit_log('pipeline_request', name=name, version=version, instance_id=instance_id)
                    return pipeline_id
                return (err, HTTPStatus.BAD_REQUEST)
            except Exception as error:
                logger.error('Exception in pipelines_name_version_instance_id_post %s (client %s)', error, _client_ip())
                return ('Unexpected error', HTTPStatus.INTERNAL_SERVER_ERROR)

        return('Invalid Request, Body must be valid JSON', HTTPStatus.BAD_REQUEST)
