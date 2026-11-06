# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: tests/test_encoder_runner.py
Description: Unit tests for encoder/runner.py's current multi-client TCP server
architecture: a per-connection frame loop (`_handle_client`) delegating encode
work to `SemanticCodecBridge`, orchestrated by `run_semantic_encoder`.
"""
from concurrent.futures import Future
import logging
import threading
from types import SimpleNamespace

import pytest

from semantic_img_comp.encoder import runner
from semantic_img_comp.utils.logging_helpers import resolve_log_level


class _DummyLogger:
    def debug(self, *args, **kwargs) -> None:
        return None

    def info(self, *args, **kwargs) -> None:
        return None


def _completed_future(result):
    """Build a Future that's already resolved, matching encode_from_jpeg's real contract."""
    future: Future = Future()
    future.set_result(result)
    return future


class _DummySocket:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _SyncThread:
    """Stand-in for threading.Thread that runs the target synchronously, so tests
    can observe `_handle_client` side effects deterministically without races."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        self._target(*self._args, **self._kwargs)


def _make_cfg(tmp_path):
    return SimpleNamespace(
        app=SimpleNamespace(log_level="DEBUG"),
        io=SimpleNamespace(output_dir=tmp_path, print_runtime_logs=True),
        mux_cfg=SimpleNamespace(),
        pipeline_manager=SimpleNamespace(compression_level=1),
    )


def test_resolve_log_level_uses_config_name():
    assert resolve_log_level("debug") == logging.DEBUG
    assert resolve_log_level("INFO") == logging.INFO
    assert resolve_log_level("unknown-level") == logging.INFO


def test_sleep_to_enforce_fps_skips_when_budget_already_exhausted(monkeypatch):
    slept = []
    monkeypatch.setattr(runner.time, "perf_counter", lambda: 10.0)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: slept.append(seconds))

    sleep_ms = runner._sleep_to_enforce_fps(frame_started_at=0.0, fps=1.0)

    assert sleep_ms == 0.0
    assert slept == []


def test_sleep_to_enforce_fps_skips_on_non_finite_input(monkeypatch):
    slept = []
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: slept.append(seconds))

    sleep_ms = runner._sleep_to_enforce_fps(frame_started_at=0.0, fps=float("nan"))

    assert sleep_ms == 0.0
    assert slept == []


def test_run_semantic_encoder_rejects_non_finite_fps(tmp_path):
    cfg = _make_cfg(tmp_path)

    with pytest.raises(ValueError, match="fps must be a finite number"):
        runner.run_semantic_encoder(cfg, fps=float("nan"))


def test_run_semantic_encoder_rejects_invalid_compression_level(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.pipeline_manager.compression_level = 5

    monkeypatch.setattr(runner, "setup_logger", lambda **kwargs: _DummyLogger())

    with pytest.raises(ValueError, match="compression_level must be 1 or 2"):
        runner.run_semantic_encoder(cfg, bridge=SimpleNamespace(encoder=SimpleNamespace()))


def test_run_semantic_encoder_starts_server_and_dispatches_clients(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    events = []
    fake_sock = _DummySocket()
    handshakes = []
    fake_encoder = SimpleNamespace(send_frame=lambda sock, payload: handshakes.append((sock, payload)))
    fake_bridge = SimpleNamespace(encoder=fake_encoder)
    conns = [(SimpleNamespace(id=1), ("1.2.3.4", 111)), (SimpleNamespace(id=2), ("1.2.3.4", 222))]
    dispatched = []

    monkeypatch.setattr(runner, "setup_logger", lambda **kwargs: _DummyLogger())
    monkeypatch.setattr(runner, "log_json", lambda logger, record: events.append(record))
    monkeypatch.setattr(runner, "connect_with_retry", lambda logger, host, port: fake_sock)
    monkeypatch.setattr(runner, "accept_clients", lambda logger, host, port: iter(conns))
    monkeypatch.setattr(runner.threading, "Thread", _SyncThread)
    monkeypatch.setattr(
        runner,
        "_handle_client",
        lambda conn, **kwargs: dispatched.append((conn, kwargs)),
    )
    runner.healthcheck.TCP_READY = False

    runner.run_semantic_encoder(
        cfg,
        decoder_host="decoder",
        decoder_port=5000,
        fps=2.0,
        listen_host="0.0.0.0",
        listen_port=6000,
        bridge=fake_bridge,
    )

    assert fake_sock.closed is True
    assert runner.healthcheck.TCP_READY is True
    assert handshakes == [(fake_sock, b"default")]
    assert len(dispatched) == 2
    for conn, kwargs in dispatched:
        assert kwargs["bridge"] is fake_bridge
        assert kwargs["encoder"] is fake_encoder
        assert kwargs["decoder_sock"] is fake_sock
        assert kwargs["runtime_compression_level"] == 1
        assert kwargs["fps"] == 2.0

    event_names = [event["event"] for event in events]
    assert "encoder_started" in event_names
    assert "socket_closed" in event_names

    start_event = next(event for event in events if event["event"] == "encoder_started")
    assert start_event["listen_host"] == "0.0.0.0"
    assert start_event["listen_port"] == 6000
    assert start_event["fps"] == 2.0


def test_run_semantic_encoder_logs_and_reraises_on_failure(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    events = []
    fake_sock = _DummySocket()

    monkeypatch.setattr(runner, "setup_logger", lambda **kwargs: _DummyLogger())
    monkeypatch.setattr(runner, "log_json", lambda logger, record: events.append(record))
    monkeypatch.setattr(runner, "connect_with_retry", lambda logger, host, port: fake_sock)

    def _raise_accept(logger, host, port):
        raise RuntimeError("boom")
        yield  # pragma: no cover - forces this to be a generator function

    monkeypatch.setattr(runner, "accept_clients", _raise_accept)

    fake_bridge = SimpleNamespace(encoder=SimpleNamespace(send_frame=lambda sock, payload: None))
    with pytest.raises(RuntimeError, match="boom"):
        runner.run_semantic_encoder(cfg, decoder_host="decoder", decoder_port=5000, bridge=fake_bridge)

    assert fake_sock.closed is True
    event_names = [event["event"] for event in events]
    assert "encoder_failed" in event_names
    assert "socket_closed" in event_names


def test_handle_client_forwards_frames_and_logs_events(monkeypatch):
    events = []
    sent = []
    cfg = SimpleNamespace(app=SimpleNamespace(client_id="default"), mux_cfg=SimpleNamespace())
    conn = SimpleNamespace(closed=False)
    conn.close = lambda: setattr(conn, "closed", True)

    frames = iter([b"frame-bytes", None])
    fake_bridge = SimpleNamespace(
        encode_from_jpeg=lambda jpeg_bytes, client_id=None, compression_level=1: _completed_future(
            SimpleNamespace(
                payload=b"wire-payload",
                img_data=SimpleNamespace(img_idx=1),
            )
        )
    )
    fake_encoder = SimpleNamespace(send_frame=lambda sock, payload: sent.append((sock, payload)))
    decoder_sock = object()

    monkeypatch.setattr(runner, "recv_frame", lambda c, mux_cfg: next(frames))
    monkeypatch.setattr(runner, "sync", lambda: None)
    monkeypatch.setattr(runner, "log_json", lambda logger, record: events.append(record))
    monkeypatch.setattr(runner, "_sleep_to_enforce_fps", lambda frame_started_at, fps: 0.0)

    runner._handle_client(
        conn,
        cfg=cfg,
        bridge=fake_bridge,
        encoder=fake_encoder,
        decoder_sock=decoder_sock,
        send_lock=threading.Lock(),
        runtime_compression_level=1,
        fps=0.0,
        logger=_DummyLogger(),
    )

    assert conn.closed is True
    assert sent == [(decoder_sock, b"wire-payload")]

    event_names = [event["event"] for event in events]
    assert event_names == ["image_processed", "client_frame_forwarded", "client_disconnected"]

    processed_event = next(event for event in events if event["event"] == "image_processed")
    assert processed_event["client"] == "default"
    assert processed_event["img_id"] == 1

    disconnect_event = next(event for event in events if event["event"] == "client_disconnected")
    assert disconnect_event["frames_processed"] == 1


def test_handle_client_logs_rate_limit_event(monkeypatch):
    events = []
    cfg = SimpleNamespace(app=SimpleNamespace(client_id="default"), mux_cfg=SimpleNamespace())
    conn = SimpleNamespace(close=lambda: None)
    frames = iter([b"frame", None])

    monkeypatch.setattr(runner, "recv_frame", lambda c, mux_cfg: next(frames))
    monkeypatch.setattr(runner, "sync", lambda: None)
    monkeypatch.setattr(runner, "log_json", lambda logger, record: events.append(record))
    monkeypatch.setattr(runner, "_sleep_to_enforce_fps", lambda frame_started_at, fps: 12.5)

    fake_bridge = SimpleNamespace(
        encode_from_jpeg=lambda jpeg_bytes, client_id=None, compression_level=1: _completed_future(
            SimpleNamespace(
                payload=b"p",
                img_data=SimpleNamespace(img_idx="x"),
            )
        )
    )
    fake_encoder = SimpleNamespace(send_frame=lambda sock, payload: None)

    runner._handle_client(
        conn,
        cfg=cfg,
        bridge=fake_bridge,
        encoder=fake_encoder,
        decoder_sock=object(),
        send_lock=threading.Lock(),
        runtime_compression_level=1,
        fps=5.0,
        logger=_DummyLogger(),
    )

    rate_event = next(event for event in events if event["event"] == "frame_rate_limited")
    assert rate_event["target_fps"] == 5.0
    assert rate_event["sleep_ms"] == 12.5


def test_handle_client_logs_connection_error_without_raising(monkeypatch):
    events = []
    cfg = SimpleNamespace(app=SimpleNamespace(client_id="default"), mux_cfg=SimpleNamespace())
    conn = SimpleNamespace(close=lambda: None)

    def _raise_connection_error(c, mux_cfg):
        raise ConnectionError("peer reset")

    monkeypatch.setattr(runner, "recv_frame", _raise_connection_error)
    monkeypatch.setattr(runner, "log_json", lambda logger, record: events.append(record))

    runner._handle_client(
        conn,
        cfg=cfg,
        bridge=SimpleNamespace(),
        encoder=SimpleNamespace(),
        decoder_sock=object(),
        send_lock=threading.Lock(),
        runtime_compression_level=1,
        fps=0.0,
        logger=_DummyLogger(),
    )

    event_names = [event["event"] for event in events]
    assert "client_connection_error" in event_names
    assert "client_disconnected" in event_names


