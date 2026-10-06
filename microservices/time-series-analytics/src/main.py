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
import base64
import binascii
import hmac
import io
import os
import logging
import shutil
import time
import json
import tarfile
import tempfile
from typing import Optional
import requests

from fastapi import FastAPI, File, HTTPException, Response, status, Request, Query, BackgroundTasks, UploadFile
from pydantic import BaseModel
from starlette.responses import JSONResponse
import uvicorn
from influxdb3_backend import InfluxDB3Backend, InfluxDB3Error
from opcua_alerts import OpcuaAlerts

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger()

REST_API_ROOT_PATH = os.getenv('REST_API_ROOT_PATH', '/')
app = FastAPI(root_path=REST_API_ROOT_PATH)

MAX_SIZE = 5 * 1024  # 5 KB
MAX_UPLOAD_SIZE = int(os.getenv('UDF_MAX_FILE_SIZE_MB', 100)) * 1024 * 1024  # 100 MB — max allowed tar upload

config = {}
OPCUA_SEND_ALERT = None
influxdb3_backend = None


def get_influxdb3_backend():
    global influxdb3_backend
    if influxdb3_backend is None:
        influxdb3_backend = InfluxDB3Backend()
    return influxdb3_backend


class DataPoint(BaseModel):
    """Data point model for input data."""
    topic: str
    tags: Optional[dict] = None
    fields: dict
    timestamp: Optional[int] = None


class Config(BaseModel):
    """Configuration model for the service."""
    udfs: dict = {"name": "udf_name", "device": "CPU"}
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


def check_udf_package(service_config, dir_name):
    udf_config = service_config.get("udfs", {})
    udf_name = udf_config.get("name")
    if not isinstance(udf_name, str) or not udf_name:
        return False
    root = os.path.realpath(os.path.join(tempfile.gettempdir(), dir_name))
    plugin_dir = os.path.realpath(os.path.join(
        root, "udfs", os.getenv("INFLUXDB3_UDF_PLUGIN_DIR", "influx3_windturbine")
    ))
    if os.path.commonpath((root, plugin_dir)) != root:
        return False
    if not os.path.isfile(os.path.join(plugin_dir, "__init__.py")):
        return False
    requirements_path = os.path.join(plugin_dir, "requirements.txt")
    if os.path.exists(requirements_path) and not os.path.isfile(requirements_path):
        return False
    model_name = udf_config.get("models")
    if model_name:
        model_path = os.path.realpath(os.path.join(root, "models", model_name))
        if os.path.commonpath((root, model_path)) != root or not os.path.isfile(model_path):
            return False
    return True


def restart_influxdb3():
    try:
        return get_influxdb3_backend().configure_udf(config, os.getenv("SAMPLE_APP"))
    except InfluxDB3Error:
        logger.exception("Failed to configure InfluxDB 3 processing trigger")
        raise


@app.get("/health")
def health_check(response: Response):
    """Get the health status of InfluxDB 3 Core."""
    try:
        get_influxdb3_backend().check_health()
        return {"status": "InfluxDB 3 Core is running"}
    except (InfluxDB3Error, requests.exceptions.RequestException):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "InfluxDB 3 Core is not running"}

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
                configured_opcua_server = config["alerts"]["opcua"]["opcua_server"]
                if OPCUA_SEND_ALERT is None or \
                    OPCUA_SEND_ALERT.configured_opcua_server != configured_opcua_server or \
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
    and writes it to InfluxDB 3 Core.

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
        HTTPException: If InfluxDB 3 Core returns an error or if any exception
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
            description: InfluxDB 3 Core is not running
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "InfluxDB 3 Core is not running"
        '4XX':
        description: Client error (e.g., invalid input or InfluxDB 3 error)
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
        if result["status"] != "InfluxDB 3 Core is running":
            raise HTTPException(status_code=503, detail="InfluxDB 3 Core is not running")
        get_influxdb3_backend().write_line_protocol(line_protocol)
        return {"status": "success", "message": "Data sent to InfluxDB 3 Core"}
    except HTTPException:
        raise
    except InfluxDB3Error as error:
        logger.error("InfluxDB 3 write failed: %s", error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:
        logger.error("Unexpected error in receive_data: %s", error)
        raise HTTPException(status_code=500, detail=str(error)) from error

@app.post("/write")
async def receive_line_protocol(request: Request, db: str = Query("datain"), precision: str = Query("auto")):
    """Accept Telegraf's InfluxDB v1-compatible line protocol writes and forward them to Core."""
    precision_map = {
        "n": "nanosecond", "ns": "nanosecond", "u": "microsecond", "us": "microsecond",
        "ms": "millisecond", "s": "second", "m": "auto", "h": "auto",
    }
    try:
        authorization = request.headers.get("authorization", "")
        try:
            scheme, encoded_credentials = authorization.split(" ", 1)
            username, password = base64.b64decode(encoded_credentials, validate=True).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            raise HTTPException(
                status_code=401,
                detail="Valid Basic authentication is required",
                headers={"WWW-Authenticate": "Basic"},
            )
        if scheme.lower() != "basic" or username != "token" or not hmac.compare_digest(
            password, get_influxdb3_backend().token
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid InfluxDB 3 write credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        line_protocol = (await request.body()).decode("utf-8")
        if not line_protocol:
            raise HTTPException(status_code=400, detail="Line protocol body is empty")
        get_influxdb3_backend().write_line_protocol(
            line_protocol,
            database=db,
            precision=precision_map.get(precision, precision),
        )
        return Response(status_code=204)
    except HTTPException:
        raise
    except InfluxDB3Error as error:
        logger.error("InfluxDB 3 line protocol write failed: %s", error)
        raise HTTPException(status_code=502, detail=str(error)) from error

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
                background_tasks.add_task(restart_influxdb3)
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
                        "device": "CPU/cpu or GPU/gpu"},
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
                error_msg = "Invalid value for 'device' in udfs: {}, must be 'CPU/cpu', 'GPU/gpu', or 'GPU:N/gpu:N' (e.g., 'GPU:0')".format(udfs["device"])
                logger.error(error_msg)
                raise HTTPException(status_code=422, detail=error_msg)

        if os.getenv("SAMPLE_APP") is not None:
            dir_name = os.getenv("SAMPLE_APP")
        else:
            dir_name = config_data.udfs["name"]
        if not check_udf_package(config_data.model_dump(), dir_name):
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
        else:
            config.pop("alerts")
        logger.info("Received configuration data: %s", config)
    except json.JSONDecodeError as error:
        logger.error("Invalid JSON format in configuration data: %s", error)
        raise HTTPException(status_code=422,
                          detail="Invalid JSON format in configuration data") from error
    except KeyError as error:
        logger.error("Missing required key in configuration data: %s", error)
        raise HTTPException(status_code=422,
                  detail=f"Missing required key: {error}") from error

    background_tasks.add_task(restart_influxdb3)
    return {"status": "success", "message": "Configuration updated successfully"}


def _scan_tar(tf: tarfile.TarFile, archive_size_bytes: int) -> None:
    """Scan a TarFile for security issues before extraction.

    Raises HTTPException(400) for any detected threat.
    """
    # Security limits for uploaded UDF tar files
    max_file_size = int(os.getenv("UDF_MAX_FILE_SIZE_MB", 100))  # Max size for a single UDF file in MB
    _TAR_MAX_TOTAL_BYTES       = max_file_size * 1024 * 1024   # 100 MB total
    _TAR_MAX_SINGLE_FILE_BYTES = max_file_size * 1024 * 1024   # 100 MB per entry
    _TAR_MAX_FILE_COUNT        = 100
    _TAR_MAX_EXPANSION_RATIO   = 100
    _TAR_ENCRYPTED_EXTENSIONS  = {".enc", ".gpg", ".pgp", ".age", ".aes"}
    _TAR_ALLOWED_EXTENSIONS    = {
        ".py", ".txt", ".cb",
        ".pkl", ".joblib", ".xml", ".bin", ".onnx", ".pt", ".pth", ".json",
    }
    entries = tf.getmembers()

    # 1. Max file count
    if len(entries) > _TAR_MAX_FILE_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Tar archive contains too many files ({len(entries)}). Maximum allowed: {_TAR_MAX_FILE_COUNT}."
        )

    total_size = 0
    for info in entries:
        name = info.name
        parts = name.replace("\\", "/").split("/")

        # 2. Path traversal
        if os.path.isabs(name) or ".." in parts:
            raise HTTPException(status_code=400, detail=f"Invalid path in tar entry: {name}")

        # 3. Symlink detection
        if info.issym() or info.islnk():
            raise HTTPException(status_code=400, detail=f"Tar entry is a link, which is not allowed: {name}")

        # 4. Device / special file detection
        if info.isdev() or info.isblk() or info.ischr() or info.isfifo():
            raise HTTPException(
                status_code=400,
                detail=f"Tar entry '{name}' is a special file type (device/fifo), which is not allowed."
            )

        # Skip directory entries for the remaining checks
        if info.isdir():
            continue

        # 5. Encrypted payload detection
        _, ext = os.path.splitext(name.lower())
        if ext in _TAR_ENCRYPTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Encrypted file '{name}' is not allowed in the UDF deployment package."
            )

        # 6. Allowed file extensions
        _, ext = os.path.splitext(name.lower())
        if ext not in _TAR_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' is not allowed in the UDF deployment package: {name}"
            )

        # 7. Reject sparse files to prevent low-size/high-expansion tar-bomb payloads.
        if getattr(info, "sparse", None):
            raise HTTPException(
                status_code=400,
                detail=f"Sparse file '{name}' is not allowed in the UDF deployment package."
            )

        # 8. Single-file size limit
        if info.size > _TAR_MAX_SINGLE_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File '{name}' exceeds the maximum allowed size of {_TAR_MAX_SINGLE_FILE_BYTES // (1024*1024)} MB."
            )

        total_size += info.size

    # 9. Total size limit
    if total_size > _TAR_MAX_TOTAL_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Total size exceeds the maximum allowed limit of {_TAR_MAX_TOTAL_BYTES // (1024*1024)} MB."
        )

    # 10. Tar-bomb style expansion-ratio detection
    effective_archive_size = max(archive_size_bytes, 1)
    expansion_ratio = total_size / effective_archive_size
    if expansion_ratio > _TAR_MAX_EXPANSION_RATIO:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Suspicious archive expansion ratio ({expansion_ratio:.0f}x) detected. "
                "Possible tar bomb."
            )
        )

    # 11. Required folder structure validation
    # Collect normalized paths of file entries only (not directories)
    file_names = [e.name.replace("\\", "/") for e in entries if not e.isdir()]

    def _has_file_in_folder(file_list, folder_segment, extension=None):
        """Return True if any file has `folder_segment` as an exact path segment."""
        for n in file_list:
            parts = n.split("/")
            # folder_segment must appear as an actual segment, and the file must follow it
            if folder_segment in parts[:-1]:
                if extension is None or n.lower().endswith(extension):
                    return True
        return False

    plugin_directory = os.getenv("INFLUXDB3_UDF_PLUGIN_DIR", "influx3_windturbine")
    plugin_entry = f"udfs/{plugin_directory}/__init__.py"
    if plugin_entry not in file_names:
        raise HTTPException(
            status_code=400,
            detail=f"Tar archive must contain the InfluxDB 3 plugin entry '{plugin_entry}'."
        )

    # models/ is optional — log a notice if absent
    if not _has_file_in_folder(file_names, "models"):
        logger.info("Tar archive does not contain a 'models/' folder (optional, skipping).")


@app.post("/udfs/package", responses={
    400: {"description": "Invalid file — not a .tar, corrupt archive, failed security scan (path traversal, symlink, encrypted payload, tar-bomb expansion), or missing required folders",
          "content": {"application/json": {"example": {"detail": "Tar archive must contain the InfluxDB 3 plugin entry 'udfs/influx3_windturbine/__init__.py'."}}}},
    413: {"description": "Uploaded file exceeds the maximum allowed size",
          "content": {"application/json": {"example": {"detail": "Uploaded file exceeds the maximum allowed size of 100 MB."}}}},
    500: {"description": "Failed to extract the UDF deployment package on the server",
          "content": {"application/json": {"example": {"detail": "Failed to extract UDF deployment package."}}}},
})
async def adds_udf_deployment_package(file: UploadFile = File(...)):
    """
    Adds UDF deployment package.

    **Request body**: multipart/form-data with a single field named `file` containing the tar archive.

    The tar must have the following structure (no wrapping top-level directory):

    .. code-block:: text

        udfs/
            <plugin_name>/
                __init__.py         (required Core trigger entry point)
                requirements.txt    (optional)
        models/                    (optional)
            <model_files>

    **Extraction destination**:

    - If `SAMPLE_APP` env var is set → `/tmp/<SAMPLE_APP>/`
    - Otherwise → `/tmp/<tar_filename_without_extension>/`

    **Allowed file extensions**: `.py`, `.txt`, `.cb`, `.pkl`, `.json`,
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
                                example: "UDF deployment package 'my_udf.tar' uploaded successfully."
        400:
            description: >
                Invalid upload — file is not a .tar, archive is corrupt, failed security
                scan (path traversal, symlink, encrypted payload, tar-bomb expansion,
                disallowed extension),
                or required folders/files are missing
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Tar archive must contain the InfluxDB 3 plugin entry 'udfs/influx3_windturbine/__init__.py'."
        413:
            description: Uploaded file exceeds the maximum allowed size
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            detail:
                                type: string
                                example: "Uploaded file exceeds the maximum allowed size of 100 MB."
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
    if not file.filename.endswith(".tar"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .tar archive.")

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
        tf = tarfile.open(fileobj=io.BytesIO(contents))
    except tarfile.TarError as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid tar archive.") from exc

    with tf:
        # Security scan before extraction
        _scan_tar(tf, archive_size_bytes=received)

        # Reserved names that must not be used as extraction directory names
        # to avoid colliding with service-critical paths under /tmp.
        _RESERVED_DIR_NAMES = {"tmp", "log", "udfs", "models", ".", ".."}

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

        base_dir = tempfile.gettempdir()

        tar_stem = _safe_dir_name(os.path.splitext(os.path.basename(file.filename))[0])
        sample_app = os.environ.get("SAMPLE_APP")
        if sample_app:
            dest_dir = os.path.join(base_dir, _safe_dir_name(sample_app))
        else:
            dest_dir = os.path.join(base_dir, tar_stem)

        # Extract into a staging directory first so a failed upload never
        # corrupts the live deployment.
        staging_dir = dest_dir + ".tmp"
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir)

        try:
            tf.extractall(staging_dir, filter='data')
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
    uvicorn.run(app, host="0.0.0.0", port=5000)
