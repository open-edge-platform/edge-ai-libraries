import os
import gc
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import List, Optional, TypedDict
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ValidationError
from huggingface_hub import snapshot_download
from .logger import logger
from .vlm_utils import vlm_compress_model, CompressionRequest

app = FastAPI(root_path="/api/v1", title="Model Download Service", version="1.0.0")
auth_token = HTTPBearer(auto_error=False)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(
        ","
    ),  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=os.getenv("CORS_ALLOW_METHODS", "*").split(","),
    allow_headers=os.getenv("CORS_ALLOW_HEADERS", "*").split(","),
)


class ModelPrecision(str, Enum):
    INT8 = "int8"
    FP16 = "fp16"
    FP32 = "fp32"


class DeviceType(str, Enum):
    CPU = "CPU"
    GPU = "GPU"


class Config(BaseModel):
    precision: ModelPrecision = ModelPrecision.INT8
    device: DeviceType = DeviceType.CPU
    cache_size: Optional[int] = Field(None, gt=0)


class ModelResult(TypedDict):
    status: str
    model_name: str
    model_path: Optional[str]
    error: Optional[str]
    is_ovms: Optional[bool]


class ModelRequest(BaseModel):
    name: str
    hub: str
    type: Optional[str] = None
    is_ovms: bool = False
    revision: Optional[str] = None
    config: Optional[Config] = None


class ModelDownloadRequest(BaseModel):
    models: List[ModelRequest]
    parallel_downloads: Optional[bool] = False


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify the service is running.
    """
    return {"status": "ok"}


@app.post("/models/download")
async def download_models(
    request: ModelDownloadRequest,
    download_path: Optional[str] = None,
    Authorization: Optional[HTTPAuthorizationCredentials] = Depends(auth_token),
):
    """
    Unified endpoint to download one or more models from Hugging Face or Ollama.

    Args:
        request: ModelDownloadRequest containing models to download and configuration
        download_path: Base directory for model downloads
        Authorization: Hugging Face API token (required only for Hugging Face models)

    Returns:
        dict: Response containing download status and results for each model

    Raises:
        HTTPException:
            - 401: If authorization token is missing for Hugging Face models
            - 422: If request validation fails
            - 400: If model download process fails
    """
    try:
        # Validate if the model hub is supported
        if any(model.hub not in {"huggingface", "ollama"} for model in request.models):
            raise HTTPException(
                status_code=400,
                detail="Unsupported model hub(s) detected. Supported hubs are 'huggingface' and 'ollama'.",
            )

        # Check if Authorization is required (only for Hugging Face models)
        huggingface_models = any(model.hub == "huggingface" for model in request.models)

        if huggingface_models and (not Authorization or not Authorization.credentials):
            raise HTTPException(
                status_code=401,
                detail="Authorization token is required for Hugging Face models",
            )

        # Log download request details with configuration
        logger.info(f"Initiating model download for {len(request.models)} model(s)")

        model_download_path = (
            os.path.join("models", download_path) if download_path else "models"
        )
        # logger.info(f"Download path: {download_path}")
        # logger.info(f"Model download path: {model_download_path}")
        # exit()
        try:
            # Process models either in parallel or sequentially
            with ThreadPoolExecutor(
                max_workers=len(request.models) if request.parallel_downloads else 1
            ) as executor:
                results = list(
                    executor.map(
                        lambda model: (
                            download_and_process_model(
                                model=model,
                                model_path=model_download_path,
                                hf_token=(
                                    Authorization.credentials if Authorization else None
                                ),
                            )
                            if model.hub == "huggingface"
                            else download_ollama_model(
                                model=model, model_path=model_download_path
                            )
                        ),
                        request.models,
                    )
                )
        except Exception as e:
            logger.error(f"Error during model download execution: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to execute model downloads: {str(e)}"
            )

        gc.collect()

        response = {"message": "Model download completed", "results": results}

        # For single model requests, maintain backward compatibility in response format
        if len(request.models) == 1:
            result = results[0]
            if result["status"] == "success":
                response.update(
                    {
                        "message": "Model downloaded successfully",
                        "model_path": result["model_path"],
                    }
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error downloading model: {result['error']}",
                )

        return response

    except ValidationError as e:
        logger.error(f"Request validation failed: {str(e)}")
        raise HTTPException(
            status_code=422, detail=f"Invalid request format: {e.errors()}"
        )
    except HTTPException:
        # Re-raise HTTP exceptions as they already have proper status codes and details
        raise
    except Exception as e:
        logger.error(f"Unexpected error in model download process: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error in model download process: {str(e)}",
        )


def download_and_process_model(
    model: ModelRequest, model_path: str, hf_token: Optional[str]
) -> ModelResult:
    """
    Download a model from Hugging Face and optionally convert it to OVMS format

    Args:
        model: The model request containing name, type, OVMS flag and configurations
        model_path: Base path for model downloads
        hf_token: Hugging Face API token

    Returns:
        ModelResult containing the status and details of the model processing

    Raises:
        OSError: If directory creation fails
        HTTPException: If model download or OVMS conversion fails
    """
    model_downloaded_path = None  # Ensure variable is always defined
    try:
        logger.info(f"Starting download for model: {model.name}")

        # Validate that HF token is provided for Hugging Face models
        if model.hub == "huggingface" and not hf_token:
            return ModelResult(
                status="error",
                model_name=model.name,
                model_path=None,
                error="Hugging Face token is required for Hugging Face models",
                is_ovms=None,
            )

        # Create model-specific directory
        model_downloaded_path = os.path.join(
            model_path, "huggingface_models", model.name.replace("/", "_")
        )
        try:
            os.makedirs(model_downloaded_path, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {model_downloaded_path}: {str(e)}")
            return ModelResult(
                status="error",
                model_name=model.name,
                model_path=None,
                error=f"Failed to create model directory: {str(e)}",
                is_ovms=None,
            )

        try:
            
            # Convert if OVMS is requested and model type is provided
            if model.is_ovms and model.type != "vlm":
                logger.info(f"Starting OVMS conversion for model: {model.name}")

                # Use model-specific OVMS config if provided, otherwise initialize default settings
                ovms_config = (
                    model.config
                    if model.config
                    else Config(
                        precision=ModelPrecision.INT8, device=DeviceType.CPU, cache_size=10
                    )
                )

                # Prepare OVMS configuration
                model_downloaded_path = os.path.join(
                    model_path,
                    "ovms_models",
                    ovms_config.device.value
                )
                logger.info(f"OVMS model directory: {model_downloaded_path}")

                try:
                    os.makedirs(model_downloaded_path, exist_ok=True)
                except OSError as e:
                    logger.error(
                        f"Failed to create OVMS directory {model_downloaded_path}: {str(e)}"
                    )
                    return ModelResult(
                        status="error",
                        model_name=model.name,
                        model_path=None,
                        error=f"Failed to create OVMS directory: {str(e)}",
                        is_ovms=None,
                    )

                ovms_params = {
                    "model_name": model.name,
                    "weight_format": ovms_config.precision.value,
                    "target_device": ovms_config.device.value,
                    "huggingface_token": hf_token,
                    "model_type": model.type,
                    "model_directory": model_downloaded_path,
                    "cache_size": ovms_config.cache_size or None,
                }

                # Filter out None values
                ovms_params = {k: v for k, v in ovms_params.items() if v is not None}

                try:
                    convert_to_ovms_format(**ovms_params)
                    logger.info(f"OVMS conversion completed for model: {model.name}")
                except HTTPException as e:
                    logger.error(f"OVMS conversion failed for {model.name}: {str(e)}")
                    return ModelResult(
                        status="error",
                        model_name=model.name,
                        model_path=None,
                        error=f"OVMS conversion failed: {str(e)}",
                        is_ovms=None,
                    )
            
            if model.type == "vlm":
                # Compress the vlm model
                vlm_compress_model(req=CompressionRequest(
                    model_name=model.name,
                    weight_format=model.config.precision.value if model.config else "int8", 
                    hf_token=hf_token,
                    model_path=model_downloaded_path
                ))
                logger.info(f"Model compression completed for: {model.name}")
            else:
                # Download model from Hugging Face
                model_downloaded_path = snapshot_download(
                    repo_id=model.name,
                    token=hf_token,
                    local_dir=model_downloaded_path,
                    revision=model.revision if model.revision else None,
                )
                logger.info(f"Model download completed: {model.name}")
                
        except Exception as e:
            logger.error(f"Failed to download model {model.name}: {str(e)}")
            return ModelResult(
                status="error",
                model_name=model.name,
                model_path=None,
                error=f"Failed to download model: {str(e)}",
                is_ovms=None,
            )
        return ModelResult(
            status="success",
            model_name=model.name,
            model_path=model_downloaded_path,
            is_ovms=model.is_ovms,
            error=None,
        )

    except Exception as e:
        logger.error(f"Model processing failed for {model.name}: {str(e)}")
        return ModelResult(
            status="error",
            model_name=model.name,
            model_path=None,
            error=f"Unexpected error: {str(e)}",
            is_ovms=None,
        )

    finally:
        if model_downloaded_path is not None:
            cleanup_model_directory(model_downloaded_path)


def download_ollama_model(model: ModelRequest, model_path: str) -> ModelResult:
    """
    Download a model from Ollama.

    Args:
        model (ModelRequest): The Ollama model request object to download.
        model_path: Base path for model downloads

    Returns:
        ModelResult: Result containing the status and details of the model processing.

    Raises:
        OSError: If directory creation fails
        HTTPException: If model download fails
    """
    import time

    if model.is_ovms:
        raise NotImplementedError(
            "Ollama models do not support OVMS conversion at this time."
        )

    model_downloaded_path = None
    try:
        # Create model-specific directory
        model_downloaded_path = os.path.join(
            model_path, "ollama_models", model.name.replace("/", "_")
        )
        os.environ["OLLAMA_MODELS"] = model_downloaded_path

        logger.info(f"Directory for Ollama model: {model_downloaded_path}")
        try:
            os.makedirs(model_downloaded_path, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {model_downloaded_path}: {str(e)}")
            return ModelResult(
                status="error",
                model_name=model.name,
                model_path=None,
                error=f"Failed to create model directory: {str(e)}",
                is_ovms=None,
            )

        logger.info("Starting ollama server")
        process = subprocess.Popen(["ollama", "serve"])

        # Sleep for 1 second to allow the server to be start
        time.sleep(1)

        logger.info(f"Starting download for Ollama model: {model.name}")
        subprocess.run(["ollama", "pull", model.name], check=True)
        logger.info(f"Ollama model {model} downloaded successfully.")

        return ModelResult(
            status="success",
            model_name=model.name,
            model_path=model_downloaded_path,
            error=None,
            is_ovms=model.is_ovms,
        )

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to download Ollama model {model}: {str(e)}")
        return ModelResult(
            status="error",
            model_name=model.name,
            model_path=None,
            error=f"Failed to download Ollama model: {str(e)}",
            is_ovms=False,
        )
    finally:
        logger.info("Stopping ollama server")
        process.terminate()
        if model_downloaded_path is not None:
            cleanup_model_directory(model_downloaded_path)


def convert_to_ovms_format(
    model_name: str,
    weight_format: str,
    huggingface_token: Optional[str],
    model_type: str,
    target_device: str,
    model_directory: str,
    cache_size: Optional[int] = None,
):
    """
    Convert a downloaded model to OpenVINO Model Server (OVMS) format.

    Args:
        model_name (str): The name of the Hugging Face model to download.
        weight_format (str): The weight format for the exported model (e.g., "int4", "fp16").
        huggingface_token (str): The Hugging Face API token for authentication.
        model_type (str): The type of the model (e.g., "llm", "embeddings", "rerank").
        cache_size (int, optional): Cache size for model optimization.

    Raises:
        HTTPException: If model type is invalid, authentication fails, or model conversion fails
    """
    # Map model_type to export type
    export_type_map = {
        "llm": "text_generation",
        "embeddings": "embeddings",
        "rerank": "rerank",
    }

    # Validate model_type
    if model_type not in export_type_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type: {model_type}. Must be one of {list(export_type_map.keys())}.",
        )

    export_type = export_type_map[model_type]

    try:
        # Validate that HF token is provided for OVMS conversion
        if not huggingface_token:
            raise HTTPException(
                status_code=401,
                detail="Hugging Face token is required for OVMS conversion",
            )

        # Step 1: Log in to Hugging Face
        logger.info("Logging in to Hugging Face...")
        result = subprocess.run(
            ["huggingface-cli", "login", "--token", huggingface_token]
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=401,
                detail="Failed to authenticate with Hugging Face. Please check your token.",
            )

        # Step 2: Download the export_model.py script
        logger.info("Checking for export_model.py script...")
        export_script_url = "https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/0/demos/common/export_models/export_model.py"
        if not os.path.exists("export_model.py"):
            logger.info("Downloading export_model.py script...")
            try:
                subprocess.run(
                    ["curl", "-o", "export_model.py", export_script_url], check=True
                )
            except subprocess.CalledProcessError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to download export script: {str(e)}",
                )
        else:
            logger.info("export_model.py already exists, skipping download.")

        # Step 3: Export the model
        logger.info(
            f"Exporting model: {model_name} with weight format: {weight_format} and export type: {export_type}..."
        )

        # models directory
        os.makedirs(model_directory, exist_ok=True)

        # Build command with base arguments
        command = [
            "python3",
            "export_model.py",
            export_type,
            "--source_model",
            model_name,
            "--weight-format",
            weight_format,
            "--config_file_path",
            f"{model_directory}/config.json",
            "--model_repository_path",
            model_directory,
            "--target_device",
            target_device,
        ]

        # Add optional parameters if provided
        if export_type == "text_generation" and cache_size is not None:
            command += ["--cache_size", str(cache_size)]

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Model conversion failed: {str(e)}. Check if the model is compatible with the specified format and device.",
            )

        return {
            "message": f"Model successfully downloaded, converted, and prepared for OVMS deployment as {export_type}."
        }

    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        logger.error(f"Unexpected error during model conversion: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during model conversion: {str(e)}",
        )


def cleanup_model_directory(model_dir_path: str):
    subdirs = [
        os.path.join(model_dir_path, d)
        for d in os.listdir(model_dir_path)
        if os.path.isdir(os.path.join(model_dir_path, d))
    ]
    if not os.listdir(model_dir_path) or all(not os.listdir(d) for d in subdirs):
        try:
            logger.warning(
                f"No files found in the directory {model_dir_path}. Removing empty directory."
            )
            shutil.rmtree(model_dir_path)

        except OSError as e:
            logger.error(f"Failed to remove empty directory {model_dir_path}: {str(e)}")
