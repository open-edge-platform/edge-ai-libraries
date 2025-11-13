import os
import pytest
import tempfile
import time
from unittest.mock import MagicMock, patch

from src.core.model_manager import ModelManager
from src.core.plugin_registry import PluginRegistry
from src.core.interfaces import ModelDownloadPlugin, DownloadTask

# Mock plugins for testing
class MockSuccessPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "mock_success"
    
    @property
    def plugin_type(self) -> str:
        return "downloader"
    
    def can_handle(self, model_name: str, **kwargs) -> bool:
        return model_name.startswith("mock:")
    
    def download(self, model_name: str, output_dir: str, progress_callback=None, **kwargs):
        # Simulate download with progress updates
        if progress_callback:
            for i in range(1, 6):
                progress_callback(model_name, i, 5)
                time.sleep(0.01)  # Small delay to simulate work
        
        # Create a dummy file to simulate download
        with open(os.path.join(output_dir, "mock_model.bin"), "w") as f:
            f.write("mock model content")
        
        return {
            "model_name": model_name,
            "source": "mock",
            "download_path": output_dir
        }

class MockParallelPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "mock_parallel"
    
    @property
    def plugin_type(self) -> str:
        return "downloader"
    
    def can_handle(self, model_name: str, **kwargs) -> bool:
        return model_name.startswith("parallel:")
    
    def get_download_tasks(self, model_name: str, **kwargs):
        # Create 5 mock tasks
        tasks = []
        for i in range(5):
            task = DownloadTask(
                model_name=model_name,
                file_path=f"file_{i}.bin",
                size=100,
                metadata={"index": i}
            )
            tasks.append(task)
        return tasks
    
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs):
        # Simulate individual task download
        time.sleep(0.01)  # Small delay
        
        # Create the file
        file_path = os.path.join(output_dir, task.file_path)
        with open(file_path, "w") as f:
            f.write(f"content for {task.file_path}")
            
        return file_path
    
    def post_process(self, model_name: str, output_dir: str, downloaded_files: list, **kwargs):
        return {
            "model_name": model_name,
            "source": "mock_parallel",
            "download_path": output_dir,
            "files": len(downloaded_files)
        }

class MockFailPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "mock_fail"
    
    @property
    def plugin_type(self) -> str:
        return "downloader"
    
    def can_handle(self, model_name: str, **kwargs) -> bool:
        return model_name.startswith("fail:")
    
    def download(self, model_name: str, output_dir: str, progress_callback=None, **kwargs):
        # Simulate a failed download
        raise ValueError("Simulated download failure")

class MockParallelFailPlugin(ModelDownloadPlugin):
    @property
    def plugin_name(self) -> str:
        return "mock_parallel_fail"
    
    @property
    def plugin_type(self) -> str:
        return "downloader"
    
    def can_handle(self, model_name: str, **kwargs) -> bool:
        return model_name.startswith("parallel_fail:")
    
    def get_download_tasks(self, model_name: str, **kwargs):
        return [
            DownloadTask(model_name, "success.bin", 100, {}),
            DownloadTask(model_name, "fail.bin", 100, {})
        ]
    
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs):
        if task.file_path == "fail.bin":
            raise ValueError(f"Simulated task failure: {task.file_path}")
        
        # Create the file for success case
        file_path = os.path.join(output_dir, task.file_path)
        with open(file_path, "w") as f:
            f.write(f"content for {task.file_path}")
            
        return file_path


@pytest.fixture
def mock_registry():
    """Create a mock plugin registry with test plugins"""
    registry = PluginRegistry()
    
    # Add our mock plugins
    registry.register_plugin(MockSuccessPlugin())
    registry.register_plugin(MockParallelPlugin())
    registry.register_plugin(MockFailPlugin())
    registry.register_plugin(MockParallelFailPlugin())
    
    return registry

@pytest.fixture
def model_manager(mock_registry):
    """Create a ModelManager instance with temp directory and mock registry"""
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = ModelManager(mock_registry, default_dir=temp_dir)
        yield manager

class TestModelManager:
    
    def test_register_job(self, model_manager):
        """Test job registration creates a job with the correct properties"""
        job_id = model_manager.register_job("mock:model")
        
        # Verify job was created
        assert job_id in model_manager._jobs
        
        job = model_manager._jobs[job_id]
        assert job["model_name"] == "mock:model"
        assert job["status"] == "queued"
        assert "start_time" in job
        assert "progress" in job
        
        # Test with custom output dir
        custom_dir = "/tmp/custom_dir"
        job_id2 = model_manager.register_job("mock:model2", output_dir=custom_dir)
        assert model_manager._jobs[job_id2]["output_dir"] == custom_dir
    
    def test_update_progress(self, model_manager):
        """Test progress updates are correctly tracked"""
        job_id = model_manager.register_job("mock:model")
        
        # Update progress
        model_manager.update_progress(job_id, 3, 10)
        
        # Verify progress was updated
        progress = model_manager._jobs[job_id]["progress"]
        assert progress["current"] == 3
        assert progress["total"] == 10
        assert progress["percentage"] == 30  # 3/10 * 100 = 30%
        
        # Test edge case with total=0
        model_manager.update_progress(job_id, 5, 0)
        assert model_manager._jobs[job_id]["progress"]["percentage"] == 0
    
    def test_download_model_success(self, model_manager):
        """Test successful model download"""
        result = model_manager.download_model("mock:test_model")
        
        # Verify successful download
        assert result["status"] == "completed"
        assert result["model_name"] == "mock:test_model"
        
        # Check that job record was updated
        job_id = result["job_id"]
        job = model_manager._jobs[job_id]
        assert job["status"] == "completed"
        assert "completion_time" in job
        assert "result" in job
        
        # Verify file was created
        model_path = os.path.join(job["output_dir"], "mock_model.bin")
        assert os.path.exists(model_path)
    
    def test_parallel_download(self, model_manager):
        """Test parallel download functionality"""
        result = model_manager.download_model("parallel:test_model", use_parallel=True, max_workers=2)
        
        # Verify successful download
        assert result["status"] == "completed"
        
        # Check that job record was updated
        job_id = result["job_id"]
        job = model_manager._jobs[job_id]
        assert job["status"] == "completed"
        
        # Verify files were created (5 tasks)
        for i in range(5):
            file_path = os.path.join(job["output_dir"], f"file_{i}.bin")
            assert os.path.exists(file_path)
    
    def test_download_failure(self, model_manager):
        """Test handling of download failures"""
        result = model_manager.download_model("fail:test_model")
        
        # Verify failure status
        assert result["status"] == "failed"
        assert "error" in result
        
        # Check job record
        job_id = result["job_id"]
        job = model_manager._jobs[job_id]
        assert job["status"] == "failed"
        assert "error" in job
        assert "Simulated download failure" in job["error"]
    
    def test_parallel_download_failure(self, model_manager):
        """Test handling of failures in parallel downloads"""
        result = model_manager.download_model("parallel_fail:test_model", use_parallel=True)
        
        # Verify failure status
        assert result["status"] == "failed"
        assert "error" in result
        
        # Check job record
        job_id = result["job_id"]
        job = model_manager._jobs[job_id]
        assert job["status"] == "failed"
        assert "error" in job
        assert "Simulated task failure" in job["error"]
    
    def test_get_job_status(self, model_manager):
        """Test retrieving job status"""
        # Create a job
        job_id = model_manager.register_job("mock:model")
        
        # Get status
        status = model_manager.get_job_status(job_id)
        
        # Verify correct status returned
        assert status["id"] == job_id
        assert status["status"] == "queued"
        
        # Test non-existent job
        assert model_manager.get_job_status("non-existent-id") is None
    
    def test_list_jobs(self, model_manager):
        """Test listing jobs with pagination"""
        # Create multiple jobs
        job_ids = [
            model_manager.register_job(f"mock:model_{i}")
            for i in range(5)
        ]
        
        # List all jobs
        jobs = model_manager.list_jobs()
        assert len(jobs) == 5
        
        # Test pagination
        jobs_paginated = model_manager.list_jobs(limit=2, offset=1)
        assert len(jobs_paginated) == 2
    
    def test_cancel_job(self, model_manager):
        """Test job cancellation"""
        # Create a job and start a long download to ensure we can cancel
        with patch.object(MockSuccessPlugin, 'download', 
                          side_effect=lambda *args, **kwargs: time.sleep(10000)):
            
            # Register job
            job_id = model_manager.register_job("mock:model")
            
            # Update status to simulate download in progress
            model_manager._jobs[job_id]["status"] = "downloading"
            
            # Cancel the job
            result = model_manager.cancel_job(job_id)
            assert result is True
            
            # Verify job was canceled
            job = model_manager._jobs[job_id]
            assert job["status"] == "canceled"
            
            # Test canceling completed job (should fail)
            completed_job_id = model_manager.register_job("mock:completed")
            model_manager._jobs[completed_job_id]["status"] = "completed"
            assert model_manager.cancel_job(completed_job_id) is False
            
            # Test canceling non-existent job
            assert model_manager.cancel_job("non-existent-id") is False
    
    def test_get_available_plugins(self, model_manager):
        """Test retrieving available plugins"""
        plugins = model_manager.get_available_plugins()
        
        # Verify we get the correct plugins
        assert "downloader" in plugins
        assert set(plugins["downloader"]) == {"mock_success", "mock_parallel", "mock_fail", "mock_parallel_fail"}