# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import uuid
import asyncio
import inspect
import concurrent.futures
from datetime import datetime
from typing import Dict, Any, Optional, List

from .plugin_registry import PluginRegistry
from .interfaces import ModelDownloadPlugin, DownloadTask

# Configure structured logging
from src.utils.logging import logger


class ModelManager:
    """
    Core orchestration component that manages model operations.

    Responsibilities:
    - Select appropriate plugins for model downloads or conversions
    - Create and manage job records
    - Coordinate parallel operations
    """

    def __init__(self, plugin_registry: PluginRegistry, default_dir: str = "./models"):
        """
        Initialize the ModelManager.

        Args:
            plugin_registry: Registry of available plugins
            default_dir: Default directory for model downloads and conversions
        """
        self.registry = plugin_registry
        self.default_dir = os.path.abspath(default_dir)
        self._jobs = {}  # In-memory job storage
        self._executors = {}  # Active executor pools by job
        os.makedirs(self.default_dir, exist_ok=True)
        logger.info("model_manager_initialized", default_dir=self.default_dir)

    def register_job(
        self,
        operation_type: str,  # New parameter to distinguish job types
        model_name: str,
        hub: str,
        output_dir: Optional[str] = None,
        plugin_name: Optional[str] = None,
        model_type: Optional[str] = None,
    ) -> str:
        """
        Register a new job and return its ID.

        Args:
            operation_type: Type of operation ('download' or 'convert')
            model_name: Name of the model to process
            output_dir: Optional custom directory for output
            plugin_name: Optional specific plugin to use
            model_type: Optional type of model (llm, embeddings, rerank, vlm, vision)

        Returns:
            Job ID as a string
        """
        job_id = str(uuid.uuid4())

        # Resolve the output directory
        if output_dir is None:
            # Create a safe directory name from the model name
            safe_name = model_name.replace("/", "_")
            output_dir = os.path.join(self.default_dir, safe_name)

        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        # Track the job
        self._jobs[job_id] = {
            "id": job_id,
            "operation_type": operation_type,  # Store operation type
            "model_name": model_name,
            "hub": hub,
            "output_dir": output_dir,
            "status": "queued",
            "start_time": datetime.now().isoformat(),
            "plugin_name": plugin_name,
            "model_type": model_type,
        }

        logger.info(
            "job_registered",
            job_id=job_id,
            operation_type=operation_type,
            model_name=model_name,
            hub=hub
        )
        return job_id

    def update_progress(self, job_id: str, current: int, total: int) -> None:
        """Update the progress of a job."""
        pass

    async def process_download(
        self,
        job_id: str,
        model_name: str,
        hub: str,
        output_dir: Optional[str] = None,
        downloader: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Process a download job with parallel execution support.

        Args:
            job_id: ID of the job to process
            model_name: Name of the model to download
            hub: From which hub model needs to be downloaded
            output_dir: Directory to save the model
            downloader: Specific downloader plugin to use
            **kwargs: Additional parameters for the download

        Returns:
            Dictionary with job details and status
        """
        try:
            # Update job status
            self._jobs[job_id]["status"] = "downloading"
            logger.info(f"Request details: {model_name}, {hub}, {kwargs}")
            # Find appropriate downloader plugin
            download_plugin = None
            if downloader:
                logger.info(f"Request details: {downloader},{model_name}, {hub}, {kwargs}")
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
                logger.info(f"Request details: {model_name}, {hub}, {kwargs}")
                download_plugin = self.registry.find_plugin_for_model(
                    "downloader", model_name, hub, **kwargs
                )

            if not download_plugin:
                err_msg = f"No suitable downloader found for model '{model_name}'"
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = err_msg
                logger.error("no_suitable_downloader", model_name=model_name)
                raise ValueError(err_msg)

            # Update job with selected plugin
            self._jobs[job_id]["plugin"] = download_plugin.plugin_name

            # Check if the plugin supports parallel downloading via tasks
            use_parallel = kwargs.pop("parallel_downloads", True)
            max_workers = kwargs.pop("max_workers", 4)

            if use_parallel:
                # Try to get downloadable tasks
                try:
                    download_tasks = download_plugin.get_download_tasks(
                        model_name, **kwargs
                    )

                    # If we have tasks, proceed with parallel download
                    if download_tasks:
                        return await asyncio.to_thread(
                            self._parallel_download,
                            job_id=job_id,
                            plugin=download_plugin,
                            model_name=model_name,
                            model_path=output_dir,
                            tasks=download_tasks,
                            max_workers=max_workers,
                            **kwargs,
                        )
                except NotImplementedError:
                    logger.debug(
                        "plugin_no_task_support", plugin=download_plugin.plugin_name
                    )
                except Exception as e:
                    logger.warning(
                        "task_download_failed",
                        plugin=download_plugin.plugin_name,
                        error=str(e),
                    )

            # Fall back to the plugin's standard download method
            logger.info(
                "using_standard_download",
                plugin=download_plugin.plugin_name,
                model_name=model_name,
            )

            # Check if the download method is async
            if inspect.iscoroutinefunction(download_plugin.download):
                result = await download_plugin.download(model_name, output_dir, **kwargs)
            else:
                result = await asyncio.to_thread(
                    download_plugin.download,
                    model_name, output_dir, **kwargs
                )

            # Check if the download was successful
            if isinstance(result, dict) and result.get("success") is False:
                # Download failed, update job status accordingly
                error_msg = result.get("error", "Unknown error")
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = error_msg
                self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
                self._jobs[job_id]["result"] = result
                
                logger.error("download_failed", job_id=job_id, model_name=model_name, error=error_msg)
                return {
                    "job_id": job_id,
                    "status": "failed",
                    "model_name": model_name,
                    "error": error_msg,
                }

            # Update job status
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            self._jobs[job_id]["result"] = result

            logger.info("download_completed", job_id=job_id, model_name=model_name)
            
            # Convert container path to host path if applicable
            host_path = output_dir
            if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
                host_prefix = os.getenv("MODEL_PATH", "models")
                host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

            logger.info("download_completed to host_path", host_path=host_path)
            return {
                "job_id": job_id,
                "status": "completed",
                "model_name": model_name,
                "download_path": host_path,
                "details": result,
            }

        except Exception as e:
            # Update job status with error
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["error"] = str(e)
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            logger.error(
                "download_failed", job_id=job_id, model_name=model_name, error=str(e)
            )
            return {
                "job_id": job_id,
                "status": "failed",
                "model_name": model_name,
                "error": str(e),
            }

    async def process_conversion(
        self,
        job_id: str,
        model_path: str,
        model_name: str,
        hub: str,
        hf_token: str,
        output_dir: Optional[str] = None,
        converter: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Process a model conversion job.

        Args:
            job_id: ID of the job to process
            model_path: Path to the model to convert
            hub: Model downloaded from the hub
            output_dir: Directory to save the converted model
            converter: Specific converter plugin to use
            **kwargs: Additional parameters for the conversion

        Returns:
            Dictionary with job details and status
        """
        try:
            # Check if hub is 'openvino'
            if hub != "openvino":
                err_msg = f"Conversion failed: incorrect hub '{hub}' provided. Only 'openvino' is supported for conversion."
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = err_msg
                self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
                logger.error("conversion_failed_incorrect_hub", job_id=job_id, model_path=model_path, hub=hub)
                return {
                    "job_id": job_id,
                    "status": "failed",
                    "model_path": model_path,
                    "error": err_msg,
                }

            # Update job status
            self._jobs[job_id]["status"] = "converting"

            # Find appropriate converter plugin
            convert_plugin = None
            if converter:
                # User specifically requested a converter
                convert_plugin = self.registry.get_plugin("converter", converter)
            if not convert_plugin:
                err_msg = f"Requested converter '{converter}' not found"
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = err_msg
                logger.error("converter_not_found", converter=converter)
                raise ValueError(err_msg)
            else:
                # Auto-detect appropriate converter based on model path and kwargs
                convert_plugin = self.registry.find_plugin_for_model(
                    "converter", hub=hub, model_name=model_name, **kwargs
                )

            if not convert_plugin:
                err_msg = f"No suitable converter found for model at '{model_path}'"
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = err_msg
                logger.error("no_suitable_converter", model_path=model_path)
                raise ValueError(err_msg)

            # Update job with selected plugin
            self._jobs[job_id]["plugin"] = convert_plugin.plugin_name

            # Execute the conversion
            logger.info(
                "starting_conversion",
                plugin=convert_plugin.plugin_name,
                model_path=model_path,
            )

            logger.info(f"Request details: {model_path}, {hub}, {kwargs}")

            result = await asyncio.to_thread(
                convert_plugin.convert,
                model_name, output_dir, hf_token=hf_token, **kwargs
            )

            # Update job status
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            self._jobs[job_id]["result"] = result

            logger.info("conversion_completed", job_id=job_id, model_path=model_path)
            
            # Convert container path to host path if applicable
            host_path = output_dir
            if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
                host_prefix = os.getenv("MODEL_PATH", "models")
                host_path = host_path.replace("/opt/models/", f"{host_prefix}/")

            logger.info("download_completed to host_path", host_path=host_path)
            return {
                "job_id": job_id,
                "status": "completed",
                "model_path": model_path,
                "conversion_path": host_path,
                "details": result,
            }

        except Exception as e:
            # Update job status with error
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["error"] = str(e)
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
            logger.error(
                "conversion_failed", job_id=job_id, model_path=model_path, error=str(e)
            )
            return {
                "job_id": job_id,
                "status": "failed",
                "model_path": model_path,
                "error": str(e),
            }

    def _parallel_download(
        self,
        job_id: str,
        plugin: ModelDownloadPlugin,
        model_name: str,
        model_path: str,
        tasks: List[DownloadTask],
        max_workers: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Perform parallel download of the given tasks.

        Args:
            job_id: ID of the job
            plugin: Plugin to use for downloading
            model_name: Name of the model
            model_path: Directory to save the model
            tasks: List of download tasks
            max_workers: Maximum number of parallel workers
            **kwargs: Additional parameters

        Returns:
            Dictionary with job details and status
        """
        logger.info(
            "starting_parallel_download",
            model_name=model_name,
            tasks=len(tasks),
            max_workers=max_workers,
        )

        downloaded_paths = []

        # Use context manager to ensure proper cleanup of executor
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Store the executor for potential cancellation
            self._executors[job_id] = executor

            try:
                # Define the worker function to download a single task
                def download_task_wrapper(task):
                    try:
                        # Check if job has been canceled
                        if self._jobs.get(job_id, {}).get("status") == "canceled":
                            logger.info("download_task_canceled", task=task.destination)
                            raise InterruptedError("Download was canceled")

                        # Call the plugin to download this task
                        path = plugin.download_task(task, model_path, **kwargs)
                        return path
                    except Exception as e:
                        logger.error(
                            "task_download_error", task=task.destination, error=str(e)
                        )
                        raise

                # Submit all tasks to the executor
                future_to_task = {
                    executor.submit(download_task_wrapper, task): task for task in tasks
                }

                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        path = future.result()
                        downloaded_paths.append(path)
                        logger.debug("task_downloaded", file=task.destination, path=path)
                    except Exception as e:
                        # If any task fails, we cancel pending tasks and fail the job
                        if self._jobs[job_id]["status"] != "canceled":
                            logger.error("task_failure", task=task.destination, error=str(e))
                            raise

                # All tasks completed successfully, perform any post-processing
                result = plugin.post_process(
                    model_name, model_path, downloaded_paths, **kwargs
                )

                # Update job status
                self._jobs[job_id]["status"] = "completed"
                self._jobs[job_id]["completion_time"] = datetime.now().isoformat()
                self._jobs[job_id]["result"] = result

                logger.info(
                    "parallel_download_completed",
                    job_id=job_id,
                    model_name=model_name,
                    files=len(downloaded_paths),
                )
                
                # Convert container path to host path if applicable
                host_path = model_path
                if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
                    host_prefix = os.getenv("MODEL_PATH", "models")
                    host_path = host_path.replace("/opt/models/", f"{host_prefix}/")
                    
                logger.info("download_completed to host_path", host_path=host_path)
                return {
                    "job_id": job_id,
                    "status": "completed",
                    "model_name": model_name,
                    "download_path": host_path,
                    "details": result,
                }

            except Exception as e:
                # Update job status with error if not already canceled
                if self._jobs[job_id]["status"] != "canceled":
                    self._jobs[job_id]["status"] = "failed"
                    self._jobs[job_id]["error"] = str(e)
                    self._jobs[job_id]["completion_time"] = datetime.now().isoformat()

                logger.error(
                    "parallel_download_failed",
                    job_id=job_id,
                    model_name=model_name,
                    error=str(e),
                )

                return {
                    "job_id": job_id,
                    "status": "failed",
                    "model_name": model_name,
                    "error": str(e),
                }
            finally:
                # Cleanup - remove from tracking dict
                if job_id in self._executors:
                    del self._executors[job_id]

    def download_model(
        self,
        model_name: str,
        hub: str,
        output_dir: Optional[str] = None,
        downloader: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Synchronous model download method.

        For asynchronous downloads, use register_job + process_download.

        Args:
            model_name: Name of the model to download
            output_dir: Directory to save the model
            downloader: Specific downloader plugin to use
            **kwargs: Additional parameters for the download

        Returns:
            Dictionary with job details and status
        """
        job_id = self.register_job("download", model_name, hub, output_dir, downloader)
        return asyncio.run(self.process_download(
            job_id, model_name, hub, output_dir, downloader, **kwargs
        ))

    def convert_model(
        self,
        model_path: str,
        output_dir: Optional[str] = None,
        converter: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Synchronous model conversion method.

        For asynchronous conversions, use register_job + process_conversion.

        Args:
            model_path: Path to the model to convert
            output_dir: Directory to save the converted model
            converter: Specific converter plugin to use
            **kwargs: Additional parameters for the conversion

        Returns:
            Dictionary with job details and status
        """
        # Extract model name from path for job registration
        model_name = os.path.basename(model_path)
        job_id = self.register_job("convert", model_name, "openvino", output_dir, converter)
        return asyncio.run(self.process_conversion(
            job_id=job_id, model_path=model_path, model_name=model_name, hub="openvino", hf_token=kwargs.get("hf_token", ""), output_dir=output_dir, converter=converter, **kwargs
        ))

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific job."""
        if job_id not in self._jobs:
            return None
        job = self._jobs[job_id].copy()  # Return a copy to prevent modification
        return job

    def list_jobs(
        self, limit: int = 100, offset: int = 0, operation_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List jobs with pagination and optional filtering by operation type.

        Args:
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            operation_type: Optional filter by operation type ('download' or 'convert')

        Returns:
            List of job details
        """
        all_jobs = list(self._jobs.values())

        # Filter by operation type if specified
        if operation_type:
            all_jobs = [
                job for job in all_jobs if job.get("operation_type") == operation_type
            ]

        # Sort by start time, newest first
        sorted_jobs = sorted(
            all_jobs, key=lambda j: j.get("start_time", ""), reverse=True
        )
        return sorted_jobs[offset : offset + limit]

    def get_available_plugins(
        self, plugin_type: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """
        Get available plugins, optionally filtered by type.

        Args:
            plugin_type: Optional filter by plugin type ('downloader' or 'converter')

        Returns:
            Dictionary mapping plugin types to lists of plugin names
        """
        if plugin_type:
            return {plugin_type: self.registry.get_plugins_by_type(plugin_type)}

        result = {}
        for p_type in self.registry.get_plugin_types():
            result[p_type] = self.registry.get_plugins_by_type(p_type)
        return result

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job if possible."""
        if job_id not in self._jobs:
            return False

        if self._jobs[job_id]["status"] in ["queued", "downloading", "converting"]:
            self._jobs[job_id]["status"] = "canceled"
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()

            # If there's an active executor for this job, shut it down
            if job_id in self._executors:
                self._executors[job_id].shutdown(wait=False, cancel_futures=True)
                del self._executors[job_id]

            logger.info("job_canceled", job_id=job_id)
            return True

        return False
