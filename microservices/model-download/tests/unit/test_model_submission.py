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
