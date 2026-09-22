# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.models import ModelDownloadRequest
from src.core.model_submission import (
    ModelSubmissionError,
    schedule_background_task,
    submit_models,
)


@pytest.fixture
def registry():
    plugin_registry = MagicMock()
    plugin_registry.plugins = {"downloader": {"huggingface": MagicMock()}}
    plugin_registry.get_plugin_names.return_value = ["huggingface"]
    plugin_registry.supported_hubs.return_value = ["huggingface"]
    plugin_registry.hub_is_available.return_value = (True, "")
    plugin_registry.get_plugin.return_value = plugin_registry.plugins["downloader"]["huggingface"]
    return plugin_registry


@pytest.fixture
def manager():
    model_manager = MagicMock()
    model_manager.register_job.return_value = "job-1"
    model_manager.process_download = AsyncMock()
    model_manager.process_conversion = AsyncMock()
    return model_manager


@pytest.mark.parametrize(
    "target",
    ["audio-analyzer", "text-to-speech"],
)
def test_model_request_accepts_supported_targets(target):
    request = ModelDownloadRequest.model_validate(
        {"models": [{"name": "org/model", "hub": "openvino", "target": target}]}
    )

    assert request.models[0].target.value == target


def test_model_request_preserves_existing_requests_without_target():
    request = ModelDownloadRequest.model_validate(
        {"models": [{"name": "org/model", "hub": "openvino", "is_ovms": True}]}
    )

    assert request.models[0].target is None
    assert request.models[0].is_ovms is True


async def test_submit_models_registers_and_schedules_download(registry, manager):
    request = ModelDownloadRequest.model_validate(
        {
            "parallel_downloads": True,
            "models": [{"name": "org/model", "hub": "huggingface"}],
        }
    )
    background_tasks = set()

    job_ids = await submit_models(
        request,
        "configured",
        plugin_registry=registry,
        model_manager=manager,
        models_dir="/models",
        background_tasks=background_tasks,
    )
    await asyncio.gather(*background_tasks)
    await asyncio.sleep(0)

    assert job_ids == ["job-1"]
    manager.register_job.assert_called_once_with(
        operation_type="download",
        model_name="org/model",
        hub="huggingface",
        output_dir="/models/configured",
        plugin_name="huggingface",
        model_type=None,
    )
    assert manager.process_download.call_args.kwargs["parallel_downloads"] is True
    assert not background_tasks


async def test_submit_models_rejects_unavailable_plugin(registry, manager):
    registry.hub_is_available.return_value = (False, "not activated")
    request = ModelDownloadRequest.model_validate(
        {"models": [{"name": "org/model", "hub": "huggingface"}]}
    )

    with pytest.raises(ModelSubmissionError, match="not activated"):
        await submit_models(
            request,
            "configured",
            plugin_registry=registry,
            model_manager=manager,
            models_dir="/models",
            background_tasks=set(),
        )

    manager.register_job.assert_not_called()


@pytest.mark.parametrize("download_path", ["../outside", "/outside"])
async def test_submit_models_rejects_destinations_outside_models_dir(
    download_path,
    registry,
    manager,
):
    request = ModelDownloadRequest.model_validate(
        {"models": [{"name": "org/model", "hub": "huggingface"}]}
    )

    with pytest.raises(ModelSubmissionError, match="remain under MODELS_DIR"):
        await submit_models(
            request,
            download_path,
            plugin_registry=registry,
            model_manager=manager,
            models_dir="/models",
            background_tasks=set(),
        )

    manager.register_job.assert_not_called()


async def test_submit_models_normalizes_destination_within_models_dir(registry, manager):
    request = ModelDownloadRequest.model_validate(
        {"models": [{"name": "org/model", "hub": "huggingface"}]}
    )
    background_tasks = set()

    await submit_models(
        request,
        "nested/../configured",
        plugin_registry=registry,
        model_manager=manager,
        models_dir="/models",
        background_tasks=background_tasks,
    )
    await asyncio.gather(*background_tasks)
    await asyncio.sleep(0)

    assert manager.register_job.call_args.kwargs["output_dir"] == "/models/configured"


@pytest.mark.parametrize(
    "target,name,model_type,precision,expected_path",
    [
        (
            "audio-analyzer",
            "openai/whisper-base",
            "speech2text",
            "int8",
            "/models/voice/audio-analyzer/openvino/whisper-base",
        ),
        (
            "text-to-speech",
            "microsoft/speecht5_tts",
            "text2speech",
            "fp16",
            "/models/voice/text-to-speech/openvino/microsoft_speecht5_tts__fp16",
        ),
    ],
)
async def test_submit_models_routes_supported_voice_targets(
    target,
    name,
    model_type,
    precision,
    expected_path,
    registry,
    manager,
):
    request = ModelDownloadRequest.model_validate(
        {
            "models": [
                {
                    "name": name,
                    "hub": "openvino",
                    "type": model_type,
                    "target": target,
                    "config": {"precision": precision, "device": "CPU"},
                }
            ]
        }
    )
    background_tasks = set()

    job_ids = await submit_models(
        request,
        "voice",
        plugin_registry=registry,
        model_manager=manager,
        models_dir="/models",
        background_tasks=background_tasks,
    )
    await asyncio.gather(*background_tasks)
    await asyncio.sleep(0)

    assert job_ids == ["job-1"]
    assert manager.register_job.call_args.kwargs["output_dir"] == expected_path
    conversion_kwargs = manager.process_conversion.call_args.kwargs
    assert conversion_kwargs["output_dir"] == expected_path
    assert conversion_kwargs["target"] == target


@pytest.mark.parametrize(
    "target,name,model_type",
    [
        ("audio-analyzer", "openai/whisper-small", "speech2text"),
        ("audio-analyzer", "openai/whisper-base", "text2speech"),
        ("text-to-speech", "microsoft/speecht5_tts", "speech2text"),
    ],
)
async def test_submit_models_rejects_unsupported_voice_target_combinations(
    target,
    name,
    model_type,
    registry,
    manager,
):
    request = ModelDownloadRequest.model_validate(
        {
            "models": [
                {
                    "name": name,
                    "hub": "openvino",
                    "type": model_type,
                    "target": target,
                }
            ]
        }
    )

    with pytest.raises(ModelSubmissionError, match="supports only"):
        await submit_models(
            request,
            "voice",
            plugin_registry=registry,
            model_manager=manager,
            models_dir="/models",
            background_tasks=set(),
        )

    manager.register_job.assert_not_called()


@pytest.mark.parametrize(
    "target,name,model_type,precision",
    [
        ("audio-analyzer", "openai/whisper-base", "speech2text", "fp16"),
        ("text-to-speech", "microsoft/speecht5_tts", "text2speech", "int4"),
    ],
)
async def test_submit_models_rejects_unsupported_voice_precision(
    target,
    name,
    model_type,
    precision,
    registry,
    manager,
):
    request = ModelDownloadRequest.model_validate(
        {
            "models": [
                {
                    "name": name,
                    "hub": "openvino",
                    "type": model_type,
                    "target": target,
                    "config": {"precision": precision},
                }
            ]
        }
    )

    with pytest.raises(ModelSubmissionError, match="supports only precision"):
        await submit_models(
            request,
            "voice",
            plugin_registry=registry,
            model_manager=manager,
            models_dir="/models",
            background_tasks=set(),
        )

    manager.register_job.assert_not_called()


async def test_submit_models_rejects_non_cpu_voice_export(registry, manager):
    request = ModelDownloadRequest.model_validate(
        {
            "models": [
                {
                    "name": "openai/whisper-base",
                    "hub": "openvino",
                    "type": "speech2text",
                    "target": "audio-analyzer",
                    "config": {"precision": "int8", "device": "NPU"},
                }
            ]
        }
    )

    with pytest.raises(ModelSubmissionError, match="supports only device='CPU'"):
        await submit_models(
            request,
            "voice",
            plugin_registry=registry,
            model_manager=manager,
            models_dir="/models",
            background_tasks=set(),
        )

    manager.register_job.assert_not_called()


async def test_submit_models_rejects_symlink_escape(tmp_path, registry, manager):
    models_dir = tmp_path / "models"
    outside_dir = tmp_path / "outside"
    models_dir.mkdir()
    outside_dir.mkdir()
    (models_dir / "escape").symlink_to(outside_dir, target_is_directory=True)
    request = ModelDownloadRequest.model_validate(
        {"models": [{"name": "org/model", "hub": "huggingface"}]}
    )

    with pytest.raises(ModelSubmissionError, match="remain under MODELS_DIR"):
        await submit_models(
            request,
            "escape",
            plugin_registry=registry,
            model_manager=manager,
            models_dir=str(models_dir),
            background_tasks=set(),
        )

    manager.register_job.assert_not_called()


async def test_background_task_is_retained_and_exception_is_consumed():
    tasks = set()

    async def fail():
        await asyncio.sleep(0)
        raise RuntimeError("background failure")

    with pytest.raises(RuntimeError, match="background failure"), pytest.MonkeyPatch.context() as monkeypatch:
        log_error = MagicMock()
        monkeypatch.setattr("src.core.model_submission.logger.error", log_error)
        task = schedule_background_task(fail(), tasks, name="failing-task")
        assert task in tasks
        await task

    await asyncio.sleep(0)
    assert task not in tasks
    log_error.assert_called_once_with(
        "model_background_task_failed",
        task_name="failing-task",
        error_type="RuntimeError",
    )


async def test_cancelled_background_task_is_removed_without_error_log():
    tasks = set()
    started = asyncio.Event()

    async def wait_forever():
        started.set()
        await asyncio.Event().wait()

    with pytest.MonkeyPatch.context() as monkeypatch:
        log_error = MagicMock()
        monkeypatch.setattr("src.core.model_submission.logger.error", log_error)
        task = schedule_background_task(wait_forever(), tasks, name="cancelled-task")
        await started.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert task not in tasks
    log_error.assert_not_called()
