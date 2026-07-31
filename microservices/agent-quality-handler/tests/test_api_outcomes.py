# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src import main
from src.batch_event_subscriber import BatchEvent
from src.utility.output_store import AgentOutputStore
from src.utility.output_store import OutputStoreError


class FakeDelivery:
    def __init__(self):
        self.acknowledged = False

    def acknowledge(self):
        self.acknowledged = True
        return True


@pytest.fixture(autouse=True)
def clear_state(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_output_store", AgentOutputStore(tmp_path))
    main._runs.clear()
    main._pending_deliveries.clear()
    while True:
        try:
            main._reasoning_queue.get_nowait()
            main._reasoning_queue.task_done()
        except main.queue.Empty:
            break
    yield
    main._runs.clear()
    main._pending_deliveries.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


def _result(errors=None):
    return {
        "use_case_id": "case",
        "policy": {"policy": True},
        "analysis": {},
        "evidence": {},
        "ticket": {},
        "errors": errors or [],
        "error": errors[0]["message"] if errors else None,
    }


def _event(**overrides):
    values = {
        "run_id": "detect-7",
        "status": "completed",
        "device": "camera-west",
        "video_filename": "inspection.mp4",
        "start_id": 10,
        "end_id": 20,
        "pipeline_status": "COMPLETED",
        "error": None,
    }
    values.update(overrides)
    return BatchEvent(**values)


def _work(run_id="run-1", min_id=10, max_id=20):
    return main.ReasoningWork(run_id, None, None, min_id, max_id)


def test_manual_run_is_queued_with_bounds(monkeypatch, client):
    queued = []
    monkeypatch.setattr(main._reasoning_queue, "put", queued.append)

    response = client.post(
        "/agents/run",
        json={"min_id": 10, "max_id": 20},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["source"] == "http"
    assert (body["min_id"], body["max_id"]) == (10, 20)
    assert queued[0].run_id == body["run_id"]


def test_manual_run_rejects_invalid_bounds(client):
    response = client.post(
        "/agents/run",
        json={"min_id": 20, "max_id": 20},
    )

    assert response.status_code == 422


def test_completed_batch_enqueues_once_and_defers_ack():
    first = FakeDelivery()
    duplicate = FakeDelivery()

    main._handle_batch_event(_event(), first)
    main._handle_batch_event(_event(), duplicate)

    work = main._reasoning_queue.get_nowait()
    main._reasoning_queue.task_done()
    assert (work.run_id, work.min_id, work.max_id) == ("detect-7", 10, 20)
    with pytest.raises(main.queue.Empty):
        main._reasoning_queue.get_nowait()
    assert main._runs["detect-7"]["status"] == "queued"
    assert not first.acknowledged
    assert not duplicate.acknowledged


def test_upstream_error_is_terminal_and_skips_reasoning():
    delivery = FakeDelivery()

    main._handle_batch_event(
        _event(
            status="error",
            pipeline_status="ABORTED",
            error="decoder failed",
            start_id=10,
            end_id=10,
        ),
        delivery,
    )

    assert main._runs["detect-7"]["status"] == "error"
    assert main._runs["detect-7"]["result"]["errors"][0]["agent"] == "detection"
    assert delivery.acknowledged
    with pytest.raises(main.queue.Empty):
        main._reasoning_queue.get_nowait()


def test_reasoning_uses_bounds_and_acknowledges_all_duplicates(monkeypatch):
    calls = []
    first = FakeDelivery()
    duplicate = FakeDelivery()
    monkeypatch.setattr(
        main,
        "run_pipeline",
        lambda **kwargs: calls.append(kwargs) or _result(),
    )
    main._handle_batch_event(_event(), first)
    main._handle_batch_event(_event(), duplicate)
    work = main._reasoning_queue.get_nowait()
    main._reasoning_queue.task_done()

    main._execute_reasoning_run(work)

    assert calls[0]["min_id"] == 10
    assert calls[0]["max_id"] == 20
    assert main._runs["detect-7"]["status"] == "completed"
    assert first.acknowledged and duplicate.acknowledged


def test_fifo_queue_preserves_mqtt_and_http_arrival_order(monkeypatch, client):
    queued = []
    monkeypatch.setattr(main._reasoning_queue, "put", queued.append)

    main._handle_batch_event(_event(run_id="mqtt-first"), FakeDelivery())
    response = client.post("/agents/run", json={})
    main._handle_batch_event(_event(run_id="mqtt-third"), FakeDelivery())

    assert [work.run_id for work in queued] == [
        "mqtt-first",
        response.json()["run_id"],
        "mqtt-third",
    ]


def test_graph_failure_and_exception_become_terminal_errors(monkeypatch):
    errors = [{
        "agent": "analysis",
        "status": "failed",
        "type": "RuntimeError",
        "message": "failed",
    }]
    main._create_run("graph-error", source="http")
    monkeypatch.setattr(main, "run_pipeline", lambda **kwargs: _result(errors))
    main._execute_reasoning_run(_work("graph-error", None, None))
    assert main._runs["graph-error"]["status"] == "error"

    main._create_run("exception", source="http")
    monkeypatch.setattr(
        main,
        "run_pipeline",
        lambda **kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    main._execute_reasoning_run(_work("exception", None, None))
    assert main._runs["exception"]["result"]["errors"][0]["type"] == "OSError"


def test_reasoning_lock_is_released_after_serialization_failure(monkeypatch):
    bad = _result()
    bad["analysis"] = {"score": math.nan}
    results = iter([bad, _result()])
    monkeypatch.setattr(main, "run_pipeline", lambda **kwargs: next(results))
    main._create_run("bad", source="http")
    main._create_run("good", source="http")

    main._execute_reasoning_run(_work("bad", None, None))
    main._execute_reasoning_run(_work("good", None, None))

    assert main._runs["bad"]["status"] == "error"
    assert main._runs["good"]["status"] == "completed"
    assert main._reasoning_lock.acquire(blocking=False)
    main._reasoning_lock.release()


def test_reasoning_lock_prevents_concurrent_graph_execution(monkeypatch):
    active = 0
    maximum_active = 0
    counter_lock = threading.Lock()

    def run(**kwargs):
        nonlocal active, maximum_active
        with counter_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with counter_lock:
            active -= 1
        return _result()

    monkeypatch.setattr(main, "run_pipeline", run)
    main._create_run("first", source="http")
    main._create_run("second", source="http")
    threads = [
        threading.Thread(
            target=main._execute_reasoning_run,
            args=(_work(run_id, None, None),),
        )
        for run_id in ("first", "second")
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert maximum_active == 1
    assert main._runs["first"]["status"] == "completed"
    assert main._runs["second"]["status"] == "completed"


def test_status_results_and_metrics_include_queue_state(client):
    main._create_run("queued", source="http", min_id=1, max_id=2)
    main._create_run("running", source="http")
    main._runs["running"]["status"] = "running"
    main._create_run("done", source="mqtt", min_id=2, max_id=3)
    main._store_result("done", "completed", _result())

    assert client.get("/agents/status/queued").json()["status"] == "queued"
    assert client.get("/agents/results/queued").status_code == 202
    result = client.get("/agents/results/done").json()
    assert result["source"] == "mqtt"
    assert (result["min_id"], result["max_id"]) == (2, 3)
    metrics = client.get("/metrics").text
    assert "aqh_agent_runs_queued 1" in metrics
    assert "aqh_agent_runs_running 1" in metrics
    assert "aqh_agent_runs_completed 1" in metrics


def test_agent_output_endpoints_query_persisted_run(client):
    main._create_run(
        "persisted",
        source="mqtt",
        min_id=10,
        max_id=20,
        metadata={"device": "camera-west"},
    )
    main._store_result("persisted", "completed", _result())

    response = client.get("/agents/outputs/policy")
    assert response.status_code == 200
    assert set(response.json()["runs"]) == {"persisted"}

    record = client.get("/agents/outputs/policy/persisted").json()
    assert record["run_id"] == "persisted"
    assert record["output"] == {"policy": True}
    assert record["batch_metadata"] == {"device": "camera-west"}
    assert client.get("/agents/outputs/unknown").status_code == 404
    assert client.get("/agents/outputs/policy/missing").status_code == 404


def test_output_persistence_failure_is_an_explicit_terminal_error(monkeypatch):
    main._create_run("output-failure", source="http")

    class FailingStore:
        def record_run(self, *args, **kwargs):
            raise OutputStoreError("volume is read-only")

        def prune(self, *args, **kwargs):
            return set()

    monkeypatch.setattr(main, "_output_store", FailingStore())
    monkeypatch.setattr(main, "run_pipeline", lambda **kwargs: _result())

    main._execute_reasoning_run(_work("output-failure", None, None))

    run = main._runs["output-failure"]
    assert run["status"] == "error"
    assert run["result"]["errors"][0]["type"] == "OutputStoreError"


def test_cleanup_preserves_nonterminal_and_pending_delivery(monkeypatch):
    monkeypatch.setattr(main, "_RUN_RETENTION_SECONDS", 0)
    main._create_run("queued", source="http")
    main._create_run("pending-ack", source="mqtt")
    main._pending_deliveries["pending-ack"] = [FakeDelivery()]
    main._store_result("pending-ack", "completed", _result())

    main._cleanup_runs(now=float("inf"))

    assert set(main._runs) == {"queued", "pending-ack"}


@pytest.mark.asyncio
async def test_lifespan_starts_worker_and_batch_subscriber(monkeypatch):
    calls = []
    settings = SimpleNamespace(mqtt_enabled=True)
    worker = SimpleNamespace()
    mqtt_client = SimpleNamespace(disconnect=lambda: calls.append("disconnect"))
    monkeypatch.setattr(main, "load_runtime_settings", lambda: settings)
    monkeypatch.setattr(main, "_start_reasoning_worker", lambda: calls.append(worker))
    monkeypatch.setattr(main, "_stop_reasoning_worker", lambda: calls.append("stop"))
    monkeypatch.setattr(
        main, "set_on_batch_callback", lambda callback: calls.append(callback)
    )
    monkeypatch.setattr(
        main, "start_subscriber", lambda configured: calls.append(configured) or mqtt_client
    )

    async with main.lifespan(main.app):
        pass

    assert calls == [
        worker,
        main._handle_batch_event,
        settings,
        "disconnect",
        None,
        "stop",
    ]
