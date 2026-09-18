# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the MCP server tools and resources."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _patch_core_init(monkeypatch):
    """Prevent real plugin discovery and ModelManager creation on import."""
    mock_registry = MagicMock()
    mock_registry.plugins = {"downloader": {}, "converter": {}}
    mock_registry.activated_plugins = ["all"]
    mock_registry.hub_is_available.return_value = (True, "")
    mock_registry.get_plugin.return_value = None
    mock_registry.find_plugin_for_model.return_value = None
    mock_registry.get_plugin_names.return_value = []
    mock_registry.supported_hubs.return_value = []

    mock_manager = MagicMock()
    mock_manager._jobs = {}
    mock_manager.default_dir = "/opt/models"
    mock_manager.get_job_status.side_effect = lambda job_id: (
        dict(mock_manager._jobs[job_id])
        if job_id in mock_manager._jobs
        else None
    )
    mock_manager.list_jobs.side_effect = lambda **_kwargs: [
        dict(job) for job in mock_manager._jobs.values()
    ]

    # Patch at module level before import
    with (
        patch("src.mcp.server.plugin_registry", mock_registry),
        patch("src.mcp.server.model_manager", mock_manager),
        patch("src.mcp.server.models_dir", "/opt/models"),
    ):
        yield {"registry": mock_registry, "manager": mock_manager}


@pytest.fixture
def mocks(_patch_core_init):
    return _patch_core_init


class TestHealthCheck:
    def test_health_check(self, mocks):
        from src.mcp.server import health_check

        result = health_check()
        assert result == {"status": "ok"}


class TestGetJobStatus:
    def test_existing_job(self, mocks):
        from src.mcp.server import get_job_status

        mocks["manager"]._jobs["abc-123"] = {
            "id": "abc-123",
            "status": "completed",
            "model_name": "test-model",
        }
        result = get_job_status("abc-123")
        assert result["status"] == "completed"
        assert result["model_name"] == "test-model"

    def test_missing_job(self, mocks):
        from src.mcp.server import get_job_status

        result = get_job_status("nonexistent")
        assert "error" in result


class TestListJobs:
    def test_empty(self, mocks):
        from src.mcp.server import list_jobs

        mocks["manager"]._jobs = {}
        result = list_jobs()
        assert result == {"jobs": []}

    def test_with_jobs(self, mocks):
        from src.mcp.server import list_jobs

        mocks["manager"]._jobs = {"j1": {"id": "j1", "status": "queued"}}
        result = list_jobs()
        assert len(result["jobs"]) == 1


class TestCancelJob:
    def test_cancel_running(self, mocks):
        from src.mcp.server import cancel_job

        mocks["manager"]._jobs["j1"] = {"id": "j1", "status": "downloading"}
        mocks["manager"].cancel_job.return_value = True
        result = cancel_job("j1")
        assert result["status"] == "canceled"

    def test_cancel_completed(self, mocks):
        from src.mcp.server import cancel_job

        mocks["manager"]._jobs["j1"] = {"id": "j1", "status": "completed"}
        result = cancel_job("j1")
        assert "error" in result

    def test_cancel_missing(self, mocks):
        from src.mcp.server import cancel_job

        result = cancel_job("nope")
        assert "error" in result


class TestGetModelJobs:
    def test_found(self, mocks):
        from src.mcp.server import get_model_jobs

        mocks["manager"]._jobs = {
            "j1": {"id": "j1", "model_name": "llama"},
            "j2": {"id": "j2", "model_name": "other"},
        }
        result = get_model_jobs("llama")
        assert len(result["jobs"]) == 1

    def test_not_found(self, mocks):
        from src.mcp.server import get_model_jobs

        mocks["manager"]._jobs = {}
        result = get_model_jobs("missing")
        assert "error" in result


class TestGetModelResults:
    def test_completed_jobs(self, mocks):
        from src.mcp.server import get_model_results

        mocks["manager"]._jobs = {
            "j1": {
                "id": "j1",
                "status": "completed",
                "model_name": "m1",
                "hub": "huggingface",
                "operation_type": "download",
                "output_dir": "/opt/models/m1",
                "completion_time": "2026-01-01T00:00:00",
            },
            "j2": {"id": "j2", "status": "downloading", "model_name": "m2"},
        }
        result = get_model_results()
        assert len(result["results"]) == 1
        assert result["results"][0]["is_ovms"] is False


class TestListPlugins:
    def test_returns_dict(self, mocks):
        from src.mcp.server import list_plugins

        result = list_plugins()
        assert "available_plugins" in result
        assert "total_count" in result


class TestDownloadModel:
    @pytest.mark.asyncio
    async def test_success(self, mocks):
        from src.mcp.server import download_model

        with patch("src.mcp.server.submit_models", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = ["job-1"]
            result = await download_model(name="test/model", hub="huggingface")
            assert result["status"] == "processing"
            assert result["job_ids"] == ["job-1"]

    @pytest.mark.asyncio
    async def test_submission_error(self, mocks):
        from src.mcp.server import download_model

        with patch("src.mcp.server.submit_models", new_callable=AsyncMock) as mock_submit:
            mock_submit.side_effect = Exception("boom")
            result = await download_model(name="bad/model", hub="huggingface")
            assert result["status"] == "failed"
            assert "boom" in result["error"]


class TestListHubModels:
    @pytest.mark.asyncio
    async def test_invalid_limit(self, mocks):
        from src.mcp.server import list_hub_models

        result = await list_hub_models(hub="huggingface", limit=0)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_no_plugin(self, mocks):
        from src.mcp.server import list_hub_models

        mocks["registry"].get_plugin.return_value = None
        mocks["registry"].find_plugin_for_model.return_value = None
        result = await list_hub_models(hub="unknown")
        assert "error" in result


class TestResources:
    def test_resource_jobs(self, mocks):
        from src.mcp.server import resource_jobs

        mocks["manager"]._jobs = {"j1": {"id": "j1", "status": "queued"}}
        data = json.loads(resource_jobs())
        assert len(data["jobs"]) == 1

    def test_resource_job_found(self, mocks):
        from src.mcp.server import resource_job

        mocks["manager"]._jobs = {"j1": {"id": "j1", "status": "queued"}}
        data = json.loads(resource_job("j1"))
        assert data["id"] == "j1"

    def test_resource_job_not_found(self, mocks):
        from src.mcp.server import resource_job

        mocks["manager"]._jobs = {}
        data = json.loads(resource_job("nope"))
        assert "error" in data

    def test_resource_results(self, mocks):
        from src.mcp.server import resource_results

        mocks["manager"]._jobs = {
            "j1": {
                "status": "completed",
                "model_name": "m",
                "hub": "hf",
                "output_dir": "/x",
                "completion_time": "t",
            }
        }
        data = json.loads(resource_results())
        assert len(data["results"]) == 1

    def test_resource_plugins(self, mocks):
        from src.mcp.server import resource_plugins

        data = json.loads(resource_plugins())
        assert "available_plugins" in data


class TestPromptLoading:
    @pytest.mark.asyncio
    async def test_register_skill_prompts_with_files(self, mocks, tmp_path):
        """Prompts are registered when skill example files exist."""
        from fastmcp import FastMCP
        from src.mcp.prompts import register_skill_prompts

        # Create a fake skill directory with example prompts
        examples_dir = tmp_path / "examples-prompts"
        examples_dir.mkdir()
        (examples_dir / "huggingface.md").write_text(
            "<!-- license -->\n"
            "Download a HuggingFace model.\n"
            "<!--\nInternal implementation note.\n-->\n"
            "- Step one\n"
            "- Step two\n"
        )
        (examples_dir / "ollama.md").write_text(
            "Pull llama3.2:3b through the API.\n"
        )
        # Create SKILL.md with hub table
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "# Skill\n\n"
            "## Supported Hubs at a Glance\n\n"
            "| Hub | Value |\n|---|---|\n| HF | huggingface |\n\n"
            "## Next Section\n"
        )

        test_mcp = FastMCP("test")
        with patch("src.mcp.prompts._SKILL_DIR", tmp_path), \
             patch("src.mcp.prompts._EXAMPLES_DIR", examples_dir), \
             patch("src.mcp.prompts._SKILL_FILE", skill_md):
            count = register_skill_prompts(test_mcp)

        # 2 example prompts + 1 hub_guide = 3
        assert count == 3
        prompt = await test_mcp.get_prompt("huggingface")
        rendered = await prompt.render()
        text = rendered.messages[0].content.text
        assert "<!--" not in text
        assert "license" not in text
        assert "Internal implementation note." not in text
        assert "Download a HuggingFace model." in text

    def test_register_skill_prompts_no_dir(self, mocks, tmp_path):
        """Gracefully handles missing skill directory."""
        from fastmcp import FastMCP
        from src.mcp.prompts import register_skill_prompts

        test_mcp = FastMCP("test")
        missing = tmp_path / "nonexistent"
        with patch("src.mcp.prompts._SKILL_DIR", missing), \
             patch("src.mcp.prompts._EXAMPLES_DIR", missing / "examples-prompts"), \
             patch("src.mcp.prompts._SKILL_FILE", missing / "SKILL.md"):
            count = register_skill_prompts(test_mcp)

        assert count == 0
