import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from src.plugins.huggingface_plugin import HuggingFacePlugin
from src.core.interfaces import DownloadTask


class TestHuggingFacePlugin:
    """Test suite for HuggingFacePlugin"""

    @pytest.fixture
    def hf_plugin(self):
        """Create an instance of HuggingFacePlugin for testing"""
        return HuggingFacePlugin()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_plugin_properties(self, hf_plugin):
        """Test plugin basic properties"""
        assert hf_plugin.plugin_name == "huggingface"
        assert hf_plugin.plugin_type == "downloader"

    @pytest.mark.parametrize("hub,expected", [
        ("huggingface", True),
        ("Huggingface", True),
        ("HuggingFace", True),
        ("HUGGINGFACE", True),
        ("ollama", False),
        ("ultralytics", False),
        ("openvino", False),
        ("random_hub", False),
    ])
    def test_can_handle_hub(self, hf_plugin, hub, expected):
        """Test can_handle method with different hubs"""
        result = hf_plugin.can_handle("test-model", hub)
        assert result == expected

    @pytest.mark.parametrize("model_name", [
        "bert-base-uncased",
        "microsoft/DialoGPT-medium",
        "facebook/opt-1.3b",
        "EleutherAI/gpt-neo-1.3B",
        "Intel/neural-chat-7b-v3-3",
        "user/custom-model",
        "organization/model-v2.0",
    ])
    def test_can_handle_various_model_names(self, hf_plugin, model_name):
        """Test can_handle with various model name formats"""
        # Should return True for huggingface hub regardless of model name
        assert hf_plugin.can_handle(model_name, "huggingface") == True
        
        # Should return False for non-huggingface hubs regardless of model name
        assert hf_plugin.can_handle(model_name, "ollama") == False

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    @patch('os.getenv')
    def test_download_success(self, mock_getenv, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test successful model download"""
        # Setup mocks
        mock_snapshot_download.return_value = "/test/downloaded/path"
        mock_getenv.return_value = "/host/models"

        result = hf_plugin.download(
            model_name="bert-base-uncased",
            output_dir=temp_dir,
            hf_token="test_token",
            revision="main"
        )

        # Verify directory structure
        expected_hub_dir = os.path.join(temp_dir, "huggingface")
        expected_model_dir = os.path.join(expected_hub_dir, "bert-base-uncased")

        # Verify calls
        mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)
        mock_snapshot_download.assert_called_once_with(
            repo_id="bert-base-uncased",
            token="test_token",
            local_dir=expected_model_dir,
            revision="main"
        )

        # Verify result
        assert result["model_name"] == "bert-base-uncased"
        assert result["source"] == "huggingface"
        assert result["success"] == True
        assert "huggingface" in result["download_path"]

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_download_without_optional_params(self, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test model download without optional parameters"""
        mock_snapshot_download.return_value = "/test/downloaded/path"

        result = hf_plugin.download(
            model_name="bert-base-uncased",
            output_dir=temp_dir
        )

        expected_hub_dir = os.path.join(temp_dir, "huggingface")
        expected_model_dir = os.path.join(expected_hub_dir, "bert-base-uncased")

        mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)
        mock_snapshot_download.assert_called_once_with(
            repo_id="bert-base-uncased",
            token=None,
            local_dir=expected_model_dir,
            revision=None
        )

        assert result["model_name"] == "bert-base-uncased"
        assert result["source"] == "huggingface"
        assert result["success"] == True

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_download_with_slash_in_model_name(self, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test model download with slash in model name"""
        mock_snapshot_download.return_value = "/test/downloaded/path"

        result = hf_plugin.download(
            model_name="microsoft/DialoGPT-medium",
            output_dir=temp_dir,
            hf_token="test_token"
        )

        # Verify slash is replaced with underscore in directory path
        expected_hub_dir = os.path.join(temp_dir, "huggingface")
        expected_model_dir = os.path.join(expected_hub_dir, "microsoft_DialoGPT-medium")

        mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)
        mock_snapshot_download.assert_called_once_with(
            repo_id="microsoft/DialoGPT-medium",
            token="test_token",
            local_dir=expected_model_dir,
            revision=None
        )

        assert result["model_name"] == "microsoft/DialoGPT-medium"

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_download_snapshot_download_error(self, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test download failure due to snapshot_download error"""
        mock_snapshot_download.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            hf_plugin.download(
                model_name="nonexistent-model",
                output_dir=temp_dir,
                hf_token="test_token"
            )

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_download_makedirs_error(self, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test download failure due to directory creation error"""
        mock_makedirs.side_effect = OSError("Permission denied")

        with pytest.raises(OSError, match="Permission denied"):
            hf_plugin.download(
                model_name="bert-base-uncased",
                output_dir=temp_dir
            )

        # Verify snapshot_download was not called due to early failure
        mock_snapshot_download.assert_not_called()

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    @patch('os.getenv')
    def test_download_path_replacement(self, mock_getenv, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test host path replacement in download results"""
        mock_snapshot_download.return_value = "/test/downloaded/path"
        mock_getenv.return_value = "/host/models"

        # Create a hub directory that starts with /opt/models/
        hub_dir = "/opt/models/huggingface"
        
        with patch('os.path.join', return_value=hub_dir):
            result = hf_plugin.download(
                model_name="bert-base-uncased",
                output_dir=temp_dir
            )

        # Should replace /opt/models/ with host prefix
        expected_path = "/host/models/huggingface"
        assert result["download_path"] == expected_path

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    @patch('os.getenv')
    def test_download_no_path_replacement(self, mock_getenv, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test no path replacement when not needed"""
        mock_snapshot_download.return_value = "/test/downloaded/path"
        mock_getenv.return_value = "/host/models"

        result = hf_plugin.download(
            model_name="bert-base-uncased",
            output_dir=temp_dir
        )

        # Path should not be replaced since it doesn't start with /opt/models/
        expected_hub_dir = os.path.join(temp_dir, "huggingface")
        assert result["download_path"] == expected_hub_dir

    def test_get_download_tasks_not_implemented(self, hf_plugin):
        """Test that get_download_tasks raises NotImplementedError"""
        with pytest.raises(NotImplementedError, match="HuggingFace plugin does not support task-based downloading"):
            hf_plugin.get_download_tasks("bert-base-uncased")

    def test_download_task_not_implemented(self, hf_plugin):
        """Test that download_task raises NotImplementedError"""
        task = DownloadTask("file1", "http://example.com", "/dest")
        
        with pytest.raises(NotImplementedError, match="HuggingFace plugin does not support task-based downloading"):
            hf_plugin.download_task(task, "/output")

    def test_post_process(self, hf_plugin):
        """Test post_process method"""
        result = hf_plugin.post_process(
            model_name="bert-base-uncased",
            output_dir="/test/output",
            downloaded_paths=["/test/output/model.bin"]
        )

        assert result["model_name"] == "bert-base-uncased"
        assert result["source"] == "huggingface"
        assert result["download_path"] == "/test/output"
        assert result["success"] == True

    @pytest.mark.parametrize("model_name,hf_token,revision", [
        ("bert-base-uncased", "hf_test_token", "main"),
        ("microsoft/DialoGPT-medium", None, "v1.0"),
        ("facebook/opt-1.3b", "another_token", None),
        ("EleutherAI/gpt-neo-1.3B", "test_token", "4f2b5a3"),
    ])
    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_download_parameter_combinations(self, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir, model_name, hf_token, revision):
        """Test download with different parameter combinations"""
        mock_snapshot_download.return_value = "/test/downloaded/path"

        kwargs = {}
        if hf_token:
            kwargs["hf_token"] = hf_token
        if revision:
            kwargs["revision"] = revision

        result = hf_plugin.download(
            model_name=model_name,
            output_dir=temp_dir,
            **kwargs
        )

        # Verify snapshot_download was called with correct parameters
        mock_snapshot_download.assert_called_once_with(
            repo_id=model_name,
            token=hf_token,
            local_dir=mock_makedirs.call_args[0][0],
            revision=revision
        )

        assert result["model_name"] == model_name
        assert result["source"] == "huggingface"
        assert result["success"] == True

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_download_with_special_characters_in_model_name(self, mock_makedirs, mock_snapshot_download, hf_plugin, temp_dir):
        """Test model download with special characters in model name"""
        mock_snapshot_download.return_value = "/test/downloaded/path"

        model_name = "organization/model-name_v2.0"
        result = hf_plugin.download(
            model_name=model_name,
            output_dir=temp_dir
        )

        # Verify slash is replaced but other characters remain
        expected_hub_dir = os.path.join(temp_dir, "huggingface")
        expected_model_dir = os.path.join(expected_hub_dir, "organization_model-name_v2.0")

        mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)
        mock_snapshot_download.assert_called_once_with(
            repo_id=model_name,
            token=None,
            local_dir=expected_model_dir,
            revision=None
        )


class TestHuggingFacePluginIntegration:
    """Integration tests for HuggingFacePlugin"""

    @pytest.fixture
    def hf_plugin(self):
        return HuggingFacePlugin()

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_end_to_end_download_workflow(self, mock_makedirs, mock_snapshot_download, hf_plugin):
        """Test complete download workflow"""
        mock_snapshot_download.return_value = "/test/downloaded/path"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test the complete workflow
            result = hf_plugin.download(
                model_name="bert-base-uncased",
                output_dir=temp_dir,
                hf_token="test_token",
                revision="main"
            )
            
            # Verify results
            assert result["model_name"] == "bert-base-uncased"
            assert result["source"] == "huggingface"
            assert result["success"] == True
            assert "huggingface" in result["download_path"]
            
            # Test post-processing
            post_result = hf_plugin.post_process(
                model_name="bert-base-uncased",
                output_dir=result["download_path"],
                downloaded_paths=[os.path.join(result["download_path"], "pytorch_model.bin")]
            )
            
            assert post_result["success"] == True
            assert post_result["model_name"] == "bert-base-uncased"

    @pytest.mark.parametrize("hub", ["huggingface", "HUGGINGFACE", "HuggingFace"])
    def test_hub_case_insensitive_handling(self, hf_plugin, hub):
        """Test that hub name handling is case-insensitive"""
        assert hf_plugin.can_handle("bert-base-uncased", hub) == True

    @pytest.mark.parametrize("model_name,expected_dir", [
        ("bert-base-uncased", "bert-base-uncased"),
        ("microsoft/DialoGPT-medium", "microsoft_DialoGPT-medium"),
        ("facebook/opt-1.3b", "facebook_opt-1.3b"),
        ("user/model_name", "user_model_name"),
        ("organization/model-v2.0", "organization_model-v2.0"),
    ])
    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_model_name_directory_conversion(self, mock_makedirs, mock_snapshot_download, hf_plugin, model_name, expected_dir):
        """Test various model name to directory conversions"""
        mock_snapshot_download.return_value = "/test/downloaded/path"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            hf_plugin.download(
                model_name=model_name,
                output_dir=temp_dir
            )
            
            # Verify directory creation
            expected_hub_dir = os.path.join(temp_dir, "huggingface")
            expected_model_dir = os.path.join(expected_hub_dir, expected_dir)
            mock_makedirs.assert_called_once_with(expected_model_dir, exist_ok=True)

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_error_handling_workflow(self, mock_makedirs, mock_snapshot_download, hf_plugin):
        """Test error handling during complete workflow"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # First test: makedirs failure
            mock_makedirs.side_effect = OSError("Permission denied")
            
            with pytest.raises(OSError) as exc_info:
                hf_plugin.download(
                    model_name="bert-base-uncased",
                    output_dir=temp_dir
                )
            
            assert "Permission denied" in str(exc_info.value)
            mock_snapshot_download.assert_not_called()

        # Reset mocks for second test
        mock_makedirs.side_effect = None
        mock_snapshot_download.side_effect = Exception("Model not found")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(Exception) as exc_info:
                hf_plugin.download(
                    model_name="nonexistent/model",
                    output_dir=temp_dir
                )
            
            assert "Model not found" in str(exc_info.value)

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    def test_concurrent_operations_simulation(self, mock_makedirs, mock_snapshot_download, hf_plugin):
        """Test behavior that simulates concurrent operations"""
        mock_snapshot_download.return_value = "/test/downloaded/path"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Simulate multiple downloads (though they'd be sequential in this test)
            models = ["bert-base-uncased", "microsoft/DialoGPT-medium", "facebook/opt-1.3b"]
            results = []
            
            for model in models:
                result = hf_plugin.download(
                    model_name=model,
                    output_dir=temp_dir,
                    hf_token="test_token"
                )
                results.append(result)
            
            # Verify all downloads completed successfully
            assert len(results) == 3
            for i, result in enumerate(results):
                assert result["model_name"] == models[i]
                assert result["success"] == True
                assert result["source"] == "huggingface"
            
            # Verify snapshot_download was called for each model
            assert mock_snapshot_download.call_count == 3

    @patch('src.plugins.huggingface_plugin.snapshot_download')
    @patch('os.makedirs')
    @patch('os.getenv')
    def test_environment_variable_handling(self, mock_getenv, mock_makedirs, mock_snapshot_download, hf_plugin):
        """Test environment variable handling for path replacement"""
        mock_snapshot_download.return_value = "/test/downloaded/path"
        
        # Test with custom MODEL_PATH
        mock_getenv.return_value = "/custom/models"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock os.path.join to return a path that starts with /opt/models/
            with patch('os.path.join') as mock_join:
                mock_join.side_effect = lambda *args: "/opt/models/" + "/".join(args[1:])
                
                result = hf_plugin.download(
                    model_name="bert-base-uncased",
                    output_dir=temp_dir
                )
                
                # Should replace /opt/models/ with custom prefix
                assert result["download_path"] == "/custom/models/huggingface"

        # Test with default MODEL_PATH
        mock_getenv.return_value = "models"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('os.path.join') as mock_join:
                mock_join.side_effect = lambda *args: "/opt/models/" + "/".join(args[1:])
                
                result = hf_plugin.download(
                    model_name="bert-base-uncased",
                    output_dir=temp_dir
                )
                
                # Should replace /opt/models/ with default prefix
                assert result["download_path"] == "models/huggingface"