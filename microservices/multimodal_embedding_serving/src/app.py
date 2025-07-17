# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .utils import ErrorMessages, logger, settings, decode_base64_image, download_image
from .models import ModelFactory, get_model_handler, list_available_models
from .wrapper import EmbeddingModel

app = FastAPI(title=settings.APP_DISPLAY_NAME, description=settings.APP_DESC)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the model once
embedding_model = None
health_status = False


@app.on_event("startup")
async def startup_event():
    global embedding_model, health_status
    logger.info(f"Starting application with model: {settings.EMBEDDING_MODEL_NAME}")
    
    # Check if the model is supported
    if not ModelFactory.is_model_supported(settings.EMBEDDING_MODEL_NAME):
        logger.error(f"Model {settings.EMBEDDING_MODEL_NAME} is not supported")
        available_models = list_available_models()
        logger.error(f"Available models: {available_models}")
        raise RuntimeError(f"Unsupported model: {settings.EMBEDDING_MODEL_NAME}")
    
    # Create model using the factory pattern
    try:
        model_handler = get_model_handler(settings.EMBEDDING_MODEL_NAME)
        model_handler.load_model()
        
        # Note: OpenVINO conversion is handled within load_model() if use_openvino=True
        # No need to call convert_to_openvino() separately
        
        # Wrap with application-level functionality
        embedding_model = EmbeddingModel(model_handler)
        
        # Check model health
        health_status = embedding_model.check_health()
        logger.info(f"Model {settings.EMBEDDING_MODEL_NAME} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load model {settings.EMBEDDING_MODEL_NAME}: {e}")
        raise RuntimeError(f"Failed to initialize model: {e}")


class TextInput(BaseModel):
    type: str
    text: Union[str, List[str]]


class ImageUrlInput(BaseModel):
    type: str
    image_url: str


class ImageBase64Input(BaseModel):
    type: str
    image_base64: str


class VideoFramesInput(BaseModel):
    type: str
    video_frames: List[Union[ImageUrlInput, ImageBase64Input]]


class VideoUrlInput(BaseModel):
    type: str
    video_url: str
    segment_config: dict


class VideoBase64Input(BaseModel):
    type: str
    video_base64: str
    segment_config: dict


class VideoFileInput(BaseModel):
    type: str
    video_path: str
    segment_config: dict


class EmbeddingRequest(BaseModel):
    model: str
    input: Union[
        TextInput,
        ImageUrlInput,
        ImageBase64Input,
        VideoFramesInput,
        VideoUrlInput,
        VideoBase64Input,
        VideoFileInput,
    ]
    encoding_format: str


@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        dict: Dictionary containing the health status.
    """
    global health_status
    if health_status:
        return {"status": "healthy"}
    elif embedding_model.check_health():
        health_status = True
        return {"status": "healthy"}
    else:
        raise HTTPException(status_code=500, detail="Model is not healthy")


@app.get("/models")
async def list_models() -> dict:
    """
    List all available models.

    Returns:
        dict: Dictionary containing available models and their configurations.
    """
    try:
        available_models = list_available_models()
        current_model = settings.EMBEDDING_MODEL_NAME
        
        return {
            "current_model": current_model,
            "available_models": available_models,
            "total_models": sum(len(models) for models in available_models.values())
        }
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing models: {e}")


@app.get("/model/current")
async def get_current_model() -> dict:
    """
    Get the currently loaded model name and basic configuration.

    Returns:
        dict: Dictionary containing current model name and configuration.
    """
    return {
        "model": settings.EMBEDDING_MODEL_NAME,
        "device": settings.EMBEDDING_DEVICE,
        "use_openvino": settings.EMBEDDING_USE_OV,
    }


@app.post("/embeddings")
async def create_embedding(request: EmbeddingRequest) -> dict:
    """
    Creates an embedding based on the input data.

    Args:
        request (EmbeddingRequest): Request object containing model and input data.

    Returns:
        dict: Dictionary containing the embedding.

    Raises:
        HTTPException: If there is an error during the embedding process.
    """
    try:
        # Check if requested model matches the currently loaded model
        if request.model != settings.EMBEDDING_MODEL_NAME:
            logger.warning(f"Model mismatch: requested '{request.model}', but server is running '{settings.EMBEDDING_MODEL_NAME}'")
            raise HTTPException(
                status_code=400, 
                detail=f"Model mismatch: requested model '{request.model}' does not match the currently loaded model '{settings.EMBEDDING_MODEL_NAME}'. Please use the correct model name or restart the server with the desired model."
            )
        
        # logger.debug(f"Creating embedding for request: {request}")
        input_data = request.input
        if input_data.type == "text":
            if isinstance(input_data.text, list):
                embedding = embedding_model.embed_documents(input_data.text)
            else:
                embedding = embedding_model.embed_query(input_data.text)
        elif input_data.type == "image_url":
            embedding = await embedding_model.get_image_embedding_from_url(
                input_data.image_url
            )
        elif input_data.type == "image_base64":
            embedding = embedding_model.get_image_embedding_from_base64(
                input_data.image_base64
            )
        elif input_data.type == "video_frames":
            frames = []
            for frame in input_data.video_frames:
                if frame.type == "image_url":
                    frames.append(await download_image(frame.image_url))
                elif frame.type == "image_base64":
                    frames.append(decode_base64_image(frame.image_base64))
            embedding = embedding_model.get_video_embeddings([frames])
        elif input_data.type == "video_url":
            embedding = await embedding_model.get_video_embedding_from_url(
                input_data.video_url, input_data.segment_config
            )
        elif input_data.type == "video_base64":
            embedding = embedding_model.get_video_embedding_from_base64(
                input_data.video_base64, input_data.segment_config
            )
        elif input_data.type == "video_file":
            embedding = await embedding_model.get_video_embedding_from_file(
                input_data.video_path, input_data.segment_config
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid input type")

        logger.info("Embedding created successfully")
        return {"embedding": embedding}
    except HTTPException as e:
        logger.error(f"HTTP error creating embedding: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Error creating embedding: {e}")
        raise HTTPException(
            status_code=500, detail=f"{ErrorMessages.CREATE_EMBEDDING_ERROR}: {e}"
        )
