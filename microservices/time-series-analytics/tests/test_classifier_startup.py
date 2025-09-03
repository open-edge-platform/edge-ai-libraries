#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import os
import time
import pytest
import threading
from unittest import mock

import classifier_startup as cs

class DummyLogger:
    def __init__(self):
        self.messages = []
    def info(self, msg, *args):
        if args:
            msg = msg % args
        self.messages.append(('info', msg))
    def error(self, msg, *args):
        if args:
            msg = msg % args
        self.messages.append(('error', msg))
    def warning(self, msg, *args):
        if args:
            msg = msg % args
        self.messages.append(('warning', msg))
    def debug(self, msg, *args):
        if args:
            msg = msg % args
        self.messages.append(('debug', msg))
    def exception(self, msg, *args):
        if args:
            msg = msg % args
        self.messages.append(('exception', msg))

@pytest.fixture
def kapacitor_classifier():
    logger = DummyLogger()
    return cs.KapacitorClassifier(logger)

def test_write_cert_creates_file_and_sets_permissions(tmp_path, kapacitor_classifier):
    src_file = tmp_path / "src_cert"
    dst_file = tmp_path / "dst_cert"
    src_file.write_text("CERTDATA")
    kapacitor_classifier.write_cert(str(dst_file), str(src_file))
    assert dst_file.exists()
    assert oct(dst_file.stat().st_mode)[-3:] == "400"

def test_write_cert_logs_on_failure(kapacitor_classifier):
    kapacitor_classifier.write_cert("/nonexistent/path/file", "/nonexistent/cert")
    assert any("Failed creating file" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "debug")

def test_check_udf_package_all_present(tmp_path, kapacitor_classifier):
    dir_name = "testudf"
    base = tmp_path / dir_name
    (base / "udfs").mkdir(parents=True)
    (base / "tick_scripts").mkdir()
    (base / "models").mkdir()
    (base / "udfs" / "myudf.py").write_text("print('hi')")
    (base / "tick_scripts" / "myudf.tick").write_text("tick")
    (base / "models" / "myudf_model").write_text("model")
    config = {"udfs": {"name": "myudf", "models": True}}
    with mock.patch("os.path.isdir", side_effect=lambda p: True), \
         mock.patch("os.path.isfile", side_effect=lambda p: True), \
         mock.patch("os.listdir", return_value=["myudf_model"]):
        assert kapacitor_classifier.check_udf_package(config, dir_name="testudf") is True

def test_check_udf_package_missing_udf(kapacitor_classifier):
    config = {"udfs": {"name": "missingudf"}}
    with mock.patch("os.path.isdir", return_value=True), \
         mock.patch("os.path.isfile", side_effect=lambda p: False), \
         mock.patch("os.listdir", return_value=[]):
        assert kapacitor_classifier.check_udf_package(config, dir_name="missingudf") is False
        assert any("Missing udf" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "warning")

def test_install_udf_package_runs_pip(monkeypatch, kapacitor_classifier):
    called = []
    def fake_run(cmd, check=False, **kwargs):
        called.append(cmd)
        class Dummy:
            pass
        return Dummy()
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    kapacitor_classifier.install_udf_package("somedir")
    # Accept either pip3 install or mkdir -p, depending on implementation
    assert any(
        (isinstance(cmd, list) and (cmd[:2] == ["mkdir", "-p"] or ("pip3" in cmd and "install" in cmd)))
        for cmd in called
    )


def test_start_kapacitor_success(monkeypatch, kapacitor_classifier):
    monkeypatch.setitem(os.environ, "KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setitem(os.environ, "KAPACITOR_INFLUXDB_0_URLS_0", "")
    monkeypatch.setattr(cs.subprocess, "Popen", lambda *a, **k: mock.Mock(wait=lambda: None))
    monkeypatch.setattr(threading, "Thread", lambda *a, **k: mock.Mock(start=lambda: None))
    assert kapacitor_classifier.start_kapacitor("localhost", False) is True

def test_start_kapacitor_failure(monkeypatch, kapacitor_classifier):
    monkeypatch.setitem(os.environ, "KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setitem(os.environ, "KAPACITOR_INFLUXDB_0_URLS_0", "")
    def raise_err(*a, **k): raise cs.subprocess.CalledProcessError(1, "kapacitord")
    monkeypatch.setattr(cs.subprocess, "Popen", raise_err)
    assert kapacitor_classifier.start_kapacitor("localhost", False) is False

# def test_process_zombie_true(monkeypatch, kapacitor_classifier):
#     monkeypatch.setattr(cs.subprocess, "run", lambda *a, **k: mock.Mock(stdout=b'1\n'))
#     assert kapacitor_classifier.process_zombie("kapacitord") is True

def test_process_zombie_false(monkeypatch, kapacitor_classifier):
    monkeypatch.setattr(cs.subprocess, "run", lambda *a, **k: mock.Mock(stdout=b'0\n'))
    assert kapacitor_classifier.process_zombie("kapacitord") is False

def test_kapacitor_port_open_success(monkeypatch, kapacitor_classifier):
    monkeypatch.setattr(kapacitor_classifier, "process_zombie", lambda n: False)
    class DummySock:
        def connect_ex(self, addr): return cs.SUCCESS
        def close(self): pass
    monkeypatch.setattr(cs.socket, "socket", lambda *a, **k: DummySock())
    assert kapacitor_classifier.kapacitor_port_open("localhost") is True

def test_kapacitor_port_open_failure(monkeypatch, kapacitor_classifier):
    monkeypatch.setattr(kapacitor_classifier, "process_zombie", lambda n: False)
    class DummySock:
        def connect_ex(self, addr): return cs.FAILURE
        def close(self): pass
    monkeypatch.setattr(cs.socket, "socket", lambda *a, **k: DummySock())
    assert kapacitor_classifier.kapacitor_port_open("localhost") is False

def test_exit_with_failure_message_logs_and_exits(monkeypatch, kapacitor_classifier):
    with pytest.raises(SystemExit):
        kapacitor_classifier.exit_with_failure_message("failmsg")
    assert any("failmsg" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "error")

def test_check_config_missing_udfs(kapacitor_classifier):
    config = {}
    msg, status = kapacitor_classifier.check_config(config)
    assert status == cs.FAILURE
    assert "udfs key is missing" in msg

def test_check_config_success(kapacitor_classifier):
    config = {"udfs": {"name": "abc"}}
    msg, status = kapacitor_classifier.check_config(config)
    assert status == cs.SUCCESS
    assert msg is None

def test_enable_tasks_missing_name(kapacitor_classifier):
    config = {"udfs": {}}
    msg, status = kapacitor_classifier.enable_tasks(config, True, "localhost", "dir")
    assert status == cs.FAILURE
    assert "UDF name key is missing" in msg

def test_enable_tasks_calls_enable_classifier_task(monkeypatch, kapacitor_classifier):
    config = {"udfs": {"name": "abc"}}
    called = {}
    monkeypatch.setattr(kapacitor_classifier, "enable_classifier_task", lambda *a, **k: called.setdefault("called", True))
    def fake_sleep(x): raise Exception("break")
    monkeypatch.setattr(cs.time, "sleep", fake_sleep)
    with pytest.raises(Exception):
        kapacitor_classifier.enable_tasks(config, True, "localhost", "dir")
    assert called["called"]

def test_delete_old_subscription(monkeypatch):
    called = {}
    class DummyClient:
        def __init__(self, **kwargs): called["init"] = kwargs
        def query(self, q):
            if q == "SHOW SUBSCRIPTIONS":
                class DummyResult:
                    def get_points(self):
                        return [{"name": "kapacitor-foo", "retention_policy": "autogen", "mode": "all", "destinations": ["dest"]}]
                return DummyResult()
            called["drop"] = q
        def close(self): called["closed"] = True
    monkeypatch.setattr(cs, "InfluxDBClient", DummyClient)
    monkeypatch.setattr(cs, "logger", DummyLogger())
    monkeypatch.setenv("INFLUX_SERVER", "host")
    monkeypatch.setenv("KAPACITOR_INFLUXDB_0_USERNAME", "user")
    monkeypatch.setenv("KAPACITOR_INFLUXDB_0_PASSWORD", "pass")
    monkeypatch.setenv("INFLUXDB_DBNAME", "db")
    cs.delete_old_subscription(secure_mode=False)
    assert "init" in called
    assert "closed" in called

def test_classifier_startup(monkeypatch):
    config = {"udfs": {"name": "temperature_classifier"}, "alerts": {"mqtt": {"name": "mqtt", "mqtt_broker_host": "host", "mqtt_broker_port": 1883}}}
    monkeypatch.setenv("SECURE_MODE", "false")
    monkeypatch.setenv("KAPACITOR_INFLUXDB_0_URLS_0", "http://localhost:8086")
    monkeypatch.setenv("KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setattr(cs, "MRHandler", lambda config, logger: type("MRHandler", (), {"fetch_from_model_registry": False, "config": config, "unique_id": None})())
    monkeypatch.setattr(cs, "delete_old_subscription", lambda secure_mode: None)
    monkeypatch.setattr(cs.shutil, "copy", lambda src, dst: None)
    class DummyTomlKit:
        @staticmethod
        def parse(x):
            return {"udf": {"functions": {}}, "mqtt": [{"url": "mqtt://MQTT_BROKER_HOST:MQTT_BROKER_PORT"}], "influxdb": [{}]}
        @staticmethod
        def dumps(d, sort_keys):
            return ""
        @staticmethod
        def table():
            return {}
    monkeypatch.setattr(cs, "tomlkit", DummyTomlKit)
    monkeypatch.setattr(cs, "logger", DummyLogger())
    monkeypatch.setattr(cs.os.path, "exists", lambda p: False)
    monkeypatch.setattr(cs.shutil, "copytree", lambda src, dst: None)
    monkeypatch.setattr(cs.kapacitor_classifier, "check_config", lambda config: (None, cs.SUCCESS))
    monkeypatch.setattr(cs.kapacitor_classifier, "check_udf_package", lambda config, dir_name: True)
    monkeypatch.setattr(cs.kapacitor_classifier, "install_udf_package", lambda dir_name: None)
    monkeypatch.setattr(cs.kapacitor_classifier, "start_kapacitor", lambda host, secure: True)
    monkeypatch.setattr(cs.kapacitor_classifier, "enable_tasks", lambda config, started, host, dir_name: (None, cs.SUCCESS))
    monkeypatch.setattr("builtins.open", mock.mock_open(read_data=""))
    cs.classifier_startup(config)

def test_enable_classifier_task_success(monkeypatch, kapacitor_classifier):
    # Simulate kapacitor_port_open returns True immediately
    monkeypatch.setattr(kapacitor_classifier, "kapacitor_port_open", lambda host: True)
    # Simulate subprocess.check_call returns SUCCESS for both define and enable
    calls = []
    def fake_check_call(cmd):
        calls.append(list(cmd))
        return cs.SUCCESS
    monkeypatch.setattr(cs.subprocess, "check_call", fake_check_call)
    # Patch time.sleep to avoid delays
    monkeypatch.setattr(cs.time, "sleep", lambda x: None)
    kapacitor_classifier.enable_classifier_task(
        host_name="localhost",
        tick_script="myudf.tick",
        dir_name="myudf",
        task_name="myudf"
    )
    # Should call define and enable
    assert any("define" in c for c in calls)
    assert any("enable" in c for c in calls)
    assert any("Kapacitor Tasks Enabled Successfully" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "info")

def test_enable_classifier_task_define_fails(monkeypatch, kapacitor_classifier):
    monkeypatch.setattr(kapacitor_classifier, "kapacitor_port_open", lambda host: True)
    # Simulate subprocess.check_call returns FAILURE for define
    calls = []
    def fake_check_call(cmd):
        calls.append(list(cmd))
        return cs.FAILURE
    monkeypatch.setattr(cs.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(cs.time, "sleep", lambda x: None)
    kapacitor_classifier.enable_classifier_task(
        host_name="localhost",
        tick_script="fail.tick",
        dir_name="faildir",
        task_name="failtask"
    )
    # Should retry 5 times
    assert sum("define" in c for c in calls) == 5
    assert any("ERROR:Cannot Communicate to Kapacitor." in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "info")
    assert any("Retrying Kapacitor Connection" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "info")

def test_enable_classifier_task_enable_fails(monkeypatch, kapacitor_classifier):
    monkeypatch.setattr(kapacitor_classifier, "kapacitor_port_open", lambda host: True)
    # Simulate subprocess.check_call returns SUCCESS for define, FAILURE for enable
    calls = []
    def fake_check_call(cmd):
        calls.append(list(cmd))
        if "define" in cmd:
            return cs.SUCCESS
        if "enable" in cmd:
            return cs.FAILURE
        return cs.FAILURE
    monkeypatch.setattr(cs.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(cs.time, "sleep", lambda x: None)
    kapacitor_classifier.enable_classifier_task(
        host_name="localhost",
        tick_script="failenable.tick",
        dir_name="failenable",
        task_name="failenable"
    )
    # Should retry 5 times
    assert sum("define" in c for c in calls) == 5
    assert sum("enable" in c for c in calls) == 5
    assert any("ERROR:Cannot Communicate to Kapacitor." in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "info")
    assert any("Retrying Kapacitor Connection" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "info")

def test_enable_classifier_task_port_never_opens(monkeypatch, kapacitor_classifier):
    # Simulate kapacitor_port_open returns False always
    monkeypatch.setattr(kapacitor_classifier, "kapacitor_port_open", lambda host: False)
    # Patch time.sleep to avoid delays
    monkeypatch.setattr(cs.time, "sleep", lambda x: None)
    # Patch os._exit to raise SystemExit so we can catch it
    monkeypatch.setattr(cs.os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    with pytest.raises(SystemExit):
        kapacitor_classifier.enable_classifier_task(
            host_name="localhost",
            tick_script="neveropen.tick",
            dir_name="neveropen",
            task_name="neveropen"
        )
    assert any("Error connecting to Kapacitor Daemon" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "error")

def test_start_kapacitor_sets_env_and_starts_proc(monkeypatch, kapacitor_classifier):
    # Setup environment variables
    monkeypatch.setitem(os.environ, "KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setitem(os.environ, "KAPACITOR_INFLUXDB_0_URLS_0", "")
    called = {}

    def fake_popen(cmd):
        called["cmd"] = cmd
        m = mock.Mock()
        m.wait = lambda: None
        return m

    def fake_thread(*args, **kwargs):
        called["thread"] = True
        class DummyThread:
            def start(self): called["thread_started"] = True
        return DummyThread()

    monkeypatch.setattr(cs.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cs.threading, "Thread", fake_thread)
    result = kapacitor_classifier.start_kapacitor("localhost", secure_mode=False)
    assert result is True
    assert "cmd" in called
    assert "thread" in called
    assert "thread_started" in called
    assert any("Started kapacitor Successfully" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "info")
    # Check KAPACITOR_URL env is set to http
    assert os.environ["KAPACITOR_URL"].startswith("http://")
    assert os.environ["KAPACITOR_UNSAFE_SSL"] == "true"

def test_start_kapacitor_secure_mode(monkeypatch, kapacitor_classifier):
    monkeypatch.setitem(os.environ, "KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setitem(os.environ, "KAPACITOR_INFLUXDB_0_URLS_0", "https://influxhost:8086")
    called = {}

    def fake_popen(cmd):
        called["cmd"] = cmd
        m = mock.Mock()
        m.wait = lambda: None
        return m

    def fake_thread(*args, **kwargs):
        class DummyThread:
            def start(self): called["thread_started"] = True
        return DummyThread()

    monkeypatch.setattr(cs.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cs.threading, "Thread", fake_thread)
    result = kapacitor_classifier.start_kapacitor("localhost", secure_mode=True)
    assert result is True
    assert os.environ["KAPACITOR_URL"].startswith("https://")
    assert os.environ["KAPACITOR_UNSAFE_SSL"] == "false"
    assert os.environ["KAPACITOR_INFLUXDB_0_URLS_0"].startswith("https://")
    assert "thread_started" in called

def test_start_kapacitor_handles_subprocess_error(monkeypatch, kapacitor_classifier):
    monkeypatch.setitem(os.environ, "KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setitem(os.environ, "KAPACITOR_INFLUXDB_0_URLS_0", "")
    def raise_err(*a, **k): raise cs.subprocess.CalledProcessError(1, "kapacitord")
    monkeypatch.setattr(cs.subprocess, "Popen", raise_err)
    result = kapacitor_classifier.start_kapacitor("localhost", secure_mode=False)
    assert result is False
    assert any("Exception Occured in Starting the Kapacitor" in m[1] for m in kapacitor_classifier.logger.messages if m[0] == "info")

def test_KapacitorDaemonLogs_waits_for_file_and_reads_lines(monkeypatch):
    # Setup: simulate file appears after 2 checks, then poll returns True once, then break
    calls = {"sleep": 0, "poll": 0, "readline": 0}
    logger = DummyLogger()
    kapacitor_log_file = "/tmp/log/kapacitor/kapacitor.log"
    file_exists = [False, False, True]  # File appears on 3rd check

    def fake_isfile(path):
        assert path == kapacitor_log_file
        return file_exists.pop(0) if file_exists else True

    def fake_sleep(secs):
        calls["sleep"] += 1
        if calls["sleep"] > 10:
            raise Exception("Infinite loop detected in sleep")

    class DummyStdout:
        def readline(self):
            calls["readline"] += 1
            return b"log line\n"

    class DummyPopen:
        def __init__(self, *a, **k):
            self.stdout = DummyStdout()
            self.stderr = None

    class DummyPoll:
        def __init__(self):
            self._calls = 0
        def register(self, fd): pass
        def poll(self, timeout):
            calls["poll"] += 1
            # Return True only on first call, then always False to break after one log
            return calls["poll"] == 1

    monkeypatch.setattr(os.path, "isfile", fake_isfile)
    monkeypatch.setattr(time, "sleep", fake_sleep)
    monkeypatch.setattr(cs.subprocess, "Popen", lambda *a, **k: DummyPopen())
    monkeypatch.setattr(cs.select, "poll", DummyPoll)

    # Patch logger.info to break after first log line
    orig_info = logger.info
    def info_patch(msg):
        orig_info(msg)
        if calls["poll"] == 1:
            raise Exception("break")  # Stop after first log line

    logger.info = info_patch

    with pytest.raises(Exception) as excinfo:
        cs.kapacitor_daemon_logs(logger)
    assert "break" in str(excinfo.value)
    # Should have waited for file, polled, and read a line
    assert calls["sleep"] >= 2
    assert calls["poll"] == 1
    assert calls["readline"] == 1
    # Should have logged the line
    assert any(b"log line" in m[1] if isinstance(m[1], bytes) else b"log line" in m[1].encode() for m in logger.messages if m[0] == "info")

def test_KapacitorDaemonLogs_handles_no_file(monkeypatch):
    # Simulate file never appears, ensure it keeps sleeping
    logger = DummyLogger()
    kapacitor_log_file = "/tmp/log/kapacitor/kapacitor.log"
    sleep_calls = {"count": 0}

    def fake_isfile(path):
        assert path == kapacitor_log_file
        return False

    def fake_sleep(secs):
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 3:
            raise Exception("break")  # Stop after a few sleeps

    monkeypatch.setattr(os.path, "isfile", fake_isfile)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    with pytest.raises(Exception) as excinfo:
        cs.kapacitor_daemon_logs(logger)
    assert "break" in str(excinfo.value)
    assert sleep_calls["count"] > 0


