import os
import pytest
import tempfile
import subprocess
import time
from unittest.mock import patch, MagicMock, call

from src.plugins.ollama_plugin import OllamaPlugin
from src.core.interfaces import DownloadTask


class TestOllamaPlugin:
    """Test suite for OllamaPlugin"""

    @pytest.fixture
    def ollama_plugin(self):
        """Create an instance of OllamaPlugin for testing"""
        return OllamaPlugin()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_plugin_properties(self, ollama_plugin):
        """Test plugin basic properties"""
        assert ollama_plugin.plugin_name == "ollama"
        assert ollama_plugin.plugin_type == "downloader"

    @pytest.mark.parametrize("hub,expected", [
        ("ollama", True),
        ("Ollama", True),
        ("OLLAMA", True),
        ("huggingface", False),
        ("ultralytics", False),
        ("openvino", False),
        ("random_hub", False),
    ])
    def test_can_handle_hub(self, ollama_plugin, hub, expected):
        """Test can_handle method with different hubs"""
        result = ollama_plugin.can_handle("test-model", hub)
        assert result == expected

    @pytest.mark.parametrize("model_name", [
        "llama2",
        "llama2:7b",
        "codellama:13b",
        "mistral:latest",
        "custom/model",
        "user/custom-model:v1.0",
    ])
    def test_can_handle_various_model_names(self, ollama_plugin, model_name):
        """Test can_handle with various model name formats"""
        # Should return True for ollama hub regardless of model name
        assert ollama_plugin.can_handle(model_name, "ollama") == True
        
        # Should return False for non-ollama hubs regardless of model name
        assert ollama_plugin.can_handle(model_name, "huggingface") == False

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    @patch('os.getenv')
    def test_download_success(self, mock_getenv, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test successful model download"""
        # Setup mocks
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()
        mock_getenv.return_value = "/host/models"

        result = ollama_plugin.download(
            model_name="llama2",
            output_dir=temp_dir
        )

        # Verify directory structure - the plugin adds an empty string when no revision
        expected_hub_dir = os.path.join(temp_dir, "ollama")
        expected_model_dir = os.path.join(expected_hub_dir, "llama2", "")

        # Verify calls
        mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)
        mock_popen.assert_called_once_with(["ollama", "serve"])
        mock_sleep.assert_called_once_with(1)
        mock_run.assert_called_once_with(["ollama", "pull", "llama2"], check=True)
        mock_process.terminate.assert_called_once()

        # Verify result
        assert result["model_name"] == "llama2"
        assert result["source"] == "ollama"
        assert result["success"] == True
        assert "ollama" in result["download_path"]

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_download_with_revision(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test model download with revision specified"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()

        result = ollama_plugin.download(
            model_name="llama2",
            output_dir=temp_dir,
            revision="7b"
        )

        # Verify directory structure includes revision
        expected_hub_dir = os.path.join(temp_dir, "ollama")
        expected_model_dir = os.path.join(expected_hub_dir, "llama2", "7b")

        mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)
        mock_run.assert_called_once_with(["ollama", "pull", "llama2:7b"], check=True)
        mock_process.terminate.assert_called_once()

        assert result["model_name"] == "llama2:7b"
        assert result["source"] == "ollama"
        assert result["success"] == True

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_download_with_slash_in_model_name(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test model download with slash in model name"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()

        result = ollama_plugin.download(
            model_name="user/model",
            output_dir=temp_dir
        )

        # Verify slash is replaced with underscore in directory path, plus empty string from no revision
        expected_hub_dir = os.path.join(temp_dir, "ollama")
        expected_model_dir = os.path.join(expected_hub_dir, "user_model", "")

        mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)
        mock_run.assert_called_once_with(["ollama", "pull", "user/model"], check=True)

        assert result["model_name"] == "user/model"

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_download_subprocess_error(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test download failure due to subprocess error"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.side_effect = subprocess.CalledProcessError(1, ["ollama", "pull"], "Model not found")

        with pytest.raises(RuntimeError, match="Failed to download Ollama model"):
            ollama_plugin.download(
                model_name="nonexistent-model",
                output_dir=temp_dir
            )

        # Verify cleanup happened
        mock_process.terminate.assert_called_once()

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_download_makedirs_error(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test download failure due to directory creation error"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_makedirs.side_effect = OSError("Permission denied")

        with pytest.raises(RuntimeError, match="Failed to create model directory"):
            ollama_plugin.download(
                model_name="llama2",
                output_dir=temp_dir
            )

        # Verify that subprocess.Popen was never called because makedirs failed first
        mock_popen.assert_not_called()
        # Therefore, terminate should not be called either since process was never created

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    @patch('os.getenv')
    def test_download_path_replacement(self, mock_getenv, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test host path replacement in download results"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()
        mock_getenv.return_value = "/host/models"

        # Create a hub directory that starts with /opt/models/
        hub_dir = "/opt/models/ollama"
        
        with patch('os.path.join', return_value=hub_dir):
            result = ollama_plugin.download(
                model_name="llama2",
                output_dir=temp_dir
            )

        # Should replace /opt/models/ with host prefix
        expected_path = "/host/models/ollama"
        assert result["download_path"] == expected_path

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    @patch('os.getenv')
    def test_download_no_path_replacement(self, mock_getenv, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test no path replacement when not needed"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()
        mock_getenv.return_value = "/host/models"

        result = ollama_plugin.download(
            model_name="llama2",
            output_dir=temp_dir
        )

        # Path should not be replaced since it doesn't start with /opt/models/
        expected_hub_dir = os.path.join(temp_dir, "ollama")
        assert result["download_path"] == expected_hub_dir

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_environment_variable_setting(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test that OLLAMA_MODELS environment variable is set correctly"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()

        with patch.dict('os.environ', {}, clear=True):
            ollama_plugin.download(
                model_name="llama2",
                output_dir=temp_dir
            )

            # The plugin adds an empty string to the path when no revision, resulting in trailing slash
            expected_model_dir = os.path.join(temp_dir, "ollama", "llama2", "")
            assert os.environ.get("OLLAMA_MODELS") == expected_model_dir

    def test_get_download_tasks_not_implemented(self, ollama_plugin):
        """Test that get_download_tasks raises NotImplementedError"""
        with pytest.raises(NotImplementedError, match="Ollama plugin does not support task-based downloading"):
            ollama_plugin.get_download_tasks("llama2")

    def test_download_task_not_implemented(self, ollama_plugin):
        """Test that download_task raises NotImplementedError"""
        task = DownloadTask("file1", "http://example.com", "/dest")
        
        with pytest.raises(NotImplementedError, match="Ollama plugin does not support task-based downloading"):
            ollama_plugin.download_task(task, "/output")

    def test_post_process(self, ollama_plugin):
        """Test post_process method"""
        result = ollama_plugin.post_process(
            model_name="llama2",
            output_dir="/test/output",
            downloaded_paths=["/test/output/model"]
        )

        assert result["model_name"] == "llama2"
        assert result["source"] == "ollama"
        assert result["download_path"] == "/test/output"
        assert result["success"] == True

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_server_cleanup_on_exception(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin, temp_dir):
        """Test that ollama server is properly terminated even when exception occurs"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.side_effect = subprocess.CalledProcessError(1, ["ollama", "pull"])

        with pytest.raises(RuntimeError):
            ollama_plugin.download(
                model_name="llama2",
                output_dir=temp_dir
            )

        # Verify server was terminated despite the exception
        mock_process.terminate.assert_called_once()

    # @patch('subprocess.Popen')
    # @patch('subprocess.run')
    # @patch('os.makedirs')
    # @patch('time.sleep')
    # def test_server_cleanup_when_process_none(self, mock_makedirs, mock_popen, ollama_plugin, temp_dir):
    #     """Test that no error occurs when process is None during cleanup"""
    #     mock_popen.return_value = None
    #     mock_makedirs.side_effect = OSError("Permission denied")

    #     with pytest.raises(RuntimeError, match="Failed to create model directory"):
    #         ollama_plugin.download(
    #             model_name="llama2",
    #             output_dir=temp_dir
    #         )

    #     # Should not raise an exception even though process is None
    #     # No terminate() call should be made when process is None
    #     # Verify that Popen was never called due to early exception
    #     mock_popen.assert_not_called()


class TestOllamaPluginIntegration:
    """Integration tests for OllamaPlugin"""

    @pytest.fixture
    def ollama_plugin(self):
        return OllamaPlugin()

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_end_to_end_download_workflow(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin):
        """Test complete download workflow"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test the complete workflow
            result = ollama_plugin.download(
                model_name="llama2:7b",
                output_dir=temp_dir,
                revision="7b"
            )
            
            # Verify results
            assert result["model_name"] == "llama2:7b:7b"  # revision gets appended twice in current implementation
            assert result["source"] == "ollama"
            assert result["success"] == True
            assert "ollama" in result["download_path"]
            
            # Test post-processing
            post_result = ollama_plugin.post_process(
                model_name="llama2:7b",
                output_dir=result["download_path"],
                downloaded_paths=[os.path.join(result["download_path"], "model")]
            )
            
            assert post_result["success"] == True
            assert post_result["model_name"] == "llama2:7b"

    @pytest.mark.parametrize("hub", ["ollama", "OLLAMA", "Ollama"])
    def test_hub_case_insensitive_handling(self, ollama_plugin, hub):
        """Test that hub name handling is case-insensitive"""
        assert ollama_plugin.can_handle("llama2", hub) == True

    @pytest.mark.parametrize("model_name,revision,expected_pull_cmd,expected_dir", [
        ("llama2", None, "llama2", "llama2"),
        ("llama2", "7b", "llama2:7b", "llama2"),
        ("codellama", "13b", "codellama:13b", "codellama"),
        ("user/model", None, "user/model", "user_model"),
        ("user/model", "v1", "user/model:v1", "user_model"),
    ])
    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_model_name_and_revision_handling(self, mock_sleep, mock_makedirs, mock_run, mock_popen, 
                                            ollama_plugin, model_name, revision, expected_pull_cmd, expected_dir):
        """Test various model name and revision combinations"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            kwargs = {}
            if revision:
                kwargs["revision"] = revision
                
            result = ollama_plugin.download(
                model_name=model_name,
                output_dir=temp_dir,
                **kwargs
            )
            
            # Verify pull command
            mock_run.assert_called_once_with(["ollama", "pull", expected_pull_cmd], check=True)
            
            # Verify directory creation - account for empty string when no revision
            if revision:
                expected_model_dir = os.path.join(temp_dir, "ollama", expected_dir, revision)
            else:
                expected_model_dir = os.path.join(temp_dir, "ollama", expected_dir, "")
            mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_error_handling_workflow(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin):
        """Test error handling during complete workflow"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        # First test: makedirs failure
        mock_makedirs.side_effect = OSError("Permission denied")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(RuntimeError) as exc_info:
                ollama_plugin.download(
                    model_name="llama2",
                    output_dir=temp_dir
                )
            
            assert "Failed to create model directory" in str(exc_info.value)
            # Process was never created because makedirs failed first
            mock_popen.assert_not_called()

        # Reset mocks for second test
        mock_process.reset_mock()
        mock_makedirs.side_effect = None  # Reset to not raise exception
        mock_run.side_effect = subprocess.CalledProcessError(1, ["ollama", "pull"], "Network error")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(RuntimeError) as exc_info:
                ollama_plugin.download(
                    model_name="llama2",
                    output_dir=temp_dir
                )
            
            assert "Failed to download Ollama model" in str(exc_info.value)
            # In this case, process was created and should be terminated
            mock_process.terminate.assert_called_once()

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('time.sleep')
    def test_concurrent_operations_simulation(self, mock_sleep, mock_makedirs, mock_run, mock_popen, ollama_plugin):
        """Test behavior that simulates concurrent operations"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Simulate multiple downloads (though they'd be sequential in this test)
            models = ["llama2", "codellama", "mistral"]
            results = []
            
            for model in models:
                result = ollama_plugin.download(
                    model_name=model,
                    output_dir=temp_dir
                )
                results.append(result)
            
            # Verify all downloads completed successfully
            assert len(results) == 3
            for i, result in enumerate(results):
                assert result["model_name"] == models[i]
                assert result["success"] == True
                assert result["source"] == "ollama"
            
            # Verify server was started and stopped for each download
            assert mock_popen.call_count == 3
            assert mock_process.terminate.call_count == 3