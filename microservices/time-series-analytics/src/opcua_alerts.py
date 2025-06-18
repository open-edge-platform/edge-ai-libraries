#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
from asyncua import Client
import os
import logging
import time
import sys


log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger()

class OpcuaAlerts:

    def __init__(self, config):
        self.config = config
        self.client = None
        self.node_id = None
        self.namespace = None
        self.opcua_server = None
        
        
    def load_opcua_config(self):
        try:
            self.node_id = self.config["alerts"]["opcua"]["node_id"]
            self.namespace = self.config["alerts"]["opcua"]["namespace"]
            self.opcua_server = self.config["alerts"]["opcua"]["opcua_server"]
            return self.node_id, self.namespace, self.opcua_server
        except Exception as e:
            logger.exception("Fetching app configuration failed, Error: {}".format(e))
            return None, None, None
    
    async def create_opcua_client(self):
        if self.opcua_server:
            logger.info(f"Creating OPC UA client for server: {self.opcua_server}")
            self.client = Client(self.opcua_server)
            self.client.application_uri = "urn:opcua:python:server"
            return self.client
        else:
            logger.error("OPC UA server URL is not provided in the configuration file.")
            return None

    async def connect_opcua_client(self, secure_mode, max_retries=10):
        logger.info(f"client - {self.client}")
        if self.client is None:
            logger.error("OPC UA client is not initialized.")
            return False
        attempt = 0
        while attempt < max_retries:
            try:
                if secure_mode.lower() == "true":
                    kapacitor_cert = "/run/secrets/time_series_analytics_microservice_Server_server_certificate.pem"
                    kapacitor_key = "/run/secrets/time_series_analytics_microservice_Server_server_key.pem"
                    self.client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{kapacitor_cert},{kapacitor_key}")
                    self.client.set_user("admin")
                logger.info(f"Attempting to connect to OPC UA server: {self.opcua_server} {self.client} (Attempt {attempt + 1})")
                await self.client.connect()
                logger.info(f"Connected to OPC UA server: {self.opcua_server} successfully.")
                return True
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                attempt += 1
                if attempt < max_retries:
                    logger.info(f"Retrying in {max_retries} seconds...")
                    time.sleep(max_retries)
                else:
                    logger.error(f"Max retries reached. Could not connect to the OPC UA server: {self.opcua_server}.")
                    if __name__ == "__main__":
                        sys.exit(1)
        return False

    async def initialize_opcua(self):
        self.node_id, self.namespace, self.opcua_server = self.load_opcua_config()
        self.client = await self.create_opcua_client()
        secure_mode = os.getenv("SECURE_MODE", "false")
        connected = await self.connect_opcua_client(secure_mode)
        if not connected:
            logger.error("Failed to connect to OPC UA server.")
            raise RuntimeError("Failed to connect to OPC UA server.")

    async def send_alert_to_opcua(self, alert_message):
        if self.client is None:
            logger.error("OPC UA client is not initialized.")
            return
        try:
            alert_node = self.client.get_node(f"ns={self.namespace};i={self.node_id}")
            await alert_node.write_value(alert_message)
            logger.info("ALERT sent to OPC UA server: {}".format(alert_message))
        except Exception as e:
            logger.error(e)
            raise Exception(f"Failed to send alert to OPC UA server node {self.node_id}: {e}")

    async def is_connected(self) -> bool:
        """
        Check if the OPC UA client is connected to the server.
        Returns True if connected, False otherwise.
        """
        try:
            node = self.client.get_node(f"ns={self.namespace};i={self.node_id}")
            await node.read_value()
            return True
        except Exception as e:
            logger.error(f"Error checking OP CUA connection status: {e}")
            return False
        
