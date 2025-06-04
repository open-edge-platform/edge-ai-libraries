#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, mock_open
import sys

import opcua_alerts

@pytest.fixture
def client():
    return TestClient(opcua_alerts.app)

def test_load_opcua_config_success(tmp_path):
    config = {
        "config": {
            "alerts": {
                "opcua": {
                    "node_id": "123",
                    "namespace": "2",
                    "opcua_server": "opc.tcp://localhost:4840"
                }
            }
        }
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    node_id, namespace, opcua_server = opcua_alerts.load_opcua_config(str(config_file))
    assert node_id == "123"
    assert namespace == "2"
    assert opcua_server == "opc.tcp://localhost:4840"

def test_load_opcua_config_failure():
    with patch("builtins.open", side_effect=Exception("fail")):
        node_id, namespace, opcua_server = opcua_alerts.load_opcua_config("badfile.json")
        assert node_id is None
        assert namespace is None
        assert opcua_server is None

def test_create_opcua_client_success():
    @patch("opcua_alerts.Client")
    def test_successful_connection(self, MockClient):
        # Create a mock instance of the Client
        mock_client_instance = MockClient.return_value
        
        # Mock the connect method to simulate a successful connection
        mock_client_instance.connect.return_value = None
        
        # Call the function to test
        client = opcua_alerts.create_opcua_client("test_opcua_server")
        
        # Assert that the Client was initialized with the correct server URL
        MockClient.assert_called_once_with("test_opcua_server")
        
        # Assert that the connect method was called on the client instance
        mock_client_instance.connect.assert_called_once()
        
        # Assert that the returned client is the mock instance
        self.assertEqual(client, mock_client_instance)

def test_create_opcua_client_no_server():
    client = opcua_alerts.create_opcua_client(None)
    assert client is None

def test_connect_opcua_client_success():
    mock_client = MagicMock()
    mock_client.connect.return_value = None
    result = opcua_alerts.connect_opcua_client(mock_client, "false", "opc.tcp://localhost:4840")
    assert result is True
    mock_client.connect.assert_called_once()

def test_connect_opcua_client_secure_mode():
    mock_client = MagicMock()
    mock_client.connect.return_value = None
    mock_client.set_security_string.return_value = None
    mock_client.set_user.return_value = None
    result = opcua_alerts.connect_opcua_client(mock_client, "true", "opc.tcp://localhost:4840")
    assert result is True
    mock_client.set_security_string.assert_called()
    mock_client.set_user.assert_called_with("admin")
    mock_client.connect.assert_called_once()

def test_connect_opcua_client_failure(monkeypatch):
    mock_client = MagicMock()
    mock_client.connect.side_effect = Exception("fail")
    # Patch sys.exit to prevent exiting test runner
    monkeypatch.setattr(sys, "exit", lambda code: None)
    result = opcua_alerts.connect_opcua_client(mock_client, "false", "opc.tcp://localhost:4840", max_retries=1)
    assert result is False

@pytest.mark.asyncio
async def test_send_alert_to_opcua_async_success(monkeypatch):
    opcua_alerts.client = MagicMock()
    opcua_alerts.namespace = "2"
    opcua_alerts.node_id = "123"
    mock_node = MagicMock()
    opcua_alerts.client.get_node.return_value = mock_node
    await opcua_alerts.send_alert_to_opcua_async("test alert")
    opcua_alerts.client.get_node.assert_called_with("ns=2;i=123")
    mock_node.write_value.assert_called_with("test alert")

@pytest.mark.asyncio
async def test_send_alert_to_opcua_async_no_client(caplog):
    opcua_alerts.client = None
    await opcua_alerts.send_alert_to_opcua_async("test alert")
    assert "OPC UA client is not initialized." in caplog.text

@pytest.mark.asyncio
async def test_send_alert_to_opcua_async_exception(monkeypatch, caplog):
    opcua_alerts.client = MagicMock()
    opcua_alerts.namespace = "2"
    opcua_alerts.node_id = "123"
    opcua_alerts.client.get_node.side_effect = Exception("fail")
    await opcua_alerts.send_alert_to_opcua_async("test alert")
    assert "fail" in caplog.text

def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "FastAPI server is running"}

def test_receive_alert_success(client):
    with patch.object(opcua_alerts, "send_alert_to_opcua_async") as mock_send:
        mock_send.return_value = None
        response = client.post("/opcua_alerts", json={"message": "alert!"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_send.assert_called_once_with("alert!")

def test_receive_alert_bad_json(client):
    response = client.post("/opcua_alerts", data="notjson", headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert "Expecting value" in response.json()["detail"]

def test_startup_event_success(monkeypatch):
    # Patch dependencies used in startup_event
    mock_load = MagicMock(return_value=("123", "2", "opc.tcp://localhost:4840"))
    mock_create = MagicMock()
    mock_connect = MagicMock(return_value=True)
    monkeypatch.setattr(opcua_alerts, "load_opcua_config", mock_load)
    monkeypatch.setattr(opcua_alerts, "create_opcua_client", mock_create)
    monkeypatch.setattr(opcua_alerts, "connect_opcua_client", mock_connect)
    monkeypatch.setattr(opcua_alerts.os, "getenv", lambda key, default=None: "false")
    # Call the startup_event function
    opcua_alerts.startup_event()
    mock_load.assert_called_once_with("/app/config.json")
    mock_create.assert_called_once_with("opc.tcp://localhost:4840")
    mock_connect.assert_called_once_with(mock_create.return_value, "false", "opc.tcp://localhost:4840")

def test_startup_event_failed_connection(monkeypatch, caplog):
    mock_load = MagicMock(return_value=("123", "2", "opc.tcp://localhost:4840"))
    mock_create = MagicMock()
    mock_connect = MagicMock(return_value=False)
    monkeypatch.setattr(opcua_alerts, "load_opcua_config", mock_load)
    monkeypatch.setattr(opcua_alerts, "create_opcua_client", mock_create)
    monkeypatch.setattr(opcua_alerts, "connect_opcua_client", mock_connect)
    monkeypatch.setattr(opcua_alerts.os, "getenv", lambda key, default=None: "false")
    opcua_alerts.startup_event()
    assert "Failed to connect to OPC UA server." in caplog.text
