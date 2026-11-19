#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os
import stat
from unittest.mock import MagicMock

import pytest

from src.server.path_validator import (
    validate_file_uri,
    validate_request_uris,
    restrict_file_destination_permissions,
)


class TestValidateFileUri:

    def test_non_file_uri_passes(self):
        assert validate_file_uri("rtsp://camera/stream") is True

    def test_none_passes(self):
        assert validate_file_uri(None) is True

    def test_non_string_passes(self):
        assert validate_file_uri(123) is True

    def test_uri_inside_resources_passes(self):
        assert validate_file_uri("file:///home/pipeline-server/resources/videos/warehouse.avi") is True

    def test_uri_outside_resources_rejected(self):
        assert validate_file_uri("file:///etc/passwd") is False

    def test_traversal_via_dotdot_rejected(self):
        assert validate_file_uri("file:///home/pipeline-server/resources/../../etc/shadow") is False

    def test_traversal_within_subpath_rejected(self):
        assert validate_file_uri("file:///home/pipeline-server/resources/videos/../../../secret") is False


class TestValidateRequestUris:

    def test_empty_request_passes(self):
        assert validate_request_uris({}) == (True, None)

    def test_non_dict_request_passes(self):
        assert validate_request_uris(None) == (True, None)

    def test_valid_source_uri_passes(self):
        request = {"source": {"type": "uri", "uri": "file:///home/pipeline-server/resources/videos/x.mp4"}}
        assert validate_request_uris(request) == (True, None)

    def test_malicious_source_uri_rejected(self):
        request = {"source": {"type": "uri", "uri": "file:///etc/passwd"}}
        is_valid, err = validate_request_uris(request)
        assert is_valid is False
        assert "source" in err

    def test_malicious_destination_uri_rejected(self):
        request = {"destination": {"uri": "file:///etc/shadow"}}
        is_valid, err = validate_request_uris(request)
        assert is_valid is False
        assert "destination" in err

    def test_destination_without_uri_field_passes(self):
        # destination.metadata.path (file-type destination) is a different
        # field, checked by restrict_file_destination_permissions, not here.
        request = {"destination": {"metadata": {"type": "file", "path": "/tmp/results.jsonl"}}}
        assert validate_request_uris(request) == (True, None)

    def test_non_uri_source_type_passes(self):
        request = {"source": {"type": "application"}}
        assert validate_request_uris(request) == (True, None)


class TestRestrictFileDestinationPermissions:

    def test_creates_file_with_restrictive_mode(self, tmp_path):
        target = tmp_path / "results.jsonl"
        request = {"destination": {"metadata": {"type": "file", "path": str(target)}}}

        restrict_file_destination_permissions(request)

        assert target.exists()
        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert mode == 0o640

    def test_restricts_mode_of_preexisting_file(self, tmp_path):
        target = tmp_path / "results.jsonl"
        target.touch()
        os.chmod(target, 0o666)
        request = {"destination": {"metadata": {"type": "file", "path": str(target)}}}

        restrict_file_destination_permissions(request)

        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert mode == 0o640

    def test_non_file_destination_is_noop(self, tmp_path):
        request = {"destination": {"metadata": {"type": "mqtt", "topic": "results"}}}
        # Should not raise, and should not create any file.
        restrict_file_destination_permissions(request)

    def test_no_destination_is_noop(self):
        restrict_file_destination_permissions({})
        restrict_file_destination_permissions(None)

    def test_missing_path_is_noop(self):
        request = {"destination": {"metadata": {"type": "file"}}}
        restrict_file_destination_permissions(request)

    def test_unwritable_path_logs_warning_but_does_not_raise(self):
        request = {"destination": {"metadata": {"type": "file", "path": "/nonexistent_dir/results.jsonl"}}}
        logger = MagicMock()

        restrict_file_destination_permissions(request, logger=logger)

        logger.warning.assert_called_once()
