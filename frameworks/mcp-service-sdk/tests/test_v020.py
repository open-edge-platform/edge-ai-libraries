"""Tests for v0.2.0 features: file log, façade config, timeout, null metrics."""

from __future__ import annotations

import time

import pytest

from mcp_service_base import (
    GateLevel,
    JSONLFileLog,
    NullTelemetry,
    ServiceConfig,
    ServiceServer,
)
from mcp_service_base.envelope import new_event


def test_jsonl_file_log_roundtrip_and_idempotency(tmp_path):
    log = JSONLFileLog(path=str(tmp_path / "events.jsonl"), service="t")
    e = new_event("x", "t", "s1", {"v": 1}, ref_id="r1")
    assert log.append(e) == 1
    assert log.append(e) == 1  # idempotent on ref_id
    log.append(new_event("x", "t", "s1", {"v": 2}, ref_id="r2"))
    assert len(log.read(event_type="x")) == 2


def test_jsonl_file_log_restart_safe(tmp_path):
    path = str(tmp_path / "events.jsonl")
    log1 = JSONLFileLog(path=path, service="t")
    log1.append(new_event("x", "t", "s1", {"v": 1}, ref_id="r1"))
    # Reopen: state (seq + seen) is rebuilt from the file.
    log2 = JSONLFileLog(path=path, service="t")
    assert log2.append(new_event("x", "t", "s1", {"v": 9}, ref_id="r1")) == 1
    assert log2.append(new_event("x", "t", "s1", {"v": 2}, ref_id="r2")) == 2


def test_from_config_jsonl_backend(tmp_path):
    cfg = ServiceConfig(
        service="svc",
        store_id="store_001",
        log_backend="jsonl",
        log_path=str(tmp_path / "e.jsonl"),
    )
    svc = ServiceServer.from_config(cfg)
    assert isinstance(svc.log, JSONLFileLog)
    svc.emit("x", {"a": 1}, ref_id="r1")
    assert len(svc.log.read(event_type="x")) == 1


def test_from_config_null_metrics():
    cfg = ServiceConfig(service="svc", store_id="s", metrics="null")
    svc = ServiceServer.from_config(cfg)
    assert isinstance(svc.telemetry, NullTelemetry)
    svc.emit("x", {"a": 1})
    assert svc.telemetry.drain() == []


def test_tool_timeout_triggers():
    svc = ServiceServer(service="svc", store_id="s", tool_timeout_s=0.05)

    @svc.act_tool("slow", level=GateLevel.AUTOMATIC)
    def slow() -> dict:
        time.sleep(0.5)
        return {"done": True}

    with pytest.raises(TimeoutError):
        svc.call_action("slow")


def test_no_timeout_by_default():
    svc = ServiceServer(service="svc", store_id="s")

    @svc.act_tool("quick", level=GateLevel.AUTOMATIC)
    def quick() -> dict:
        return {"done": True}

    assert svc.call_action("quick")["executed"] is True
