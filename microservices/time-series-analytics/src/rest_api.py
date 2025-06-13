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
import json
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Extra
from typing import Optional
import uvicorn
import subprocess
import threading
import classifier_startup
from fastapi import BackgroundTasks
import opcua_alerts
import socket

log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger()
app = FastAPI()

KAPACITOR_URL = os.getenv('KAPACITOR_URL','http://localhost:9092')
CONFIG_FILE = "/app/config.json"
global CONFIG

class DataPoint(BaseModel):
    topic: str
    tags: Optional[dict] = None
    fields: dict
    timestamp: Optional[int] = None

class Config(BaseModel):
    model_registry : dict = {"enable": False, "version": "1.0"}
    udfs: dict = {"name": "udf_name"}
    alerts: Optional[dict] = {}

class OpcuaAlerts(BaseModel):
   class Config:
       extra = Extra.allow

def json_to_line_protocol(data_point: DataPoint):

    tags = data_point.tags or {}
    tags_part = ''
    if tags:
        tags_part = ','.join([f"{key}={value}" for key, value in tags.items()])

    fields_part = ','.join([f"{key}={value}" for key, value in data_point.fields.items()])
    
    # Use current time in nanoseconds if timestamp is None
    ts = data_point.timestamp or int(time.time() * 1e9)

    if tags_part:
        line_protocol = f"{data_point.topic},{tags_part} {fields_part} {ts}"
    else:
        line_protocol = f"{data_point.topic} {fields_part} {ts}"
    logger.debug(f"Converted line protocol: {line_protocol}")
    return line_protocol

# def start_opcua_alerts(CONFIG):
#     try:
#         with socket.create_connection(("localhost", 5000), timeout=5):
#                 return
#     except (socket.timeout, socket.error) as e: 
#         opcua_thread = threading.Thread(target=opcua_alerts.main, args=(CONFIG,), daemon=True)
#         opcua_thread.start()

def start_kapacitor_service(CONFIG):
    # try:
    #     if "alerts" in CONFIG.keys() and "opcua" in CONFIG["alerts"].keys():
    #         start_opcua_alerts(CONFIG)
    classifier_startup.classifier_startup(CONFIG)
    # except subprocess.CalledProcessError as e:
    #     logger.error(f"Failed to start Kapacitor service: {e}")
    #     raise HTTPException(status_code=500, detail="Failed to start Kapacitor service")

def stop_kapacitor_service():

    out1 = subprocess.run(["ps", "-eaf"], stdout=subprocess.PIPE,
                                  check=False)
    out2 = subprocess.run(["grep", "kapacitord"], input=out1.stdout,
                                  stdout=subprocess.PIPE, check=False)
    if out2.returncode == 0:
        response = requests.get(f"{KAPACITOR_URL}/kapacitor/v1/tasks")
        tasks = response.json().get('tasks', [])
        id = tasks[0].get('id')
        logger.info(f"Stopping Kapacitor tasks: {id}")
        subprocess.run(["kapacitor", "disable", id], check=False)
        subprocess.run(["pkill", "-9", "kapacitord"], check=False)
    

@app.get("/")
def read_root():
    return {"message": "FastAPI Input server is running"}

@app.post("/opcua_alerts")
async def receive_alert(alert: OpcuaAlerts):
    try:
        if "alerts" in CONFIG.keys() and "opcua" in CONFIG["alerts"].keys():
            if not hasattr(opcua_alerts, "initialized") or not opcua_alerts.initialized:
                opcua_alerts.initialize_opcua(CONFIG)
                opcua_alerts.initialized = True
            alert_message = json.dumps(alert.model_dump())
            try:
                await opcua_alerts.send_alert_to_opcua_async(alert_message)
            except Exception as e:
                logger.exception(e)
            return {"status_code": 200, "status": "success", "message": "Alert received"}
        else:
            raise HTTPException(status_code=404, detail="OPC UA alerts are not configured in the service")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/input")
async def receive_data(data_point: DataPoint):
    """
    Receives a data point in JSON format, converts it to InfluxDB line protocol, and sends it to the Kapacitor service.

    The input JSON must include:
        - topic (str): The topic name.
        - tags (dict): Key-value pairs for tags (e.g., {"location": "factory1"}).
        - fields (dict): Key-value pairs for fields (e.g., {"temperature": 23.5}).
        - timestamp (int, optional): Epoch time in nanoseconds. If omitted, current time is used.

    Example request body:
    {
        "topic": "sensor_data",
        "tags": {"location": "factory1", "device": "sensorA"},
        "fields": {"temperature": 23.5, "humidity": 60},
        "timestamp": 1718000000000000000
    }

    Args:
        data_point (DataPoint): The data point to be processed, provided in the request body.
    Returns:
        dict: A status message indicating success or failure.
    Raises:
        HTTPException: If the Kapacitor service returns an error or if any exception occurs during processing.

    responses:
        '200':
        description: Data successfully sent to the Time series Analytics microservice
        content:
            application/json:
            schema:
                type: object
                properties:
                status:
                    type: string
                    example: success
                message:
                    type: string
                    example: Data sent to Time series Analytics microservice
        '4XX':
        description: Client error (e.g., invalid input or Kapacitor error)
        content:
            application/json:
            schema:
                $ref: '#/components/schemas/HTTPValidationError'
        '500':
        description: Internal server error
        content:
            application/json:
            schema:
                type: object
                properties:
                detail:
                    type: string
    """
    try:
        # Convert JSON to line protocol
        line_protocol = json_to_line_protocol(data_point)
        logging.info(f"Received data point: {line_protocol}")
        
        url = f"{KAPACITOR_URL}/kapacitor/v1/write?db=datain&rp=autogen"
        # Send data to Kapacitor
        response = requests.post(url, data=line_protocol, headers={"Content-Type": "text/plain"})

        if response.status_code == 204:
            return {"status": "success", "message": "Data sent to Time series Analytics microservice"}
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/config")
async def get_config():
    """
    Endpoint to retrieve the current configuration of the input service.
    Returns the current configuration in JSON format.

    ---
    responses:
        200:
            description: Current configuration retrieved successfully
            content:
                application/json:
                    schema:
                        type: object
                        additionalProperties: true
                        example:
                            {
                                "model_registry": {},
                                "udfs": {},
                                "alerts": {}
                            }
        500:
            description: Failed to retrieve configuration
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Failed to retrieve configuration"
    """
    try:
        return CONFIG
    except Exception as e:
        logger.error(f"Error retrieving configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config")
async def config_file_change(config_data: Config, background_tasks: BackgroundTasks):
    """
    Endpoint to handle configuration changes.
    This endpoint can be used to update the configuration of the input service.
    Updates the configuration of the input service with the provided key-value pairs.

    ---
    requestBody:
        required: true
        content:
            application/json:
                schema:
                    type: object
                    additionalProperties: true
                example:
                    {"model_registry": {
                        "enable": true
                        "version": "2.0"
                    },
                    "udfs": {
                        "name": "udf_name",
                        "model": "model_name"}
                    "alerts": {
                    }
    responses:
        200:
            description: Configuration updated successfully
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            status:
                                type: string
                                example: "success"
                            message:
                                type: string
                                example: "Configuration updated successfully"
        400:
            description: Invalid input or error processing request
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Error message"
        500:
            description: Failed to write configuration to file
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Failed to write configuration to file"
    """
    try:
        CONFIG = {}
        CONFIG["model_registry"] = config_data.model_registry
        CONFIG["udfs"] = config_data.udfs
        if config_data.alerts:
            CONFIG["alerts"] = config_data.alerts
        logger.debug(f"Received configuration data: {CONFIG}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in configuration data: {e}")
        raise HTTPException(status_code=422, detail="Invalid JSON format in configuration data")
    except KeyError as e:
        logger.error(f"Missing required key in configuration data: {e}")
        raise HTTPException(status_code=422, detail=f"Missing required key: {e}")

    def restart_kapacitor():
        stop_kapacitor_service()
        start_kapacitor_service(CONFIG)

    background_tasks.add_task(restart_kapacitor)
    return {"status": "success", "message": "Configuration updated successfully"}


if __name__ == "__main__":
    # Start the FastAPI server
    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=5000)

    server_thread = threading.Thread(target=run_server)
    server_thread.start()
    CONFIG = {}
    try:
        with open (CONFIG_FILE, 'r') as file:
            CONFIG = json.load(file)
        logger.info("App configuration loaded successfully from config.json file")
        start_kapacitor_service(CONFIG)
    except FileNotFoundError:
        logger.info("config.json file not found, waiting for the configuration")
    except Exception as e:
        logger.info(f"Time Series Microservice failure - {e}")


    