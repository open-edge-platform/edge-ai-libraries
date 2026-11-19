#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import json
from unittest.mock import MagicMock, patch

import src.rest_api.endpoints as endpoints


class TestClientIp:

    def test_returns_remote_addr(self):
        with patch("src.rest_api.endpoints.connexion") as mock_connexion:
            mock_connexion.request.remote_addr = "203.0.113.5"
            assert endpoints._client_ip() == "203.0.113.5"

    def test_returns_unknown_on_exception(self):
        with patch("src.rest_api.endpoints.connexion") as mock_connexion:
            type(mock_connexion).request = property(lambda self: (_ for _ in ()).throw(RuntimeError("no context")))
            assert endpoints._client_ip() == "unknown"


class TestAuditLog:

    def test_emits_structured_json_with_expected_fields(self):
        with patch("src.rest_api.endpoints.connexion") as mock_connexion, \
             patch.object(endpoints, "audit_logger") as mock_audit_logger:
            mock_connexion.request.remote_addr = "203.0.113.5"

            endpoints._audit_log("pipeline_start", name="my_pipeline", version="1", instance_id="abc123")

            mock_audit_logger.info.assert_called_once()
            (logged_line,), _ = mock_audit_logger.info.call_args
            payload = json.loads(logged_line)
            assert payload["audit"] is True
            assert payload["action"] == "pipeline_start"
            assert payload["name"] == "my_pipeline"
            assert payload["version"] == "1"
            assert payload["instance_id"] == "abc123"
            assert payload["client_ip"] == "203.0.113.5"
            assert "timestamp" in payload

    def test_defaults_are_none_when_not_provided(self):
        with patch("src.rest_api.endpoints.connexion") as mock_connexion, \
             patch.object(endpoints, "audit_logger") as mock_audit_logger:
            mock_connexion.request.remote_addr = "203.0.113.5"

            endpoints._audit_log("pipeline_stop", instance_id="abc123")

            (logged_line,), _ = mock_audit_logger.info.call_args
            payload = json.loads(logged_line)
            assert payload["action"] == "pipeline_stop"
            assert payload["name"] is None
            assert payload["version"] is None
