#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from http import HTTPStatus
from unittest.mock import MagicMock, patch

import src.rest_api.endpoints as endpoints
from src.rest_api.endpoints import Endpoints


class TestValidIdentifier:

    def test_accepts_alphanumeric_underscore_dot_dash(self):
        assert endpoints._valid_identifier("pallet_defect_detection")
        assert endpoints._valid_identifier("user_defined_pipelines")
        assert endpoints._valid_identifier("1.0")
        assert endpoints._valid_identifier("my-pipeline")

    def test_rejects_path_traversal_and_special_characters(self):
        assert not endpoints._valid_identifier("../../etc/passwd")
        assert not endpoints._valid_identifier("name/with/slashes")
        assert not endpoints._valid_identifier("name;rm -rf /")
        assert not endpoints._valid_identifier("")

    def test_rejects_oversized_input(self):
        assert not endpoints._valid_identifier("a" * 129)
        assert endpoints._valid_identifier("a" * 128)

    def test_rejects_non_string_input(self):
        assert not endpoints._valid_identifier(None)
        assert not endpoints._valid_identifier(123)


class TestValidInstanceId:

    def test_accepts_uuid1_hex_format(self):
        assert endpoints._valid_instance_id("a6d67224eacc11ec9f360242c0a86003")

    def test_rejects_non_hex_and_dashed_uuid(self):
        assert not endpoints._valid_instance_id("a6d67224-eacc-11ec-9f36-0242c0a86003")
        assert not endpoints._valid_instance_id("not-an-instance-id!")

    def test_rejects_non_string_input(self):
        assert not endpoints._valid_instance_id(None)


class TestPathParamValidationInHandlers:

    def test_pipelines_instance_id_delete_rejects_invalid_instance_id(self):
        Endpoints.pipeline_server_manager = MagicMock()

        result, status = Endpoints.pipelines_instance_id_delete("../etc/passwd")

        assert status == HTTPStatus.BAD_REQUEST
        assert result == endpoints.BAD_REQUEST_RESPONSE
        Endpoints.pipeline_server_manager.stop_instance.assert_not_called()

    def test_pipelines_name_version_post_rejects_invalid_name(self):
        Endpoints.pipeline_server_manager = MagicMock()

        with patch.object(endpoints, "connexion") as mock_connexion:
            mock_connexion.request.is_json = True
            result, status = Endpoints.pipelines_name_version_post("../../etc", "1")

        assert status == HTTPStatus.BAD_REQUEST
        assert result == endpoints.BAD_REQUEST_RESPONSE
        Endpoints.pipeline_server_manager.start_instance.assert_not_called()
