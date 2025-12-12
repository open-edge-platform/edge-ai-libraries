import os
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
            openvino_plugin.download("test-model", temp_dir)

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_success(self, mock_getenv, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test successful model conversion"""
        # Setup mocks
        mock_convert_to_ovms.return_value = 0
        mock_getenv.return_value = "/host/models"

        result = openvino_plugin.convert(
            model_name="Intel/neural-chat-7b-v3-3",
            output_dir=temp_dir,
            hf_token="test_token",
            config={
                "precision": "int8",
                "device": "CPU",
                "cache": 10
            },
            type="llm"
        )

        # Verify convert_to_ovms_format was called with correct parameters
        mock_convert_to_ovms.assert_called_once_with(
            weight_format="int8",
            huggingface_token="test_token",
            model_type="llm",
            target_device="CPU",
            model_directory=temp_dir,
            cache_size=10,
            version="",
            model_name="Intel/neural-chat-7b-v3-3"
        )

        # Verify result
        assert result["model_name"] == "Intel/neural-chat-7b-v3-3"
        assert result["source"] == "openvino"
        assert result["type"] == "llm"
        assert result["is_ovms"] == True
        assert result["success"] == True
        assert result["config"]["precision"] == "int8"
        assert result["config"]["device"] == "CPU"
        assert result["config"]["cache"] == 10

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_convert_with_default_parameters(self, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test conversion with default parameters"""
        mock_convert_to_ovms.return_value = 0

        result = openvino_plugin.convert(
            model_name="bert-base-uncased",
            output_dir=temp_dir,
            hf_token="test_token"
        )

        # Verify defaults were used
        mock_convert_to_ovms.assert_called_once_with(
            weight_format="fp16",  # default
            huggingface_token="test_token",
            model_type="llm",  # default
            target_device="CPU",  # default
            model_directory=temp_dir,
            cache_size=None,  # default
            version="",  # default
            model_name="bert-base-uncased"
        )

        assert result["config"]["precision"] == "fp16"
        assert result["config"]["device"] == "CPU"
        assert result["config"]["cache"] is None

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    def test_convert_failure_return_code(self, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test conversion failure due to non-zero return code"""
        mock_convert_to_ovms.return_value = 1

        with pytest.raises(RuntimeError, match="Model conversion failed with return code 1"):
            openvino_plugin.convert(
                model_name="invalid-model",
                output_dir=temp_dir,
                hf_token="test_token"
            )

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
        mock_convert_to_ovms.return_value = 0
        mock_getenv.return_value = "/host/models"

        # Create a directory that starts with /opt/models/
        output_dir = "/opt/models/test_model"
        
        result = openvino_plugin.convert(
            model_name="bert-base-uncased",
            output_dir=output_dir,
            hf_token="test_token"
        )

        # Should replace /opt/models/ with host prefix
        expected_path = "/host/models/test_model"
        assert result["conversion_path"] == expected_path

    @patch.object(OpenVINOConverter, 'convert_to_ovms_format')
    @patch('os.getenv')
    def test_convert_no_path_replacement(self, mock_getenv, mock_convert_to_ovms, openvino_plugin, temp_dir):
        """Test no path replacement when not needed"""
        mock_convert_to_ovms.return_value = 0
        mock_getenv.return_value = "/host/models"

        result = openvino_plugin.convert(
            model_name="bert-base-uncased",
            output_dir=temp_dir,
            hf_token="test_token"
        )

        # Path should not be replaced since it doesn't start with /opt/models/
        assert result["conversion_path"] == temp_dir

    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_convert_to_ovms_format_success(self, mock_makedirs, mock_exists, mock_popen, mock_run, openvino_plugin):
        """Test successful convert_to_ovms_format method"""
        # Setup mocks
        mock_run.return_value.returncode = 0
        mock_exists.return_value = True  # export_model.py exists
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
            cache_size=10
        )

        assert result == 0
        mock_run.assert_called_once_with(["hf", "auth", "login", "--token", "test_token"])
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
        mock_run.return_value.returncode = 1

        with pytest.raises(RuntimeError, match="Failed to authenticate with Hugging Face"):
            openvino_plugin.convert_to_ovms_format(
                model_name="test-model",
                weight_format="fp16",
                huggingface_token="invalid_token",
                model_type="llm",
                target_device="CPU",
                model_directory="/test/output"
            )

    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_convert_to_ovms_format_download_script(self, mock_makedirs, mock_exists, mock_popen, mock_run, openvino_plugin):
        """Test convert_to_ovms_format downloads script when not present"""
        # Setup mocks
        mock_run.side_effect = [
            MagicMock(returncode=0),  # hf auth success
            MagicMock(returncode=0)   # curl download success
        ]
        mock_exists.return_value = False  # export_model.py doesn't exist
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
                         "https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/3/demos/common/export_models/export_model.py",
                         "-o", "export_model.py"], check=True)
        assert curl_call in mock_run.call_args_list

    @pytest.mark.parametrize("model_type,expected_export_type", [
        ("llm", "text_generation"),
        ("embeddings", "embeddings"),
        ("rerank", "rerank"),
    ])
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_convert_to_ovms_format_model_types(self, mock_makedirs, mock_exists, mock_popen, mock_run, 
                                               openvino_plugin, model_type, expected_export_type):
        """Test convert_to_ovms_format with different model types"""
        mock_run.return_value.returncode = 0
        mock_exists.return_value = True
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

        assert result == 0
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
        result = openvino_plugin.post_process(
            model_name="bert-base-uncased",
            output_dir="/test/output",
            downloaded_paths=["/test/output/model.xml"],
            config={
                "precision": "int8",
                "device": "GPU",
                "cache": 15
            },
            type="embeddings"
        )

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
        ({}, "fp16", "CPU", None),  # defaults
        ({"precision": "fp32"}, "fp32", "CPU", None),  # partial config
    ])
    def test_post_process_config_handling(self, openvino_plugin, config, expected_precision, expected_device, expected_cache):
        """Test post_process with different config combinations"""
        result = openvino_plugin.post_process(
            model_name="test-model",
            output_dir="/test/output",
            downloaded_paths=[],
            config=config
        )

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
        mock_convert_to_ovms.return_value = 0
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test the complete workflow
            result = openvino_plugin.convert(
                model_name="Intel/neural-chat-7b-v3-3",
                output_dir=temp_dir,
                hf_token="test_token",
                config={
                    "precision": "int8",
                    "device": "CPU",
                    "cache": 10
                },
                type="llm"
            )
            
            # Verify results
            assert result["model_name"] == "Intel/neural-chat-7b-v3-3"
            assert result["source"] == "openvino"
            assert result["type"] == "llm"
            assert result["success"] == True
            assert result["is_ovms"] == True
            
            # Test post-processing
            post_result = openvino_plugin.post_process(
                model_name="Intel/neural-chat-7b-v3-3",
                output_dir=result["conversion_path"],
                downloaded_paths=[os.path.join(result["conversion_path"], "model.xml")],
                config=result["config"],
                type="llm"
            )
            
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
            mock_convert_to_ovms.return_value = 1
            
            with pytest.raises(RuntimeError) as exc_info:
                openvino_plugin.convert(
                    model_name="invalid-model",
                    output_dir=temp_dir,
                    hf_token="test_token"
                )
            
            assert "Model conversion failed with return code 1" in str(exc_info.value)

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
        mock_convert_to_ovms.return_value = 0
        
        test_cases = [
            # (config, kwargs, expected_calls)
            (
                {"precision": "int4", "device": "GPU", "cache": 20},
                {"type": "embeddings", "version": "v1.0"},
                {"weight_format": "int4", "target_device": "GPU", "cache_size": 20, "model_type": "embeddings", "version": "v1.0"}
            ),
            (
                {},
                {"precision": "fp32", "device": "CPU"},
                {"weight_format": "fp32", "target_device": "CPU", "cache_size": None, "model_type": "llm", "version": ""}
            ),
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            for config, kwargs, expected in test_cases:
                mock_convert_to_ovms.reset_mock()
                
                result = openvino_plugin.convert(
                    model_name="test-model",
                    output_dir=temp_dir,
                    hf_token="test_token",
                    config=config,
                    **kwargs
                )
                
                # Verify the call was made with expected parameters
                call_kwargs = mock_convert_to_ovms.call_args[1]
                for key, value in expected.items():
                    assert call_kwargs[key] == value
                
                assert result["success"] == True

    @patch('subprocess.run')
    @patch('subprocess.Popen')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_full_convert_to_ovms_format_workflow(self, mock_makedirs, mock_exists, mock_popen, mock_run, openvino_plugin):
        """Test full convert_to_ovms_format workflow with various scenarios"""
        # Test successful workflow with cache_size for LLM
        mock_run.return_value.returncode = 0
        mock_exists.return_value = True
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
            cache_size=15,
            version="v2.0"
        )

        assert result == 0
        
        # Verify the command was constructed correctly
        command = mock_popen.call_args[0][0]
        assert "text_generation" in command
        assert "--cache_size" in command
        assert "15" in command
        assert "--version" in command
        assert "v2.0" in command
