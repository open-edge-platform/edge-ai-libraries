# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""API tests for the dynamic prompt-task registry (/v1/tasks).

These exercise the migrated prompt-factory feature:
- exactly two built-in tasks (`summary`, `summary_zh`);
- registering the consolidated fridge task as a *dynamic* task (full mode);
- round-trip, conflict, immutability and rename semantics;
- autogen mode with a mocked service LLM;
- feeding a registered dynamic task into /v1/summary.

The registry singleton is isolated to a per-test tmp cache dir so nothing
touches the user's real ~/.cache/.multilevel-video-understanding/tasks/.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import video_analyzer.prompts.prompt_registry as registry_mod
from video_analyzer.core.settings import settings

# The consolidated fridge task content lives next to the tests as a fixture.
FRIDGE_CONTENT = (Path(__file__).resolve().parent.parent / "fixtures" / "refrigerator_monitor_en.py").read_text(encoding="utf-8")
FRIDGE_TASK = "refrigerator_monitor_en"


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    """Point the registry singleton at a throwaway cache dir for this test."""
    monkeypatch.setattr(settings, "VIDEO_SUMMARY_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(registry_mod, "_registry", None)
    # First access builds a fresh registry backed by tmp_path.
    return registry_mod.get_registry()


# ---------------------------------------------------------------- list / builtins
@pytest.mark.api
def test_builtins_are_exactly_summary_and_summary_zh(isolated_registry, test_client: TestClient):
    resp = test_client.get("/v1/tasks")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    builtins = sorted(t["name"] for t in tasks if t["source"] == "builtin")
    assert builtins == ["summary", "summary_zh"]
    # Fresh registry → no dynamic tasks yet.
    assert [t for t in tasks if t["source"] == "dynamic"] == []


@pytest.mark.api
def test_get_builtin_task_detail_roundtrips_anchors(isolated_registry, test_client: TestClient):
    for name in ("summary", "summary_zh"):
        resp = test_client.get(f"/v1/tasks/{name}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source"] == "builtin"
        for anchor in ("GLOBAL_PROMPT", "MACRO_CHUNK_PROMPT", "LOCAL_PROMPT", "T_MINUS_1_PROMPT"):
            assert anchor in body["content"]


# ---------------------------------------------------------------- register (full)
@pytest.mark.api
def test_register_fridge_full_mode(isolated_registry, test_client: TestClient):
    resp = test_client.post(
        "/v1/tasks",
        json={"task_name": FRIDGE_TASK, "mode": "full", "content": {"text": FRIDGE_CONTENT}},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == FRIDGE_TASK
    assert body["source"] == "dynamic"
    # LOCAL is the fridge video-summary; GLOBAL is the daily report.
    assert "refrigerator monitoring camera" in body["content"]
    assert "Refrigerator Activity Summary" in body["content"]

    # Now it shows up as dynamic in the listing, builtins unchanged.
    listing = test_client.get("/v1/tasks").json()["tasks"]
    assert any(t["name"] == FRIDGE_TASK and t["source"] == "dynamic" for t in listing)
    assert sorted(t["name"] for t in listing if t["source"] == "builtin") == ["summary", "summary_zh"]

    # Persisted to the isolated cache dir.
    cache_file = Path(settings.VIDEO_SUMMARY_CACHE) / "tasks" / f"{FRIDGE_TASK}.json"
    assert cache_file.exists()


@pytest.mark.api
def test_register_rejects_builtin_name_conflict(isolated_registry, test_client: TestClient):
    resp = test_client.post(
        "/v1/tasks",
        json={"task_name": "summary", "mode": "full", "content": {"text": FRIDGE_CONTENT}},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "builtin_conflict"


@pytest.mark.api
def test_register_duplicate_dynamic_conflict(isolated_registry, test_client: TestClient):
    payload = {"task_name": FRIDGE_TASK, "mode": "full", "content": {"text": FRIDGE_CONTENT}}
    assert test_client.post("/v1/tasks", json=payload).status_code == 201
    resp = test_client.post("/v1/tasks", json=payload)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "already_registered"


# ---------------------------------------------------------------- delete / immutable
@pytest.mark.api
def test_delete_builtin_forbidden(isolated_registry, test_client: TestClient):
    resp = test_client.delete("/v1/tasks/summary")
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "builtin_immutable"


@pytest.mark.api
def test_delete_dynamic_task(isolated_registry, test_client: TestClient):
    test_client.post(
        "/v1/tasks",
        json={"task_name": FRIDGE_TASK, "mode": "full", "content": {"text": FRIDGE_CONTENT}},
    )
    assert test_client.delete(f"/v1/tasks/{FRIDGE_TASK}").status_code == 204
    assert test_client.get(f"/v1/tasks/{FRIDGE_TASK}").status_code == 404


# ---------------------------------------------------------------- patch / rename
@pytest.mark.api
def test_rename_dynamic_task(isolated_registry, test_client: TestClient):
    test_client.post(
        "/v1/tasks",
        json={"task_name": FRIDGE_TASK, "mode": "full", "content": {"text": FRIDGE_CONTENT}},
    )
    resp = test_client.patch(f"/v1/tasks/{FRIDGE_TASK}", json={"new_task_name": "fridge_en"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "fridge_en"
    assert test_client.get(f"/v1/tasks/{FRIDGE_TASK}").status_code == 404
    assert test_client.get("/v1/tasks/fridge_en").status_code == 200


# ---------------------------------------------------------------- autogen (mocked LLM)
@pytest.mark.api
def test_register_autogen_mode(isolated_registry, test_client: TestClient):
    generated = {
        "global": "Summarize the scene. {question}\n",
        "macro": "Summarize from {st_tm} to {end_tm}.\n",
        "local": "Describe from {st_tm} to {end_tm}.\n",
        "t_minus": "Previous {dur}s [{st_tm}-{end_tm}]: {past_summary}\n",
    }
    with patch("video_analyzer.api.endpoints.tasks.LLM", MagicMock()), \
         patch("video_analyzer.api.endpoints.tasks.generate_prompt_set",
               AsyncMock(return_value=generated)):
        resp = test_client.post(
            "/v1/tasks",
            json={"task_name": "my_scene", "mode": "autogen",
                  "description": "generic scene monitor"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "my_scene"
    assert body["source"] == "dynamic"
    assert "Summarize the scene" in body["content"]


# ---------------------------------------------------------------- /v1/summary uses dynamic task
@pytest.mark.api
def test_summary_accepts_registered_dynamic_task(isolated_registry, test_client: TestClient):
    # Register the fridge task, then run a caption-only summary against it.
    test_client.post(
        "/v1/tasks",
        json={"task_name": FRIDGE_TASK, "mode": "full", "content": {"text": FRIDGE_CONTENT}},
    )

    summarizer_instance = MagicMock()
    summarizer_instance.summarize = AsyncMock(
        return_value=("job-fridge", {"summary": "Fridge daily report", "video_duration": 0.0})
    )
    with patch("video_analyzer.api.endpoints.summarization.VideoSummarizer",
               return_value=summarizer_instance) as mock_vs:
        resp = test_client.post(
            "/v1/summary",
            json={
                "video": "none",
                "video_subtitles": {"text": "1\n00:00:00,000 --> 00:00:05,000\n[motion] fridge opened\n"},
                "task": FRIDGE_TASK,
                "method": "SIMPLE",
            },
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["summary"] == "Fridge daily report"
    kwargs = mock_vs.call_args.kwargs
    assert kwargs["task"] == FRIDGE_TASK
    assert kwargs["video_path"] == "none"          # caption-only
    assert kwargs["video_subtitles"] is not None
