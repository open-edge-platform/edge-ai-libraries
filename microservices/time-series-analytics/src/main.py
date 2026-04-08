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
import io
import os
import logging
import shutil
import time
import json
import subprocess
import threading
import zipfile
from typing import Optional
import requests

from fastapi import FastAPI, File, HTTPException, Response, status, Request, Query, BackgroundTasks, UploadFile
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
MAX_UPLOAD_SIZE = int(os.getenv('UDF_MAX_FILE_SIZE_MB', 100)) * 1024 * 1024  # 100 MB — max allowed zip upload

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
    if result["status"] != "Kapacitor daemon is running":
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
    """Get the health status of the Kapacitor daemon."""
    url = f"{KAPACITOR_URL}/kapacitor/v1/ping"
    try:
        # Make an HTTP GET request to the service
        request_response = requests.get(url, timeout=1)
        if request_response.status_code in (200, 204):
            return {"status": "Kapacitor daemon is running"}

        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "Kapacitor daemon is not running"}
    except requests.exceptions.ConnectionError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "Kapacitor daemon is not running"}
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
        if result["status"] != "Kapacitor daemon is running":
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

@app.post("/config", responses={
    413: {"description": "Request payload exceeds the maximum allowed size of 5 KB",
          "content": {"application/json": {"example": {"error": "Request exceeds the maximum allowed payload size of 5 KB."}}}},
    422: {"description": "Unprocessable request - invalid or missing fields, invalid device value, "
                         "or UDF deployment package files are missing from the server",
          "content": {"application/json": {"example": {"detail": "UDF deployment package validation failed for <udf_name>."}}}},
    500: {"description": "Failed to write configuration to file",
          "content": {"application/json": {"example": {"detail": "Failed to write configuration to file"}}}},
})
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
                        "device": "cpu or gpu"},
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
        413:
            description: Request payload exceeds the maximum allowed size of 5 KB
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            error:
                                type: string
                                example: "Request exceeds the maximum allowed payload size of 5 KB."
        422:
            description: >
                Unprocessable request - invalid or missing fields, invalid device value,
                or UDF deployment package files are missing from the server
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "UDF deployment package validation failed for <udf_name>."
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

        if os.getenv("SAMPLE_APP") is not None:
            dir_name = os.getenv("SAMPLE_APP")
        else:
            dir_name = config_data.udfs["name"]
        if not classifier_startup.kapacitor_classifier.check_udf_package(config_data.model_dump(), dir_name):
            error_msg = (
                f"UDF deployment package validation failed for {config_data.udfs['name']}. "
                "Please check and upload/copy the UDF deployment package with correct structure and files."
            )
            logger.error(error_msg)
            raise HTTPException(status_code=422, detail=error_msg)
        logger.info("UDF deployment package %s validated successfully.", config_data.udfs["name"])        

        config["udfs"] = {}
        config["alerts"] = {}
        config["udfs"] = config_data.udfs
        if config_data.alerts:
            config["alerts"] = config_data.alerts
        logger.info("Received configuration data: %s", config)
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


def _scan_zip(zf: zipfile.ZipFile) -> None:
    """Scan a ZipFile for security issues before extraction.

    Raises HTTPException(400) for any detected threat.
    """
    # Security limits for uploaded UDF zip files
    max_file_size = int(os.getenv("UDF_MAX_FILE_SIZE_MB", 100))  # Max size for a single UDF file in MB
    _ZIP_MAX_UNCOMPRESSED_BYTES = max_file_size * 1024 * 1024   # 100 MB total
    _ZIP_MAX_SINGLE_FILE_BYTES  = max_file_size * 1024 * 1024   # 100 MB per entry
    _ZIP_MAX_FILE_COUNT         = 100
    _ZIP_MAX_COMPRESSION_RATIO  = 100                  # flag zip-bomb if ratio > 100x
    _ZIP_ALLOWED_EXTENSIONS     = {
        ".py", ".tick", ".txt", ".cb",
        ".pkl", ".joblib", ".xml", ".bin", ".onnx", ".pt", ".pth",
    }
    entries = zf.infolist()

    # 1. Max file count
    if len(entries) > _ZIP_MAX_FILE_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Zip archive contains too many files ({len(entries)}). Maximum allowed: {_ZIP_MAX_FILE_COUNT}."
        )

    total_uncompressed = 0
    for info in entries:
        name = info.filename
        parts = name.replace("\\", "/").split("/")

        # 2. Path traversal
        if os.path.isabs(name) or ".." in parts:
            raise HTTPException(status_code=400, detail=f"Invalid path in zip entry: {name}")

        # 3. Symlink detection (Unix symlink bit is 0xA in the high nibble of external_attr)
        unix_attrs = (info.external_attr >> 16) & 0xFFFF
        is_symlink = (unix_attrs & 0xF000) == 0xA000
        if is_symlink:
            raise HTTPException(status_code=400, detail=f"Zip entry is a symlink, which is not allowed: {name}")

        # 4. Encryption detection (bit 0 of flag_bits indicates the entry is encrypted)
        if info.flag_bits & 0x1:
            raise HTTPException(
                status_code=400,
                detail=f"Zip entry '{name}' is encrypted/password-protected. Encrypted archives are not allowed."
            )

        # Skip directory entries for the remaining checks
        if info.is_dir():
            continue

        # 4. Allowed file extensions
        _, ext = os.path.splitext(name.lower())
        if ext not in _ZIP_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' is not allowed in the UDF deployment package: {name}"
            )

        # 5. Single-file size limit
        if info.file_size > _ZIP_MAX_SINGLE_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File '{name}' exceeds the maximum allowed size of {_ZIP_MAX_SINGLE_FILE_BYTES // (1024*1024)} MB."
            )

        # 6. Zip-bomb detection via compression ratio
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > _ZIP_MAX_COMPRESSION_RATIO:
                raise HTTPException(
                    status_code=400,
                    detail=f"Suspicious compression ratio ({ratio:.0f}x) detected in '{name}'. Possible zip bomb."
                )

        total_uncompressed += info.file_size

    # 7. Total uncompressed size limit
    if total_uncompressed > _ZIP_MAX_UNCOMPRESSED_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Total uncompressed size exceeds the maximum allowed limit of {_ZIP_MAX_UNCOMPRESSED_BYTES // (1024*1024)} MB."
        )

    # 8. Required folder structure validation
    # Collect normalized paths of file entries only (not directories)
    file_names = [e.filename.replace("\\", "/") for e in entries if not e.is_dir()]

    def _has_file_in_folder(file_list, folder_segment, extension=None):
        """Return True if any file has `folder_segment` as an exact path segment."""
        for n in file_list:
            parts = n.split("/")
            # folder_segment must appear as an actual segment, and the file must follow it
            if folder_segment in parts[:-1]:
                if extension is None or n.lower().endswith(extension):
                    return True
        return False

    # udfs/ must contain at least one .py file
    if not _has_file_in_folder(file_names, "udfs", ".py"):
        raise HTTPException(
            status_code=400,
            detail="Zip archive must contain a 'udfs/' folder with at least one .py file."
        )

    # tick_scripts/ must contain at least one .tick file
    if not _has_file_in_folder(file_names, "tick_scripts", ".tick"):
        raise HTTPException(
            status_code=400,
            detail="Zip archive must contain a 'tick_scripts/' folder with at least one .tick file."
        )

    # models/ is optional — log a notice if absent
    if not _has_file_in_folder(file_names, "models"):
        logger.info("Zip archive does not contain a 'models/' folder (optional, skipping).")


@app.post("/udfs/package", responses={
    400: {"description": "Invalid file — not a .zip, corrupt archive, failed security scan, or missing required folders",
          "content": {"application/json": {"example": {"detail": "Zip archive must contain a 'udfs/' folder with at least one .py file."}}}},
    413: {"description": "Uploaded file exceeds the maximum allowed size",
          "content": {"application/json": {"example": {"detail": "Uploaded file exceeds the maximum allowed size of 500 MB."}}}},
    500: {"description": "Failed to extract the UDF deployment package on the server",
          "content": {"application/json": {"example": {"detail": "Failed to extract UDF deployment package."}}}},
})
async def adds_udf_deployment_package(file: UploadFile = File(...)):
    """
    Adds UDF deployment package.

    **Request body**: multipart/form-data with a single field named `file` containing the zip archive.

    The zip must have the following structure (no wrapping top-level directory):

    .. code-block:: text

        udfs/
            <udf_name>.py          (required)
            requirements.txt       (optional)
        tick_scripts/
            <udf_name>.tick        (required)
        models/                    (optional)
            <model_files>

    **Extraction destination**:

    - If `SAMPLE_APP` env var is set → `/tmp/<SAMPLE_APP>/`
    - Otherwise → `/tmp/<zip_filename_without_extension>/`

    **Allowed file extensions**: `.py`, `.tick`, `.txt`, `.cb`, `.pkl`,
    `.joblib`, `.xml`, `.bin`, `.onnx`, `.pt`, `.pth`

    responses:
        200:
            description: UDF deployment package uploaded and extracted successfully
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
                                example: "UDF deployment package 'my_udf.zip' uploaded successfully."
        400:
            description: >
                Invalid upload — file is not a .zip, archive is corrupt, failed security
                scan (path traversal, symlink, encryption, zip-bomb, disallowed extension),
                or required folders/files are missing
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Zip archive must contain a 'udfs/' folder with at least one .py file."
        413:
            description: Uploaded file exceeds the maximum allowed size
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Uploaded file exceeds the maximum allowed size of 500 MB."
        500:
            description: Server failed to extract the UDF deployment package
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Failed to extract UDF deployment package."
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .zip archive.")

    # Read in chunks to enforce upload size limit before loading into memory
    chunks = []
    received = 0
    chunk_size = 1024 * 1024  # 1 MB per read
    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            received += len(chunk)
            if received > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"Uploaded file exceeds the maximum allowed size of {MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
                )
            chunks.append(chunk)
    finally:
        await file.close()
    contents = b"".join(chunks)

    try:
        zf = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid zip archive.") from exc

    with zf:
        # Security scan before extraction
        _scan_zip(zf)

        # Reserved names that must not be used as extraction directory names
        # to avoid colliding with service-critical paths under SECURE_TEMP_DIR.
        _RESERVED_DIR_NAMES = {
            "tmp", "log", "kapacitor", "py_package", "udfs",
            "tick_scripts", "models", ".", "..",
        }

        def _safe_dir_name(name: str) -> str:
            """Validate and return a safe directory name, or raise HTTPException."""
            import re
            if not name:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot derive a valid deployment directory name: name is empty."
                )
            # Allow only alphanumeric, hyphen, underscore, dot (no slashes or other special chars)
            if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot derive a valid deployment directory name: '{name}' "
                           "contains disallowed characters (only alphanumeric, '-', '_', '.' are allowed)."
                )
            if name.lower() in _RESERVED_DIR_NAMES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot extract into reserved directory name '{name}'. "
                )
            return name

        base_dir = classifier_startup.SECURE_TEMP_DIR

        zip_stem = _safe_dir_name(os.path.splitext(os.path.basename(file.filename))[0])
        sample_app = os.environ.get("SAMPLE_APP")
        if sample_app:
            dest_dir = os.path.join(base_dir, _safe_dir_name(sample_app))
        else:
            dest_dir = os.path.join(base_dir, zip_stem)

        # Extract into a staging directory first so a failed upload never
        # corrupts the live deployment.
        staging_dir = dest_dir + ".tmp"
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir)

        try:
            zf.extractall(staging_dir)
        except Exception as exc:
            logger.error("Failed to extract UDF deployment package: %s", exc)
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Failed to extract UDF deployment package.") from exc

    if os.path.exists(dest_dir):
        old_dir = dest_dir + ".old"
        os.rename(dest_dir, old_dir)
        try:
            os.rename(staging_dir, dest_dir)
        except Exception as exc:
            # Roll back: restore previous deployment
            os.rename(old_dir, dest_dir)
            shutil.rmtree(staging_dir, ignore_errors=True)
            logger.error("Failed to replace UDF deployment directory: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to extract UDF deployment package.") from exc
        shutil.rmtree(old_dir, ignore_errors=True)
    else:
        os.rename(staging_dir, dest_dir)

    logger.info("UDF deployment package '%s' uploaded and extracted to %s.", file.filename, dest_dir)
    return {"status": "success", "message": f"UDF deployment package '{file.filename}' uploaded successfully."}

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
