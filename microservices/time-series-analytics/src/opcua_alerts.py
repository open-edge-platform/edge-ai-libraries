#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
from asyncua.sync import Client
import os
import logging
import time
import sys
# import json
# from fastapi import FastAPI, HTTPException, Request
# import uvicorn
# import threading


log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)
CONFIG = {}
# Configure logging
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger()
#app = FastAPI()
client = None
node_id = None
namespace = None
opcua_server = None

def load_opcua_config(CONFIG):
    try:
        node_id = CONFIG["alerts"]["opcua"]["node_id"]
        namespace = CONFIG["alerts"]["opcua"]["namespace"]
        opcua_server = CONFIG["alerts"]["opcua"]["opcua_server"]
        return node_id, namespace, opcua_server
    except Exception as e:
        logger.exception("Fetching app configuration failed, Error: {}".format(e))
        return None, None, None

def create_opcua_client(opcua_server):
    if opcua_server:
        client = Client(opcua_server)
        client.application_uri = "urn:opcua:python:server"
        return client
    else:
        logger.error("OPC UA server URL is not provided in the configuration file.")
        return None

def connect_opcua_client(client, secure_mode, opcua_server, max_retries=10):
    if client is None:
        logger.error("OPC UA client is not initialized.")
        return False
    attempt = 0
    while attempt < max_retries:
        try:
            if secure_mode.lower() == "true":
                kapacitor_cert = "/run/secrets/time_series_analytics_microservice_Server_server_certificate.pem"
                kapacitor_key = "/run/secrets/time_series_analytics_microservice_Server_server_key.pem"
                client.set_security_string(f"Basic256Sha256,SignAndEncrypt,{kapacitor_cert},{kapacitor_key}")
                client.set_user("admin")
            logger.info(f"Attempting to connect to OPC UA server: {opcua_server} (Attempt {attempt + 1})")
            client.connect()
            logger.info(f"Connected to OPC UA server: {opcua_server} successfully.")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            attempt += 1
            if attempt < max_retries:
                logger.info(f"Retrying in {max_retries} seconds...")
                time.sleep(max_retries)
            else:
                logger.error(f"Max retries reached. Could not connect to the OPC UA server: {opcua_server}.")
                if __name__ == "__main__":
                    sys.exit(1)
    return False


def initialize_opcua(CONFIG):
    global node_id, namespace, opcua_server, client
    node_id, namespace, opcua_server = load_opcua_config(CONFIG)
    client = create_opcua_client(opcua_server)
    secure_mode = os.getenv("SECURE_MODE", "false")
    connected = connect_opcua_client(client, secure_mode, opcua_server)
    if not connected:
        logger.error("Failed to connect to OPC UA server.")


async def send_alert_to_opcua_async(alert_message):
    if client is None:
        logger.error("OPC UA client is not initialized.")
        return
    try:
        alert_node = client.get_node(f"ns={namespace};i={node_id}")
        alert_node.write_value(alert_message)
        logger.debug("Alert sent to OPC UA server: {}".format(alert_message))
    except Exception as e:
        logger.exception(e)



# @app.get("/")
# def read_root():
#     return {"message": "FastAPI server is running"}

# def main(config):
#     # Start the FastAPI server
#     secure_mode = os.getenv("SECURE_MODE", "false")
#     global CONFIG
#     CONFIG = config
#     initialize_opcua()
#     #def run_server():
#     if secure_mode.lower() == "true":
#         uvicorn.run(app, host="0.0.0.0", port=5000, log_level=log_level.lower(), access_log=False, 
#                     ssl_certfile="/run/secrets/time_series_analytics_microservice_Server_server_certificate.pem", 
#                     ssl_keyfile="/run/secrets/time_series_analytics_microservice_Server_server_key.pem")
#     else:
#         uvicorn.run(app, host="0.0.0.0", port=5000, log_level=log_level.lower(), access_log=False)
# #server_thread = threading.Thread(target=run_server)
#     #server_thread.start()
