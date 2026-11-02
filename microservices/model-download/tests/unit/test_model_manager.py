# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock
import json

import pytest

from src.core.model_manager import ModelManager


@pytest.mark.asyncio
async def test_process_download_refreshes_credentials_for_each_request(tmp_path):
    registry = MagicMock()
    download_plugin = MagicMock()
    download_plugin.plugin_name = "huggingface"
    download_plugin.resolve_config.side_effect = lambda overrides, hub=None: overrides.copy()
    download_plugin.download = AsyncMock(return_value={"success": True})
    registry.get_plugin.return_value = download_plugin

    manager = ModelManager(registry, default_dir=str(tmp_path))
    for index, token in enumerate(("first-token", "second-token"), start=1):
        job_id = manager.register_job(
            "download",
            "org/model",
            "huggingface",
            str(tmp_path),
            "huggingface",
        )
        result = await manager.process_download(
            job_id=job_id,
            model_name="org/model",
            hub="huggingface",
            output_dir=str(tmp_path),
            downloader="huggingface",
            parallel_downloads=False,
            override_credentials={"HF_TOKEN": token},
        )
        assert result["status"] == "completed", index

    assert [call.args[0] for call in download_plugin.resolve_config.call_args_list] == [
        {"HF_TOKEN": "first-token"},
        {"HF_TOKEN": "second-token"},
    ]
    assert [
        call.kwargs["resolved_config"]
        for call in download_plugin.download.call_args_list
    ] == [
        {"HF_TOKEN": "first-token"},
        {"HF_TOKEN": "second-token"},
    ]


@pytest.mark.asyncio
async def test_process_conversion_keeps_explicit_converter_for_huggingface_source(tmp_path):
    registry = MagicMock()
    converter_plugin = MagicMock()
    converter_plugin.plugin_name = "openvino"
    converter_plugin.convert.return_value = {"success": True, "source": "openvino"}

    registry.get_plugin.return_value = converter_plugin
    registry.find_plugin_for_model.return_value = None

    manager = ModelManager(registry, default_dir=str(tmp_path))
    output_dir = tmp_path / "converted"
    job_id = manager.register_job(
        "convert",
        "meta-llama/Llama-3.2-1B",
        "openvino",
        str(output_dir),
        "openvino",
        "llm",
    )

    result = await manager.process_conversion(
        job_id=job_id,
        model_path="llm-converted",
        model_name="meta-llama/Llama-3.2-1B",
        hub="openvino",
        hf_token="test-token",
        output_dir=str(output_dir),
        converter="openvino",
        precision="int4",
        device="CPU",
        cache_size=4,
    )

    assert result["status"] == "completed"
    assert manager.get_job_status(job_id)["status"] == "completed"
    registry.get_plugin.assert_called_once_with("converter", "openvino")
    registry.find_plugin_for_model.assert_not_called()
    converter_plugin.convert.assert_called_once()


@pytest.mark.asyncio
async def test_process_conversion_auto_detects_converter_for_huggingface_source(tmp_path):
    registry = MagicMock()
    converter_plugin = MagicMock()
    converter_plugin.plugin_name = "openvino"
    converter_plugin.convert.return_value = {"success": True, "source": "openvino"}

    registry.find_plugin_for_model.return_value = converter_plugin

    manager = ModelManager(registry, default_dir=str(tmp_path))
    output_dir = tmp_path / "converted"
    job_id = manager.register_job(
        "convert",
        "sentence-transformers/all-MiniLM-L6-v2",
        "openvino",
        str(output_dir),
        None,
        "embeddings",
    )

    result = await manager.process_conversion(
        job_id=job_id,
        model_path="embedding-models",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        hub="openvino",
        hf_token="test-token",
        output_dir=str(output_dir),
        converter=None,
        precision="int8",
        device="CPU",
    )

    assert result["status"] == "completed"
    call_kwargs = registry.find_plugin_for_model.call_args[1]
    assert call_kwargs["hub"] == "openvino"
    assert call_kwargs["model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert call_kwargs["is_ovms"] is True
    assert call_kwargs["precision"] == "int8"
    assert call_kwargs["device"] == "CPU"


def test_cancel_job_downloading(tmp_path):
    """Cancel a job that is currently downloading."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("download", "test-model", "huggingface", str(tmp_path))
    manager._jobs[job_id]["status"] = "downloading"

    assert manager.cancel_job(job_id) is True
    assert manager._jobs[job_id]["status"] == "canceled"
    assert "completion_time" in manager._jobs[job_id]


def test_cancel_job_queued(tmp_path):
    """Cancel a job that is still queued."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("download", "test-model", "huggingface", str(tmp_path))

    assert manager._jobs[job_id]["status"] == "queued"
    assert manager.cancel_job(job_id) is True
    assert manager._jobs[job_id]["status"] == "canceled"


def test_cancel_job_converting(tmp_path):
    """Cancel a job that is currently converting."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("convert", "test-model", "openvino", str(tmp_path))
    manager._jobs[job_id]["status"] = "converting"

    assert manager.cancel_job(job_id) is True
    assert manager._jobs[job_id]["status"] == "canceled"


def test_cancel_job_completed_returns_false(tmp_path):
    """Cancelling a completed job should return False."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("download", "test-model", "huggingface", str(tmp_path))
    manager._jobs[job_id]["status"] = "completed"

    assert manager.cancel_job(job_id) is False
    assert manager._jobs[job_id]["status"] == "completed"


def test_cancel_job_nonexistent_returns_false(tmp_path):
    """Cancelling a non-existent job should return False."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))

    assert manager.cancel_job("nonexistent-id") is False


def test_cancel_job_shuts_down_executor(tmp_path):
    """Cancel should shut down the executor if one is active."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("download", "test-model", "huggingface", str(tmp_path))
    manager._jobs[job_id]["status"] = "downloading"

    mock_executor = MagicMock()
    manager._executors[job_id] = mock_executor

    assert manager.cancel_job(job_id) is True
    mock_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
    assert job_id not in manager._executors


def test_cancel_job_kills_active_processes(tmp_path):
    """Cancel should terminate and kill registered subprocesses."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("download", "test-model", "ollama", str(tmp_path))
    manager._jobs[job_id]["status"] = "downloading"

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # still running after terminate
    manager._active_processes[job_id] = [mock_proc]
    manager.get_cancel_event(job_id)

    assert manager.cancel_job(job_id) is True
    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()


def test_cancel_event_persists_for_thread_check(tmp_path):
    """Cancel event must remain accessible after cancel_job returns."""
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("download", "test-model", "huggingface", str(tmp_path))
    manager._jobs[job_id]["status"] = "downloading"
    manager.get_cancel_event(job_id)

    manager.cancel_job(job_id)
    # The background thread needs to check this after cancel_job returns
    assert manager.is_job_cancelled(job_id) is True


@pytest.mark.asyncio
async def test_process_download_returns_canceled_when_subprocess_killed(tmp_path):
    """When a subprocess is killed by cancel_job, process_download returns canceled."""
    registry = MagicMock()
    download_plugin = MagicMock()
    download_plugin.plugin_name = "ollama"
    download_plugin.resolve_config.return_value = {}
    download_plugin.get_download_tasks.side_effect = NotImplementedError
    download_plugin.download = MagicMock(side_effect=RuntimeError("process killed"))
    registry.get_plugin.return_value = download_plugin

    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("download", "llama2", "ollama", str(tmp_path))
    # Simulate cancel_job having been called (set event, mark status)
    manager.get_cancel_event(job_id).set()
    manager._jobs[job_id]["status"] = "canceled"

    result = await manager.process_download(
        job_id=job_id,
        model_name="llama2",
        hub="ollama",
        output_dir=str(tmp_path),
        downloader="ollama",
    )
    assert result["status"] == "canceled"


def test_cleanup_prunes_empty_parents_and_removes_empty_config_all(tmp_path):
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("convert", "microsoft/Phi-3.5-mini-instruct", "openvino", str(tmp_path))

    leaf = tmp_path / "openvino_models" / "cpu" / "int8" / "microsoft" / "Phi-3.5-mini-instruct"
    leaf.mkdir(parents=True)
    config_path = tmp_path / "openvino_models" / "cpu" / "int8" / "config_all.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "model_config_list": [
                    {
                        "config": {
                            "name": "microsoft/Phi-3.5-mini-instruct",
                            "base_path": "microsoft/Phi-3.5-mini-instruct",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manager._model_download_dir[job_id] = [str(leaf)]
    manager._cleanup_model_download_dir(job_id)

    assert not leaf.exists()
    assert not config_path.exists()
    assert not (tmp_path / "openvino_models" / "cpu" / "int8").exists()


def test_cleanup_keeps_config_all_for_remaining_models(tmp_path):
    registry = MagicMock()
    manager = ModelManager(registry, default_dir=str(tmp_path))
    job_id = manager.register_job("convert", "microsoft/Phi-3.5-mini-instruct", "openvino", str(tmp_path))

    parent = tmp_path / "openvino_models" / "cpu" / "int8" / "microsoft"
    removed_leaf = parent / "Phi-3.5-mini-instruct"
    kept_leaf = parent / "Phi-4-mini"
    removed_leaf.mkdir(parents=True)
    kept_leaf.mkdir(parents=True)

    config_path = tmp_path / "openvino_models" / "cpu" / "int8" / "config_all.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "model_config_list": [
                    {
                        "config": {
                            "name": "microsoft/Phi-3.5-mini-instruct",
                            "base_path": "microsoft/Phi-3.5-mini-instruct",
                        }
                    },
                    {
                        "config": {
                            "name": "microsoft/Phi-4-mini",
                            "base_path": "microsoft/Phi-4-mini",
                        }
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    manager._model_download_dir[job_id] = [str(removed_leaf)]
    manager._cleanup_model_download_dir(job_id)

    assert not removed_leaf.exists()
    assert kept_leaf.exists()
    assert config_path.exists()

    data = json.loads(config_path.read_text(encoding="utf-8"))
    names = [entry["config"]["name"] for entry in data.get("model_config_list", [])]
    assert names == ["microsoft/Phi-4-mini"]
