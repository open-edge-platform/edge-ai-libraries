from unittest.mock import MagicMock, patch

# Import the module to test
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from rabbitmq_mqtt_client import RabbitMQMQTTClient


class TestRabbitMQMQTTClient:
    """Test cases for RabbitMQMQTTClient class."""

    @patch("rabbitmq_mqtt_client.mqtt.Client")
    def test_init_and_callbacks(self, mock_mqtt_client):
        """
        Verifies correct initialization, connection, disconnection, and publish callbacks.
        """
        # Setup
        mock_instance = MagicMock()
        mock_mqtt_client.return_value = mock_instance

        # Initialize client
        client = RabbitMQMQTTClient("test_broker", 1883, "test_user", "test_pass")

        # Verify initialization
        mock_instance.username_pw_set.assert_called_once_with("test_user", "test_pass")
        mock_instance.connect.assert_called_once_with("test_broker", 1883, keepalive=10)
        assert mock_instance.loop_start.call_count == 1

        # Test on_connect callback (successful connection)
        client.connected = False
        client.on_connect(MagicMock(), MagicMock(), MagicMock(), 0)
        assert client.connected is True

        # Test on_disconnect callback
        client.on_disconnect(MagicMock(), MagicMock(), 0)
        assert client.connected is False

        # Test on_publish callback
        client.publish_complete = False
        client.on_publish(MagicMock(), MagicMock(), 1234)
        assert client.publish_complete is True

        # Test is_connected method
        client.connected = True
        assert client.is_connected() is True
        client.connected = False
        assert client.is_connected() is False

    @patch("rabbitmq_mqtt_client.mqtt.Client")
    def test_publish(self, mock_mqtt_client):
        """
        Ensures publish method handles both successful and failed publish states correctly.
        """
        mock_instance = MagicMock()
        mock_mqtt_client.return_value = mock_instance

        # Create client
        client = RabbitMQMQTTClient("test_broker", 1883, "test_user", "test_pass")

        # Test successful publish
        mock_instance.publish.return_value = (0, 1)  # (rc, mid)
        client.publish_complete = True  # Reset
        client.publish("test_topic", "test_message")
        mock_instance.publish.assert_called_with(
            "test_topic", "test_message", qos=0, retain=False
        )
        assert client.publish_complete is False

        # Test failed publish
        mock_instance.publish.return_value = (1, None)  # Error state
        client.publish("test_topic2", "test_message2")  # Should not raise

    @patch("rabbitmq_mqtt_client.mqtt.Client")
    def test_disconnect_and_stop(self, mock_mqtt_client):
        """
        Checks disconnection and stopping the MQTT client loop, ensuring calls are made only when connected.
        """
        mock_instance = MagicMock()
        mock_mqtt_client.return_value = mock_instance
        client = RabbitMQMQTTClient("test_broker", 1883, "test_user", "test_pass")

        # Test disconnect when connected
        client.connected = True
        client.disconnect()
        mock_instance.disconnect.assert_called_once()

        # Test disconnect when not connected
        mock_instance.reset_mock()
        client.connected = False
        client.disconnect()
        mock_instance.disconnect.assert_not_called()

        # Test stop method
        client.connected = True
        client.stop()
        assert mock_instance.loop_stop.call_count == 1
        assert mock_instance.disconnect.call_count == 1
