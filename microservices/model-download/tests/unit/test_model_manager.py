# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import threading
from unittest.mock import MagicMock, patch

import pytest

from src.core.interfaces import DownloadTask
from src.core.model_manager import ModelManager


def _manager(tmp_path, plugin=None):
    registry = MagicMock()
    registry.get_plugin.return_value = plugin
    return ModelManager(registry, default_dir=str(tmp_path))


def _register(manager, tmp_path, operation_type="download"):
    return manager.register_job(
        operation_type,
        "org/model",
        "huggingface" if operation_type == "download" else "openvino",
        str(tmp_path / "output"),
        "test-plugin",
    )


def test_jobs_have_stable_initial_progress(tmp_path):
    manager = _manager(tmp_path)

    job_id = _register(manager, tmp_path)

    assert manager.get_job_status(job_id)["progress"] == {
        "current": 0,
        "total": 0,
        "percentage": 0,
    }


def test_update_progress_is_bounded_and_ignores_unknown_jobs(tmp_path):
    manager = _manager(tmp_path)
    job_id = _register(manager, tmp_path)

    manager.update_progress(job_id, 15, 10)
    assert manager.get_job_status(job_id)["progress"] == {
        "current": 10,
        "total": 10,
        "percentage": 100,
    }

    manager.update_progress(job_id, -5, 10)
    assert manager.get_job_status(job_id)["progress"] == {
        "current": 0,
        "total": 10,
        "percentage": 0,
    }

    manager.update_progress(job_id, 5, 0)
    assert manager.get_job_status(job_id)["progress"] == {
        "current": 0,
        "total": 0,
        "percentage": 0,
    }
    manager.update_progress("missing", 1, 1)


def test_update_progress_is_thread_safe(tmp_path):
    manager = _manager(tmp_path)
    job_id = _register(manager, tmp_path)
    errors = []

    def update(current):
        try:
            manager.update_progress(job_id, current, 100)
        except Exception as error:  # pragma: no cover - asserted empty below
            errors.append(error)

    threads = [threading.Thread(target=update, args=(value,)) for value in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    progress = manager.get_job_status(job_id)["progress"]
    assert not errors
    assert progress["total"] == 100
    assert 0 <= progress["current"] <= 100
    assert progress["percentage"] == progress["current"]


@pytest.mark.asyncio
async def test_standard_download_receives_explicit_progress_callback(tmp_path):
    observed_progress = []

    class Plugin:
        plugin_name = "callback"

        def get_download_tasks(self, model_name, **kwargs):
            raise NotImplementedError

        async def download(
            self, model_name, output_dir, progress_callback=None, **kwargs
        ):
            progress_callback(25, 100)
            observed_progress.append(
                manager.get_job_status(job_id)["progress"].copy()
            )
            return {"success": True}

    manager = _manager(tmp_path, Plugin())
    job_id = _register(manager, tmp_path)

    result = await manager.process_download(
        job_id,
        "org/model",
        "huggingface",
        str(tmp_path / "output"),
        "test-plugin",
    )

    assert result["status"] == "completed"
    assert observed_progress == [{"current": 25, "total": 100, "percentage": 25}]
    assert manager.get_job_status(job_id)["progress"] == {
        "current": 100,
        "total": 100,
        "percentage": 100,
    }


@pytest.mark.asyncio
async def test_standard_download_without_callback_remains_compatible(tmp_path):
    class Plugin:
        plugin_name = "no-callback"

        def get_download_tasks(self, model_name, **kwargs):
            raise NotImplementedError

        def download(self, model_name, output_dir):
            return {"success": True}

    manager = _manager(tmp_path, Plugin())
    job_id = _register(manager, tmp_path)

    result = await manager.process_download(
        job_id,
        "org/model",
        "huggingface",
        str(tmp_path / "output"),
        "test-plugin",
    )

    assert result["status"] == "completed"
    assert manager.get_job_status(job_id)["progress"]["percentage"] == 100


@pytest.mark.asyncio
async def test_failed_download_keeps_nonterminal_progress(tmp_path):
    class Plugin:
        plugin_name = "failed"

        def get_download_tasks(self, model_name, **kwargs):
            raise NotImplementedError

        async def download(
            self, model_name, output_dir, progress_callback=None, **kwargs
        ):
            progress_callback(4, 10)
            return {"success": False, "error": "download failed"}

    manager = _manager(tmp_path, Plugin())
    job_id = _register(manager, tmp_path)

    result = await manager.process_download(
        job_id,
        "org/model",
        "huggingface",
        str(tmp_path / "output"),
        "test-plugin",
    )

    job = manager.get_job_status(job_id)
    assert result["status"] == "failed"
    assert job["status"] == "failed"
    assert job["progress"] == {"current": 4, "total": 10, "percentage": 40}


@pytest.mark.asyncio
async def test_failed_fallback_download_has_failed_terminal_state(tmp_path):
    class Plugin:
        plugin_name = "failed-fallback"

        def get_download_tasks(self, model_name, **kwargs):
            raise NotImplementedError

        def download(self, model_name, output_dir):
            raise RuntimeError("fallback failed")

    manager = _manager(tmp_path, Plugin())
    job_id = _register(manager, tmp_path)

    result = await manager.process_download(
        job_id,
        "org/model",
        "huggingface",
        str(tmp_path / "output"),
        "test-plugin",
    )

    job = manager.get_job_status(job_id)
    assert result["status"] == "failed"
    assert job["status"] == "failed"
    assert job["error"] == "fallback failed"
    assert job["progress"] == {"current": 0, "total": 0, "percentage": 0}


@pytest.mark.asyncio
async def test_parallel_download_updates_progress_as_files_complete(tmp_path):
    tasks = [
        DownloadTask(str(index), f"https://example.com/{index}", f"file-{index}")
        for index in range(3)
    ]

    class Plugin:
        plugin_name = "parallel"

        def get_download_tasks(self, model_name, **kwargs):
            return tasks

        def download_task(self, task, output_dir, **kwargs):
            return str(tmp_path / task.destination)

        async def post_process(self, model_name, output_dir, downloaded_paths, **kwargs):
            return {"success": True, "downloaded_paths": downloaded_paths}

    manager = _manager(tmp_path, Plugin())
    job_id = _register(manager, tmp_path)

    result = await manager.process_download(
        job_id,
        "org/model",
        "huggingface",
        str(tmp_path / "output"),
        "test-plugin",
        parallel_downloads=True,
    )

    assert result["status"] == "completed"
    assert manager.get_job_status(job_id)["progress"] == {
        "current": 3,
        "total": 3,
        "percentage": 100,
    }


@pytest.mark.asyncio
async def test_parallel_download_failure_has_failed_terminal_state(tmp_path):
    tasks = [
        DownloadTask(str(index), f"https://example.com/{index}", f"file-{index}")
        for index in range(2)
    ]

    class Plugin:
        plugin_name = "parallel-failure"

        def get_download_tasks(self, model_name, **kwargs):
            return tasks

        def download_task(self, task, output_dir, **kwargs):
            if task.file_id == "1":
                raise RuntimeError("file failed")
            return str(tmp_path / task.destination)

    manager = _manager(tmp_path, Plugin())
    job_id = _register(manager, tmp_path)

    result = await manager.process_download(
        job_id,
        "org/model",
        "huggingface",
        str(tmp_path / "output"),
        "test-plugin",
        parallel_downloads=True,
        max_workers=1,
    )

    job = manager.get_job_status(job_id)
    assert result["status"] == "failed"
    assert job["status"] == "failed"
    assert job["error"] == "file failed"
    assert job["progress"]["total"] == 2
    assert job["progress"]["percentage"] < 100


@pytest.mark.asyncio
async def test_conversion_uses_lifecycle_progress_fallback(tmp_path):
    plugin = MagicMock()
    plugin.plugin_name = "openvino"
    plugin.convert.return_value = {"success": True}
    manager = _manager(tmp_path, plugin)
    manager.registry.find_plugin_for_model.return_value = plugin
    job_id = _register(manager, tmp_path, operation_type="convert")

    result = await manager.process_conversion(
        job_id,
        "org/model",
        "org/model",
        "openvino",
        "",
        str(tmp_path / "output"),
        "test-plugin",
    )

    assert result["status"] == "completed"
    assert manager.get_job_status(job_id)["progress"] == {
        "current": 1,
        "total": 1,
        "percentage": 100,
    }


def test_progress_logs_are_structured_and_throttled(tmp_path):
    manager = _manager(tmp_path)
    job_id = _register(manager, tmp_path)

    with patch("src.core.model_manager.time.monotonic", return_value=100), patch(
        "src.core.model_manager.logger.info"
    ) as log_info:
        manager._last_progress_log.clear()
        manager.update_progress(job_id, 1, 10)
        manager.update_progress(job_id, 2, 10)

    progress_logs = [
        call for call in log_info.call_args_list if call.args == ("job_progress",)
    ]
    assert len(progress_logs) == 1
    fields = progress_logs[0].kwargs
    assert fields["current"] == 1
    assert fields["total"] == 10
    assert fields["percentage"] == 10
    assert fields["progress_bar"] == "[##------------------]  10%"
