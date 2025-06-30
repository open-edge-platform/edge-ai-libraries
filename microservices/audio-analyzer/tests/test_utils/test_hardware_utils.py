# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib
from unittest.mock import patch, MagicMock

import pytest

from audio_analyzer.utils.hardware_utils import is_intel_gpu_available


@pytest.mark.unit
def test_is_intel_gpu_available_success():
    """Test GPU detection when Intel GPU is available"""
    # Mock importlib.util.find_spec to return True for openvino modules
    with patch("importlib.util.find_spec", return_value=True):
        # Mock OpenVINO Core to report GPU in available devices
        with patch("openvino.Core") as mock_core:
            # Create a mock for Core instance
            mock_core_instance = MagicMock()
            mock_core.return_value = mock_core_instance
            
            # Configure available_devices to include GPU
            mock_core_instance.available_devices = ["CPU", "GPU"]
            
            # Call the function and check result
            result = is_intel_gpu_available()
            
            assert result is True
            mock_core.assert_called_once()


@pytest.mark.unit
def test_is_intel_gpu_available_no_gpu():
    """Test GPU detection when no Intel GPU is available"""
    # Mock importlib.util.find_spec to return True for openvino modules
    with patch("importlib.util.find_spec", return_value=True):
        # Mock OpenVINO Core to report only CPU in available devices
        with patch("openvino.Core") as mock_core:
            # Create a mock for Core instance
            mock_core_instance = MagicMock()
            mock_core.return_value = mock_core_instance
            
            # Configure available_devices to NOT include GPU
            mock_core_instance.available_devices = ["CPU"]
            
            # Call the function and check result
            result = is_intel_gpu_available()
            
            assert result is False
            mock_core.assert_called_once()


@pytest.mark.unit
def test_is_intel_gpu_available_no_openvino():
    """Test GPU detection when OpenVINO is not available"""
    # Mock importlib.util.find_spec to return False for openvino modules
    with patch("importlib.util.find_spec", return_value=None):
        # Call the function and check result
        result = is_intel_gpu_available()
        
        assert result is False


@pytest.mark.unit
def test_is_intel_gpu_available_exception():
    """Test GPU detection when an exception occurs"""
    # Mock importlib.util.find_spec to return True for openvino modules
    with patch("importlib.util.find_spec", return_value=True):
        # Mock OpenVINO Core to raise an exception
        with patch("openvino.Core", side_effect=Exception("Test exception")):
            # Call the function and check result
            result = is_intel_gpu_available()
            
            assert result is False
