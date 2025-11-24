#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""
Time Series Analytics Microservice's main module

This module exposes FastAPI server providing capabilities for data ingestion,
configuration management, and OPC UA alerts.
"""
import os
import logging
import time
import json
import subprocess
import threading
from typing import Optional
import requests

from fastapi import FastAPI, HTTPException, Response, status, Request, Query, BackgroundTasks
from pydantic import BaseModel
from starlette.responses import JSONResponse
import uvicorn
import classifier_startup
from opcua_alerts import OpcuaAlerts

log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger()

REST_API_ROOT_PATH = os.getenv('REST_API_ROOT_PATH', '/')
app = FastAPI(root_path=REST_API_ROOT_PATH)

KAPACITOR_URL = os.getenv('KAPACITOR_URL', 'http://localhost:9092')
CONFIG_FILE = "/app/config.json"
MAX_SIZE = 5 * 1024  # 5 KB

config = {}
OPCUA_SEND_ALERT = None
config_updated_event = threading.Event()


class DataPoint(BaseModel):
    """Data point model for input data."""
    topic: str
    tags: Optional[dict] = None
    fields: dict
    timestamp: Optional[int] = None


class Config(BaseModel):
    """Configuration model for the service."""
    udfs: dict = {"name": "udf_name", "device": "cpu"}
    alerts: Optional[dict] = {}


class OpcuaAlertsMessage(BaseModel):
    """Model for OPC UA alert messages."""

    class Config:
        """Pydantic configuration."""
        extra = 'allow'

def json_to_line_protocol(data_point: DataPoint):
    """
    Convert a DataPoint object to InfluxDB line protocol format.
    
    Args:
        data_point: DataPoint object containing topic, tags, fields, and timestamp
        
    Returns:
        str: Formatted line protocol string
    """
    tags = data_point.tags or {}
    tags_part = ''
    if tags:
        tags_part = ','.join([f"{key}={value}" for key, value in tags.items()])

    fields_part = ','.join([f"{key}={value}" for key, value in data_point.fields.items()])

    # Use current time in nanoseconds if timestamp is None
    timestamp = data_point.timestamp or int(time.time() * 1e9)

    if tags_part:
        line_protocol = f"{data_point.topic},{tags_part} {fields_part} {timestamp}"
    else:
        line_protocol = f"{data_point.topic} {fields_part} {timestamp}"
    logger.debug("Converted line protocol: %s", line_protocol)
    return line_protocol


def start_kapacitor_service(service_config):
    """
    Start the Kapacitor service with the given configuration.
    
    Args:
        service_config: Configuration dictionary for the service
    """
    classifier_startup.classifier_startup(service_config)


def stop_kapacitor_service():
    """Stop the Kapacitor service and all running tasks."""
    response = Response()
    result = health_check(response)
    if result["status"] != "kapacitor daemon is running":
        logger.info("Kapacitor daemon is not running.")
        return
    try:
        response = requests.get(f"{KAPACITOR_URL}/kapacitor/v1/tasks", timeout=30)
        tasks = response.json().get('tasks', [])
        if len(tasks) > 0:
            task_id = tasks[0].get('id')
            print("Stopping Kapacitor tasks:", task_id)
            logger.info("Stopping Kapacitor tasks: %s", task_id)
            subprocess.run(["kapacitor", "disable", task_id], check=False)
            subprocess.run(["pkill", "-9", "kapacitord"], check=False)
    except subprocess.CalledProcessError as error:
        logger.error("Error stopping Kapacitor service: %s", error)


def restart_kapacitor():
    """Restart the Kapacitor service."""
    stop_kapacitor_service()
    start_kapacitor_service(config)


@app.get("/health")
def health_check(response: Response):
    """Get the health status of the kapacitor daemon."""
    url = f"{KAPACITOR_URL}/kapacitor/v1/ping"
    try:
        # Make an HTTP GET request to the service
        request_response = requests.get(url, timeout=1)
        if request_response.status_code in (200, 204):
            return {"status": "kapacitor daemon is running"}

        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "kapacitor daemon is not running properly"}
    except requests.exceptions.ConnectionError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "Port not accessible and kapacitor daemon not running"}
    except requests.exceptions.RequestException:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "An error occurred while checking the service"}

@app.post("/opcua_alerts")
async def receive_alert(alert: OpcuaAlertsMessage):
    """
    Receive and process OPC UA alerts.

    This endpoint accepts alert messages in JSON format and forwards them to the 
    configured OPC UA client.
    If the OPC UA client is not initialized, it will attempt to initialize it 
    using the current configuration.

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
        '400':
            description: OPC UA alerts are not configured in the service
            content:
                application/json:
                    example:
                        {
                            "detail": "OPC UA alerts are not configured in the service"
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
        HTTPException: If OPC UA alerts are not configured or if there is an error during 
        processing.
    """
    global OPCUA_SEND_ALERT
    try:
        if "alerts" in config.keys() and "opcua" in config["alerts"].keys():
            try:
                if OPCUA_SEND_ALERT is None or \
                    OPCUA_SEND_ALERT.opcua_server != config["alerts"]["opcua"]["opcua_server"] or \
                    not (await OPCUA_SEND_ALERT.is_connected()):
                    logger.info("Initializing OPC UA client for sending alerts")
                    OPCUA_SEND_ALERT = OpcuaAlerts(config)
                    await OPCUA_SEND_ALERT.initialize_opcua()
            except Exception as error:
                logger.exception("Failed to initialize OPC UA client")
                raise HTTPException(status_code=500,
                                  detail=f"Failed to initialize OPC UA client: {error}") from error

            if OPCUA_SEND_ALERT.node_id != config["alerts"]["opcua"]["node_id"] or \
                OPCUA_SEND_ALERT.namespace != config["alerts"]["opcua"]["namespace"]:
                OPCUA_SEND_ALERT.node_id = config["alerts"]["opcua"]["node_id"]
                OPCUA_SEND_ALERT.namespace = config["alerts"]["opcua"]["namespace"]

            alert_message = json.dumps(alert.model_dump())
            try:
                await OPCUA_SEND_ALERT.send_alert_to_opcua(alert_message)
            except Exception as e:
                logger.exception("Failed to send alert to OPC UA node: %s", e)
                raise HTTPException(status_code=500, detail=f"Failed to send alert: {e}")
        else:
            raise HTTPException(status_code=400,
                              detail="OPC UA alerts are not configured in the service")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in receive_alert: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "status_code": 500,
                "status": "error",
                "message": f"Unexpected error: {exc}"
            }
        )
    return {"status_code": 200, "status": "success", "message": "Alert received"}

@app.post("/input")
async def receive_data(data_point: DataPoint):
    """
    Receives a data point in JSON format, converts it to InfluxDB line protocol, 
    and sends it to the Kapacitor service.

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
        HTTPException: If the Kapacitor service returns an error or if any exception 
        occurs during processing.

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
        '503':
            description: Kapacitor daemon is not running
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Kapacitor daemon is not running"
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
        logger.debug("Received data point: %s", line_protocol)
        response = Response()
        result = health_check(response)
        if result["status"] != "kapacitor daemon is running":
            logger.warning("Kapacitor daemon is not running.")
            raise HTTPException(status_code=503, detail="Kapacitor daemon is not running")  
        url = f"{KAPACITOR_URL}/kapacitor/v1/write?db=datain&rp=autogen"
        # Send data to Kapacitor
        kapacitor_response = requests.post(url, data=line_protocol,
                                         headers={"Content-Type": "text/plain"}, timeout=30)

        if kapacitor_response.status_code == 204:
            return {"status": "success",
                   "message": "Data sent to Time Series Analytics microservice"}

        raise HTTPException(status_code=kapacitor_response.status_code,
                          detail=kapacitor_response.text)
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Unexpected error in receive_data: %s", error)
        raise HTTPException(status_code=500, detail=str(error)) from error

@app.get("/config")
async def get_config(
    request: Request,
    restart: Optional[bool] = Query(False,
                                   description="Restart the Time Series Analytics "
                                             "Microservice UDF deployment if true"),
    background_tasks: BackgroundTasks = None):
    """
    Endpoint to retrieve the current configuration of the input service.
    Accepts an optional 'restart' query parameter and returns the current configuration 
    in JSON format.
    If 'restart=true' is provided, the Time Series Analytics Microservice UDF deployment 
    service will be restarted before returning the configuration.

    ---
    parameters:
        - in: query
          name: restart
          schema:
            type: boolean
            default: false
          description: Restart the Time Series Analytics Microservice UDF deployment if true
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
        if restart:

            if background_tasks is not None:
                background_tasks.add_task(restart_kapacitor)
        params = dict(request.query_params)
        # Remove 'restart' from params to avoid filtering config by it
        params.pop('restart', None)
        if not params:
            return config
        filtered_config = {k: config.get(k) for k in params if k in config}
        return filtered_config
    except Exception as error:
        logger.error("Error retrieving configuration: %s", error)
        raise HTTPException(status_code=500, detail=str(error)) from error

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
                    {
                    "udfs": {
                        "name": "udf_name",
                        "model": "model_name",
                        "device": "cpu or gpu"}
                    "alerts": {
                    }
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
        if len(json.dumps(config_data.model_dump()).encode('utf-8')) > MAX_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": "Request exceeds the maximum allowed payload size of 5 KB."})
        udfs = config_data.udfs
        if "name" not in udfs:
            logger.error("Missing key 'name' in udfs")
            raise HTTPException(
            status_code=422,
            detail="Missing key 'name' in udfs"
            )
        if "device" in udfs:
            device_value = udfs["device"].lower()
            is_valid = (device_value == "cpu" or 
                       device_value == "gpu" or 
                       (device_value.startswith("gpu:") and device_value.split(":")[1].isdigit()))
            
            if not is_valid:
                error_msg = "Invalid value for 'device' in udfs: {}, must be 'cpu', 'gpu', or 'gpu:N' (e.g., 'gpu:0')".format(udfs["device"])
                logger.error(error_msg)
                raise HTTPException(status_code=422, detail=error_msg)
                
        config["udfs"] = {}
        config["alerts"] = {}
        config["udfs"] = config_data.udfs
        if config_data.alerts:
            config["alerts"] = config_data.alerts
        logger.debug("Received configuration data: %s", config)
    except json.JSONDecodeError as error:
        logger.error("Invalid JSON format in configuration data: %s", error)
        raise HTTPException(status_code=422,
                          detail="Invalid JSON format in configuration data") from error
    except KeyError as error:
        logger.error("Missing required key in configuration data: %s", error)
        raise HTTPException(status_code=422,
                  detail=f"Missing required key: {error}") from error

    background_tasks.add_task(restart_kapacitor)
    return {"status": "success", "message": "Configuration updated successfully"}


if __name__ == "__main__":  # pragma: no cover
    # Start the FastAPI server
    def run_server():
        """Run the FastAPI server."""
        uvicorn.run(app, host="0.0.0.0", port=5000)

    server_thread = threading.Thread(target=run_server)
    server_thread.start()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as file:
            config = json.load(file)
        logger.info("App configuration loaded successfully from config.json file")
        start_kapacitor_service(config)
        while True:
            time.sleep(1)
    except FileNotFoundError:
        logger.warning("config.json file not found, waiting for the configuration")
    except Exception as error:
        logger.error("Time Series Analytics Microservice failure - %s", error)
