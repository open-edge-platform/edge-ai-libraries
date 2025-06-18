# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import paho.mqtt.client as mqtt

class RabbitMQMQTTClient:
    def __init__(self, broker, port, username, password):
        self.log = logging.getLogger('RABBITMQ_MQTT_CLIENT')
        self.log.setLevel(logging.INFO)
        self.log.debug(f"In {__name__}...")

        self.broker = broker
        self.port = port
        self.username = username
        self.password = password

        # Connection status flag
        self.connected = False
        # Flag to track publish confirmation
        self.publish_complete = False

        # Create the MQTT client instance.
        self.client = mqtt.Client()

        # Set username and password for authentication.
        self.client.username_pw_set(self.username, self.password)

        # Assign callback methods.
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish

        # Auto-connect and start the network loop.
        self.log.info(f"Connecting to MQTT Broker at {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port, keepalive=10)
        self.client.loop_start()  # Start the loop as soon as the object is created.
        self.log.info("Network loop started.")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            self.log.info(f"Connected successfully to {self.broker}:{self.port}")
        else:
            self.log.info(f"Connection failed with code {rc}")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        self.log.info(f"Disconnecting from broker with code{rc}")

    def on_publish(self, client, userdata, mid):
        self.log.info(f"Publish confirmed (mid = {mid})")
        self.publish_complete = True

    def is_connected(self):
        """Return the connection status."""
        return self.connected

    def publish(self, topic, message, qos=0, retain=False):
        """Publish a message to a given topic."""
        self.publish_complete = False
        result = self.client.publish(topic, message, qos=qos, retain=retain)
        status = result[0]
        if status == 0:
            self.log.debug(f"Publishing message to topic '{topic}': {message}")
        else:
            self.log.info(f"Failed to publish message to topic '{topic}' (status {status})")

    def disconnect(self):
        """Disconnect from the broker."""
        if self.connected:
            self.client.disconnect()
            self.log.info("Disconnected from broker...")

    def stop(self):
        """Stop the MQTT client loop and disconnect."""
        self.client.loop_stop()
        self.disconnect()
        self.log.info("MQTT client loop stopped and disconnected.")
