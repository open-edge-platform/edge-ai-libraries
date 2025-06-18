# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from minio.error import S3Error

from audio_intelligence.utils.minio_handler import MinioHandler


@pytest.mark.unit
def test_get_client(mock_minio_client):
    """Test getting a MinIO client instance"""
    with patch("audio_intelligence.utils.minio_handler.settings") as mock_settings:
        # Configure mock settings
        mock_settings.MINIO_ENDPOINT = "localhost:9000"
        mock_settings.MINIO_ACCESS_KEY = "test_access_key"
        mock_settings.MINIO_SECRET_KEY = "test_secret_key"
        mock_settings.MINIO_SECURE = False
        
        # Get client and verify it's created with correct parameters
        client = MinioHandler.get_client()
        
        # Check that the Minio constructor was called with correct parameters
        from audio_intelligence.utils.minio_handler import Minio
        Minio.assert_called_once_with(
            mock_settings.MINIO_ENDPOINT,
            access_key=mock_settings.MINIO_ACCESS_KEY,
            secret_key=mock_settings.MINIO_SECRET_KEY,
            secure=mock_settings.MINIO_SECURE
        )

