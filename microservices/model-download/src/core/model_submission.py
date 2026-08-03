# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from src.api.models import ModelDownloadRequest, ModelHub
from src.core.model_manager import ModelManager
from src.core.plugin_registry import PluginRegistry
from src.utils.logging import logger


class ModelSubmissionError(ValueError):
    """An expected model submission error that maps to an HTTP 400 response."""


def _resolve_destination(
    models_dir: str,
    download_path: str,
    *children: str,
) -> str:
    """Resolve a requested destination and require it to remain under MODELS_DIR."""

    try:
        models_root = Path(models_dir).resolve()
        requested_path = Path(download_path)
        destination = (
            requested_path
            if requested_path.is_absolute()
            else models_root / requested_path
        )
        destination = destination.joinpath(*children).resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise ModelSubmissionError(
            "Requested model destination is not a valid path under MODELS_DIR."
        ) from error

    if not destination.is_relative_to(models_root):
        raise ModelSubmissionError(
            "Requested model destination must remain under MODELS_DIR."
        )

    return str(destination)


def _handle_task_completion(task: asyncio.Task[Any], tasks: set[asyncio.Task[Any]]) -> None:
    tasks.discard(task)
    if task.cancelled():
        return

    error = task.exception()
    if error is not None:
        logger.error(
            "model_background_task_failed",
            task_name=task.get_name(),
            error_type=type(error).__name__,
        )


def schedule_background_task(
    coroutine: Coroutine[Any, Any, Any],
    tasks: set[asyncio.Task[Any]],
    *,
    name: str,
) -> asyncio.Task[Any]:
    """Create and retain a task until its result or exception is consumed."""

    task = asyncio.create_task(coroutine, name=name)
    tasks.add(task)
    task.add_done_callback(lambda completed: _handle_task_completion(completed, tasks))
    return task


async def submit_models(
    request: ModelDownloadRequest,
    download_path: str,
    *,
    plugin_registry: PluginRegistry,
    model_manager: ModelManager,
    models_dir: str,
    background_tasks: set[asyncio.Task[Any]],
) -> list[str]:
    """Validate, register, and asynchronously schedule model jobs."""

    supported_hubs = set(plugin_registry.supported_hubs())
    for plugin_type in plugin_registry.plugins:
        supported_hubs.update(
            name.lower() for name in plugin_registry.get_plugin_names(plugin_type)
        )
    for model in request.models:
        logger.info(f"Requested Model Hub: {model.hub}")
        if model.hub.lower() not in supported_hubs:
            raise ModelSubmissionError(
                "Unsupported model download/conversion detected. "
                f"Supported methods are {supported_hubs}."
            )

    hf_token = os.getenv("HF_TOKEN")
    logger.info(f"Initiating model download for {len(request.models)} model(s)")
    job_ids = []

    for model in request.models:
        hub_name = model.hub.value
        is_plugin_available, error_reason = plugin_registry.hub_is_available(hub_name)
        if not is_plugin_available:
            raise ModelSubmissionError(
                f"Plugin '{model.hub}' is not available: {error_reason}"
            )

        extra_kwargs = model.model_dump().copy()
        request_credentials = extra_kwargs.get("override_credentials") or {}
        plugin = plugin_registry.get_plugin("downloader", hub_name)
        if plugin is None:
            plugin = plugin_registry.find_plugin_for_model(
                "downloader",
                model.name,
                hub_name,
            )
        if model.is_ovms and plugin is None:
            plugin = plugin_registry.get_plugin("converter", "openvino")
        if request_credentials and plugin is not None:
            try:
                plugin.resolve_config(request_credentials, hub=hub_name)
            except ValueError as error:
                raise ModelSubmissionError(str(error)) from error

        logger.info(
            "model_submission_started",
            model_name=model.name,
            hub=model.hub,
        )

        needs_conversion = model.is_ovms
        model_download_path = _resolve_destination(models_dir, download_path)

        if model.hub.lower() in [hub.value.lower() for hub in ModelHub] and not needs_conversion:
            extra_kwargs["token"] = hf_token
            extra_kwargs["parallel_downloads"] = request.parallel_downloads
            extra_kwargs.pop("hub", None)
            extra_kwargs.pop("is_ovms", None)

            try:
                download_job_id = model_manager.register_job(
                    operation_type="download",
                    model_name=model.name,
                    hub=model.hub,
                    output_dir=model_download_path,
                    plugin_name=model.hub,
                    model_type=model.type,
                )
            except OSError as error:
                raise ModelSubmissionError(
                    "Unable to prepare the requested destination under MODELS_DIR."
                ) from error
            job_ids.append(download_job_id)
            schedule_background_task(
                model_manager.process_download(
                    job_id=download_job_id,
                    model_name=model.name,
                    hub=model.hub,
                    output_dir=model_download_path,
                    downloader=model.hub,
                    **extra_kwargs,
                ),
                background_tasks,
                name=f"model-download-{download_job_id}",
            )

        if needs_conversion:
            is_openvino_available, openvino_error = plugin_registry.hub_is_available("openvino")
            if not is_openvino_available:
                raise ModelSubmissionError(
                    "OpenVINO conversion requested but plugin is not available: "
                    f"{openvino_error}"
                )

            extra_kwargs["token"] = hf_token
            config = model.config.model_dump() if model.config else {}
            config["device"] = config.get("device") or config.get("target_device") or "CPU"
            config["precision"] = (
                config.get("weight-format") or config.get("precision") or "int8"
            ).lower()

            if config["device"].upper() == "NPU":
                logger.warning(
                    "NPU target device selected. Only 'int4' weight format is supported "
                    "for NPU. Overriding weight_format to 'int4'."
                )
                config["precision"] = "int4"

            convert_output_dir = _resolve_destination(
                models_dir,
                download_path,
                "openvino_models",
                config["device"].lower(),
                config["precision"].lower(),
            )

            try:
                convert_job_id = model_manager.register_job(
                    operation_type="convert",
                    model_name=model.name,
                    hub=model.hub,
                    output_dir=convert_output_dir,
                    plugin_name="openvino",
                    model_type=model.type,
                )
            except OSError as error:
                raise ModelSubmissionError(
                    "Unable to prepare the requested destination under MODELS_DIR."
                ) from error
            job_ids.append(convert_job_id)
            schedule_background_task(
                model_manager.process_conversion(
                    job_id=convert_job_id,
                    model_path=model_download_path,
                    hub=model.hub,
                    output_dir=convert_output_dir,
                    converter="openvino",
                    model_name=model.name,
                    model_type=model.type,
                    hf_token=extra_kwargs["token"],
                    override_credentials=request_credentials,
                    **config,
                ),
                background_tasks,
                name=f"model-conversion-{convert_job_id}",
            )

    return job_ids
