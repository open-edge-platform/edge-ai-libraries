# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Tests for scripts/qmassa_reader.py — the Telegraf execd input that parses
qmassa GPU telemetry from a FIFO and emits InfluxDB Line Protocol.

These tests focus on the missing-FIFO backoff behaviour (graceful no-op
on hosts without an Intel GPU). Full integration with a real qmassa
binary requires Intel GPU hardware and is out of scope for unit tests.
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QMASSA_READER_PATH = PROJECT_ROOT / "scripts" / "qmassa_reader.py"


def _load_qmassa_reader():
    """Import scripts/qmassa_reader.py as a module without executing __main__.

    The module opens a log file at import time (defaulting to
    ``/app/qmassa_reader_trace.log``), which doesn't exist outside the
    container. ``QMASSA_LOG_TO_STDERR=true`` switches the handler to a
    StreamHandler so the import works in any environment.
    """
    os.environ.setdefault("QMASSA_LOG_TO_STDERR", "true")
    spec = importlib.util.spec_from_file_location(
        "qmassa_reader_under_test", QMASSA_READER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def qmassa_reader():
    """Provide a freshly loaded qmassa_reader module."""
    return _load_qmassa_reader()


class TestMissingFifoBackoff:
    """Verify the warn-once + idle-after-N-retries behaviour when the FIFO
    is missing (i.e. host has no Intel GPU / qmassa not running)."""

    def test_logs_single_warning_and_switches_to_idle_sleep(
        self, qmassa_reader, caplog
    ):
        # Stop the infinite loop after enough sleeps to cover:
        # - MAX_FAST_RETRIES short retries (RETRY_DELAY)
        # - one transition into idle mode (IDLE_SLEEP_S)
        # - one further idle wake-up (must remain silent)
        max_retries = qmassa_reader.MAX_FAST_RETRIES
        retry_delay = qmassa_reader.RETRY_DELAY
        idle_sleep = qmassa_reader.IDLE_SLEEP_S
        sleep_calls: list[float] = []
        stop_after = max_retries + 2

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= stop_after:
                raise SystemExit("stop the loop")

        with patch.object(qmassa_reader, "open", side_effect=FileNotFoundError):
            with patch.object(qmassa_reader.time, "sleep", side_effect=fake_sleep):
                caplog.set_level("DEBUG", logger=qmassa_reader.logger.name)
                with pytest.raises(SystemExit):
                    qmassa_reader.main()

        # First MAX_FAST_RETRIES-1 sleeps are short; from MAX_FAST_RETRIES
        # onward we enter idle mode and sleep IDLE_SLEEP_S.
        assert (
            sleep_calls[: max_retries - 1] == [retry_delay] * (max_retries - 1)
        ), f"Expected {max_retries - 1} fast retries of {retry_delay}s, got {sleep_calls[: max_retries - 1]}"
        assert sleep_calls[max_retries - 1 :] == [idle_sleep] * (
            stop_after - (max_retries - 1)
        ), f"Expected long idle sleeps of {idle_sleep}s after {max_retries} failures, got {sleep_calls[max_retries - 1 :]}"

        # Exactly one WARNING about the missing FIFO across the whole lifecycle.
        warn_records = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "FIFO" in r.message and "not found" in r.message
        ]
        assert len(warn_records) == 1, (
            f"Expected exactly one missing-FIFO warning, got "
            f"{[r.message for r in warn_records]}"
        )

        # Exactly one INFO about transitioning into idle mode (no repeats on
        # subsequent idle wake-ups).
        idle_records = [
            r for r in caplog.records
            if r.levelname == "INFO" and "idle mode" in r.message
        ]
        assert len(idle_records) == 1, (
            f"Expected exactly one idle-mode notice, got "
            f"{[r.message for r in idle_records]}"
        )


class TestHostnameOverride:
    """METRICS_MANAGER_HOSTNAME must override os.uname()[1] for the host tag.

    Dashboards (Grafana Live, Prometheus relabeling) need a stable host
    label across reboots; both readers and Telegraf honour the same env
    var so all three sources agree on the value.
    """

    def test_env_var_overrides_kernel_hostname(self, monkeypatch):
        monkeypatch.setenv("METRICS_MANAGER_HOSTNAME", "unit-test-host")
        # Force a fresh import so module-level HOSTNAME is re-evaluated.
        sys.modules.pop("qmassa_reader_under_test", None)
        module = _load_qmassa_reader()
        assert module.HOSTNAME == "unit-test-host"

    def test_falls_back_to_kernel_hostname_when_unset(self, monkeypatch):
        monkeypatch.delenv("METRICS_MANAGER_HOSTNAME", raising=False)
        sys.modules.pop("qmassa_reader_under_test", None)
        module = _load_qmassa_reader()
        assert module.HOSTNAME == os.uname()[1]

    def test_empty_env_var_falls_back_to_kernel_hostname(self, monkeypatch):
        # `METRICS_MANAGER_HOSTNAME=` (empty) is what `compose.yaml` sets when
        # the user has not specified an override - it must NOT poison the tag.
        monkeypatch.setenv("METRICS_MANAGER_HOSTNAME", "")
        sys.modules.pop("qmassa_reader_under_test", None)
        module = _load_qmassa_reader()
        assert module.HOSTNAME == os.uname()[1]
