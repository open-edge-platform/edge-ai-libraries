#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""
OPC UA Alerts Module.

This module provides functionality for sending alerts to OPC UA servers
in the Time Series Analytics Microservice.
"""
import os
import logging
import time
import sys
import json
from asyncua import Client

log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger()


class OpcuaAlerts:
    """Class for handling OPC UA alerts communication."""

    def __init__(self, config):
        """
        Initialize OPC UA alerts handler.
        
        Args:
            config: Configuration dictionary containing OPC UA settings
        """
        self.config = config
        self.client = None
        self.node_id = None
        self.namespace = None
        self.opcua_server = None

    def load_opcua_config(self):
        """
        Load OPC UA configuration from the config dictionary.
        
        Returns:
            tuple: (node_id, namespace, opcua_server) or (None, None, None) if error
        """
        try:
            self.node_id = self.config["alerts"]["opcua"]["node_id"]
            self.namespace = self.config["alerts"]["opcua"]["namespace"]
            self.opcua_server = self.config["alerts"]["opcua"]["opcua_server"]
            return self.node_id, self.namespace, self.opcua_server
        except Exception as error:
            logger.exception("Fetching app configuration failed, Error: %s", error)
            return None, None, None


    async def connect_opcua_client(self, secure_mode, max_retries=10):
        """
        Connect to OPC UA client with retry mechanism.
        
        Args:
            secure_mode: String indicating if secure mode should be used
            max_retries: Maximum number of connection retry attempts
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        if self.opcua_server:
            logger.info("Creating OPC UA client for server: %s", self.opcua_server)
            self.client = Client(self.opcua_server)
            self.client.application_uri = "urn:opcua:python:server"
        else:
            logger.error("OPC UA server URL is not provided in the configuration file.")
            return None

        if self.client is None:
            logger.error("OPC UA client is not initialized.")
            return False
        attempt = 0
        while attempt < max_retries:
            try:
                if secure_mode.lower() == "true":
                    kapacitor_cert = ("/run/secrets/"
                                    "time_series_analytics_microservice_Server_server_certificate.pem")
                    kapacitor_key = ("/run/secrets/"
                                   "time_series_analytics_microservice_Server_server_key.pem")
                    self.client.set_security_string(
                        f"Basic256Sha256,SignAndEncrypt,{kapacitor_cert},{kapacitor_key}")
                    self.client.set_user("admin")
                logger.info("Attempting to connect to OPC UA server: %s "
                            "%s (Attempt %s)", self.opcua_server, self.client, attempt + 1)
                await self.client.connect()
                logger.info("Connected to OPC UA server: %s successfully.", self.opcua_server)
                return True
            except Exception as error:
                logger.error("Connection failed: %s", error)
                attempt += 1
                if attempt < max_retries:
                    logger.info("Retrying in %s seconds...", max_retries)
                    time.sleep(max_retries)
                else:
                    logger.error("Max retries reached. Could not connect to the OPC UA server: %s",
                                 self.opcua_server)
                    if __name__ == "__main__":
                        sys.exit(1)
        return False

    async def initialize_opcua(self):
        """
        Initialize OPC UA connection using configuration settings.
        
        Raises:
            RuntimeError: If connection to OPC UA server fails
        """
        self.node_id, self.namespace, self.opcua_server = self.load_opcua_config()
        secure_mode = os.getenv("SECURE_MODE", "false")
        connected = await self.connect_opcua_client(secure_mode)
        if not connected:
            logger.error("Failed to connect to OPC UA server.")
            raise RuntimeError("Failed to connect to OPC UA server.")

    async def send_alert_to_opcua(self, alert_message):
        """
        Send alert message to OPC UA server.
        
        Args:
            alert_message: JSON string containing alert data
            
        Raises:
            RuntimeError: If sending alert fails
        """
        if self.client is None:
            logger.error("OPC UA client is not initialized.")
            return
        try:
            alert_node = self.client.get_node(f"ns={self.namespace};i={self.node_id}")
            await alert_node.write_value(alert_message)
            alert_dict = json.loads(alert_message)
            alert_message_text = alert_dict.get("message", "")
            logger.info("ALERT sent to OPC UA server: %s", alert_message_text)
        except Exception as error:
            logger.error("%s", error)
            raise RuntimeError(f"Failed to send alert to OPC UA server node \
                               {self.node_id}: {error}")

    async def is_connected(self) -> bool:
        """
        Check if the OPC UA client is connected to the server.
        Returns True if connected, False otherwise.
        """
        try:
            node = self.client.get_node(f"ns={self.namespace};i={self.node_id}")
            await node.read_value()
            return True
        except Exception as error:
            logger.error("Error checking OPC UA connection status: %s", error)
            return False
