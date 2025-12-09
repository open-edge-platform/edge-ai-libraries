import os
import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, call

from src.plugins.ultralytics_plugin import UltralyticsDownloader
from src.core.interfaces import DownloadTask


class TestUltralyticsDownloader:
    """Test suite for UltralyticsDownloader plugin"""

    @pytest.fixture
    def ultralytics_plugin(self):
        """Create an instance of UltralyticsDownloader for testing"""
        return UltralyticsDownloader()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_script_content(self):
        """Mock content for download_public_models.sh script"""
        return '''#!/bin/bash
SUPPORTED_MODELS=(
    "yolov8n.pt"
    "yolov8s.pt"
    "yolov8m.pt"
    "yolov8l.pt"
    "yolov8x.pt"
    "yolov5n.pt"
    "yolov5s.pt"
)

SUPPORTED_QUANTIZATION_DATASETS=(
    ["coco"]="coco/val2017"
    ["imagenet"]="imagenet/val"
    ["voc"]="voc/2012"
)
'''

    def test_plugin_properties(self, ultralytics_plugin):
        """Test plugin basic properties"""
        assert ultralytics_plugin.plugin_name == "ultralytics"
        assert ultralytics_plugin.plugin_type == "downloader"

    @pytest.mark.parametrize("hub,model_name,expected", [
        ("ultralytics", "yolov8n.pt", True),
        ("Ultralytics", "yolov8n.pt", True),
        ("ULTRALYTICS", "yolov8n.pt", True),
        ("huggingface", "yolov8n.pt", True),  # True because model is in supported list
        ("ollama", "yolov8n.pt", True),       # True because model is in supported list
        ("openvino", "yolov8n.pt", True),     # True because model is in supported list
        ("huggingface", "unsupported_model.pt", False),  # False because model not supported
        ("ollama", "unsupported_model.pt", False),       # False because model not supported
        ("openvino", "unsupported_model.pt", False),     # False because model not supported
    ])
    def test_can_handle_hub(self, ultralytics_plugin, hub, model_name, expected):
        """Test can_handle method with different hubs and models"""
        with patch.object(ultralytics_plugin, 'get_supported_models', return_value=["yolov8n.pt"]):
            result = ultralytics_plugin.can_handle(model_name, hub)
            assert result == expected

    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_can_handle_supported_model(self, mock_file, mock_exists, ultralytics_plugin, mock_script_content):
        """Test can_handle with supported model names"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = mock_script_content

        # Test with supported model
        assert ultralytics_plugin.can_handle("yolov8n.pt", "other_hub") == True
        
        # Test with unsupported model
        assert ultralytics_plugin.can_handle("unsupported_model.pt", "other_hub") == False

    def test_can_handle_all_models(self, ultralytics_plugin):
        """Test can_handle with 'all' model name"""
        with patch.object(ultralytics_plugin, 'get_supported_models', return_value=["yolov8n.pt"]):
            assert ultralytics_plugin.can_handle("all", "other_hub") == True

    def test_can_handle_exception(self, ultralytics_plugin):
        """Test can_handle method when get_supported_models raises exception"""
        with patch.object(ultralytics_plugin, 'get_supported_models', side_effect=Exception("Script not found")):
            result = ultralytics_plugin.can_handle("yolov8n.pt", "other_hub")
            assert result == False

    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_get_supported_models(self, mock_file, mock_exists, ultralytics_plugin, mock_script_content):
        """Test get_supported_models method"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = mock_script_content

        models = ultralytics_plugin.get_supported_models()
        
        expected_models = [
            "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", 
            "yolov8l.pt", "yolov8x.pt", "yolov5n.pt", "yolov5s.pt"
        ]
        assert models == expected_models

    @patch('pathlib.Path.exists')
    def test_get_supported_models_script_not_found(self, mock_exists, ultralytics_plugin):
        """Test get_supported_models when script doesn't exist"""
        mock_exists.return_value = False
        
        with pytest.raises(FileNotFoundError):
            ultralytics_plugin.get_supported_models()

    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_get_supported_quantization_datasets(self, mock_file, mock_exists, ultralytics_plugin, mock_script_content):
        """Test get_supported_quantization_datasets method"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = mock_script_content

        datasets = ultralytics_plugin.get_supported_quantization_datasets()
        
        expected_datasets = {
            "coco": "coco/val2017",
            "imagenet": "imagenet/val",
            "voc": "voc/2012"
        }
        assert datasets == expected_datasets

    @patch('pathlib.Path.exists')
    def test_get_supported_quantization_datasets_script_not_found(self, mock_exists, ultralytics_plugin):
        """Test get_supported_quantization_datasets when script doesn't exist"""
        mock_exists.return_value = False
        
        with pytest.raises(FileNotFoundError):
            ultralytics_plugin.get_supported_quantization_datasets()

    @patch('os.path.exists')
    @patch('subprocess.Popen')
    def test_call_bash_script_success(self, mock_popen, mock_exists, ultralytics_plugin):
        """Test successful bash script execution"""
        mock_exists.return_value = True
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Script output\n", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        result = ultralytics_plugin._call_bash_script(
            model="yolov8n.pt", 
            quantize="coco", 
            models_path="/test/path"
        )

        assert result == 0
        mock_popen.assert_called_once()
        
        # Verify command structure
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "bash"
        assert cmd[2] == "yolov8n.pt"
        assert cmd[3] == "coco"

        # Verify environment variable
        env = call_args[1]['env']
        assert env['MODELS_PATH'] == "/test/path"

    @patch('os.path.exists')
    def test_call_bash_script_not_found(self, mock_exists, ultralytics_plugin):
        """Test bash script execution when script not found"""
        mock_exists.return_value = False
        
        with pytest.raises(FileNotFoundError):
            ultralytics_plugin._call_bash_script()

    @patch('os.path.exists')
    @patch('subprocess.Popen')
    def test_call_bash_script_failure(self, mock_popen, mock_exists, ultralytics_plugin):
        """Test bash script execution failure"""
        mock_exists.return_value = True
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Error occurred\n", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.poll.return_value = 1  # Non-zero return code
        mock_popen.return_value = mock_process

        result = ultralytics_plugin._call_bash_script(model="invalid_model.pt")

        assert result == 1

    @patch.object(UltralyticsDownloader, '_call_bash_script')
    @patch('os.getenv')
    def test_download_success(self, mock_getenv, mock_call_script, ultralytics_plugin, temp_dir):
        """Test successful model download"""
        mock_call_script.return_value = 0
        mock_getenv.return_value = "/host/models"

        result = ultralytics_plugin.download(
            model_name="yolov8n.pt",
            output_dir=temp_dir,
            quantize="coco"
        )

        expected_hub_dir = os.path.join(temp_dir, "ultralytics")
        mock_call_script.assert_called_once_with(
            model="yolov8n.pt",
            quantize="coco",
            models_path=expected_hub_dir
        )

        assert result["model_name"] == "yolov8n.pt"
        assert result["source"] == "ultralytics"
        assert result["return_code"] == 0
        assert "ultralytics" in result["download_path"]

    @patch.object(UltralyticsDownloader, '_call_bash_script')
    def test_download_failure(self, mock_call_script, ultralytics_plugin, temp_dir):
        """Test failed model download"""
        mock_call_script.return_value = 1  # Non-zero return code

        with pytest.raises(RuntimeError, match="Failed to download Ultralytics model"):
            ultralytics_plugin.download(
                model_name="invalid_model.pt",
                output_dir=temp_dir
            )

    @patch.object(UltralyticsDownloader, '_call_bash_script')
    def test_download_without_quantization(self, mock_call_script, ultralytics_plugin, temp_dir):
        """Test model download without quantization parameter"""
        mock_call_script.return_value = 0

        result = ultralytics_plugin.download(
            model_name="yolov8n.pt",
            output_dir=temp_dir
        )

        expected_hub_dir = os.path.join(temp_dir, "ultralytics")
        mock_call_script.assert_called_once_with(
            model="yolov8n.pt",
            quantize="",
            models_path=expected_hub_dir
        )

        assert result["model_name"] == "yolov8n.pt"
        assert result["source"] == "ultralytics"
        assert result["return_code"] == 0

    @patch.object(UltralyticsDownloader, '_call_bash_script')
    @patch('os.getenv')
    def test_download_path_replacement(self, mock_getenv, mock_call_script, ultralytics_plugin, temp_dir):
        """Test host path replacement in download results"""
        mock_call_script.return_value = 0
        mock_getenv.return_value = "/host/models"

        # Create a hub directory that starts with /opt/models/
        hub_dir = "/opt/models/ultralytics"
        
        with patch('os.path.join', return_value=hub_dir):
            result = ultralytics_plugin.download(
                model_name="yolov8n.pt",
                output_dir=temp_dir
            )

        # Should replace /opt/models/ with host prefix
        expected_path = "/host/models/ultralytics"
        assert result["download_path"] == expected_path

    @patch.object(UltralyticsDownloader, '_call_bash_script')
    @patch('os.getenv')
    def test_download_no_path_replacement(self, mock_getenv, mock_call_script, ultralytics_plugin, temp_dir):
        """Test no path replacement when not needed"""
        mock_call_script.return_value = 0
        mock_getenv.return_value = "/host/models"

        result = ultralytics_plugin.download(
            model_name="yolov8n.pt",
            output_dir=temp_dir
        )

        # Path should not be replaced since it doesn't start with /opt/models/
        expected_hub_dir = os.path.join(temp_dir, "ultralytics")
        assert result["download_path"] == expected_hub_dir

    def test_download_task_not_implemented(self, ultralytics_plugin):
        """Test that download_task raises NotImplementedError"""
        task = DownloadTask("file1", "http://example.com", "/dest")
        
        with pytest.raises(NotImplementedError, match="Ultralytics plugin does not support individual file downloads"):
            ultralytics_plugin.download_task(task, "/output")

    def test_post_process(self, ultralytics_plugin):
        """Test post_process method"""
        result = ultralytics_plugin.post_process(
            model_name="yolov8n.pt",
            output_dir="/test/output",
            downloaded_paths=["/test/output/model.pt"]
        )

        assert result["model_name"] == "yolov8n.pt"
        assert result["source"] == "ultralytics"
        assert result["download_path"] == "/test/output"
        assert result["success"] == True

    @pytest.mark.parametrize("model_name,quantize,expected_calls", [
        ("yolov8n.pt", "", 1),
        ("yolov8s.pt", "coco", 1),
        ("all", "imagenet", 1),
    ])
    @patch.object(UltralyticsDownloader, '_call_bash_script')
    def test_download_different_parameters(self, mock_call_script, ultralytics_plugin, temp_dir, model_name, quantize, expected_calls):
        """Test download with different parameter combinations"""
        mock_call_script.return_value = 0

        kwargs = {}
        if quantize:
            kwargs["quantize"] = quantize

        result = ultralytics_plugin.download(
            model_name=model_name,
            output_dir=temp_dir,
            **kwargs
        )

        assert mock_call_script.call_count == expected_calls
        assert result["model_name"] == model_name
        assert result["source"] == "ultralytics"
        assert result["return_code"] == 0

    @patch('os.path.exists')
    @patch('subprocess.Popen')
    def test_call_bash_script_with_stderr_output(self, mock_popen, mock_exists, ultralytics_plugin):
        """Test bash script execution with stderr output"""
        mock_exists.return_value = True
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Starting download\n", ""]
        mock_process.stderr.readline.side_effect = ["Warning: deprecated option\n", ""]
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        result = ultralytics_plugin._call_bash_script(model="yolov8n.pt")

        assert result == 0

    @patch('os.path.exists')
    @patch('subprocess.Popen')
    def test_call_bash_script_default_parameters(self, mock_popen, mock_exists, ultralytics_plugin):
        """Test bash script execution with default parameters"""
        mock_exists.return_value = True
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.poll.return_value = 0
        mock_popen.return_value = mock_process

        result = ultralytics_plugin._call_bash_script()

        assert result == 0
        
        # Verify default parameters
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert "all" in cmd  # Default model

    @patch.object(UltralyticsDownloader, 'get_supported_models')
    def test_can_handle_with_model_list_exception(self, mock_get_models, ultralytics_plugin):
        """Test can_handle when getting supported models fails"""
        mock_get_models.side_effect = FileNotFoundError("Script not found")
        
        # Should return False for non-ultralytics hub when script fails
        result = ultralytics_plugin.can_handle("yolov8n.pt", "other_hub")
        assert result == False
        
        # Should still return True for ultralytics hub regardless of script
        result = ultralytics_plugin.can_handle("yolov8n.pt", "ultralytics")
        assert result == True

    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_get_supported_models_parsing_edge_cases(self, mock_file, mock_exists, ultralytics_plugin):
        """Test get_supported_models with edge cases in script parsing"""
        mock_exists.return_value = True
        script_content = '''#!/bin/bash
SUPPORTED_MODELS=(
    "model1.pt"
    # This is a comment
    ""  # Empty string should be ignored
    "model2.pt"
    "model3.pt"
)
'''
        mock_file.return_value.read.return_value = script_content

        models = ultralytics_plugin.get_supported_models()
        
        # Should only include non-empty model names
        expected_models = ["model1.pt", "model2.pt", "model3.pt"]
        assert models == expected_models

    @patch('pathlib.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_get_supported_quantization_datasets_parsing_edge_cases(self, mock_file, mock_exists, ultralytics_plugin):
        """Test get_supported_quantization_datasets with edge cases"""
        mock_exists.return_value = True
        script_content = '''#!/bin/bash
SUPPORTED_QUANTIZATION_DATASETS=(
    ["dataset1"]="path1"
    # Comment line
    [""]=""  # Empty entries should be ignored
    ["dataset2"]="path2"
)
'''
        mock_file.return_value.read.return_value = script_content

        datasets = ultralytics_plugin.get_supported_quantization_datasets()
        
        # Should only include non-empty entries
        expected_datasets = {"dataset1": "path1", "dataset2": "path2"}
        assert datasets == expected_datasets


class TestUltralyticsPluginIntegration:
    """Integration tests for UltralyticsDownloader"""

    @pytest.fixture
    def ultralytics_plugin(self):
        return UltralyticsDownloader()

    @patch.object(UltralyticsDownloader, '_call_bash_script')
    def test_end_to_end_download_workflow(self, mock_call_script, ultralytics_plugin):
        """Test complete download workflow"""
        mock_call_script.return_value = 0
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test the complete workflow
            result = ultralytics_plugin.download(
                model_name="yolov8n.pt",
                output_dir=temp_dir,
                quantize="coco"
            )
            
            # Verify results
            assert result["model_name"] == "yolov8n.pt"
            assert result["source"] == "ultralytics"
            assert result["return_code"] == 0
            assert "ultralytics" in result["download_path"]
            
            # Test post-processing
            post_result = ultralytics_plugin.post_process(
                model_name="yolov8n.pt",
                output_dir=result["download_path"],
                downloaded_paths=[os.path.join(result["download_path"], "yolov8n.pt")]
            )
            
            assert post_result["success"] == True
            assert post_result["model_name"] == "yolov8n.pt"

    @pytest.mark.parametrize("hub", ["ultralytics", "ULTRALYTICS", "Ultralytics"])
    @patch.object(UltralyticsDownloader, 'get_supported_models')
    def test_hub_case_insensitive_handling(self, mock_get_models, ultralytics_plugin, hub):
        """Test that hub name handling is case-insensitive"""
        mock_get_models.return_value = ["yolov8n.pt"]
        
        assert ultralytics_plugin.can_handle("yolov8n.pt", hub) == True

    @patch.object(UltralyticsDownloader, '_call_bash_script')
    def test_error_handling_in_download(self, mock_call_script, ultralytics_plugin):
        """Test error handling during download process"""
        mock_call_script.return_value = 1
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(RuntimeError) as exc_info:
                ultralytics_plugin.download(
                    model_name="invalid_model.pt",
                    output_dir=temp_dir
                )
            
            assert "Failed to download Ultralytics model" in str(exc_info.value)
            assert "invalid_model.pt" in str(exc_info.value)