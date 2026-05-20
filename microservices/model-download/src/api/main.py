# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import io
import zipfile
import shutil
import yaml
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from ..core.plugin_registry import PluginRegistry
from ..core.model_manager import ModelManager
import importlib
from .models import ModelDownloadRequest, ModelHub
from ..utils.logging import logger
from ..utils.helper import validate_zip_contents_within_target, validate_zip_file, sanitize_path_part

app = FastAPI(
    root_path="/api/v1",
    title="Model Download Service",
    version="1.0.1",
)

# Custom OpenAPI schema loader
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_yaml_path = os.path.join(
        os.path.dirname(__file__),
        "../../docs/user-guide/_assets/openapi.yaml"
    )

    with open(openapi_yaml_path, 'r') as f:
        app.openapi_schema = yaml.safe_load(f)

    return app.openapi_schema

app.openapi = custom_openapi

plugin_registry = PluginRegistry()
plugins_package = importlib.import_module("src.plugins")
plugin_registry.discover_plugins(plugins_package)
models_dir = os.getenv("MODELS_DIR", "/opt/models")
model_manager = ModelManager(plugin_registry, default_dir=models_dir)

MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500")) * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = int(os.getenv("UPLOAD_CHUNK_SIZE_KB", "8")) * 1024
CUSTOM_MODELS_SUBDIR = "custom_uploaded_models"

# Log which plugins are activated at startup
for plugin_type in plugin_registry.plugins:
    for plugin_name in plugin_registry.get_plugin_names(plugin_type):
        is_available, reason = plugin_registry.check_plugin_dependencies(plugin_name)
        status = "AVAILABLE" if is_available else f"NOT AVAILABLE: {reason}"
        logger.info(f"Plugin {plugin_name} ({plugin_type}): {status}")


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=os.getenv("CORS_ALLOW_METHODS", "*").split(","),
    allow_headers=os.getenv("CORS_ALLOW_HEADERS", "*").split(","),
)


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify the service is running.
    """
    return {"status": "ok"}


@app.post("/models/download")
async def download_models(
    request: ModelDownloadRequest,
    download_path: str,
) -> Dict[str, Any]:
    """
    Download and optionally convert models.

    Models are downloaded from the specified hub (huggingface, ollama, etc.).
    Models will be converted to OpenVINO format if:
    1. is_ovms is set to true in the request for openvino conversion, or
    2. type can be set to 'llm,embeddings,reranker,vlm or vision' in the request

    The config object is optional and used only for conversion.

    Note: HF_TOKEN environment variable is optional and only required for downloading
    gated models from HuggingFace. Public models can be downloaded without authentication.
    """
    try:
        supported_hubs = set()
        for plugin_type in plugin_registry.plugins:
            supported_hubs.update(name.lower() for name in plugin_registry.get_plugin_names(plugin_type))
        for model in request.models:
            logger.info(f"Requested Model Hub: {model.hub}")
            if model.hub.lower() not in supported_hubs:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported model download/conversion detected. Supported methods are {supported_hubs}.",
                )

        # Get HuggingFace token from environment variable
        hf_token = os.getenv("HF_TOKEN")

        logger.info(f"Initiating model download for {len(request.models)} model(s)")
        job_ids = []

        for model in request.models:
            # Check if the plugin's dependencies are installed
            is_plugin_available, error_reason = plugin_registry.check_plugin_dependencies(model.hub)
            if not is_plugin_available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Plugin '{model.hub}' is not available: {error_reason}"
                )

            extra_kwargs = model.model_dump().copy()
            logger.info(f"Model '{model.name}' download initiated using hub '{model.hub}' with parameters: {extra_kwargs}")

            needs_conversion = model.is_ovms
            model_download_path = os.path.join(models_dir, download_path)

            if model.hub.lower() in [hub.value.lower() for hub in ModelHub] and not needs_conversion:
                extra_kwargs["token"] = hf_token
                # Remove fields that shouldn't be passed to plugins
                extra_kwargs.pop("hub", None)
                extra_kwargs.pop("is_ovms", None)

                model_download_path = os.path.join(
                    models_dir, download_path
                )
                # Register download job
                download_job_id = model_manager.register_job(
                    operation_type="download",
                    model_name=model.name,
                    hub=model.hub,
                    output_dir=model_download_path,
                    plugin_name=model.hub,
                    model_type=model.type,
                )

                # Add to job_ids for response
                job_ids.append(download_job_id)

                # Start download in background (async parallel execution)
                asyncio.create_task(
                    model_manager.process_download(
                        job_id=download_job_id,
                        model_name=model.name,
                        hub=model.hub,
                        output_dir=model_download_path,
                        downloader=model.hub,
                        **extra_kwargs
                    )
                )

            if needs_conversion:
                # Check if OpenVINO plugin is available for conversion
                is_openvino_available, openvino_error = plugin_registry.check_plugin_dependencies("openvino")
                if not is_openvino_available:
                    raise HTTPException(
                        status_code=400,
                        detail=f"OpenVINO conversion requested but plugin is not available: {openvino_error}"
                    )

                # Get configuration for conversion
                extra_kwargs["token"] = hf_token
                config = model.config.dict() if model.config else {}
                config['device'] = (config.get("device") or config.get("target_device") or "CPU")
                config["precision"] = (
                    config.get("weight-format") or
                    config.get("precision") or
                    "int8"
                ).lower()

                if config['device'].upper() == "NPU":
                    logger.warning("NPU target device selected. Only 'int4' weight format is supported for NPU. Overriding weight_format to 'int4'.")
                    config['precision'] = "int4"


                # Create a unique output directory for the converted model
                convert_output_dir = os.path.join(
                    models_dir,
                    download_path,
                    "openvino_models",
                    config["device"],
                    config["precision"]
                ).lower()

                # Register conversion job
                convert_job_id = model_manager.register_job(
                    operation_type="convert",
                    model_name=model.name,
                    hub=model.hub,
                    output_dir=convert_output_dir,
                    plugin_name="openvino",
                    model_type=model.type,
                )

                # Add to job_ids for response
                job_ids.append(convert_job_id)

                # Start conversion in background (async parallel execution)
                asyncio.create_task(
                    model_manager.process_conversion(
                        job_id=convert_job_id,
                        model_path=download_path,
                        hub=model.hub,
                        output_dir=convert_output_dir,
                        converter="openvino",
                        model_name=model.name,
                        model_type=model.type,
                        hf_token=extra_kwargs["token"],
                        **config
                    )
                )

        # Return response immediately with job IDs
        return {
            "message": f"Started processing {len(request.models)} model(s)",
            "job_ids": job_ids,
            "status": "processing"
        }
    except ValidationError as e:
        logger.error(f"Request validation failed: {str(e)}")
        raise HTTPException(
            status_code=422, detail=f"Invalid request format: {e.errors()}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in model download process: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error in model download process: {str(e)}",
        )


@app.get("/models/jobs", tags=["Jobs"])
async def get_model_jobs(model_name: str):
    """
    Get all jobs related to a specific model.
    """
    model_jobs = []

    for job_id, job in model_manager._jobs.items():
        if job.get("model_name") == model_name:
            model_jobs.append(job)

    if not model_jobs:
        raise HTTPException(status_code=404, detail=f"No jobs found for model {model_name}")

    return {"jobs": model_jobs}


@app.get("/jobs/{job_id}", tags=["Jobs"])
async def get_job_status(job_id: str):
    """
    Get the status of a specific job.
    """
    if job_id not in model_manager._jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return model_manager._jobs[job_id]


@app.get("/models/results", tags=["Models"])
async def get_model_results():
    """
    Get completed model downloads and conversions.
    """
    completed_jobs = []

    for job_id, job in model_manager._jobs.items():
        if job.get("status") == "completed":
            # Format job as result
            operation_type = job.get("operation_type")
            result = {
                "job_id": job_id,
                "model_name": job.get("model_name"),
                "hub": job.get("hub"),
                "operation_type": operation_type,
                "status": "success",
                "model_path": job.get("output_dir"),
                "completion_time": job.get("completion_time")
            }

            # Keep is_ovms for for download/convert responses and omit for upload responses as upload is user-initiated
            if operation_type != "upload":
                result["is_ovms"] = operation_type == "convert"

            completed_jobs.append(result)

    return {"results": completed_jobs}


@app.get("/jobs", tags=["Jobs"])
async def list_jobs():
    """
    List all jobs.
    """
    return {"jobs": list(model_manager._jobs.values())}


@app.get("/plugins", tags=["Plugins"])
async def list_plugins():
    """
    List all available plugins and their capabilities.
    """
    plugins_info = {}

    # Get plugins for each type
    for plugin_type in plugin_registry.plugins:
        plugins_info[plugin_type] = []
        for plugin_name, plugin in plugin_registry.plugins.get(plugin_type, {}).items():
            # Get plugin capabilities
            can_handle_parallel = hasattr(plugin, "get_download_tasks") and callable(getattr(plugin, "get_download_tasks"))

            # Check if plugin dependencies are installed
            is_available, reason = plugin_registry.check_plugin_dependencies(plugin_name)

            plugin_info = {
                "name": plugin_name,
                "type": plugin_type,
                "description": getattr(plugin, "__doc__", "No description available").strip(),
                "capabilities": {
                    "supports_parallel_downloads": can_handle_parallel,
                },
                "available": is_available,
                "unavailable_reason": reason if not is_available else None
            }
            plugins_info[plugin_type].append(plugin_info)

    # Count available plugins
    total_plugins = sum(len(plugins) for plugins in plugins_info.values())
    available_plugins = sum(
        1 for plugin_type in plugins_info for plugin in plugins_info[plugin_type]
        if plugin.get("available", False)
    )

    return {
        "available_plugins": plugins_info,
        "total_count": total_plugins,
        "available_count": available_plugins,
        "activation_instructions": "To enable/disable plugins, restart the container with the --plugins option specifying the plugins you need (e.g. huggingface,openvino,ultralytics,ollama) or use 'all' to enable all plugins"
    }


@app.post("/models/upload", tags=["Models"])
async def upload_model(
    file: UploadFile = File(...),
    model_name: str = Form(...),
    provider: str = Form("geti"),
    framework: str = Form("openvino"),
    precision: Optional[str] = Form("FP16"),
):
    """
    Upload an OpenVINO IR model as a ZIP file containing model.xml and model.bin.
    The uploaded model is immediately visible in GET /models/results.
    Storage path: {MODELS_DIR}/custom_uploaded_models/{provider}/{framework}/{model_name}/[{precision}/]
    """
    # Early size check using file metadata
    if file.size and file.size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size {file.size} bytes exceeds the "
                f"{MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB upload limit."
            ),
        )

    # Read file in chunks to prevent memory exhaustion with large uploads
    chunk_size = UPLOAD_CHUNK_SIZE_BYTES
    accumulated_size = 0
    chunks = []

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break

        accumulated_size += len(chunk)
        if accumulated_size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File size exceeds the "
                    f"{MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB upload limit."
                ),
            )
        chunks.append(chunk)

    content = b''.join(chunks)
    # check if it's a valid ZIP file
    validate_zip_file(content)

    # Build target directory path
    upload_base_dir = os.path.abspath(os.path.join(models_dir, CUSTOM_MODELS_SUBDIR))
    sanitized_model_name = sanitize_path_part(model_name, "model_name")
    path_parts = [
        upload_base_dir,
        sanitize_path_part(provider, "provider"),
        sanitize_path_part(framework, "framework"),
        sanitized_model_name,
    ]
    if precision:
        path_parts.append(sanitize_path_part(precision, "precision"))
    target_dir = os.path.abspath(os.path.join(*path_parts))

    if os.path.commonpath([upload_base_dir, target_dir]) != upload_base_dir:
        raise HTTPException(
            status_code=400,
            detail="Invalid upload path. Target directory must stay under custom_uploaded_models.",
        )

    # Reject duplicate model
    if os.path.exists(target_dir):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Model '{sanitized_model_name}' already exists at '{target_dir}'."
            ),
        )

    # Extract ZIP to target directory
    try:
        os.makedirs(target_dir, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            validate_zip_contents_within_target(zf, target_dir)
            zf.extractall(target_dir)
    except ValueError as e:
        shutil.rmtree(target_dir, ignore_errors=True)
        logger.error(f"ZIP validation failed for model '{sanitized_model_name}': {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        shutil.rmtree(target_dir, ignore_errors=True)
        logger.error(f"Failed to extract uploaded model '{sanitized_model_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract model: {str(e)}",
        )

    # Register as a completed job so it appears in GET /models/results
    job_id = model_manager.register_job(
        operation_type="upload",
        model_name=sanitized_model_name,
        hub="user-uploaded",
        output_dir=target_dir,
    )
    model_manager._jobs[job_id]["status"] = "completed"
    model_manager._jobs[job_id]["completion_time"] = datetime.now().isoformat()

    logger.info(f"Model '{sanitized_model_name}' uploaded successfully to '{target_dir}' (job_id={job_id})")

    return {
        "status": "success",
        "message": f"Model '{sanitized_model_name}' uploaded successfully.",
        "job_id": job_id,
        "model_name": sanitized_model_name,
        "model_path": target_dir,
    }
