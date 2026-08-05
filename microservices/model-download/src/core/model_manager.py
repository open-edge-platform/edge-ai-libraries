# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import json
import shutil
import time
import uuid
import asyncio
import inspect
import concurrent.futures
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

from .plugin_registry import PluginRegistry
from .interfaces import ModelDownloadPlugin, DownloadTask

# Configure structured logging
from src.utils.logging import logger


# Kwarg keys that may carry secrets (tokens, raw overrides) and must never be logged.
_SENSITIVE_KWARG_KEYS = {"override_credentials", "resolved_config", "token", "hf_token"}


def _redact_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of ``kwargs`` with sensitive values masked for logging."""
    return {
        key: ("***" if key in _SENSITIVE_KWARG_KEYS else value)
        for key, value in kwargs.items()
    }


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
        self._cancel_events: Dict[str, threading.Event] = {}  # Cancellation signals per job
        self._asyncio_tasks: Dict[str, asyncio.Task] = {}  # Asyncio tasks per job
        self._active_processes: Dict[str, List] = {}  # Subprocess handles per job
        self._model_download_dir: Dict[str, List[str]] = {}  # Exact model dirs a plugin created, per job
        self._jobs_lock = threading.RLock()
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
        with self._jobs_lock:
            self._jobs[job_id] = {
                "id": job_id,
                "operation_type": operation_type,
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

    def _set_job_status(self, job_id: str, status: str) -> None:
        with self._jobs_lock:
            self._jobs[job_id]["status"] = status

    def _mark_job_completed(self, job_id: str, result: Any) -> None:
        with self._jobs_lock:
            job = self._jobs[job_id]
            job["status"] = "completed"
            job["completion_time"] = datetime.now().isoformat()
            job["result"] = result

    def _mark_job_failed(
        self, job_id: str, error: Any, result: Any = None
    ) -> None:
        with self._jobs_lock:
            job = self._jobs[job_id]
            job["status"] = "failed"
            job["error"] = str(error)
            job["completion_time"] = datetime.now().isoformat()
            if result is not None:
                job["result"] = result

    @staticmethod
    def _cleanup_stale_config_all(parent_dir: str) -> None:
        """Prune stale config_all.json entries whose base_path no longer exists.

        After model-leaf deletion, this removes stale model entries from the
        per-precision metadata file. If no entries remain, config_all.json is
        deleted so now-empty directories can be pruned.
        """
        config_path = os.path.join(parent_dir, "config_all.json")
        if not os.path.isfile(config_path):
            return

        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config_data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return

        entries = config_data.get("model_config_list")
        if not isinstance(entries, list):
            return

        kept_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                kept_entries.append(entry)
                continue

            base_path = entry.get("config", {}).get("base_path")
            if not base_path:
                kept_entries.append(entry)
                continue

            candidate = os.path.abspath(os.path.join(parent_dir, base_path))
            if os.path.exists(candidate):
                kept_entries.append(entry)

        # None of the models are deleted
        if len(kept_entries) == len(entries):
            return

        try:
            # some models are deleted
            if kept_entries:
                config_data["model_config_list"] = kept_entries
                with open(config_path, "w", encoding="utf-8") as file:
                    json.dump(config_data, file, indent=4)

            # all models are deleted
            else:
                os.remove(config_path)
        except OSError:
            return

    def _prune_empty_parents(self, path: str) -> None:
        """Prune empty parent dirs of ``path`` up to (but excluding) models root."""
        root = self.default_dir
        current = os.path.abspath(os.path.dirname(path))

        while current != root and os.path.commonpath([root, current]) == root:
            if not os.path.isdir(current):
                break

            # Keep per-precision metadata consistent before checking emptiness.
            self._cleanup_stale_config_all(current)

            try:
                if os.listdir(current):
                    break
                os.rmdir(current)
            except OSError:
                break

            current = os.path.abspath(os.path.dirname(current))

    def _cleanup_model_download_dir(self, job_id: str) -> None:
        """Remove only the exact model directories a plugin created for this job.

        Plugins register the precise leaf dir they write to (precision-specific
        for geti/openvino) via the shared ``_model_download_dir`` list. Only those dirs
        are removed, and each must stay strictly under the models root — the
        root itself is never deleted, so sibling models, other hubs, and other
        precisions of the same model are left intact.
        """
        root = self.default_dir

        for path in self._model_download_dir.get(job_id, []):
            if not path:
                continue
            candidate = os.path.abspath(path)
            # Safety: never delete the models root or anything outside it.
            if candidate == root or os.path.commonpath([root, candidate]) != root:
                continue
            if os.path.isdir(candidate):
                shutil.rmtree(candidate, ignore_errors=True)
                logger.info("canceled_job_cleanup", job_id=job_id, removed_dir=candidate)
            elif os.path.isfile(candidate):
                try:
                    os.remove(candidate)
                    logger.info("canceled_job_cleanup", job_id=job_id, removed_file=candidate)
                except OSError:
                    continue

            self._prune_empty_parents(candidate)

    def _handle_cancelled_job(self, job_id: str, log_event: str, **log_extra) -> None:
        """Clean up residual files for a cancelled job and log the event."""
        self._cleanup_model_download_dir(job_id)
        self._model_download_dir.pop(job_id, None)
        self._cancel_events.pop(job_id, None)
        logger.info(log_event, job_id=job_id, **log_extra)

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
        # Ensure a cancel event exists for cooperative cancellation
        self.get_cancel_event(job_id)

        # Provide a shared list for plugins to register subprocess handles
        proc_list: List = []
        self._active_processes[job_id] = proc_list
        kwargs["_active_processes"] = proc_list

        # Provide a shared list for plugins to register the exact model dir(s)
        # they create, so cancellation removes only those (precision-safe).
        model_dirs: List[str] = []
        self._model_download_dir[job_id] = model_dirs
        kwargs["_model_download_dir"] = model_dirs

        try:
            # Update job status
            self._set_job_status(job_id, "downloading")
            request_credentials = kwargs.pop("override_credentials", None) or {}
            logger.info(
                "download_processing_started",
                model_name=model_name,
                hub=hub,
                downloader=downloader,
            )
            # Find appropriate downloader plugin
            download_plugin = None
            if downloader:
                download_plugin = self.registry.get_plugin("downloader", downloader)
                if not download_plugin:
                    download_plugin = self.registry.find_plugin_for_model(
                        "downloader", model_name, downloader, **kwargs
                    )
                if not download_plugin:
                    err_msg = f"Requested downloader '{downloader}' not found"
                    logger.error("downloader_not_found", downloader=downloader)
                    raise ValueError(err_msg)
            else:
                # Auto-detect appropriate downloader
                download_plugin = self.registry.find_plugin_for_model(
                    "downloader", model_name, hub, **kwargs
                )

            if not download_plugin:
                err_msg = f"No suitable downloader found for model '{model_name}'"
                logger.error("no_suitable_downloader", model_name=model_name)
                raise ValueError(err_msg)

            # Resolve per-request overrides for the selected plugin and expose
            # them via 'resolved_config'. Values are scoped to this call only.
            kwargs["resolved_config"] = download_plugin.resolve_config(request_credentials, hub=hub)
            # validate_credentials is consumed at submission time; drop it so
            # it does not leak into plugin download/convert kwargs.
            kwargs.pop("validate_credentials", None)

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
                        error_type=type(e).__name__,
                    )

            # Fall back to the plugin's standard download method
            logger.info(
                "using_standard_download",
                plugin=download_plugin.plugin_name,
                model_name=model_name,
            )

            # Expose hub to multi-hub plugins; single-hub plugins ignore it.
            kwargs.setdefault("hub", hub)

            # Check if the download method is async
            if inspect.iscoroutinefunction(download_plugin.download):
                result = await download_plugin.download(
                    model_name, output_dir, **kwargs
                )
            else:
                result = await asyncio.to_thread(
                    download_plugin.download, model_name, output_dir, **kwargs
                )

            # Check if job was cancelled while the blocking download was running.
            # For hubs that use in-process API calls (huggingface, geti, openvino pull), the
            # download thread cannot be interrupted and may have written files
            # after cancel_job's initial rmtree. Clean up any residual files.
            # HF/Geti/OpenVINO-pull: thread finished naturally after cancel
            if self.is_job_cancelled(job_id):
                self._handle_cancelled_job(job_id, "download_cancelled_after_completion", model_name=model_name)
                return {"job_id": job_id, "status": "canceled", "model_name": model_name}

            # Check if the download was successful
            if isinstance(result, dict) and result.get("success") is False:
                # Download failed, update job status accordingly
                error_msg = result.get("error", "Unknown error")
                self._mark_job_failed(job_id, error_msg, result)
                
                logger.error(
                    "download_failed",
                    job_id=job_id,
                    model_name=model_name,
                    failure_reason="plugin_reported_failure",
                )
                return {
                    "job_id": job_id,
                    "status": "failed",
                    "model_name": model_name,
                    "error": error_msg,
                }

            self._mark_job_completed(job_id, result)

            logger.info("download_completed", job_id=job_id, model_name=model_name)

            # Report the exact model dir the plugin created (same path used for
            # cancellation cleanup). Falls back to output_dir if none registered.
            registered = self._model_download_dir.get(job_id) or []
            host_path = registered[-1] if registered else output_dir
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

        except asyncio.CancelledError:
            # App shutdown cancelled the task (docker stop/restart/OOM)
            self._handle_cancelled_job(job_id, "download_cancelled_server_exit", model_name=model_name)
            return {"job_id": job_id, "status": "canceled", "model_name": model_name}
        except Exception as e:
            if self.is_job_cancelled(job_id):
                # Subprocess killed by cancel_job raised an error
                self._handle_cancelled_job(job_id, "download_cancelled_subprocess_killed", model_name=model_name)
                return {"job_id": job_id, "status": "canceled", "model_name": model_name}
            self._mark_job_failed(job_id, e)
            logger.error(
                "download_failed",
                job_id=job_id,
                model_name=model_name,
                error_type=type(e).__name__,
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
        # Ensure a cancel event exists for cooperative cancellation
        self.get_cancel_event(job_id)

        # Provide a shared list for plugins to register subprocess handles
        proc_list: List = []
        self._active_processes[job_id] = proc_list
        kwargs["_active_processes"] = proc_list

        # Provide a shared list for plugins to register the exact model dir(s)
        # they create, so cancellation removes only those (precision-safe).
        model_dirs: List[str] = []
        self._model_download_dir[job_id] = model_dirs
        kwargs["_model_download_dir"] = model_dirs

        try:
            # Check if hub is 'openvino'
            if hub != "openvino":
                err_msg = f"Conversion failed: incorrect hub '{hub}' provided. Only 'openvino' is supported for conversion."
                self._mark_job_failed(job_id, err_msg)
                logger.error("conversion_failed_incorrect_hub", job_id=job_id, model_path=model_path, hub=hub)
                return {
                    "job_id": job_id,
                    "status": "failed",
                    "model_path": model_path,
                    "error": err_msg,
                }

            # Update job status
            self._set_job_status(job_id, "converting")

            # Per-request connection overrides for the converter.
            request_credentials = kwargs.pop("override_credentials", None) or {}

            # Find appropriate converter plugin
            convert_plugin = None
            if converter:
                convert_plugin = self.registry.get_plugin("converter", converter)
                if convert_plugin is None:
                    err_msg = f"Requested converter '{converter}' not found"
                    logger.error("converter_not_found", converter=converter)
                    raise ValueError(err_msg)
            else:
                convert_plugin = self.registry.find_plugin_for_model(
                    "converter",
                    hub=hub,
                    model_name=model_name,
                    is_ovms=True,
                    **kwargs,
                )

            if convert_plugin is None:
                err_msg = f"No suitable converter found for model at '{model_path}'"
                logger.error("no_suitable_converter", model_path=model_path)
                raise ValueError(err_msg)

            # Resolve per-request overrides for the converter (override wins,
            # env fallback); scoped to this call only.
            kwargs["resolved_config"] = convert_plugin.resolve_config(request_credentials, hub=hub)
            # validate_credentials is consumed at submission time; drop it so
            # it does not leak into plugin convert kwargs.
            kwargs.pop("validate_credentials", None)

            # Execute the conversion
            logger.info(
                "starting_conversion",
                plugin=convert_plugin.plugin_name,
                model_path=model_path,
            )

            logger.info(f"Request details: {model_path}, {hub}, {_redact_kwargs(kwargs)}")
            result = await asyncio.to_thread(
                convert_plugin.convert,
                model_name, output_dir, hf_token=hf_token, **kwargs
            )

            # Check if job was cancelled while the blocking conversion was running
            # OpenVINO pull (snapshot_download): thread finished naturally after cancel
            if self.is_job_cancelled(job_id):
                self._handle_cancelled_job(job_id, "conversion_cancelled_after_completion", model_name=model_name)
                return {"job_id": job_id, "status": "canceled", "model_path": model_path}

            self._mark_job_completed(job_id, result)

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

        except asyncio.CancelledError:
            # App shutdown cancelled the task (docker stop/restart/OOM)
            self._handle_cancelled_job(job_id, "conversion_cancelled_server_exit", model_name=model_name)
            return {"job_id": job_id, "status": "canceled", "model_path": model_path}
        except Exception as e:
            if self.is_job_cancelled(job_id):
                # subprocess killed by cancel_job raised an error
                self._handle_cancelled_job(job_id, "conversion_cancelled_subprocess_killed", model_name=model_name)
                return {"job_id": job_id, "status": "canceled", "model_path": model_path}
            self._mark_job_failed(job_id, e)
            logger.error(
                "conversion_failed",
                job_id=job_id,
                model_path=model_path,
                error_type=type(e).__name__,
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
                        # Check if job has been canceled via the cancel event
                        if self.is_job_cancelled(job_id):
                            logger.info("download_task_canceled", task=task.destination)
                            raise InterruptedError("Download was canceled")

                        # Call the plugin to download this task
                        path = plugin.download_task(task, model_path, **kwargs)
                        return path
                    except Exception as e:
                        logger.error(
                            "task_download_error",
                            task=task.destination,
                            error_type=type(e).__name__,
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
                            logger.error(
                                "task_failure",
                                task=task.destination,
                                error_type=type(e).__name__,
                            )
                            raise

                # All tasks completed successfully, perform any post-processing
                result = plugin.post_process(
                    model_name, model_path, downloaded_paths, **kwargs
                )
                if inspect.isawaitable(result):
                    result = asyncio.run(result)

                self._mark_job_completed(job_id, result)

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
                    self._mark_job_failed(job_id, e)

                logger.error(
                    "parallel_download_failed",
                    job_id=job_id,
                    model_name=model_name,
                    error_type=type(e).__name__,
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
        job_id = self.register_job("download", model_name, hub, output_dir)
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
        job_id = self.register_job("convert", model_name, "openvino", output_dir)
        return asyncio.run(self.process_conversion(
            job_id=job_id, model_path=model_path, model_name=model_name, hub="openvino", hf_token=kwargs.get("hf_token", ""), output_dir=output_dir, converter=converter, **kwargs
        ))

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific job."""
        with self._jobs_lock:
            if job_id not in self._jobs:
                return None
            return self._jobs[job_id].copy()

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
        with self._jobs_lock:
            all_jobs = [job.copy() for job in self._jobs.values()]

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

    def register_asyncio_task(self, job_id: str, task: asyncio.Task) -> None:
        """Associate an asyncio task with a job for cancellation support."""
        self._asyncio_tasks[job_id] = task

    def is_job_cancelled(self, job_id: str) -> bool:
        """Check whether a job has been cancelled (thread-safe)."""
        event = self._cancel_events.get(job_id)
        return event is not None and event.is_set()

    def get_cancel_event(self, job_id: str) -> threading.Event:
        """Get or create the cancellation event for a job."""
        if job_id not in self._cancel_events:
            self._cancel_events[job_id] = threading.Event()
        return self._cancel_events[job_id]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job if possible, cleaning up partial downloads."""
        with self._jobs_lock:
            if job_id not in self._jobs:
                return False
            if self._jobs[job_id]["status"] not in [
                "queued",
                "downloading",
                "converting",
            ]:
                return False
            self._jobs[job_id]["status"] = "canceled"
            self._jobs[job_id]["completion_time"] = datetime.now().isoformat()

        # Signal cooperative cancellation to any running thread
        cancel_event = self._cancel_events.get(job_id)
        if cancel_event is not None:
            cancel_event.set()

        # If there's an active executor for this job, shut it down
        if job_id in self._executors:
            self._executors[job_id].shutdown(wait=False, cancel_futures=True)
            del self._executors[job_id]

        # Remove the asyncio task reference but do NOT cancel it. The thread
        # will finish naturally and hit the is_job_cancelled() check which does
        # final cleanup. Cancelling the task causes CancelledError which races
        # with threads still writing files (e.g. snapshot_download).
        self._asyncio_tasks.pop(job_id, None)

        # Kill any active subprocesses registered by plugins
        active_procs = self._active_processes.pop(job_id, [])
        for proc in active_procs:
            try:
                proc.terminate()
            except OSError:
                pass
        # Give processes a moment then force-kill survivors
        time.sleep(0.5)
        for proc in active_procs:
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                pass

        # Clean up only the exact model dir(s) this job created, never the
        # shared download_path base (which may hold other models/hubs/precisions).
        self._cleanup_model_download_dir(job_id)

        # Do NOT clean up the cancel event here. The background thread needs
        # to check is_job_cancelled() after it finishes. The event is cleaned
        # up by _handle_cancelled_job or left to be garbage collected.

        logger.info("job_canceled", job_id=job_id)
        return True
