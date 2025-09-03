#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, mock_open
import types
from unittest.mock import patch, MagicMock, AsyncMock
from opcua_alerts import OpcuaAlerts


@pytest.fixture
def valid_config():
    return {
        "alerts": {
            "opcua": {
                "node_id": "123",
                "namespace": "2",
                "opcua_server": "opc.tcp://localhost:4840"
            }
        }
    }

@pytest.fixture
def invalid_config():
    return {}

def test_load_opcua_config_success(valid_config):
    alerts = OpcuaAlerts(valid_config)
    node_id, namespace, opcua_server = alerts.load_opcua_config()
    assert node_id == "123"
    assert namespace == "2"
    assert opcua_server == "opc.tcp://localhost:4840"

def test_load_opcua_config_failure(invalid_config, caplog):
    alerts = OpcuaAlerts(invalid_config)
    node_id, namespace, opcua_server = alerts.load_opcua_config()
    assert node_id is None
    assert namespace is None
    assert opcua_server is None
    assert "Fetching app configuration failed" in caplog.text

@pytest.mark.asyncio
async def test_connect_opcua_client_success(valid_config):
    alerts = OpcuaAlerts(valid_config)
    alerts.node_id, alerts.namespace, alerts.opcua_server = alerts.load_opcua_config()
    with patch("opcua_alerts.Client") as MockClient:
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.connect.return_value = None
        result = await alerts.connect_opcua_client("false")
        assert result is True
        mock_client_instance.connect.assert_awaited_once()

@pytest.mark.asyncio
async def test_connect_opcua_client_secure_mode(valid_config):
    alerts = OpcuaAlerts(valid_config)
    alerts.node_id, alerts.namespace, alerts.opcua_server = alerts.load_opcua_config()
    with patch("opcua_alerts.Client") as MockClient:
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.connect.return_value = None
        mock_client_instance.set_security_string.return_value = None
        mock_client_instance.set_user.return_value = None
        result = await alerts.connect_opcua_client("true")
        assert result is True
        mock_client_instance.set_security_string.assert_called()
        mock_client_instance.set_user.assert_called_with("admin")
        mock_client_instance.connect.assert_awaited_once()

@pytest.mark.asyncio
async def test_connect_opcua_client_failure(valid_config):
    alerts = OpcuaAlerts(valid_config)
    alerts.node_id, alerts.namespace, alerts.opcua_server = alerts.load_opcua_config()
    with patch("opcua_alerts.Client") as MockClient, patch("opcua_alerts.time.sleep", return_value=None):
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance
        mock_client_instance.connect.side_effect = Exception("fail")
        # Patch sys.exit to prevent exiting test runner
        with patch("opcua_alerts.sys.exit") as mock_exit:
            result = await alerts.connect_opcua_client("false", max_retries=2)
            assert result is False or result is None
            assert mock_client_instance.connect.await_count == 2

@pytest.mark.asyncio
async def test_connect_opcua_client_no_server(valid_config):
    alerts = OpcuaAlerts(valid_config)
    alerts.opcua_server = None
    result = await alerts.connect_opcua_client("false")
    assert result is None

@pytest.mark.asyncio
async def test_initialize_opcua_success(valid_config):
    alerts = OpcuaAlerts(valid_config)
    with patch.object(alerts, "connect_opcua_client", new=AsyncMock(return_value=True)):
        await alerts.initialize_opcua()
        assert alerts.node_id == "123"
        assert alerts.namespace == "2"
        assert alerts.opcua_server == "opc.tcp://localhost:4840"

@pytest.mark.asyncio
async def test_initialize_opcua_failure(valid_config):
    alerts = OpcuaAlerts(valid_config)
    with patch.object(alerts, "connect_opcua_client", new=AsyncMock(return_value=False)):
        with pytest.raises(RuntimeError):
            await alerts.initialize_opcua()

@pytest.mark.asyncio
async def test_send_alert_to_opcua_success(valid_config):
    alerts = OpcuaAlerts(valid_config)
    alerts.node_id, alerts.namespace, alerts.opcua_server = alerts.load_opcua_config()
    alerts.client = MagicMock()
    mock_node = AsyncMock()
    alerts.client.get_node.return_value = mock_node
    alert_message = json.dumps({"message": "test alert"})
    await alerts.send_alert_to_opcua(alert_message)
    alerts.client.get_node.assert_called_with("ns=2;i=123")
    mock_node.write_value.assert_awaited_with(alert_message)

@pytest.mark.asyncio
async def test_send_alert_to_opcua_no_client(valid_config, caplog):
    alerts = OpcuaAlerts(valid_config)
    alerts.client = None
    await alerts.send_alert_to_opcua("test")
    assert "OPC UA client is not initialized." in caplog.text

@pytest.mark.asyncio
async def test_send_alert_to_opcua_exception(valid_config):
    alerts = OpcuaAlerts(valid_config)
    alerts.node_id, alerts.namespace, alerts.opcua_server = alerts.load_opcua_config()
    alerts.client = MagicMock()
    alerts.client.get_node.side_effect = Exception("fail")
    with pytest.raises(Exception) as excinfo:
        await alerts.send_alert_to_opcua("test")
    assert "Failed to send alert to OPC UA server node" in str(excinfo.value)

@pytest.mark.asyncio
async def test_is_connected_true(valid_config):
    alerts = OpcuaAlerts(valid_config)
    alerts.node_id, alerts.namespace, alerts.opcua_server = alerts.load_opcua_config()
    alerts.client = MagicMock()
    mock_node = AsyncMock()
    alerts.client.get_node.return_value = mock_node
    mock_node.read_value.return_value = "some_value"
    result = await alerts.is_connected()
    assert result is True
    alerts.client.get_node.assert_called_with("ns=2;i=123")
    mock_node.read_value.assert_awaited_once()

@pytest.mark.asyncio
async def test_is_connected_false(valid_config, caplog):
    alerts = OpcuaAlerts(valid_config)
    alerts.node_id, alerts.namespace, alerts.opcua_server = alerts.load_opcua_config()
    alerts.client = MagicMock()
    alerts.client.get_node.side_effect = Exception("fail")
    result = await alerts.is_connected()
    assert result is False
    assert "Error checking OPC UA connection status" in caplog.text
