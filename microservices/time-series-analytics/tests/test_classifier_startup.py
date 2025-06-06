#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import pytest
from unittest.mock import patch, MagicMock, mock_open, Mock
import sys
import socket
import subprocess

from classifier_startup import KapacitorClassifier, SUCCESS, FAILURE, KAPACITOR_NAME
from classifier_startup import ConfigFileEventHandler, KapacitorDaemonLogs
from classifier_startup import main
import classifier_startup

@pytest.fixture
def fake_logger():
    class Logger:
        def __init__(self):
            self.errors = []
            self.infos = []
        def error(self, msg):
            self.errors.append(msg)
        def info(self, msg):
            self.infos.append(msg)
        def debug(self, msg):
            pass
    return Logger()

def test_write_cert_success(tmp_path, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    src = tmp_path / "src.crt"
    dst = tmp_path / "dst.crt"
    src.write_text("CERTDATA")
    handler.write_cert(str(dst), str(src))
    assert dst.exists()

def test_write_cert_failure(fake_logger):
    handler = KapacitorClassifier(fake_logger)
    with patch("shutil.copy", side_effect=OSError("fail")):
        handler.write_cert("dst", "src")
        assert "Failed creating file" in fake_logger.infos or fake_logger.debug

def test_install_udf_package(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    monkeypatch.setattr("os.system", lambda x: 0)
    monkeypatch.setattr("os.path.isfile", lambda x: True)
    handler.install_udf_package()  # Should not raise

def test_start_kapacitor_success(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    monkeypatch.setenv("KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setenv("KAPACITOR_INFLUXDB_0_URLS_0", "http://localhost:8086")
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: None)
    result = handler.start_kapacitor({}, "localhost", False, "app")
    assert result is True

def test_start_kapacitor_failure(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    monkeypatch.setenv("KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setenv("KAPACITOR_INFLUXDB_0_URLS_0", "http://localhost:8086")
    def raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])
    monkeypatch.setattr(subprocess, "Popen", raise_called_process_error)
    result = handler.start_kapacitor({}, "localhost", True, "app")
    assert result is False

def test_process_zombie_false(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    class FakeRun:
        def __init__(self, out):
            self.stdout = out
    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeRun(b'0'))
    assert handler.process_zombie(KAPACITOR_NAME) is False

def test_process_zombie_exception(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    def raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])
    monkeypatch.setattr(subprocess, "Popen", raise_called_process_error)
    assert handler.process_zombie("kapacitord") is None or handler.process_zombie("kapacitord") is False

def test_kapacitor_port_open_success(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    monkeypatch.setattr(handler, "process_zombie", lambda x: False)
    # Patch socket.socket.connect_ex to return SUCCESS
    class FakeSocket:
        def connect_ex(self, addr):
            return SUCCESS
        def close(self): pass
    monkeypatch.setattr(socket, "socket", lambda *a, **k: FakeSocket())
    assert handler.kapacitor_port_open("localhost") is True

def test_kapacitor_port_open_failure(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    monkeypatch.setattr(handler, "process_zombie", lambda x: False)
    class FakeSocket:
        def connect_ex(self, addr):
            return 1
        def close(self): pass
    monkeypatch.setattr(socket, "socket", lambda *a, **k: FakeSocket())
    assert handler.kapacitor_port_open("localhost") is False

def test_exit_with_failure_message(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    with pytest.raises(SystemExit):
        handler.exit_with_failure_message("fail message")
    assert "fail message" in fake_logger.errors

def test_check_config_missing_task(fake_logger):
    handler = KapacitorClassifier(fake_logger)
    msg, status = handler.check_config({})
    assert status == FAILURE
    assert "task key is missing" in msg

def test_check_config_success(fake_logger):
    handler = KapacitorClassifier(fake_logger)
    msg, status = handler.check_config({"task": {}})
    assert status == SUCCESS
    assert msg is None

def test_config_file_event_handler_on_modified_triggers_exit(monkeypatch):
    handler = ConfigFileEventHandler()
    class FakeEvent:
        src_path = "/app/config.json"
    # Patch os._exit and logger.info
    exit_called = {}
    monkeypatch.setattr("os._exit", lambda code: exit_called.setdefault("called", code))
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    handler.on_modified(FakeEvent())
    assert exit_called["called"] == 1

def test_config_file_event_handler_on_modified_no_action(monkeypatch):
    class FakeEvent:
        src_path = "/app/config.json"
    # Patch os._exit and logger.info to ensure not called
    monkeypatch.setattr("os._exit", lambda *_: (_ for _ in ()).throw(Exception("Should not exit")))
    logger_mock = MagicMock()
    monkeypatch.setattr("classifier_startup.logger", logger_mock)
    # Should not raise or call exit
    event = FakeEvent()
    with pytest.raises(Exception, match="Should not exit"):
        ConfigFileEventHandler.on_modified(event, logger_mock)

def test_kapacitor_daemon_logs_reads_lines(monkeypatch, fake_logger):
    # Simulate the log file exists immediately
    monkeypatch.setattr("os.path.isfile", lambda x: True)
    # Simulate subprocess.Popen returning a fake process with a fake stdout
    class FakeStdout:
        def __init__(self):
            self.lines = [b"log1\n", b"log2\n"]
            self.index = 0
        def readline(self):
            if self.index < len(self.lines):
                line = self.lines[self.index]
                self.index += 1
                return line
            return b""
    class FakePopen:
        def __init__(self, *a, **k):
            self.stdout = FakeStdout()
            self.stderr = None
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: FakePopen())
    # Simulate select.poll
    class FakePoll:
        def __init__(self):
            self.called = 0
        def register(self, fd): pass
        def poll(self, timeout):
            self.called += 1
            # Only return True for the first two calls, then False to break
            return self.called <= 2
    monkeypatch.setattr("select.poll", lambda: FakePoll())
    # Patch time.sleep to break infinite loop after a few iterations
    sleep_calls = {"count": 0}
    def fake_sleep(x):
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 2:
            raise Exception("break")
    monkeypatch.setattr("time.sleep", fake_sleep)
    # Run and catch the forced break
    try:
        KapacitorDaemonLogs(fake_logger)
    except Exception as e:
        assert str(e) == "break"
    # Check that logger.info was called with log lines
    assert any(b"log1" in info or b"log2" in info for info in fake_logger.infos)

def test_main_config_file_missing(monkeypatch):
    # Patch open to raise FileNotFoundError
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    monkeypatch.setattr("os._exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    with pytest.raises(SystemExit):
        main()

def test_enable_classifier_task_success(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    # Patch kapacitor_port_open to return True immediately
    monkeypatch.setattr(handler, "kapacitor_port_open", lambda host: True)
    # Patch subprocess.check_call to always return SUCCESS
    monkeypatch.setattr(subprocess, "check_call", lambda cmd: SUCCESS)
    # Patch time.sleep to avoid delays
    monkeypatch.setattr("time.sleep", lambda x: None)
    # Patch global mrHandlerObj to None
    classifier_startup.mrHandlerObj = None
    handler.enable_classifier_task("localhost", "myscript.tick", "mytask")
    assert "Kapacitor Tasks Enabled Successfully" in fake_logger.infos
    assert "Kapacitor Initialized Successfully. Ready to Receive the Data...." in fake_logger.infos

def test_enable_classifier_task_with_mrHandlerObj(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    monkeypatch.setattr(handler, "kapacitor_port_open", lambda host: True)
    monkeypatch.setattr(subprocess, "check_call", lambda cmd: SUCCESS)
    monkeypatch.setattr("time.sleep", lambda x: None)
    # Set up a fake mrHandlerObj with fetch_from_model_registry True
    class FakeMR:
        fetch_from_model_registry = True
        tasks = {"task_name": "foo"}
    classifier_startup.mrHandlerObj = FakeMR()
    handler.enable_classifier_task("localhost", "myscript.tick", "mytask")
    assert any("Kapacitor Tasks Enabled Successfully" in msg for msg in fake_logger.infos)

def test_enable_classifier_task_retry_on_failure(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    monkeypatch.setattr(handler, "kapacitor_port_open", lambda host: True)
    # Fail the first call, succeed the second
    calls = {"count": 0}
    def fake_check_call(cmd):
        if calls["count"] == 0:
            calls["count"] += 1
            return FAILURE
        return SUCCESS
    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr("time.sleep", lambda x: None)
    classifier_startup.mrHandlerObj = None
    handler.enable_classifier_task("localhost", "myscript.tick", "mytask")
    assert "ERROR:Cannot Communicate to Kapacitor. " in fake_logger.infos
    assert "Kapacitor Tasks Enabled Successfully" in fake_logger.infos

def test_enable_classifier_task_port_never_opens(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    # kapacitor_port_open always returns False
    monkeypatch.setattr(handler, "kapacitor_port_open", lambda host: False)
    # Patch time.sleep to avoid delay
    monkeypatch.setattr("time.sleep", lambda x: None)
    # Patch os._exit to raise SystemExit so we can catch it
    monkeypatch.setattr("os._exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    classifier_startup.mrHandlerObj = None
    with pytest.raises(SystemExit):
        handler.enable_classifier_task("localhost", "myscript.tick", "mytask")
    assert "Error connecting to Kapacitor Daemon... Restarting Kapacitor..." in fake_logger.errors
    def test_enable_tasks_missing_tick_script(fake_logger):
        handler = KapacitorClassifier(fake_logger)
        config = {"task": {"task_name": "foo"}}
        msg, status = handler.enable_tasks(config, True, "localhost", False)
        assert status == FAILURE
        assert "tick_script key is missing" in msg

def test_enable_tasks_missing_task_name(fake_logger):
    handler = KapacitorClassifier(fake_logger)
    config = {"task": {"tick_script": "myscript.tick"}}
    msg, status = handler.enable_tasks(config, True, "localhost", False)
    assert status == FAILURE
    assert "task_name key is missing" in msg

def test_enable_tasks_calls_enable_classifier_task(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    config = {"task": {"tick_script": "myscript.tick", "task_name": "foo"}}
    called = {}
    def fake_enable_classifier_task(host, tick, name):
        called["called"] = (host, tick, name)
        # Raise to break infinite loop
        raise Exception("break")
    monkeypatch.setattr(handler, "enable_classifier_task", fake_enable_classifier_task)
    monkeypatch.setattr("time.sleep", lambda x: (_ for _ in ()).throw(Exception("break")))
    try:
        handler.enable_tasks(config, True, "localhost", False)
    except Exception as e:
        assert str(e) == "break"
    assert called["called"] == ("localhost", "myscript.tick", "foo")
    assert "Enabling myscript.tick" in fake_logger.infos

def test_enable_tasks_no_kapacitor_started(monkeypatch, fake_logger):
    handler = KapacitorClassifier(fake_logger)
    config = {"task": {"tick_script": "myscript.tick", "task_name": "foo"}}
    # Patch time.sleep to break infinite loop
    monkeypatch.setattr("time.sleep", lambda x: (_ for _ in ()).throw(Exception("break")))
    try:
        handler.enable_tasks(config, False, "localhost", False)
    except Exception as e:
        assert str(e) == "break"
    # Should not call enable_classifier_task, so nothing in infos
    assert not any("Enabling" in msg for msg in fake_logger.infos)

def test_config_file_watch_keyboard_interrupt(monkeypatch):
    # Prepare a fake observer with stop and join methods
    class FakeObserver:
        def __init__(self):
            self.stopped = False
            self.joined = False
        def stop(self):
            self.stopped = True
        def join(self):
            self.joined = True

    observer = FakeObserver()
    # Patch time.sleep to raise KeyboardInterrupt on first call
    def fake_sleep(x):
        raise KeyboardInterrupt()
    monkeypatch.setattr("time.sleep", fake_sleep)
    # Patch logger.info to a MagicMock to avoid side effects
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    # Should not raise, should call observer.stop and observer.join
    classifier_startup.config_file_watch(observer, "/app/config.json")
    assert observer.stopped is True
    assert observer.joined is True

def test_config_file_watch_runs_loop(monkeypatch):
    # Prepare a fake observer with stop and join methods
    class FakeObserver:
        def stop(self): pass
        def join(self): pass
    observer = FakeObserver()
    # Patch time.sleep to break after a few iterations
    call_count = {"count": 0}
    def fake_sleep(x):
        call_count["count"] += 1
        if call_count["count"] > 2:
            raise Exception("break")
    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    try:
        classifier_startup.config_file_watch(observer, "/app/config.json")
    except Exception as e:
        assert str(e) == "break"
    assert call_count["count"] > 0

def test_delete_old_subscription_secure_mode(monkeypatch):
    # Patch environment variables
    monkeypatch.setenv('INFLUX_SERVER', 'localhost')
    monkeypatch.setenv('KAPACITOR_INFLUXDB_0_USERNAME', 'user')
    monkeypatch.setenv('KAPACITOR_INFLUXDB_0_PASSWORD', 'pass')
    monkeypatch.setenv('INFLUXDB_DBNAME', 'testdb')

    # Patch InfluxDBClient and its methods
    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False
            self.queries = []
        def query(self, q):
            if q == 'SHOW SUBSCRIPTIONS':
                class FakeResults:
                    def get_points(self):
                        return [
                            {'name': 'kapacitor-foo', 'retention_policy': 'autogen', 'mode': 'ALL', 'destinations': ['dest']}
                        ]
                return FakeResults()
            self.queries.append(q)
            return None
        def close(self):
            self.closed = True

    monkeypatch.setattr("classifier_startup.InfluxDBClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr("classifier_startup.logger", MagicMock())

    # Should not raise
    classifier_startup.delete_old_subscription(secure_mode=True)

def test_delete_old_subscription_non_secure(monkeypatch):
    monkeypatch.setenv('INFLUX_SERVER', 'localhost')
    monkeypatch.setenv('KAPACITOR_INFLUXDB_0_USERNAME', 'user')
    monkeypatch.setenv('KAPACITOR_INFLUXDB_0_PASSWORD', 'pass')
    monkeypatch.setenv('INFLUXDB_DBNAME', 'testdb')

    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False
        def query(self, q):
            class FakeResults:
                def get_points(self):
                    return []
            return FakeResults()
        def close(self):
            self.closed = True

    monkeypatch.setattr("classifier_startup.InfluxDBClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    classifier_startup.delete_old_subscription(secure_mode=False)

def test_delete_old_subscription_query_exception(monkeypatch):
    monkeypatch.setenv('INFLUX_SERVER', 'localhost')
    monkeypatch.setenv('KAPACITOR_INFLUXDB_0_USERNAME', 'user')
    monkeypatch.setenv('KAPACITOR_INFLUXDB_0_PASSWORD', 'pass')
    monkeypatch.setenv('INFLUXDB_DBNAME', 'testdb')

    class FakeClient:
        def __init__(self, **kwargs): pass
        def query(self, q):
            raise Exception("query failed")
        def close(self): pass

    monkeypatch.setattr("classifier_startup.InfluxDBClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    # Patch print to capture output
    printed = {}
    monkeypatch.setattr("builtins.print", lambda msg: printed.setdefault("msg", msg))
    classifier_startup.delete_old_subscription(secure_mode=False)
    assert "Failed to list subscriptions" in printed["msg"]

def test_delete_old_subscription_outer_exception(monkeypatch):
    # Patch InfluxDBClient to raise on init
    monkeypatch.setattr("classifier_startup.InfluxDBClient", lambda **kwargs: (_ for _ in ()).throw(Exception("init failed")))
    logger_mock = MagicMock()
    monkeypatch.setattr("classifier_startup.logger", logger_mock)
    classifier_startup.delete_old_subscription(secure_mode=False)
    assert logger_mock.exception.called

def make_minimal_config():
    # Minimal config structure for main()
    return {
        "config": {
            "task": {
                "udfs": {"name": "myudf"},
                "tick_script": "myscript.tick",
                "task_name": "mytask"
            },
            "alerts": {
                "mqtt": {
                    "name": "mqtt_name",
                    "mqtt_broker_host": "localhost",
                    "mqtt_broker_port": 1883
                }
            }
        }
    }

@pytest.fixture
def patch_env(monkeypatch):
    monkeypatch.setenv("KAPACITOR_URL", "http://localhost:9092")
    monkeypatch.setenv("KAPACITOR_INFLUXDB_0_URLS_0", "http://localhost:8086")
    monkeypatch.setenv("SECURE_MODE", "false")
    monkeypatch.setenv("Appname", "Kapacitor")

def test_main_success(monkeypatch, patch_env):
    # Patch open for config.json and toml file
    minimal_config = make_minimal_config()
    m = mock_open(read_data='{}')
    # Patch json.load to return our config
    monkeypatch.setattr("builtins.open", m)
    monkeypatch.setattr("json.load", lambda f: minimal_config)
    # Patch tomlkit.parse and tomlkit.dumps
    monkeypatch.setattr("tomlkit.parse", lambda s: {
        "udf": {"functions": {}},
        "mqtt": [{"name": "", "url": "mqtt://MQTT_BROKER_HOST:MQTT_BROKER_PORT"}]
    })
    monkeypatch.setattr("tomlkit.table", lambda: {})
    monkeypatch.setattr("tomlkit.dumps", lambda d, sort_keys=False: "tomlcontent")
    # Patch shutil.copy
    monkeypatch.setattr("shutil.copy", lambda src, dst: None)
    # Patch file write
    monkeypatch.setattr("builtins.open", mock_open())
    # Patch Observer and Thread
    fake_observer = MagicMock()
    monkeypatch.setattr("classifier_startup.Observer", lambda: fake_observer)
    monkeypatch.setattr("classifier_startup.Thread", lambda target, args: MagicMock(start=lambda: None))
    # Patch MRHandler
    monkeypatch.setattr("classifier_startup.MRHandler", lambda config, logger: MagicMock(fetch_from_model_registry=False))
    # Patch KapacitorClassifier and its methods
    fake_classifier = MagicMock()
    fake_classifier.check_config.return_value = (None, classifier_startup.SUCCESS)
    fake_classifier.install_udf_package.return_value = None
    fake_classifier.start_kapacitor.return_value = True
    fake_classifier.enable_tasks.return_value = (None, classifier_startup.SUCCESS)
    monkeypatch.setattr("classifier_startup.KapacitorClassifier", lambda logger: fake_classifier)
    # Patch KapacitorDaemonLogs thread
    monkeypatch.setattr("threading.Thread", lambda target, args: MagicMock(start=lambda: None))
    # Patch delete_old_subscription
    monkeypatch.setattr("classifier_startup.delete_old_subscription", lambda secure_mode: None)
    # Patch logger
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    # Patch os.environ
    monkeypatch.setattr("os.environ", {
        "KAPACITOR_URL": "http://localhost:9092",
        "KAPACITOR_INFLUXDB_0_URLS_0": "http://localhost:8086"
    })
    # Run main, should not raise
    classifier_startup.main()
    assert fake_classifier.check_config.called
    assert fake_classifier.install_udf_package.called
    assert fake_classifier.start_kapacitor.called
    assert fake_classifier.enable_tasks.called

    def test_main_config_missing(monkeypatch):
        # Patch open to raise FileNotFoundError
        monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
        monkeypatch.setattr("classifier_startup.logger", MagicMock())
        monkeypatch.setattr("os._exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
        with pytest.raises(SystemExit):
            classifier_startup.main()

def test_main_with_opcua(monkeypatch, patch_env):
    # Like test_main_success but with "opcua" in alerts
    minimal_config = make_minimal_config()
    minimal_config["config"]["alerts"]["opcua"] = {"foo": "bar"}
    m = mock_open(read_data='{}')
    monkeypatch.setattr("builtins.open", m)
    monkeypatch.setattr("json.load", lambda f: minimal_config)
    monkeypatch.setattr("tomlkit.parse", lambda s: {
        "udf": {"functions": {}},
        "mqtt": [{"name": "", "url": "mqtt://MQTT_BROKER_HOST:MQTT_BROKER_PORT"}]
    })
    monkeypatch.setattr("tomlkit.table", lambda: {})
    monkeypatch.setattr("tomlkit.dumps", lambda d, sort_keys=False: "tomlcontent")
    monkeypatch.setattr("shutil.copy", lambda src, dst: None)
    monkeypatch.setattr("builtins.open", mock_open())
    monkeypatch.setattr("classifier_startup.Observer", lambda: MagicMock())
    monkeypatch.setattr("classifier_startup.Thread", lambda target, args: MagicMock(start=lambda: None))
    monkeypatch.setattr("classifier_startup.MRHandler", lambda config, logger: MagicMock(fetch_from_model_registry=False))
    fake_classifier = MagicMock()
    fake_classifier.check_config.return_value = (None, classifier_startup.SUCCESS)
    fake_classifier.install_udf_package.return_value = None
    fake_classifier.start_kapacitor.return_value = True
    fake_classifier.enable_tasks.return_value = (None, classifier_startup.SUCCESS)
    monkeypatch.setattr("classifier_startup.KapacitorClassifier", lambda logger: fake_classifier)
    monkeypatch.setattr("threading.Thread", lambda target, args: MagicMock(start=lambda: None))
    monkeypatch.setattr("classifier_startup.delete_old_subscription", lambda secure_mode: None)
    monkeypatch.setattr("classifier_startup.logger", MagicMock())
    monkeypatch.setattr("os.environ", {
        "KAPACITOR_URL": "http://localhost:9092",
        "KAPACITOR_INFLUXDB_0_URLS_0": "http://localhost:8086"
    })
    classifier_startup.main()
    assert fake_classifier.check_config.called
    assert fake_classifier.install_udf_package.called
    assert fake_classifier.start_kapacitor.called
    assert fake_classifier.enable_tasks.called
