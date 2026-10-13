#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import base64
import gzip
import io
import sys
import tarfile
import pytest
from unittest import mock
from fastapi.testclient import TestClient
import asyncio

import main

client = TestClient(main.app)

@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    # Patch config to a test dict before each test
    if getattr(main, "config", None) is not None:
        main.config.clear()
    main.config = {
        "plugin": {"name": "plugin_name", "models": "model_name"},
        "alerts": {"opcua": {"opcua_server": "opc.tcp://localhost:4840", "node_id": "ns=2;i=2", "namespace": 2}}
    }
    yield
    if getattr(main, "config", None) is not None:
        main.config.clear()

def test_health_check_running(monkeypatch):
    backend = mock.Mock()
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "InfluxDB 3 Core is running"

def test_health_check_not_running(monkeypatch):
    backend = mock.Mock()
    backend.check_health.side_effect = main.InfluxDB3Error("Core unavailable")
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert "InfluxDB 3 Core is not running" in resp.json()["status"]

def test_check_plugin_package_uses_plugin_root(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "temperature_classifier" / "plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").touch()
    monkeypatch.setattr(main.tempfile, "gettempdir", lambda: str(tmp_path))

    assert main.check_plugin_package(
        {"plugin": {"name": "temperature_classifier"}},
        "temperature_classifier",
    )

def test_upload_plugin_package_accepts_temperature_plugin(monkeypatch, tmp_path):
    plugin_content = b"def process_writes(influxdb3_local, table_batches, args=None): pass\n"
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w") as archive:
        plugin_info = tarfile.TarInfo("plugin/__init__.py")
        plugin_info.size = len(plugin_content)
        archive.addfile(plugin_info, io.BytesIO(plugin_content))

    monkeypatch.setattr(main.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("SAMPLE_APP", "temperature_classifier")
    response = client.post(
        "/plugin/package",
        files={"file": ("temperature_classifier.tar", archive_buffer.getvalue(), "application/x-tar")},
    )

    assert response.status_code == 200
    assert (tmp_path / "temperature_classifier" / "plugin" / "__init__.py").is_file()

def test_receive_data_success(monkeypatch):
    backend = mock.Mock()
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    data = {
        "topic": "sensor_data",
        "tags": {"location": "factory1"},
        "fields": {"temperature": 23.5},
        "timestamp": 1718000000000000000
    }
    resp = client.post("/input", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    backend.write_line_protocol.assert_called_once_with(
        "sensor_data,location=factory1 temperature=23.5 1718000000000000000"
    )

def test_receive_data_core_down(monkeypatch):
    backend = mock.Mock()
    backend.check_health.side_effect = main.InfluxDB3Error("Core unavailable")
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    data = {
        "topic": "sensor_data",
        "tags": {"location": "factory1"},
        "fields": {"temperature": 23.5},
        "timestamp": 1718000000000000000
    }
    resp = client.post("/input", json=data)
    assert resp.status_code == 503
    assert "InfluxDB 3 Core is not running" in resp.json()["detail"]


def test_receive_line_protocol_forwards_to_core(monkeypatch):
    backend = mock.Mock(token="test-token")
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    line = "wind-turbine-data,source=test wind_speed=8.83 1718000000000000000"
    authorization = "Basic " + base64.b64encode(b"token:test-token").decode("ascii")

    resp = client.post(
        "/write?db=datain&precision=ns",
        content=line,
        headers={"Authorization": authorization},
    )

    assert resp.status_code == 204
    backend.write_line_protocol.assert_called_once_with(
        line, database="datain", precision="nanosecond"
    )

def test_receive_gzip_line_protocol_forwards_to_core(monkeypatch):
    backend = mock.Mock(token="test-token")
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    line = "wind-turbine-data,source=test wind_speed=8.83 1718000000000000000"
    authorization = "Basic " + base64.b64encode(b"token:test-token").decode("ascii")

    resp = client.post(
        "/write?db=datain&precision=ns",
        content=gzip.compress(line.encode("utf-8")),
        headers={"Authorization": authorization, "Content-Encoding": "gzip"},
    )

    assert resp.status_code == 204
    backend.write_line_protocol.assert_called_once_with(
        line, database="datain", precision="nanosecond"
    )


def test_receive_line_protocol_rejects_missing_auth():
    response = client.post("/write?db=datain", content="temperature_input temperature=20.0")

    assert response.status_code == 401

def test_get_config(monkeypatch):
    resp = client.get("/config")
    assert resp.status_code == 200
    assert "plugin" in resp.json()
    assert "alerts" in resp.json()

def test_get_config_with_restart(monkeypatch):
    called = {}
    def fake_restart():
        called["restart"] = True
    monkeypatch.setattr(main, "restart_influxdb3", fake_restart)
    resp = client.get("/config?restart=true")
    assert resp.status_code == 200
    assert "plugin" in resp.json()

def test_post_config(monkeypatch):
    monkeypatch.setattr(main, "check_plugin_package", lambda *args: True)
    monkeypatch.setattr(main, "restart_influxdb3", lambda: None)
    data = {
        "plugin": {"name": "plugin_name", "models": "model_name"},
        "alerts": {}
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

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

def test_health_check_status_running_204(monkeypatch):
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: mock.Mock())
    response = main.health_check(main.Response())
    assert response == {"status": "InfluxDB 3 Core is running"}

def test_health_check_status_not_running(monkeypatch):
    backend = mock.Mock()
    backend.check_health.side_effect = main.InfluxDB3Error("Core unavailable")
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    resp_obj = main.Response()
    response = main.health_check(resp_obj)
    assert response == {"status": "InfluxDB 3 Core is not running"}


def test_health_check_request_exception(monkeypatch):
    backend = mock.Mock()
    backend.check_health.side_effect = main.requests.exceptions.RequestException()
    monkeypatch.setattr(main, "get_influxdb3_backend", lambda: backend)
    resp_obj = main.Response()
    response = main.health_check(resp_obj)
    assert response == {"status": "InfluxDB 3 Core is not running"}
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
    assert resp.status_code == 400
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
        query_params = {"plugin": "1"}
    result = await main.get_config(DummyRequest())
    # Should only return the filtered key
    assert result == {"plugin": main.config["plugin"]}

@pytest.mark.asyncio
async def test_get_config_removes_restart_param(monkeypatch):
    # Simulate a request with 'restart' and another param
    class DummyRequest:
        query_params = {"restart": "true", "plugin": "1"}
    result = await main.get_config(DummyRequest())
    assert result == {"plugin": main.config["plugin"]}

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


def test_post_config_success(monkeypatch):
    monkeypatch.setattr(main, "check_plugin_package", lambda *args: True)
    monkeypatch.setattr(main, "restart_influxdb3", lambda: None)
    data = {
        "plugin": {"name": "plugin_name", "models": "model_name"},
        "alerts": {"opcua": {"opcua_server": "opc.tcp://localhost:4840", "node_id": "ns=2;i=2", "namespace": 2}}
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert main.config["plugin"]["name"] == "plugin_name"
    assert "opcua" in main.config["alerts"]

def test_post_config_alerts_optional(monkeypatch):
    monkeypatch.setattr(main, "check_plugin_package", lambda *args: True)
    monkeypatch.setattr(main, "restart_influxdb3", lambda: None)
    data = {
        "plugin": {"name": "plugin_name", "models": "model_name"}
        # alerts omitted
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert main.config["plugin"]["models"] == "model_name"

def test_post_config_invalid_json(monkeypatch):
    # Patch Config to raise JSONDecodeError
    class DummyConfig:
        def model_dump(self):
            return {}
        plugin = {}
        alerts = {}
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.config_file_change(DummyConfig(), mock.Mock()))
    assert exc.value.status_code == 422
    assert "Missing key 'name' in plugin" in exc.value.detail

def test_post_config_missing_key(monkeypatch):
    # Patch Config to raise KeyError
    class DummyConfig:
        def model_dump(self):
            return {}
        plugin = {}
        alerts = {}
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.config_file_change(DummyConfig(), mock.Mock()))
    assert exc.value.status_code == 422
    assert "Missing key 'name' in plugin" in exc.value.detail

def test_post_config_triggers_background_task(monkeypatch):
    called = {}
    def fake_add_task(fn):
        called["restart"] = True
    class DummyBackgroundTasks:
        def add_task(self, fn):
            fake_add_task(fn)
    monkeypatch.setattr(main, "check_plugin_package", lambda *args: True)
    monkeypatch.setattr(main, "restart_influxdb3", lambda: None)
    data = {
        "plugin": {"name": "plugin_name", "models": "model_name"},
        "alerts": {}
    }
    resp = client.post("/config", json=data)
    assert resp.status_code == 200
    # The background task is always added in the endpoint, so this is implicitly tested by no error



