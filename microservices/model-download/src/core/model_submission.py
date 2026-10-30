# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
import re
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from src.api.models import ModelDownloadRequest, ModelHub, ModelPrecision, ModelTarget
from src.core.model_manager import ModelManager
from src.core.plugin_registry import PluginRegistry
from src.utils.logging import logger


class ModelSubmissionError(ValueError):
    """An expected model submission error that maps to an HTTP 400 response."""


_VOICE_TARGET_MODELS = {
    ModelTarget.AUDIO_ANALYZER: ("openai/whisper-base", "speech2text"),
    ModelTarget.TEXT_TO_SPEECH: ("microsoft/speecht5_tts", "text2speech"),
}


def _validate_voice_target(model) -> None:
    if model.target not in _VOICE_TARGET_MODELS:
        return

    expected_name, expected_type = _VOICE_TARGET_MODELS[model.target]
    if (
        model.hub != ModelHub.OPENVINO
        or model.name != expected_name
        or model.type != expected_type
    ):
        raise ModelSubmissionError(
            f"Target '{model.target.value}' supports only name='{expected_name}', "
            f"hub='openvino', type='{expected_type}'."
        )

    precision = (
        model.config.precision
        if model.config is not None and model.config.precision is not None
        else ModelPrecision.INT8
    )
    supported_precisions = {
        ModelTarget.AUDIO_ANALYZER: {ModelPrecision.INT8},
        ModelTarget.TEXT_TO_SPEECH: {ModelPrecision.INT8, ModelPrecision.FP16},
    }[model.target]
    if precision not in supported_precisions:
        allowed = ", ".join(sorted(value.value for value in supported_precisions))
        raise ModelSubmissionError(
            f"Target '{model.target.value}' supports only precision: {allowed}."
        )

    device = model.config.device if model.config is not None else None
    if device is not None and device.upper() != "CPU":
        raise ModelSubmissionError(
            f"Target '{model.target.value}' supports only device='CPU'."
        )


def _voice_output_children(model, precision: str) -> tuple[str, ...] | None:
    if model.target == ModelTarget.AUDIO_ANALYZER:
        return ("audio-analyzer", "openvino", "whisper-base")
    if model.target == ModelTarget.TEXT_TO_SPEECH:
        return (
            "text-to-speech",
            "openvino",
            f"microsoft_speecht5_tts__{precision}",
        )
    return None


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

    valid_hubs = {hub.value for hub in ModelHub}
    for model in request.models:
        _validate_voice_target(model)
        logger.info(f"Requested Model Hub: {model.hub}")
        if model.hub.lower() not in valid_hubs:
            raise ModelSubmissionError(
                "Unsupported model download/conversion detected. "
                f"Supported valid hubs are {valid_hubs}."
            )
        is_available, reason = plugin_registry.hub_is_available(model.hub.lower())
        if not is_available:
            raise ModelSubmissionError(
                f"Plugin '{model.hub}' is not available: {reason}"
            )

    hf_token = os.getenv("HF_TOKEN")
    logger.info(f"Initiating model download for {len(request.models)} model(s)")
    job_ids = []

    for model in request.models:
        hub_name = model.hub.value

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
        if plugin is not None:
            # Validate override keys are recognised by the plugin.
            if request_credentials:
                try:
                    plugin.resolve_config(request_credentials, hub=hub_name)
                except ValueError as error:
                    raise ModelSubmissionError(str(error)) from error

            # Opt-in credential pre-check: fail fast before creating a job.
            if extra_kwargs.get("validate_credentials"):
                resolved = plugin.resolve_config(request_credentials, hub=hub_name)
                validation = plugin.validate_credentials(resolved)
                if not validation.get("ok"):
                    raise ModelSubmissionError(
                        f"Credential validation failed [{validation['name']}]: "
                        f"{validation['message']}"
                    )
                logger.info(
                    "credential_validation_result",
                    plugin=plugin.plugin_name,
                    message=validation.get("message"),
                )

        logger.info(
            "model_submission_started",
            model_name=model.name,
            hub=model.hub,
        )

        needs_conversion = model.is_ovms or model.target is not None
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
            task = schedule_background_task(
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
            model_manager.register_asyncio_task(download_job_id, task)

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

            # Create a unique output directory for the converted model.
            # HETERO devices contain ':' and ',' which are hostile in paths,
            # so the device is slugified for the directory (HETERO:GPU,CPU ->
            # hetero_gpu_cpu) while the raw value is still passed to conversion.
            device_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", config["device"])
            voice_children = _voice_output_children(model, config["precision"].lower())
            if voice_children is None:
                convert_output_dir = _resolve_destination(
                    models_dir,
                    download_path,
                    "openvino_models",
                    device_slug.lower(),
                    config["precision"].lower(),
                )
            else:
                convert_output_dir = _resolve_destination(
                    models_dir,
                    download_path,
                    *voice_children,
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
            task = schedule_background_task(
                model_manager.process_conversion(
                    job_id=convert_job_id,
                    model_path=model_download_path,
                    hub=model.hub,
                    output_dir=convert_output_dir,
                    converter="openvino",
                    model_name=model.name,
                    model_type=model.type,
                    hf_token=extra_kwargs["token"],
                    target=model.target.value if model.target else None,
                    override_credentials=request_credentials,
                    **config,
                ),
                background_tasks,
                name=f"model-conversion-{convert_job_id}",
            )
            model_manager.register_asyncio_task(convert_job_id, task)

    return job_ids
