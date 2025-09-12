# Model download orchestration
import os
import uuid
from src.utils.logging import logger
import concurrent.futures
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable

from .plugin_registry import PluginRegistry
from .interfaces import ModelDownloadPlugin, DownloadTask

class ModelManager:
    """
    Core orchestration component that manages the download process.
    
    Responsibilities:
    - Select appropriate plugins for model downloads
    - Create and manage job records
    - Coordinate parallel downloads
    - Track job status and progress
    """
    
    def __init__(self, plugin_registry: PluginRegistry, default_dir: str = "./models"):
        """
        Initialize the ModelManager.
        
        Args:
            plugin_registry: Registry of available plugins
            default_dir: Default directory for model downloads
        """
        self.registry = plugin_registry
        self.default_dir = os.path.abspath(default_dir)
        self._jobs = {}  # In-memory job storage
        self._executors = {}  # Active executor pools by job
        os.makedirs(self.default_dir, exist_ok=True)
        logger.info("Model Manager has been initialized", default_dir=self.default_dir)

    def register_job(self, model_name: str, model_path: Optional[str] = None,
                    downloader: Optional[str] = None) -> str:
        """
        Register a new download job and return its ID.
        
        Args:
            model_name: Name of the model to download
            model_path: download path for the model
            downloader: Optional specific downloader plugin to use
            
        Returns:
            Job ID as a string
        """
        job_id = str(uuid.uuid4())

        # Resolve the model path
        if model_path is None:
            # Create a directory name from the model name
            dir_name = model_name.replace("/", "_").replace(":", "_")
            model_path = os.path.join(self.default_dir, dir_name)

        model_path = os.path.abspath(model_path)
        os.makedirs(model_path, exist_ok=True)
        
        # Track the job
        self._jobs[job_id] = {
            "id": job_id,
            "model_name": model_name,
            "model_path": model_path,
            "status": "queued",
            "start_time": datetime.now().isoformat(),
            "downloader": downloader,
            "progress": {
                "current": 0,
                "total": 0,
                "percentage": 0
            }
        }
        
        logger.info("Job Registered: ", job_id=job_id, model_name=model_name)
        return job_id
    
    def update_progress(self, job_id: str, current: int, total: int) -> None:
        """
        Update the progress of a job.
        
        Args:
            job_id: ID of the job to update
            current: Current progress value
            total: Total expected value for completion
        """
        if job_id in self._jobs:
            percentage = int((current / total) * 100) if total > 0 else 0
            self._jobs[job_id]["progress"] = {
                "current": current,
                "total": total,
                "percentage": percentage
            }
            logger.info("Job Progress Updated: ", job_id=job_id, 
                         current=current, total=total, percentage=percentage)
    
    def process_download(self, job_id: str, model_name: str, model_path: Optional[str] = None,
                       downloader: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Process a download job with parallel execution support.
        
        Args:
            job_id: ID of the job to process
            model_name: Name of the model to download
            model_path: Directory to save the model
            downloader: Specific downloader plugin to use
            **kwargs: Additional parameters for the download
            
        Returns:
            Dictionary with job details and status
        """
        try:
            # Update job status
            self._jobs[job_id]["status"] = "downloading"
            
            # Create progress callback
            def progress_callback(model_name, current, total):
                self.update_progress(job_id, current, total)
            
            # Find appropriate downloader plugin
            download_plugin = None
            if downloader:
                # User specifically requested a downloader
                download_plugin = self.registry.get_plugin("downloader", downloader)
                if not download_plugin:
                    err_msg = f"Requested downloader '{downloader}' not found"
                    self._jobs[job_id]["status"] = "failed"
                    self._jobs[job_id]["error"] = err_msg
                    logger.error("downloader_not_found", downloader=downloader)
                    raise ValueError(err_msg)
            else:
                # Auto-detect appropriate downloader
                download_plugin = self.registry.find_plugin_for_model("downloader", model_name, **kwargs)
            
            if not download_plugin:
                err_msg = f"No suitable downloader found for model '{model_name}'"
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = err_msg
                logger.error("no_suitable_downloader", model_name=model_name)
                raise ValueError(err_msg)
            
            # Update job with selected plugin
            self._jobs[job_id]["plugin"] = download_plugin.plugin_name
            
            # Check if the plugin supports parallel downloading via tasks
            use_parallel = kwargs.pop('use_parallel', True)
            max_workers = kwargs.pop('max_workers', 4)
            
            if use_parallel:
                # Try to get downloadable tasks
                try:
                    download_tasks = download_plugin.get_download_tasks(model_name, **kwargs)
                    
                    # If we have tasks, proceed with parallel download
                    if download_tasks:
                        return self._parallel_download(
                            job_id=job_id,
                            plugin=download_plugin,
                            model_name=model_name,
                            model_path=model_path,
                            tasks=download_tasks,
                            max_workers=max_workers,
                            progress_callback=progress_callback,
                            **kwargs
                        )
                except NotImplementedError:
                    logger.debug("plugin_no_task_support", 
                                plugin=download_plugin.plugin_name)
                except Exception as e:
                    logger.warning("task_download_failed", 
                                  plugin=download_plugin.plugin_name, 
                                  error=str(e))
            
            # Fall back to the plugin's standard download method
            logger.info("using_standard_download", 
                       plugin=download_plugin.plugin_name, 
                       model_name=model_name)
                       
            result = download_plugin.download(
                model_name, 
                model_path, 
                progress_callback=progress_callback, 
                **kwargs
            )
            
            # Update job status
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            self._jobs[job_id]["result"] = result
            
            logger.info("download_completed", job_id=job_id, model_name=model_name)
            
            return {
                "job_id": job_id,
                "status": "completed",
                "model_name": model_name,
                "download_path": model_path,
                "details": result
            }
            
        except Exception as e:
            # Update job status with error
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["error"] = str(e)
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            logger.error("download_failed", job_id=job_id, model_name=model_name, error=str(e))
            return {
                "job_id": job_id,
                "status": "failed",
                "model_name": model_name,
                "error": str(e)
            }
    
    def _parallel_download(self, job_id: str, plugin: ModelDownloadPlugin, model_name: str, 
                         model_path: str, tasks: List[DownloadTask], max_workers: int,
                         progress_callback: Optional[Callable] = None, **kwargs) -> Dict[str, Any]:
        """
        Perform parallel download of the given tasks.
        
        Args:
            job_id: ID of the job
            plugin: Plugin to use for downloading
            model_name: Name of the model
            model_path: Directory to save the model
            tasks: List of download tasks
            max_workers: Maximum number of parallel workers
            progress_callback: Callback for progress updates
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with job details and status
        """
        logger.info("starting_parallel_download", 
                   model_name=model_name, 
                   tasks=len(tasks), 
                   max_workers=max_workers)
        
        downloaded_paths = []
        total_tasks = len(tasks)
        completed_tasks = 0
        
        # Store the executor for potential cancellation
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._executors[job_id] = executor
        
        try:
            # Define the worker function to download a single task
            def download_task_wrapper(task):
                nonlocal completed_tasks
                try:
                    # Check if job has been canceled
                    if self._jobs.get(job_id, {}).get("status") == "canceled":
                        logger.info("download_task_canceled", task=task.file_path)
                        raise InterruptedError("Download was canceled")
                    
                    # Call the plugin to download this task
                    path = plugin.download_task(task, model_path, **kwargs)
                    
                    # Update progress
                    completed_tasks += 1
                    if progress_callback:
                        progress_callback(model_name, completed_tasks, total_tasks)
                    
                    return path
                except Exception as e:
                    logger.error("task_download_error", task=task.file_path, error=str(e))
                    raise
            
            # Submit all tasks to the executor
            future_to_task = {
                executor.submit(download_task_wrapper, task): task 
                for task in tasks
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    path = future.result()
                    downloaded_paths.append(path)
                    logger.debug("task_downloaded", file=task.file_path, path=path)
                except Exception as e:
                    # If any task fails, we cancel pending tasks and fail the job
                    if self._jobs[job_id]["status"] != "canceled":
                        logger.error("task_failure", task=task.file_path, error=str(e))
                        raise
            
            # All tasks completed successfully, perform any post-processing
            result = plugin.post_process(model_name, model_path, downloaded_paths, **kwargs)
            
            # Update job status
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            self._jobs[job_id]["result"] = result
            
            # Cleanup
            if job_id in self._executors:
                del self._executors[job_id]
            
            logger.info("parallel_download_completed", 
                       job_id=job_id, 
                       model_name=model_name, 
                       files=len(downloaded_paths))
            
            return {
                "job_id": job_id,
                "status": "completed",
                "model_name": model_name,
                "download_path": model_path,
                "details": result
            }
            
        except Exception as e:
            # Update job status with error if not already canceled
            if self._jobs[job_id]["status"] != "canceled":
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = str(e)
                self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            
            # Cleanup
            if job_id in self._executors:
                del self._executors[job_id]
                
            logger.error("parallel_download_failed", 
                        job_id=job_id, 
                        model_name=model_name, 
                        error=str(e))
            
            return {
                "job_id": job_id,
                "status": "failed",
                "model_name": model_name,
                "error": str(e)
            }
    
    def download_model(self, model_name: str, model_path: Optional[str] = None, 
                      downloader: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Synchronous model download method.
        
        For asynchronous downloads, use register_job + process_download.
        
        Args:
            model_name: Name of the model to download
            model_path: Directory to save the model
            downloader: Specific downloader plugin to use
            **kwargs: Additional parameters for the download
            
        Returns:
            Dictionary with job details and status
        """
        job_id = self.register_job(model_name, model_path, downloader)
        return self.process_download(job_id, model_name, model_path, downloader, **kwargs)
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a specific job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Job details or None if job not found
        """
        if job_id not in self._jobs:
            return None
        
        job = self._jobs[job_id].copy()  # Return a copy to prevent modification
        return job
    
    def list_jobs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all jobs with pagination.
        
        Args:
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            
        Returns:
            List of job details
        """
        all_jobs = list(self._jobs.values())
        # Sort by start time, newest first
        sorted_jobs = sorted(all_jobs, key=lambda j: j.get("start_time", ""), reverse=True)
        return sorted_jobs[offset:offset+limit]
    
    def get_available_plugins(self) -> Dict[str, List[str]]:
        """
        Get all available plugins by type.
        
        Returns:
            Dictionary mapping plugin types to lists of plugin names
        """
        result = {}
        for plugin_type in self.registry.get_plugin_types():
            result[plugin_type] = self.registry.get_plugins_by_type(plugin_type)
        return result
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job if possible.
        
        Args:
            job_id: ID of the job to cancel
            
        Returns:
            True if job was canceled, False otherwise
        """
        if job_id not in self._jobs:
            return False
            
        if self._jobs[job_id]["status"] in ["queued", "downloading"]:
            self._jobs[job_id]["status"] = "canceled"
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            
            # If there's an active executor for this job, shut it down
            if job_id in self._executors:
                self._executors[job_id].shutdown(wait=False, cancel_futures=True)
                del self._executors[job_id]
            
            logger.info("job_canceled", job_id=job_id)    
            return True
            
        return False