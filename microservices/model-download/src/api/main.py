# FastAPI application entry point

import os
import gc
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import ValidationError

from ..core.plugin_registry import PluginRegistry
from ..core.model_manager import ModelManager
import importlib
from .models import ModelDownloadRequest, ModelHub
from ..utils.logging import logger

app = FastAPI(root_path="/api/v1", title="Model Download Service", version="1.0.0")
plugin_registry = PluginRegistry()
plugins_package = importlib.import_module("src.plugins")
plugin_registry.discover_plugins(plugins_package)
model_manager = ModelManager(plugin_registry, default_dir=os.getenv("MODELS_DIR", "./models"))
auth_token = HTTPBearer(auto_error=False)


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
    background_tasks: BackgroundTasks,
    Authorization: Optional[HTTPAuthorizationCredentials] = Depends(auth_token),
) -> Dict[str, Any]:
    """
    Download and optionally convert models.
    
    Models are downloaded from the specified hub (huggingface, ollama, etc.).
    Models will be converted to OpenVINO format if:
    1. is_ovms is set to true in the request for openvino conversion, or
    2. type can be set to 'vlm/llm/embeddings/reranker' in the request
    
    The config object is optional and used only for conversion.
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

        # Authorization for HuggingFace
        huggingface_models = any(model.hub == "huggingface" for model in request.models)
        if huggingface_models and (not Authorization or not Authorization.credentials):
            raise HTTPException(
                status_code=401,
                detail="Authorization token is required for Hugging Face models",
            )

        logger.info(f"Initiating model download for {len(request.models)} model(s)")
        job_ids = []
        
        for model in request.models:
            # Pass token for HuggingFace
            extra_kwargs = model.dict()
            needs_conversion = model.is_ovms or (model.type and model.type.lower() == "vlm")
            if model.hub.lower() in [hub.value.lower() for hub in ModelHub] and not needs_conversion:
                
                extra_kwargs["token"] = Authorization.credentials if Authorization else None
                download_path = os.path.join(
                    "models", download_path, model.hub
                )
                # First, register download job
                download_job_id = model_manager.register_job(
                    operation_type="download",
                    model_name=model.name,
                    hub=model.hub,
                    output_dir=download_path,
                    plugin_name=model.hub,
                )
                
                # Add to job_ids for response
                job_ids.append(download_job_id)
                
                # Start download in background
                background_tasks.add_task(
                    model_manager.process_download,
                    job_id=download_job_id,
                    model_name=model.name,
                    output_dir=download_path,
                    downloader=model.hub,
                    **extra_kwargs
                )

            if needs_conversion:
                # Get configuration for conversion
                extra_kwargs["token"] = Authorization.credentials if Authorization else None
                config = model.config.dict() if model.config else {}

                # Create a unique output directory for the converted model
                convert_output_dir = os.path.join( "models",
                    download_path,
                    "openvino_models",
                    config['device'],
                    config['precision']
                )

                # Register conversion job
                convert_job_id = model_manager.register_job(
                    operation_type="convert",
                    model_name=model.name,
                    hub=model.hub,
                    output_dir=convert_output_dir,
                    plugin_name="openvino"
                )
                
                # Add to job_ids for response
                job_ids.append(convert_job_id)
                
                # Start conversion in background
                background_tasks.add_task(
                    model_manager.process_conversion,
                    job_id=convert_job_id,
                    #hf_token=
                    model_path=download_path,
                    hub=model.hub,
                    output_dir=convert_output_dir,
                    converter="openvino",
                    model_name=model.name,
                    model_type=model.type,
                    **config,
                    hf_token=extra_kwargs["token"]
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


@app.get("/models/{model_name}/jobs", tags=["Jobs"])
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
            result = {
                "job_id": job_id,
                "model_name": job.get("model_name"),
                "hub": job.get("hub"),
                "operation_type": job.get("operation_type"),
                "status": "success",
                "model_path": job.get("output_dir"),
                "is_ovms": job.get("operation_type") == "convert",
                "completion_time": job.get("completion_time")
            }
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
            
            plugin_info = {
                "name": plugin_name,
                "type": plugin_type,
                "description": getattr(plugin, "__doc__", "No description available").strip(),
                "capabilities": {
                    "supports_parallel_downloads": can_handle_parallel,
                }
            }
            plugins_info[plugin_type].append(plugin_info)
    
    return {
        "available_plugins": plugins_info,
        "total_count": sum(len(plugins) for plugins in plugins_info.values())
    }
