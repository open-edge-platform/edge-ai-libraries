# FastAPI application entry point

import os
import gc
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import ValidationError

from ..core.plugin_registry import get_plugin
from .models import ModelDownloadRequest
from ..utils.logging import logger

app = FastAPI(root_path="/api/v1", title="Model Download Service", version="1.0.0")
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
        if any(model.hub not in {"huggingface", "ollama"} for model in request.models):
            raise HTTPException(
                status_code=400,
                detail="Unsupported model hub(s) detected. Supported hubs are 'huggingface' and 'ollama'.",
            )

        huggingface_models = any(model.hub == "huggingface" for model in request.models)
        if huggingface_models and (not Authorization or not Authorization.credentials):
            raise HTTPException(
                status_code=401,
                detail="Authorization token is required for Hugging Face models",
            )

        logger.info(f"Initiating model download for {len(request.models)} model(s)")
        model_download_path = (
            os.path.join("models", download_path) if download_path else "models"
        )

        from concurrent.futures import ThreadPoolExecutor

        def process_model(model):
            plugin = get_plugin(model.hub)
            return plugin.download(
                model=model,
                model_path=model_download_path,
                hf_token=(Authorization.credentials if Authorization else None),
            )

        with ThreadPoolExecutor(
            max_workers=len(request.models) if request.parallel_downloads else 1
        ) as executor:
            results = list(executor.map(process_model, request.models))

        gc.collect()
        response = {"message": "Model download completed", "results": results}
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
