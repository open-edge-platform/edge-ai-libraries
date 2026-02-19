# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import asyncio
import pytest
import tempfile
import subprocess
from unittest.mock import patch, MagicMock, call

from src.plugins.openvino_plugin import OpenVINOConverter
from src.core.interfaces import DownloadTask


class TestOpenVINOConverter:
    """Test suite for OpenVINOConverter plugin"""

    @pytest.fixture
    def openvino_plugin(self):
        """Create an instance of OpenVINOConverter for testing"""
        return OpenVINOConverter()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_plugin_properties(self, openvino_plugin):
        """Test plugin basic properties"""
        assert openvino_plugin.plugin_name == "openvino"
        assert openvino_plugin.plugin_type == "converter"

    @pytest.mark.parametrize("hub,is_ovms,expected", [
        ("openvino", False, True),
        ("Openvino", False, True),
        ("OPENVINO", False, True),
        ("huggingface", True, True),
        ("ollama", True, True),
        ("ultralytics", True, True),
        ("huggingface", False, False),
        ("ollama", False, False),
        ("ultralytics", False, False),
        ("random_hub", False, False),
    ])
    def test_can_handle_hub_and_ovms(self, openvino_plugin, hub, is_ovms, expected):
        """Test can_handle method with different hubs and is_ovms values"""
        result = openvino_plugin.can_handle("test-model", hub, is_ovms=is_ovms)
        assert result == expected

    @pytest.mark.parametrize("model_name", [
        "bert-base-uncased",
        "microsoft/DialoGPT-medium",
        "facebook/opt-1.3b",
        "Intel/neural-chat-7b-v3-3",
        "BAAI/bge-small-en-v1.5",
        "user/custom-model",
    ])
    def test_can_handle_various_model_names(self, openvino_plugin, model_name):
        """Test can_handle with various model name formats"""
        # Should return True for openvino hub regardless of model name
        assert openvino_plugin.can_handle(model_name, "openvino") == True
        
        # Should return True when is_ovms=True regardless of hub
        assert openvino_plugin.can_handle(model_name, "huggingface", is_ovms=True) == True
        
        # Should return False for non-openvino hubs when is_ovms=False
        assert openvino_plugin.can_handle(model_name, "huggingface", is_ovms=False) == False

    def test_download_not_implemented(self, openvino_plugin, temp_dir):
        """Test that download method raises NotImplementedError"""
        with pytest.raises(NotImplementedError, match="OpenVINO plugin is a converter, not a downloader"):
            asyncio.run(openvino_plugin.download("test-model", temp_dir))

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_success(self, mock_getenv, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test successful model conversion"""
        # Setup mocks
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        mock_getenv.return_value = "/host/models"

        result = openvino_plugin.convert(
            model_name="Intel/neural-chat-7b-v3-3",
            output_dir=temp_dir,
            hf_token="test_token",
            precision="int8",
            device="CPU",
            cache=10,
            type="llm"
        )

        # Verify convert_to_ovms_format was called with correct parameters
        mock_convert_to_ovms.assert_called_once_with(
            weight_format="int8",
            huggingface_token="test_token",
            model_type="llm",
            target_device="CPU",
            model_directory=temp_dir,
            version="",
            model_name="Intel/neural-chat-7b-v3-3",
            config_dict={
                "precision": "int8",
                "device": "CPU",
                "cache": 10,
                "type": "llm"
            }
        )

        # Verify result
        assert result["model_name"] == "Intel/neural-chat-7b-v3-3"
        assert result["source"] == "openvino"
        assert result["type"] == "llm"
        assert result["is_ovms"] == True
        assert result["success"] == True
        assert result["config"] == {"precision": "int8", "device": "CPU", "cache": 10}

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_convert_with_default_parameters(self, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test conversion with default parameters"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}

        result = openvino_plugin.convert(
            model_name="bert-base-uncased",
            output_dir=temp_dir,
            hf_token="test_token"
        )

        # Verify defaults were used
        call_kwargs = mock_convert_to_ovms.call_args.kwargs
        assert call_kwargs["weight_format"] == "int8"
        assert call_kwargs["huggingface_token"] == "test_token"
        assert call_kwargs["model_type"] == "llm"
        assert call_kwargs["target_device"] == "CPU"
        assert call_kwargs["model_directory"] == temp_dir
        assert call_kwargs["version"] == ""
        assert call_kwargs["model_name"] == "bert-base-uncased"
        assert call_kwargs["config_dict"] == {}

        assert result["config"] == {}

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_convert_failure_return_code(self, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test conversion failure due to non-zero return code"""
        mock_convert_to_ovms.return_value = {"returncode": 1, "stdout": "", "stderr": "Conversion failed"}

        with pytest.raises(RuntimeError) as exc_info:
            openvino_plugin.convert(
                model_name="invalid-model",
                output_dir=temp_dir,
                hf_token="test_token",
                precision="int8"
            )
        assert "Model conversion failed due to Conversion failed" in str(exc_info.value)

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_convert_failure_exception(self, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test conversion failure due to exception"""
        mock_convert_to_ovms.side_effect = Exception("Conversion error")

        with pytest.raises(RuntimeError, match="Failed to convert model to OVMS format: Conversion error"):
            openvino_plugin.convert(
                model_name="bert-base-uncased",
                output_dir=temp_dir,
                hf_token="test_token"
            )

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_path_replacement(self, mock_getenv, mock_convert_to_ovms, openvino_plugin):
        """Test host path replacement in conversion results"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        mock_getenv.return_value = "/host/models"

        # Create a directory that starts with /opt/models/
        output_dir = "/opt/models/test_model"
        
        result = openvino_plugin.convert(
            model_name="bert-base-uncased",
            output_dir=output_dir,
            hf_token="test_token",
            precision="int8"
        )

        # Should replace /opt/models/ with host prefix
        expected_path = "/host/models/test_model"
        assert result["conversion_path"] == expected_path

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_no_path_replacement(self, mock_getenv, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test no path replacement when not needed"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        mock_getenv.return_value = "/host/models"

        result = openvino_plugin.convert(
            model_name="bert-base-uncased",
            output_dir=temp_dir,
            hf_token="test_token",
            precision="int8"
        )

        # Path should not be replaced since it doesn't start with /opt/models/
        assert result["conversion_path"] == temp_dir

    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.makedirs')
    def test_convert_to_ovms_format_success(self, mock_makedirs, mock_popen, mock_run, openvino_plugin):
        """Test successful convert_to_ovms_format method"""
        # Setup mocks
        mock_run.side_effect = [MagicMock(returncode=0)]  # Already logged in
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Processing...", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        result = openvino_plugin.convert_to_ovms_format(
            model_name="Intel/neural-chat-7b-v3-3",
            weight_format="int8",
            huggingface_token="test_token",
            model_type="llm",
            target_device="CPU",
            model_directory="/test/output",
            config_dict={"cache_size": 10}
        )

        assert result["returncode"] == 0
        first_call = mock_run.call_args_list[0]
        assert first_call[0][0] == ["hf", "auth", "whoami"]
        assert first_call[1]["capture_output"] is True
        assert first_call[1]["text"] is True
        mock_makedirs.assert_called_once_with("/test/output", exist_ok=True)

    @patch('subprocess.run')
    def test_convert_to_ovms_format_invalid_model_type(self, mock_run, openvino_plugin):
        """Test convert_to_ovms_format with invalid model type"""
        with pytest.raises(RuntimeError, match="Invalid model_type: invalid"):
            openvino_plugin.convert_to_ovms_format(
                model_name="test-model",
                weight_format="fp16",
                huggingface_token="test_token",
                model_type="invalid",
                target_device="CPU",
                model_directory="/test/output"
            )

    @patch('subprocess.run')
    def test_convert_to_ovms_format_no_hf_token(self, mock_run, openvino_plugin):
        """Test convert_to_ovms_format without HF token"""
        with pytest.raises(RuntimeError, match="Hugging Face token is required for OVMS conversion"):
            openvino_plugin.convert_to_ovms_format(
                model_name="test-model",
                weight_format="fp16",
                huggingface_token="",
                model_type="llm",
                target_device="CPU",
                model_directory="/test/output"
            )

    @patch('subprocess.run')
    def test_convert_to_ovms_format_hf_auth_failure(self, mock_run, openvino_plugin):
        """Test convert_to_ovms_format with HF authentication failure"""
        mock_run.side_effect = [
            MagicMock(returncode=1),  # whoami check fails
            MagicMock(returncode=1)   # login fails
        ]

        with pytest.raises(RuntimeError, match="Failed to authenticate with Hugging Face"):
            openvino_plugin.convert_to_ovms_format(
                model_name="test-model",
                weight_format="fp16",
                huggingface_token="invalid_token",
                model_type="llm",
                target_device="CPU",
                model_directory="/test/output"
            )
            assert mock_run.call_args_list[1][0][0][:3] == ["hf", "auth", "login"]

    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.makedirs')
    def test_convert_to_ovms_format_handles_missing_script(self, mock_makedirs, mock_popen, mock_run, openvino_plugin):
        """Test convert_to_ovms_format does not attempt script download in current implementation"""
        mock_run.return_value = MagicMock(returncode=0)
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        result = openvino_plugin.convert_to_ovms_format(
            model_name="test-model",
            weight_format="fp16",
            huggingface_token="test_token",
            model_type="llm",
            target_device="CPU",
            model_directory="/test/output"
        )

        assert result == 0
        # Verify curl was called to download the script
        curl_call = call(["curl", 
                         "https://raw.githubusercontent.com/openvinotoolkit/model_server/tags/releases/2026/0/demos/common/export_models/export_model.py",
                         "-o", "export_model.py"], check=True)
        assert curl_call in mock_run.call_args_list

    @pytest.mark.parametrize("model_type,expected_export_type", [
        ("llm", "text_generation"),
        ("embeddings", "embeddings_ov"),
        ("rerank", "rerank_ov"),
    ])
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.makedirs')
    def test_convert_to_ovms_format_model_types(self, mock_makedirs, mock_popen, mock_run, 
                                               openvino_plugin, model_type, expected_export_type):
        """Test convert_to_ovms_format with different model types"""
        mock_run.side_effect = [MagicMock(returncode=0)]
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        result = openvino_plugin.convert_to_ovms_format(
            model_name="test-model",
            weight_format="fp16",
            huggingface_token="test_token",
            model_type=model_type,
            target_device="CPU",
            model_directory="/test/output"
        )

        assert result["returncode"] == 0
        # Verify the correct export type was used in the command
        mock_popen.assert_called_once()
        command = mock_popen.call_args[0][0]
        assert expected_export_type in command

    def test_get_download_tasks_not_implemented(self, openvino_plugin):
        """Test that get_download_tasks raises NotImplementedError"""
        with pytest.raises(NotImplementedError, match="OpenVINO converter does not support task-based downloading"):
            openvino_plugin.get_download_tasks("test-model")

    def test_download_task_not_implemented(self, openvino_plugin):
        """Test that download_task raises NotImplementedError"""
        task = DownloadTask("file1", "http://example.com", "/dest")
        
        with pytest.raises(NotImplementedError, match="OpenVINO converter does not support task-based downloading"):
            openvino_plugin.download_task(task, "/output")

    def test_post_process(self, openvino_plugin):
        """Test post_process method"""
        result = asyncio.run(openvino_plugin.post_process(
            model_name="bert-base-uncased",
            output_dir="/test/output",
            downloaded_paths=["/test/output/model.xml"],
            config={
                "precision": "int8",
                "device": "GPU",
                "cache": 15
            },
            type="embeddings"
        ))

        assert result["model_name"] == "bert-base-uncased"
        assert result["source"] == "openvino"
        assert result["type"] == "embeddings"
        assert result["conversion_path"] == "/test/output"
        assert result["is_ovms"] == True
        assert result["success"] == True
        assert result["config"]["precision"] == "int8"
        assert result["config"]["device"] == "GPU"
        assert result["config"]["cache"] == 15

    @pytest.mark.parametrize("config,expected_precision,expected_device,expected_cache", [
        ({"precision": "int4", "device": "GPU", "cache": 20}, "int4", "GPU", 20),
        ({}, "int8", "CPU", None),  # defaults align with implementation
        ({"precision": "fp32"}, "fp32", "CPU", None),  # partial config
    ])
    def test_post_process_config_handling(self, openvino_plugin, config, expected_precision, expected_device, expected_cache):
        """Test post_process with different config combinations"""
        result = asyncio.run(openvino_plugin.post_process(
            model_name="test-model",
            output_dir="/test/output",
            downloaded_paths=[],
            config=config
        ))

        assert result["config"]["precision"] == expected_precision
        assert result["config"]["device"] == expected_device
        assert result["config"]["cache"] == expected_cache


class TestOpenVINOConverterIntegration:
    """Integration tests for OpenVINOConverter"""

    @pytest.fixture
    def openvino_plugin(self):
        return OpenVINOConverter()

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_end_to_end_conversion_workflow(self, mock_convert_to_ovms, openvino_plugin):
        """Test complete conversion workflow"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test the complete workflow
            result = openvino_plugin.convert(
                model_name="Intel/neural-chat-7b-v3-3",
                output_dir=temp_dir,
                hf_token="test_token",
                precision="int8",
                device="CPU",
                cache=10,
                type="llm"
            )
            
            # Verify results
            assert result["model_name"] == "Intel/neural-chat-7b-v3-3"
            assert result["source"] == "openvino"
            assert result["type"] == "llm"
            assert result["success"] == True
            assert result["is_ovms"] == True
            
            # Test post-processing
            post_result = asyncio.run(openvino_plugin.post_process(
                model_name="Intel/neural-chat-7b-v3-3",
                output_dir=result["conversion_path"],
                downloaded_paths=[os.path.join(result["conversion_path"], "model.xml")],
                config=result["config"],
                type="llm"
            ))
            
            assert post_result["success"] == True
            assert post_result["model_name"] == "Intel/neural-chat-7b-v3-3"

    @pytest.mark.parametrize("hub,is_ovms", [
        ("openvino", False),
        ("huggingface", True),
        ("ollama", True),
    ])
    def test_can_handle_integration(self, openvino_plugin, hub, is_ovms):
        """Test can_handle integration scenarios"""
        assert openvino_plugin.can_handle("test-model", hub, is_ovms=is_ovms) == True

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_error_handling_workflow(self, mock_convert_to_ovms, openvino_plugin):
        """Test error handling during complete workflow"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test conversion failure
            mock_convert_to_ovms.return_value = {"returncode": 1, "stdout": "", "stderr": "Conversion failed"}
            
            with pytest.raises(RuntimeError) as exc_info:
                openvino_plugin.convert(
                    model_name="invalid-model",
                    output_dir=temp_dir,
                    hf_token="test_token"
                )
            
            assert "Model conversion failed due to Conversion failed" in str(exc_info.value)

        # Test exception during conversion
        mock_convert_to_ovms.side_effect = Exception("Network error")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(RuntimeError) as exc_info:
                openvino_plugin.convert(
                    model_name="test-model",
                    output_dir=temp_dir,
                    hf_token="test_token"
                )
            
            assert "Failed to convert model to OVMS format: Network error" in str(exc_info.value)

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_parameter_combinations(self, mock_convert_to_ovms, openvino_plugin):
        """Test various parameter combinations"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        
        test_cases = [
            # (config, kwargs, expected_calls)
            (
                {"precision": "int4", "device": "GPU", "cache": 20},
                {"type": "embeddings", "version": "v1.0"},
                {"weight_format": "int4", "target_device": "GPU", "model_type": "embeddings", "version": "v1.0"}
            ),
            (
                {},
                {"precision": "fp32", "device": "CPU"},
                {"weight_format": "fp32", "target_device": "CPU", "model_type": "llm", "version": ""}
            ),
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            for config, kwargs, expected in test_cases:
                mock_convert_to_ovms.reset_mock()
                
                result = openvino_plugin.convert(
                    model_name="test-model",
                    output_dir=temp_dir,
                    hf_token="test_token",
                    **config,
                    **kwargs
                )
                
                # Verify the call was made with expected parameters
                call_kwargs = mock_convert_to_ovms.call_args[1]
                for key, value in expected.items():
                    assert call_kwargs[key] == value
                expected_config_dict = {**config, **kwargs}
                assert call_kwargs["config_dict"] == expected_config_dict
                
                assert result["success"] == True

    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.makedirs')
    def test_full_convert_to_ovms_format_workflow(self, mock_makedirs, mock_popen, mock_run, openvino_plugin):
        """Test full convert_to_ovms_format workflow with various scenarios"""
        # Test successful workflow with cache_size for LLM
        mock_run.side_effect = [MagicMock(returncode=0)]
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Model exported successfully", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        result = openvino_plugin.convert_to_ovms_format(
            model_name="Intel/neural-chat-7b-v3-3",
            weight_format="int8",
            huggingface_token="test_token",
            model_type="llm",
            target_device="CPU",
            model_directory="/test/output",
            version="v2.0",
            config_dict={"cache_size": 15}
        )

        assert result["returncode"] == 0
        
        # Verify the command was constructed correctly
        command = mock_popen.call_args[0][0]
        assert "text_generation" in command
        assert "--cache_size" in command
        assert "15" in command
        assert "--version" in command
        assert "v2.0" in command


class TestOpenVINOPluginFutureProof:
    """Test suite for future-proof parameter handling in OpenVINOConverter"""

    @pytest.fixture
    def openvino_plugin(self):
        """Create an instance of OpenVINOConverter for testing"""
        return OpenVINOConverter()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_get_param_from_nested_openvino_config(self, openvino_plugin):
        """Test _get_param falls back to default when only nested config is provided"""
        config = {
            "openvino_config": {
                "precision": "int4",
                "device": "GPU",
                "cache_size": 20
            }
        }
        
        assert openvino_plugin._get_param("precision", config, {}, "fallback") == "fallback"
        assert openvino_plugin._get_param("device", config, {}, "CPU") == "CPU"
        assert openvino_plugin._get_param("cache_size", config, {}, 0) == 0

    def test_get_param_from_flat_config(self, openvino_plugin):
        """Test _get_param extracts from flat config structure (backward compat)"""
        config = {
            "precision": "int8",
            "device": "CPU",
            "cache_size": 10
        }
        
        assert openvino_plugin._get_param("precision", config, {}) == "int8"
        assert openvino_plugin._get_param("device", config, {}) == "CPU"
        assert openvino_plugin._get_param("cache_size", config, {}) == 10

    def test_get_param_from_kwargs(self, openvino_plugin):
        """Test _get_param extracts from direct kwargs (legacy)"""
        kwargs = {
            "precision": "fp16",
            "device": "NPU"
        }
        
        assert openvino_plugin._get_param("precision", {}, kwargs) == "fp16"
        assert openvino_plugin._get_param("device", {}, kwargs) == "NPU"

    def test_get_param_fallback_chain(self, openvino_plugin):
        """Test _get_param checks config, then kwargs, then default"""
        config = {"precision": "int8"}
        kwargs = {"precision": "fp16", "device": "CPU"}
        
        # Config takes priority over kwargs
        assert openvino_plugin._get_param("precision", config, kwargs) == "int8"
        
        # Falls back to kwargs if config missing
        config_empty = {}
        assert openvino_plugin._get_param("device", config_empty, kwargs) == "CPU"
        
        # Falls back to default if all missing
        assert openvino_plugin._get_param("unknown", {}, {}, "default") == "default"

    def test_build_export_command_with_known_params(self, openvino_plugin, temp_dir):
        """Test _build_export_command correctly maps known parameters"""
        config_dict = {
            "precision": "int8",
            "device": "CPU",
            "cache_size": 20,
            "kv_cache_precision": "u8",
            "enable_prefix_caching": True,
            "truncate": False,  # Should not be added (False)
            "num_streams": 2
        }
        
        command = openvino_plugin._build_export_command(
            export_type="text_generation",
            model_name="test-model",
            output_dir=temp_dir,
            config_dict=config_dict,
            target_device="CPU",
            weight_format="int8"
        )
        
        # Check known parameters are mapped correctly
        assert "--weight-format" in command
        assert "int8" in command
        assert "--target_device" in command
        assert "--cache_size" in command
        assert "20" in command
        assert "--kv_cache_precision" in command
        assert "u8" in command
        assert "--enable_prefix_caching" in command
        assert "--num_streams" in command
        assert "2" in command
        # Boolean False should not be added
        assert "--truncate" not in command

    def test_build_export_command_with_unknown_params(self, openvino_plugin, temp_dir):
        """Test _build_export_command passes unknown parameters through (future-proof)"""
        config_dict = {
            "precision": "int8",
            "new_quantization_method": "gptq",  # Unknown parameter
            "custom_optimization_flag": True,    # Unknown boolean
            "future_param_value": "test_value"   # Unknown parameter
        }
        
        command = openvino_plugin._build_export_command(
            export_type="text_generation",
            model_name="test-model",
            output_dir=temp_dir,
            config_dict=config_dict,
            target_device="CPU",
            weight_format="int8"
        )
        
        # Unknown parameters should be converted to kebab-case and added to command
        assert "--new_quantization_method" in command
        assert "gptq" in command
        assert "--custom_optimization_flag" in command  # Boolean True
        assert "--future_param_value" in command
        assert "test_value" in command

    def test_build_export_command_skips_none_values(self, openvino_plugin, temp_dir):
        """Test _build_export_command skips None values"""
        config_dict = {
            "precision": "int8",
            "cache_size": None,
            "normalize": None
        }
        
        command = openvino_plugin._build_export_command(
            export_type="embeddings_ov",
            model_name="test-model",
            output_dir=temp_dir,
            config_dict=config_dict,
            target_device="CPU",
            weight_format="int8"
        )
        
        # None values should not be added to command
        assert "--cache_size" not in command
        assert "--normalize" not in command

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_backward_compat_flat_config(self, mock_getenv, mock_convert_to_ovms, 
                                                 openvino_plugin, temp_dir, conversion_config):
        """Test convert supports legacy flat config structure"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        mock_getenv.return_value = "/host/models"

        result = openvino_plugin.convert(
            model_name="test-model",
            output_dir=temp_dir,
            hf_token="test_token",
            **conversion_config,
            type="llm"
        )

        # Verify call was made with extracted parameters
        assert mock_convert_to_ovms.called
        call_kwargs = mock_convert_to_ovms.call_args[1]
        assert call_kwargs["weight_format"] == conversion_config["precision"]
        assert call_kwargs["target_device"] == conversion_config["device"]
        
        # Response should include config that was in request
        assert result["config"]["precision"] == "int8"
        assert result["config"]["device"] == "CPU"
        assert result["config"]["cache"] == 10

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_new_nested_openvino_config(self, mock_getenv, mock_convert_to_ovms, 
                                               openvino_plugin, temp_dir, conversion_config_optimum_cli):
        """Test convert supports new Optimum CLI-aligned nested structure"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        mock_getenv.return_value = "/host/models"

        nested_config = conversion_config_optimum_cli["openvino_config"]

        result = openvino_plugin.convert(
            model_name="test-model",
            output_dir=temp_dir,
            hf_token="test_token",
            **nested_config,
            type="llm"
        )

        # Verify convert_to_ovms_format called with config_dict
        assert mock_convert_to_ovms.called
        call_kwargs = mock_convert_to_ovms.call_args[1]
        assert call_kwargs["weight_format"] == nested_config["precision"]
        assert call_kwargs["target_device"] == nested_config["device"]
        assert "config_dict" in call_kwargs
        
        # Response should only include params from openvino_config
        response_config = result["config"]
        assert "precision" in response_config
        assert "device" in response_config
        assert response_config["precision"] == "int4"

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_response_only_includes_requested_params(self, mock_getenv, mock_convert_to_ovms, 
                                                              openvino_plugin, temp_dir):
        """Test that response config only includes parameters present in request"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        mock_getenv.return_value = "/host/models"

        # Request with only precision and device  
        config = {
            "precision": "int8",
            "device": "CPU"
        }

        result = openvino_plugin.convert(
            model_name="test-model",
            output_dir=temp_dir,
            hf_token="test_token",
            **config,
            type="llm"
        )

        # Response should only have precision and device
        response_config = result["config"]
        assert "precision" in response_config
        assert "device" in response_config
        assert "cache" not in response_config

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_with_unknown_future_params(self, mock_getenv, mock_convert_to_ovms, 
                                                openvino_plugin, temp_dir, conversion_config_with_unknown_params):
        """Test convert passes unknown parameters to convert_to_ovms_format (future-proof)"""
        mock_convert_to_ovms.return_value = {"returncode": 0, "stdout": "", "stderr": ""}
        mock_getenv.return_value = "/host/models"

        config = conversion_config_with_unknown_params["openvino_config"]

        result = openvino_plugin.convert(
            model_name="test-model",
            output_dir=temp_dir,
            hf_token="test_token",
            **config,
            type="llm"
        )

        # Verify unknown params are passed to convert_to_ovms_format in config_dict
        assert mock_convert_to_ovms.called
        call_kwargs = mock_convert_to_ovms.call_args[1]
        config_dict = call_kwargs["config_dict"]
        
        # Unknown parameters should be in config_dict
        assert "new_quantization_method" in config_dict
        assert config_dict["new_quantization_method"] == "gptq"
        assert "custom_optimization_flag" in config_dict
        assert config_dict["custom_optimization_flag"] is True
        assert result["config"]["precision"] == config["precision"]

