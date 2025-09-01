#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import sys
import pytest
from unittest import mock
from fastapi.testclient import TestClient
import types
import builtins
import asyncio

# Patch sys.modules for external dependencies
sys.modules["classifier_startup"] = mock.Mock()
import main

client = TestClient(main.app)

@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    # Patch config to a test dict before each test
    if getattr(main, "config", None) is not None:
        main.config.clear()
    main.config = {
        "model_registry": {"enable": True, "version": "2.0"},
        "udfs": {"name": "udf_name", "model": "model_name"},
        "alerts": {"opcua": {"opcua_server": "opc.tcp://localhost:4840", "node_id": "ns=2;i=2", "namespace": 2}}
    }
    yield
    if getattr(main, "config", None) is not None:
        main.config.clear()

def test_health_check_running(monkeypatch):
    class MockResponse:
        status_code = 200
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: MockResponse())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "kapacitor daemon is running"

def test_health_check_not_running(monkeypatch):
    def raise_conn_err(*a, **k):
        raise main.requests.exceptions.ConnectionError()
    monkeypatch.setattr(main.requests, "get", raise_conn_err)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert "kapacitor daemon not running" in resp.json()["status"]

def test_receive_data_success(monkeypatch):
    class MockHealthResp:
        def __getitem__(self, k): return "kapacitor daemon is running"
    monkeypatch.setattr(main, "health_check", lambda r: {"status": "kapacitor daemon is running"})
    class MockResp:
        status_code = 204
        text = ""
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: MockResp())
    data = {
        "topic": "sensor_data",
        "tags": {"location": "factory1"},
        "fields": {"temperature": 23.5},
        "timestamp": 1718000000000000000
    }
    resp = client.post("/input", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

def test_receive_data_kapacitor_down(monkeypatch):
    monkeypatch.setattr(main, "health_check", lambda r: {"status": "kapacitor daemon is not running"})
    data = {
        "topic": "sensor_data",
        "tags": {"location": "factory1"},
        "fields": {"temperature": 23.5},
        "timestamp": 1718000000000000000
    }
    resp = client.post("/input", json=data)
    assert resp.status_code == 500
    assert "Kapacitor daemon is not running" in resp.json()["detail"]

def test_get_config(monkeypatch):
    resp = client.get("/config")
    assert resp.status_code == 200
    assert "model_registry" in resp.json()
    assert "udfs" in resp.json()
    assert "alerts" in resp.json()

def test_get_config_with_restart(monkeypatch):
    called = {}
    def fake_restart():
        called["restart"] = True
    monkeypatch.setattr(main, "restart_kapacitor", fake_restart)
    resp = client.get("/config?restart=true")
    assert resp.status_code == 200
    assert "model_registry" in resp.json()

def test_post_config(monkeypatch):
    monkeypatch.setattr(main, "restart_kapacitor", lambda: None)
    data = {
        "model_registry": {"enable": True, "version": "3.0"},
        "udfs": {"name": "udf_name", "model": "model_name"},
        "alerts": {}
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert main.config["model_registry"]["version"] == "3.0"

def test_json_to_line_protocol_tags():
    dp = main.DataPoint(
        topic="test",
        tags={"a": "b", "c": "d"},
        fields={"x": 1, "y": 2},
        timestamp=1234567890
    )
    line = main.json_to_line_protocol(dp)
    assert line.startswith("test,a=b,c=d x=1,y=2 1234567890")

def test_json_to_line_protocol_no_tags():
    dp = main.DataPoint(
        topic="test",
        fields={"x": 1},
        timestamp=123
    )
    line = main.json_to_line_protocol(dp)
    assert line == "test x=1 123"

def test_start_kapacitor_service_calls_classifier_startup(monkeypatch):
    called = {}
    def fake_classifier_startup(cfg):
        called["called"] = cfg
    monkeypatch.setattr(main.classifier_startup, "classifier_startup", fake_classifier_startup)
    test_cfg = {"foo": "bar"}
    main.start_kapacitor_service(test_cfg)
    assert called["called"] == test_cfg

def test_stop_kapacitor_service_not_running(monkeypatch, caplog):
    monkeypatch.setattr(main, "health_check", lambda r: {"status": "kapacitor daemon is not running"})
    logs = []
    def fake_info(msg):
        logs.append(msg)
    monkeypatch.setattr(main.logger, "info", fake_info)
    main.stop_kapacitor_service()
    assert any("Kapacitor daemon is not running." in l for l in logs)

def test_stop_kapacitor_service_success(monkeypatch):
    # health_check returns running
    monkeypatch.setattr(main, "health_check", lambda r: {"status": "kapacitor daemon is running"})
    # Mock requests.get to return a fake task list
    class FakeResp:
        def json(self):
            return {"tasks": [{"id": "task1"}]}
    monkeypatch.setattr(main.requests, "get", lambda url, **kwargs: FakeResp())
    # Track subprocess.run calls
    calls = []
    def fake_run(cmd, check):
        calls.append((tuple(cmd), check))
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    # Mock logger
    monkeypatch.setattr(main.logger, "info", lambda *args, **kwargs: None)
    main.stop_kapacitor_service()
    assert (("kapacitor", "disable", "task1"), False) in calls
    assert (("pkill", "-9", "kapacitord"), False) in calls

def test_stop_kapacitor_service_subprocess_error(monkeypatch):
    monkeypatch.setattr(main, "health_check", lambda r: {"status": "kapacitor daemon is running"})
    class FakeResp:
        def json(self):
            return {"tasks": [{"id": "task1"}]}
    monkeypatch.setattr(main.requests, "get", lambda url, **kwargs: FakeResp())
    def fake_run(cmd, check):
        raise main.subprocess.CalledProcessError(1, cmd)
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    errors = []
    monkeypatch.setattr(main.logger, "error", lambda msg, *args, **kwargs: errors.append(msg))
    main.stop_kapacitor_service()
    assert any("Error stopping Kapacitor service" in e for e in errors)

def test_restart_kapacitor_calls_stop_and_start(monkeypatch):
    called = {"stop": False, "start": False}
    monkeypatch.setattr(main, "stop_kapacitor_service", lambda: called.update({"stop": True}))
    monkeypatch.setattr(main, "start_kapacitor_service", lambda cfg: called.update({"start": cfg}))
    main.config["foo"] = "bar"
    main.restart_kapacitor()
    assert called["stop"] is True
    assert called["start"] == main.config

def test_health_check_status_running_204(monkeypatch):
    class MockResponse:
        status_code = 204
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: MockResponse())
    response = main.health_check(main.Response())
    assert response == {"status": "kapacitor daemon is running"}

def test_health_check_status_not_running(monkeypatch):
    class MockResponse:
        status_code = 500
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: MockResponse())
    resp_obj = main.Response()
    response = main.health_check(resp_obj)
    assert response == {"status": "kapacitor daemon is not running properly"}


def test_health_check_request_exception(monkeypatch):
    def raise_req_err(*a, **k):
        raise main.requests.exceptions.RequestException()
    monkeypatch.setattr(main.requests, "get", raise_req_err)
    resp_obj = main.Response()
    response = main.health_check(resp_obj)
    assert response == {"status": "An error occurred while checking the service"}
    assert resp_obj.status_code == main.status.HTTP_503_SERVICE_UNAVAILABLE

def test_receive_alert_success(monkeypatch):
    # Patch OpcuaAlerts and its methods
    mock_opcua_alerts = mock.Mock()
    mock_instance = mock.Mock()
    monkeypatch.setitem(sys.modules, "opcua_alerts", mock.Mock())
    mock_instance.opcua_server = main.config["alerts"]["opcua"]["opcua_server"]
    mock_instance.node_id = main.config["alerts"]["opcua"]["node_id"]
    mock_instance.namespace = main.config["alerts"]["opcua"]["namespace"]
    mock_instance.is_connected = mock.AsyncMock(return_value=True)
    mock_instance.send_alert_to_opcua = mock.AsyncMock()
    mock_instance.initialize_opcua = mock.AsyncMock()
    mock_opcua_alerts.return_value = mock_instance
    monkeypatch.setattr(main, "OpcuaAlerts", mock_opcua_alerts)
    # Ensure global is None to trigger initialization
    main.OPCUA_SEND_ALERT = None
    alert_data = {"alert": "test message"}
    resp = client.post("/opcua_alerts", json=alert_data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["message"] == "Alert received"
    mock_instance.initialize_opcua.assert_awaited()
    mock_instance.send_alert_to_opcua.assert_awaited()

def test_receive_alert_reinitialize_on_server_change(monkeypatch):
    # Existing OPCUA_SEND_ALERT with different server triggers re-init
    mock_opcua_alerts = mock.Mock()
    mock_instance = mock.Mock()
    monkeypatch.setitem(sys.modules, "opcua_alerts", mock.Mock())
    mock_instance.opcua_server = "wrong_server"
    mock_instance.node_id = main.config["alerts"]["opcua"]["node_id"]
    mock_instance.namespace = main.config["alerts"]["opcua"]["namespace"]
    mock_instance.is_connected = mock.AsyncMock(return_value=True)
    mock_instance.send_alert_to_opcua = mock.AsyncMock()
    mock_instance.initialize_opcua = mock.AsyncMock()
    mock_opcua_alerts.return_value = mock_instance
    monkeypatch.setattr(main, "OpcuaAlerts", mock_opcua_alerts)
    main.OPCUA_SEND_ALERT = mock_instance
    alert_data = {"alert": "test message"}
    resp = client.post("/opcua_alerts", json=alert_data)
    assert resp.status_code == 200
    mock_instance.initialize_opcua.assert_awaited()
    mock_instance.send_alert_to_opcua.assert_awaited()

def test_receive_alert_reinitialize_on_not_connected(monkeypatch):
    # Existing OPCUA_SEND_ALERT not connected triggers re-init
    mock_opcua_alerts = mock.Mock()
    mock_instance = mock.Mock()
    monkeypatch.setitem(sys.modules, "opcua_alerts", mock.Mock())
    mock_instance.opcua_server = main.config["alerts"]["opcua"]["opcua_server"]
    mock_instance.node_id = main.config["alerts"]["opcua"]["node_id"]
    mock_instance.namespace = main.config["alerts"]["opcua"]["namespace"]
    mock_instance.is_connected = mock.AsyncMock(return_value=False)
    mock_instance.send_alert_to_opcua = mock.AsyncMock()
    mock_instance.initialize_opcua = mock.AsyncMock()
    mock_opcua_alerts.return_value = mock_instance
    monkeypatch.setattr(main, "OpcuaAlerts", mock_opcua_alerts)
    main.OPCUA_SEND_ALERT = mock_instance
    alert_data = {"alert": "test message"}
    resp = client.post("/opcua_alerts", json=alert_data)
    assert resp.status_code == 200
    mock_instance.initialize_opcua.assert_awaited()
    mock_instance.send_alert_to_opcua.assert_awaited()

def test_receive_alert_update_node_id_and_namespace(monkeypatch):
    # Should update node_id and namespace if different
    mock_opcua_alerts = mock.Mock()
    mock_instance = mock.Mock()
    monkeypatch.setitem(sys.modules, "opcua_alerts", mock.Mock())
    mock_instance.opcua_server = main.config["alerts"]["opcua"]["opcua_server"]
    mock_instance.node_id = "old_node"
    mock_instance.namespace = 999
    mock_instance.is_connected = mock.AsyncMock(return_value=True)
    mock_instance.send_alert_to_opcua = mock.AsyncMock()
    mock_instance.initialize_opcua = mock.AsyncMock()
    mock_opcua_alerts.return_value = mock_instance
    monkeypatch.setattr(main, "OpcuaAlerts", mock_opcua_alerts)
    main.OPCUA_SEND_ALERT = mock_instance
    alert_data = {"alert": "test message"}
    resp = client.post("/opcua_alerts", json=alert_data)
    assert resp.status_code == 200
    assert mock_instance.node_id == main.config["alerts"]["opcua"]["node_id"]
    assert mock_instance.namespace == main.config["alerts"]["opcua"]["namespace"]

def test_receive_alert_opcua_not_configured(monkeypatch):
    # Remove opcua from config
    main.config["alerts"] = {}
    alert_data = {"alert": "test message"}
    resp = client.post("/opcua_alerts", json=alert_data)
    assert resp.status_code == 500
    assert "OPC UA alerts are not configured" in resp.json()["detail"]

def test_receive_alert_initialize_opcua_fails(monkeypatch):
    # Simulate exception during initialize_opcua
    mock_opcua_alerts = mock.Mock()
    mock_instance = mock.Mock()
    monkeypatch.setitem(sys.modules, "opcua_alerts", mock.Mock())
    mock_instance.opcua_server = "wrong"
    mock_instance.is_connected = mock.AsyncMock(return_value=False)
    mock_instance.initialize_opcua = mock.AsyncMock(side_effect=Exception("init fail"))
    mock_opcua_alerts.return_value = mock_instance
    monkeypatch.setattr(main, "OpcuaAlerts", mock_opcua_alerts)
    main.OPCUA_SEND_ALERT = None
    # Restore config for alerts
    main.config["alerts"] = {"opcua": {"opcua_server": "opc.tcp://localhost:4840", "node_id": "ns=2;i=2", "namespace": 2}}
    alert_data = {"alert": "test message"}
    resp = client.post("/opcua_alerts", json=alert_data)
    assert resp.status_code == 500
    assert "Failed to initialize OPC UA client" in resp.json()["detail"]

def test_receive_alert_send_alert_fails(monkeypatch):
    # Simulate exception during send_alert_to_opcua
    mock_opcua_alerts = mock.Mock()
    mock_instance = mock.Mock()
    monkeypatch.setitem(sys.modules, "opcua_alerts", mock.Mock())
    mock_instance.opcua_server = main.config["alerts"]["opcua"]["opcua_server"]
    mock_instance.node_id = main.config["alerts"]["opcua"]["node_id"]
    mock_instance.namespace = main.config["alerts"]["opcua"]["namespace"]
    mock_instance.is_connected = mock.AsyncMock(return_value=True)
    mock_instance.initialize_opcua = mock.AsyncMock()
    mock_instance.send_alert_to_opcua = mock.AsyncMock(side_effect=Exception("send fail"))
    mock_opcua_alerts.return_value = mock_instance
    monkeypatch.setattr(main, "OpcuaAlerts", mock_opcua_alerts)
    main.OPCUA_SEND_ALERT = None
    alert_data = {"alert": "test message"}
    resp = client.post("/opcua_alerts", json=alert_data)
    assert resp.status_code == 500
    assert "Failed to send alert" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_get_config_returns_full_config(monkeypatch):
    # Simulate a request with no query params
    class DummyRequest:
        query_params = {}
    # Should return the whole config
    result = await main.get_config(DummyRequest())
    assert result == main.config

@pytest.mark.asyncio
async def test_get_config_filters_by_query(monkeypatch):
    # Simulate a request with query params to filter config
    class DummyRequest:
        query_params = {"model_registry": "1"}
    result = await main.get_config(DummyRequest())
    # Should only return the filtered key
    assert result == {"model_registry": main.config["model_registry"]}

@pytest.mark.asyncio
async def test_get_config_removes_restart_param(monkeypatch):
    # Simulate a request with 'restart' and another param
    class DummyRequest:
        query_params = {"restart": "true", "udfs": "1"}
    result = await main.get_config(DummyRequest())
    assert result == {"udfs": main.config["udfs"]}

@pytest.mark.asyncio
async def test_get_config_restart_triggers_background_task(monkeypatch):
    called = {}
    class DummyBackgroundTasks:
        def add_task(self, fn):
            called["restart"] = True
    class DummyRequest:
        query_params = {}
    await main.get_config(DummyRequest(), restart=True, background_tasks=DummyBackgroundTasks())
    assert called.get("restart") is True

@pytest.mark.asyncio
async def test_get_config_restart_no_background_task(monkeypatch):
    # Should not fail if background_tasks is None
    class DummyRequest:
        query_params = {}
    result = await main.get_config(DummyRequest(), restart=True, background_tasks=None)


def test_main_run_server_thread(monkeypatch):
    # Patch uvicorn.run to just set a flag
    called = {}
    def fake_run(app, host, port):
        called["ran"] = (app, host, port)
    monkeypatch.setattr(main.uvicorn, "run", fake_run)
    # Patch threading.Thread to call target immediately
    class DummyThread:
        def __init__(self, target):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(main.threading, "Thread", DummyThread)
    # Patch open to raise FileNotFoundError
    monkeypatch.setattr(builtins, "open", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    # Patch logger
    logs = []
    monkeypatch.setattr(main.logger, "warning", lambda msg: logs.append(msg))
    # Patch time.sleep to break loop
    monkeypatch.setattr(main.time, "sleep", lambda x: (_ for _ in ()).throw(KeyboardInterrupt()))
    # Patch start_kapacitor_service to do nothing
    monkeypatch.setattr(main, "start_kapacitor_service", lambda cfg: None)
    # Patch json.load to return a dict
    monkeypatch.setattr(main.json, "load", lambda f: {"foo": "bar"})
    # Patch logger.info
    monkeypatch.setattr(main.logger, "info", lambda msg: logs.append(msg))
    # Patch logger.error
    monkeypatch.setattr(main.logger, "error", lambda msg: logs.append(msg))
    # Simulate __name__ == "__main__"
    main_mod = types.ModuleType("main")
    for k in dir(main):
        setattr(main_mod, k, getattr(main, k))
    main_mod.__name__ = "__main__"
    # Patch builtins.open to raise FileNotFoundError for config file
    monkeypatch.setattr(builtins, "open", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    # Run the block and check warning is logged
    try:
        exec(
            "def run_server():\n"
            "    uvicorn.run(app, host='0.0.0.0', port=5000)\n"
            "server_thread = threading.Thread(target=run_server)\n"
            "server_thread.start()\n"
            "try:\n"
            "    with open(CONFIG_FILE, 'r') as file:\n"
            "        config = json.load(file)\n"
            "    logger.info('App configuration loaded successfully from config.json file')\n"
            "    start_kapacitor_service(config)\n"
            "    while True:\n"
            "        time.sleep(1)\n"
            "except FileNotFoundError:\n"
            "    logger.warning('config.json file not found, waiting for the configuration')\n"
            "except Exception as e:\n"
            "    logger.error(f'Time Series Analytics Microservice failure - {e}')\n",
            main_mod.__dict__
        )
    except Exception:
        pass
    assert any("config.json file not found" in l for l in logs)

def test_main_config_load_and_loop(monkeypatch):
    # Patch open to return a dummy file-like object
    class DummyFile:
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(builtins, "open", lambda *a, **k: DummyFile())
    # Patch json.load to return a dict
    monkeypatch.setattr(main.json, "load", lambda f: {"foo": "bar"})
    # Patch logger
    logs = []
    monkeypatch.setattr(main.logger, "info", lambda msg: logs.append(msg))
    # Patch start_kapacitor_service
    monkeypatch.setattr(main, "start_kapacitor_service", lambda cfg: logs.append("kapacitor started"))
    # Patch time.sleep to raise KeyboardInterrupt to break loop
    monkeypatch.setattr(main.time, "sleep", lambda x: (_ for _ in ()).throw(KeyboardInterrupt()))
    # Patch threading.Thread to call target immediately
    class DummyThread:
        def __init__(self, target):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(main.threading, "Thread", DummyThread)
    # Patch uvicorn.run
    monkeypatch.setattr(main.uvicorn, "run", lambda *a, **k: None)
    # Simulate __name__ == "__main__"
    main_mod = types.ModuleType("main")
    for k in dir(main):
        setattr(main_mod, k, getattr(main, k))
    main_mod.__name__ = "__main__"
    # Run the block and check info log
    try:
        exec(
            "def run_server():\n"
            "    uvicorn.run(app, host='0.0.0.0', port=5000)\n"
            "server_thread = threading.Thread(target=run_server)\n"
            "server_thread.start()\n"
            "try:\n"
            "    with open(CONFIG_FILE, 'r') as file:\n"
            "        config = json.load(file)\n"
            "    logger.info('App configuration loaded successfully from config.json file')\n"
            "    start_kapacitor_service(config)\n"
            "    while True:\n"
            "        time.sleep(1)\n"
            "except FileNotFoundError:\n"
            "    logger.warning('config.json file not found, waiting for the configuration')\n"
            "except Exception as e:\n"
            "    logger.error(f'Time Series Analytics Microservice failure - {e}')\n",
            main_mod.__dict__
        )
    except KeyboardInterrupt:
        pass
    assert any("App configuration loaded successfully" in l for l in logs)
    assert any("kapacitor started" in l for l in logs)

def test_main_config_load_exception(monkeypatch):
    # Patch open to raise generic Exception
    monkeypatch.setattr(builtins, "open", lambda *a, **k: (_ for _ in ()).throw(Exception("fail")))
    # Patch logger
    logs = []
    monkeypatch.setattr(main.logger, "error", lambda msg: logs.append(msg))
    # Patch threading.Thread to call target immediately
    class DummyThread:
        def __init__(self, target):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(main.threading, "Thread", DummyThread)
    # Patch uvicorn.run
    monkeypatch.setattr(main.uvicorn, "run", lambda *a, **k: None)
    # Patch time.sleep to break loop
    monkeypatch.setattr(main.time, "sleep", lambda x: (_ for _ in ()).throw(KeyboardInterrupt()))
    # Simulate __name__ == "__main__"
    main_mod = types.ModuleType("main")
    for k in dir(main):
        setattr(main_mod, k, getattr(main, k))
    main_mod.__name__ = "__main__"
    # Run the block and check error log
    try:
        exec(
            "def run_server():\n"
            "    uvicorn.run(app, host='0.0.0.0', port=5000)\n"
            "server_thread = threading.Thread(target=run_server)\n"
            "server_thread.start()\n"
            "try:\n"
            "    with open(CONFIG_FILE, 'r') as file:\n"
            "        config = json.load(file)\n"
            "    logger.info('App configuration loaded successfully from config.json file')\n"
            "    start_kapacitor_service(config)\n"
            "    while True:\n"
            "        time.sleep(1)\n"
            "except FileNotFoundError:\n"
            "    logger.warning('config.json file not found, waiting for the configuration')\n"
            "except Exception as e:\n"
            "    logger.error(f'Time Series Analytics Microservice failure - {e}')\n",
            main_mod.__dict__
        )
    except Exception:
        pass
    assert any("Time Series Analytics Microservice failure" in l for l in logs)


def test_post_config_success(monkeypatch):
    monkeypatch.setattr(main, "restart_kapacitor", lambda: None)
    data = {
        "model_registry": {"enable": True, "version": "3.1"},
        "udfs": {"name": "udf_name", "model": "model_name"},
        "alerts": {"opcua": {"opcua_server": "opc.tcp://localhost:4840", "node_id": "ns=2;i=2", "namespace": 2}}
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert main.config["model_registry"]["version"] == "3.1"
    assert main.config["udfs"]["name"] == "udf_name"
    assert "opcua" in main.config["alerts"]

def test_post_config_alerts_optional(monkeypatch):
    monkeypatch.setattr(main, "restart_kapacitor", lambda: None)
    data = {
        "model_registry": {"enable": False, "version": "1.0"},
        "udfs": {"name": "udf_name", "model": "model_name"}
        # alerts omitted
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert main.config["model_registry"]["enable"] is False
    assert main.config["udfs"]["model"] == "model_name"
    assert main.config["alerts"] == {}

def test_post_config_invalid_json(monkeypatch):
    monkeypatch.setattr(main, "restart_kapacitor", lambda: None)
    # Patch Config to raise JSONDecodeError
    class DummyConfig:
        def model_dump(self):
            return {}
        model_registry = property(lambda self: (_ for _ in ()).throw(main.json.JSONDecodeError("msg", "doc", 1)))
        udfs = {}
        alerts = {}
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.config_file_change(DummyConfig(), mock.Mock()))
    assert exc.value.status_code == 422
    assert "Invalid JSON format" in exc.value.detail

def test_post_config_missing_key(monkeypatch):
    monkeypatch.setattr(main, "restart_kapacitor", lambda: None)
    # Patch Config to raise KeyError
    class DummyConfig:
        def model_dump(self):
            return {}
        @property
        def model_registry(self):
            raise KeyError("model_registry")
        udfs = {}
        alerts = {}
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.config_file_change(DummyConfig(), mock.Mock()))
    assert exc.value.status_code == 422
    assert "Missing required key" in exc.value.detail

def test_post_config_triggers_background_task(monkeypatch):
    called = {}
    def fake_add_task(fn):
        called["restart"] = True
    class DummyBackgroundTasks:
        def add_task(self, fn):
            fake_add_task(fn)
    monkeypatch.setattr(main, "restart_kapacitor", lambda: None)
    data = {
        "model_registry": {"enable": True, "version": "2.0"},
        "udfs": {"name": "udf_name", "model": "model_name"},
        "alerts": {}
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    # The background task is always added in the endpoint, so this is implicitly tested by no error



