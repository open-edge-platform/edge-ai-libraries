#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
import os
import logging
import time
import json
import requests
from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel
from typing import Optional
import uvicorn
import subprocess
import threading
import classifier_startup
from fastapi import BackgroundTasks
from opcua_alerts import OpcuaAlerts

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
config = {}
opcua_send_alert = None

class DataPoint(BaseModel):
    topic: str
    tags: Optional[dict] = None
    fields: dict
    timestamp: Optional[int] = None

class Config(BaseModel):
    model_registry : dict = {"enable": False, "version": "1.0"}
    udfs: dict = {"name": "udf_name"}
    alerts: Optional[dict] = {}

class Opcua_Alerts_Message(BaseModel):
   class Config:
       extra = 'allow'

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

def start_kapacitor_service(config):
    classifier_startup.classifier_startup(config)

def stop_kapacitor_service():
    response = Response()
    result = health_check(response)
    if result["status"] != "kapacitor daemon is running":
        logger.info("Kapacitor daemon is not running.")
        return
    try:
        response = requests.get(f"{KAPACITOR_URL}/kapacitor/v1/tasks")
        tasks = response.json().get('tasks', [])
        id = tasks[0].get('id')
        logger.info(f"Stopping Kapacitor tasks: {id}")
        subprocess.run(["kapacitor", "disable", id], check=False)
        subprocess.run(["pkill", "-9", "kapacitord"], check=False)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error stopping Kapacitor service: {e}")


@app.get("/")
def read_root():
    """Get health status of the Input server."""
    return {"message": "FastAPI Input server is running"}

@app.get("/health")
def health_check(response: Response):
    """Get the health status of the kapacitor daemon."""
    url = f"{KAPACITOR_URL}/kapacitor/v1/ping"
    try:
        # Make an HTTP GET request to the service
        r = requests.get(url, timeout=1)
        if r.status_code == 200 or r.status_code == 204:
            return {"status": "kapacitor daemon is running"}
        else:
            r.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "kapacitor daemon is not running properly"}
    except requests.exceptions.ConnectionError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "Port not accessible and kapacitor daemon not running"}
    except requests.exceptions.RequestException:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "An error occurred while checking the service"}

@app.post("/opcua_alerts")
async def receive_alert(alert: Opcua_Alerts_Message):
    """
    Receive and process OPC UA alerts.

    This endpoint accepts alert messages in JSON format and forwards them to the configured OPC UA client.
    If the OPC UA client is not initialized, it will attempt to initialize it using the current configuration.

    Request Body Example:
        {
            "alert": "message"
        }

    Responses:
        200:
            description: Alert received and processed successfully.
            content:
                application/json:
                    example:
                        {
                            "status_code": 200,
                            "status": "success",
                            "message": "Alert received"
                        }
        500:
            description: Failed to process the alert due to server error or misconfiguration.
            content:
                application/json:
                    example:
                        {
                            "detail": "Failed to initialize OPC UA client: <error_message>"
                        }

    Raises:
        HTTPException: If OPC UA alerts are not configured or if there is an error during processing.
    """
    global opcua_send_alert
    try:
        if "alerts" in config.keys() and "opcua" in config["alerts"].keys():
            try:
                if opcua_send_alert is None or \
                    opcua_send_alert.opcua_server != config["alerts"]["opcua"]["opcua_server"] or \
                    not(await opcua_send_alert.is_connected()):
                    logger.info("Initializing OPC UA client for sending alerts")
                    opcua_send_alert = OpcuaAlerts(config)
                    await opcua_send_alert.initialize_opcua()
            except Exception as e:
                logger.exception("Failed to initialize OPC UA client")  # This logs the full traceback
                raise HTTPException(status_code=500, detail=f"Failed to initialize OPC UA client: {e}")

            if opcua_send_alert.node_id != config["alerts"]["opcua"]["node_id"] or \
                opcua_send_alert.namespace != config["alerts"]["opcua"]["namespace"]:
                opcua_send_alert.node_id = config["alerts"]["opcua"]["node_id"]
                opcua_send_alert.namespace = config["alerts"]["opcua"]["namespace"]
            
            alert_message = json.dumps(alert.model_dump())
            try:
                await opcua_send_alert.send_alert_to_opcua(alert_message)
            except Exception as e:
                logger.exception(f"Failed to send alert to OPC UA node:{e}")
                raise HTTPException(status_code=500, detail=f"Failed to send alert: {e}")
        else:
            raise HTTPException(status_code=500, detail="OPC UA alerts are not configured in the service")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status_code": 200, "status": "success", "message": "Alert received"}

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
        logging.debug(f"Received data point: {line_protocol}")
        response = Response()
        result = health_check(response)
        if result["status"] != "kapacitor daemon is running":
            logger.info("Kapacitor daemon is not running.")
            raise HTTPException(status_code=500, detail="Kapacitor daemon is not running")
        url = f"{KAPACITOR_URL}/kapacitor/v1/write?db=datain&rp=autogen"
        # Send data to Kapacitor
        response = requests.post(url, data=line_protocol, headers={"Content-Type": "text/plain"})

        if response.status_code == 204:
            return {"status": "success", "message": "Data sent to Time Series Analytics microservice"}
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
                                "model_registry": { "enable": true, "version": "2.0" },
                                "udfs": { "name": "udf_name", "model": "model_name" },
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
        return config
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
        config["model_registry"] = {}
        config["udfs"] = {}
        config["alerts"] = {}
        config["model_registry"] = config_data.model_registry
        config["udfs"] = config_data.udfs
        if config_data.alerts:
            config["alerts"] = config_data.alerts
        logger.debug(f"Received configuration data: {config}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in configuration data: {e}")
        raise HTTPException(status_code=422, detail="Invalid JSON format in configuration data")
    except KeyError as e:
        logger.error(f"Missing required key in configuration data: {e}")
        raise HTTPException(status_code=422, detail=f"Missing required key: {e}")

    def restart_kapacitor():
        stop_kapacitor_service()
        start_kapacitor_service(config)

    background_tasks.add_task(restart_kapacitor)
    return {"status": "success", "message": "Configuration updated successfully"}


if __name__ == "__main__":
    # Start the FastAPI server
    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=5000)

    server_thread = threading.Thread(target=run_server)
    server_thread.start()
    try:
        with open (CONFIG_FILE, 'r') as file:
            config = json.load(file)
        logger.info("App configuration loaded successfully from config.json file")
        start_kapacitor_service(config)
    except FileNotFoundError:
        logger.warning("config.json file not found, waiting for the configuration")
    except Exception as e:
        logger.error(f"Time Series Analytics Microservice failure - {e}")
