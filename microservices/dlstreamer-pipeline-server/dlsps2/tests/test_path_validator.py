# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for config.path_validator (path traversal + file permission hardening)."""

import os
import stat
import sys
from unittest.mock import MagicMock

# Mock gi/GStreamer so modules can be imported without a real GStreamer install
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gst'] = MagicMock()

from api.schema import SourceConfig, DestinationConfig, MetadataDestinationConfig
from config.path_validator import (
    validate_file_uri,
    validate_file_path,
    validate_source_destination,
    restrict_file_destination_permissions,
)


class TestValidateFileUri:

    def test_non_file_uri_passes(self):
        assert validate_file_uri("rtsp://camera/stream") is True

    def test_none_passes(self):
        assert validate_file_uri(None) is True

    def test_uri_inside_resources_passes(self):
        assert validate_file_uri("file:///home/pipeline-server/resources/videos/x.mp4") is True

    def test_uri_outside_resources_rejected(self):
        assert validate_file_uri("file:///etc/passwd") is False

    def test_traversal_rejected(self):
        assert validate_file_uri("file:///home/pipeline-server/resources/../../etc/shadow") is False


class TestValidateFilePath:

    def test_empty_path_passes(self):
        assert validate_file_path(None) is True
        assert validate_file_path("") is True

    def test_path_inside_resources_passes(self):
        assert validate_file_path("/home/pipeline-server/resources/results.jsonl") is True

    def test_traversal_path_rejected(self):
        assert validate_file_path("/home/pipeline-server/resources/../../etc/shadow") is False

    def test_absolute_path_outside_resources_rejected(self):
        assert validate_file_path("/etc/shadow") is False


class TestValidateSourceDestination:

    def test_no_source_no_destination_passes(self):
        assert validate_source_destination(None, None) == (True, None)

    def test_valid_source_uri_passes(self):
        source = SourceConfig(uri="file:///home/pipeline-server/resources/videos/x.mp4", type="uri")
        assert validate_source_destination(source, None) == (True, None)

    def test_malicious_source_uri_rejected(self):
        source = SourceConfig(uri="file:///etc/passwd", type="uri")
        is_valid, err = validate_source_destination(source, None)
        assert is_valid is False
        assert "source.uri" in err

    def test_non_file_destination_type_not_checked(self):
        destination = DestinationConfig(metadata=MetadataDestinationConfig(type="mqtt", topic="results"))
        assert validate_source_destination(None, destination) == (True, None)

    def test_valid_file_destination_path_passes(self):
        destination = DestinationConfig(
            metadata=MetadataDestinationConfig(type="file", path="/home/pipeline-server/resources/results.jsonl")
        )
        assert validate_source_destination(None, destination) == (True, None)

    def test_malicious_file_destination_path_rejected(self):
        destination = DestinationConfig(metadata=MetadataDestinationConfig(type="file", path="/etc/shadow"))
        is_valid, err = validate_source_destination(None, destination)
        assert is_valid is False
        assert "destination.metadata.path" in err


class TestRestrictFileDestinationPermissions:

    def test_creates_file_with_restrictive_mode(self, tmp_path):
        target = tmp_path / "results.jsonl"
        destination = DestinationConfig(metadata=MetadataDestinationConfig(type="file", path=str(target)))

        restrict_file_destination_permissions(destination)

        assert target.exists()
        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert mode == 0o640

    def test_non_file_destination_is_noop(self, tmp_path):
        destination = DestinationConfig(metadata=MetadataDestinationConfig(type="mqtt", topic="results"))
        restrict_file_destination_permissions(destination)  # must not raise

    def test_no_destination_is_noop(self):
        restrict_file_destination_permissions(None)

    def test_unwritable_path_logs_warning_but_does_not_raise(self):
        destination = DestinationConfig(
            metadata=MetadataDestinationConfig(type="file", path="/nonexistent_dir/results.jsonl")
        )
        logger = MagicMock()

        restrict_file_destination_permissions(destination, logger=logger)

        logger.warning.assert_called_once()
