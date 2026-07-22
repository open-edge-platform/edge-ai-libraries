# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from src.utility.output_store import (
    AGENT_RESULT_KEYS,
    AgentOutputStore,
    OutputStoreError,
)


def _result(label):
    return {
        "policy": {"recommendation": label},
        "analysis": {"summary": label},
        "evidence": {"records": [label]},
        "ticket": {"title": label},
        "errors": [],
    }


def test_store_creates_one_multi_run_file_per_agent(tmp_path):
    store = AgentOutputStore(tmp_path)

    store.record_run(
        "run-1",
        status="completed",
        result=_result("first"),
        source="mqtt",
        min_id=10,
        max_id=20,
        metadata={"device": "camera-west"},
        completed_at=100,
    )
    store.record_run(
        "run-2",
        status="completed",
        result=_result("second"),
        source="http",
        min_id=None,
        max_id=None,
        metadata={},
        completed_at=200,
    )

    for agent, (result_key, _) in AGENT_RESULT_KEYS.items():
        path = tmp_path / f"{agent}.json"
        document = json.loads(path.read_text())
        assert set(document["runs"]) == {"run-1", "run-2"}
        assert document["runs"]["run-1"]["output"] == _result("first")[result_key]
        assert document["runs"]["run-1"]["batch_metadata"] == {
            "device": "camera-west"
        }


def test_store_replaces_duplicate_run_id_idempotently(tmp_path):
    store = AgentOutputStore(tmp_path)
    values = {
        "status": "completed",
        "source": "http",
        "min_id": None,
        "max_id": None,
        "metadata": {},
    }

    store.record_run("run-1", result=_result("old"), completed_at=100, **values)
    store.record_run("run-1", result=_result("new"), completed_at=200, **values)

    policy = store.get_agent("policy")
    assert list(policy["runs"]) == ["run-1"]
    assert policy["runs"]["run-1"]["output"] == {"recommendation": "new"}


def test_store_retains_agent_specific_errors(tmp_path):
    store = AgentOutputStore(tmp_path)
    result = _result("partial")
    result["errors"] = [
        {"agent": "analysis", "status": "failed", "message": "unavailable"},
        {"agent": "ticketing", "status": "skipped", "message": "dependency"},
    ]

    store.record_run(
        "run-1",
        status="error",
        result=result,
        source="mqtt",
        min_id=1,
        max_id=2,
        metadata={},
    )

    assert store.get_run("analysis", "run-1")["errors"][0]["status"] == "failed"
    assert store.get_run("ticket", "run-1")["errors"][0]["status"] == "skipped"
    assert store.get_run("policy", "run-1")["errors"] == []
    assert len(store.get_run("policy", "run-1")["run_errors"]) == 2


def test_prune_applies_age_and_count_to_every_agent(tmp_path, monkeypatch):
    store = AgentOutputStore(tmp_path)
    values = {
        "status": "completed",
        "result": _result("value"),
        "source": "http",
        "min_id": None,
        "max_id": None,
        "metadata": {},
    }
    store.record_run("expired", completed_at=100, **values)
    store.record_run("older", completed_at=180, **values)
    store.record_run("newer", completed_at=190, **values)
    monkeypatch.setattr("src.utility.output_store.time.time", lambda: 200)

    removed = store.prune(retention_seconds=50, max_runs=1)

    assert removed == {"expired", "older"}
    for agent in AGENT_RESULT_KEYS:
        assert set(store.get_agent(agent)["runs"]) == {"newer"}


def test_invalid_existing_file_is_reported(tmp_path):
    (tmp_path / "policy.json").write_text("{not json")
    store = AgentOutputStore(tmp_path)

    with pytest.raises(OutputStoreError, match="Cannot read"):
        store.ensure_files()


def test_unknown_agent_is_rejected_without_path_access(tmp_path):
    store = AgentOutputStore(tmp_path)

    with pytest.raises(ValueError, match="Unknown agent"):
        store.get_agent("../secret")
