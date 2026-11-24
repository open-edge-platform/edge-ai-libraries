# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Opt-in tests using real Telegraf and the current native NPU executable."""

import asyncio
import json
import os
import socket
import struct
import subprocess
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import routes, sse

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = [
    ROOT / "telegraf.conf",
    ROOT / "native/packaging/etc/telegraf.conf",
    ROOT / "helm/metrics-manager/files/telegraf-restricted.conf",
]
TELEGRAF = os.environ.get("TEST_TELEGRAF_BINARY")
NPU = os.environ.get("TEST_NPU_BINARY")
pytestmark = pytest.mark.skipif(
    not TELEGRAF or not NPU,
    reason="Set TEST_TELEGRAF_BINARY and TEST_NPU_BINARY to run the native pipeline tests",
)


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    pytest.fail("Timed out waiting for the telemetry pipeline")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def pipeline(tmp_path):
    processes = []
    logs = []

    def start(
        config=CONFIGS[0],
        ttl=None,
        legacy=False,
        native=True,
        fixed_ttl=None,
        initial_snapshot=None,
    ):
        directory = tmp_path / str(len(processes))
        directory.mkdir()
        device = directory / "class/intel_pmt/telem0"
        device.mkdir(parents=True)
        for name, value in {"guid": "0x3086000", "size": "3352", "offset": "0"}.items():
            (device / name).write_text(value)
        buffer = bytearray(3352)
        struct.pack_into("<Q", buffer, 0x18, 40)
        (device / "telem").write_bytes(buffer if initial_snapshot is None else initial_snapshot)
        pci = directory / "bus/pci/drivers/intel_vpu/0000:00:0b.0"
        pci.mkdir(parents=True)
        busy = pci / "npu_busy_time_us"
        busy.write_text("0")

        output = tomllib.loads(config.read_text())["outputs"]["prometheus_client"][0]
        if legacy:
            output.pop("expiration_interval", None)
        if fixed_ttl is not None:
            output["expiration_interval"] = fixed_ttl
        port, ingest_port = free_port(), free_port()
        output["listen"] = f"127.0.0.1:{port}"
        text = '[agent]\ninterval = "100ms"\nflush_interval = "100ms"\n'
        text += "[[outputs.prometheus_client]]\n"
        text += "\n".join(f"{key} = {json.dumps(value)}" for key, value in output.items())
        text += (
            "\n[[inputs.http_listener_v2]]\n"
            f'service_address = "127.0.0.1:{ingest_port}"\n'
            'paths = ["/write"]\nmethods = ["POST"]\ndata_format = "influx"\n'
        )
        if native:
            text += (
                "[[inputs.execd]]\ncommand = "
                + json.dumps([NPU, "-sysfs-root", str(directory), "-interval", "100ms"])
                + '\ndata_format = "influx"\n'
            )
        config_path = directory / "telegraf.conf"
        config_path.write_text(text)
        environment = dict(os.environ)
        environment.pop("TELEGRAF_EXPIRATION_INTERVAL", None)
        if ttl is not None:
            environment["TELEGRAF_EXPIRATION_INTERVAL"] = ttl
        log = (directory / "stderr").open("w+")
        logs.append(log)
        process = subprocess.Popen(
            [TELEGRAF, "--config", str(config_path)],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=log,
        )
        processes.append(process)
        endpoint = f"http://127.0.0.1:{port}"

        def scrape():
            if process.poll() is not None:
                log.flush()
                log.seek(0)
                pytest.fail(f"Telegraf exited: {log.read()}")
            try:
                response = httpx.get(endpoint + "/metrics", timeout=1, trust_env=False)
            except httpx.ConnectError:
                return None
            response.raise_for_status()
            return response.text

        wait_for(lambda: scrape() is not None)

        def push():
            response = httpx.post(
                f"http://127.0.0.1:{ingest_port}/write",
                content="slow_sensor value=0\n",
                timeout=2,
                trust_env=False,
            )
            response.raise_for_status()
            wait_for(lambda: "slow_sensor" in scrape())

        return SimpleNamespace(
            endpoint=endpoint,
            scrape=scrape,
            push=push,
            busy=busy,
            device=device,
            buffer=buffer,
            log=log,
        )

    yield start
    for process in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    for log in logs:
        log.close()


@pytest.mark.parametrize("config", CONFIGS, ids=["docker", "debian", "helm"])
def test_npu_failure_expiration_and_recovery(pipeline, config, monkeypatch):
    run = pipeline(config, ttl="500ms")
    wait_for(lambda: "npu_utilization" in run.scrape())
    monkeypatch.setattr(
        sse, "get_settings", lambda: SimpleNamespace(prometheus_telegraf_endpoint=run.endpoint)
    )
    event = json.loads(asyncio.run(sse.fetch_metrics()))
    measured_zero = next(m for m in event["metrics"] if m["name"] == "npu_utilization")
    assert measured_zero["value"] == 0
    timestamp = measured_zero["timestamp"]

    (run.device / "telem").write_bytes(b"")
    wait_for(lambda: "npu_frequency_hz" not in run.scrape())
    run.log.flush()
    run.log.seek(0)
    assert "incomplete Panther Lake telemetry" in run.log.read()
    assert not any(
        m["name"].startswith("npu_")
        for m in json.loads(asyncio.run(sse.fetch_metrics()))["metrics"]
    )

    (run.device / "telem").write_bytes(run.buffer)
    wait_for(lambda: "npu_utilization" in run.scrape())
    latest = asyncio.run(routes._fetch_prometheus_metrics(run.endpoint))
    utilization = next(m for m in latest.values() if m.name == "npu_utilization")
    assert utilization.fields["value"] == 0
    assert utilization.timestamp // 1_000_000 > timestamp
    run.busy.write_text("unreadable")
    wait_for(lambda: "npu_utilization" not in run.scrape())
    assert "npu_frequency_hz" in run.scrape()

    # Global TTL affects an infrequent custom metric despite healthy NPU updates.
    run.push()
    wait_for(lambda: "slow_sensor" not in run.scrape())
    assert "npu_frequency_hz" in run.scrape()


def test_default_ttl_remains_sixty_seconds_without_new_environment(pipeline):
    run = pipeline(native=False)
    run.push()
    time.sleep(16)
    assert "slow_sensor" in run.scrape(), "Default TTL must not silently become 15s"
    time.sleep(42)
    assert "slow_sensor" in run.scrape(), "Default TTL must retain a sample for almost 60s"
    wait_for(lambda: "slow_sensor" not in run.scrape(), timeout=4)


@pytest.mark.parametrize(
    "legacy,ttl,fixed_ttl", [(False, "0", None), (True, "200ms", None), (False, "200ms", "2s")]
)
def test_disabled_expiration_and_legacy_config_are_preserved(pipeline, legacy, ttl, fixed_ttl):
    run = pipeline(native=False, legacy=legacy, ttl=ttl, fixed_ttl=fixed_ttl)
    run.push()
    time.sleep(1)
    assert "slow_sensor" in run.scrape()
    if fixed_ttl is not None:
        wait_for(lambda: "slow_sensor" not in run.scrape())


@pytest.mark.parametrize("ttl", ["invalid", "-1s"])
def test_invalid_expiration_fails_visibly(pipeline, ttl):
    with pytest.raises(pytest.fail.Exception, match="Telegraf exited"):
        pipeline(native=False, ttl=ttl)


def test_incomplete_initial_snapshot_recovers(pipeline):
    running = pipeline(initial_snapshot=b"")

    def rejected():
        running.log.seek(0)
        return "retrying initial sample" in running.log.read()

    wait_for(rejected)
    assert "npu_frequency_hz" not in running.scrape()
    (running.device / "telem").write_bytes(running.buffer)
    wait_for(lambda: "npu_frequency_hz" in running.scrape())
