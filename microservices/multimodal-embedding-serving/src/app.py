# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
FastAPI application for multimodal embedding serving.

This module provides a REST API for generating embeddings from various input types:
- Text queries and documents
- Images from URLs or base64 encoded data  
- Videos from URLs, base64, or file paths with frame extraction

The application supports multiple embedding models including CLIP, MobileCLIP, 
SigLIP, and BLIP2, with optional OpenVINO optimization for improved performance.

Key endpoints:
- /health: Health check endpoint
- /models: List available models
- /model/current: Get current model information
- /embeddings: Generate embeddings from input data

The application follows a factory pattern for model instantiation and provides
comprehensive error handling and logging.
"""

from typing import List, Union, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
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
    """
    Application startup event handler.
    
    Initializes the embedding model based on configuration settings.
    Validates model support, loads the model handler, and performs health checks.
    
    Raises:
        RuntimeError: If model is not supported or fails to initialize
    """
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
    """
    Input model for text data.
    
    Attributes:
        type: Input type identifier (should be "text")
        text: Single text string or list of text strings to embed
    """
    type: str
    text: Union[str, List[str]]


class ImageUrlInput(BaseModel):
    """
    Input model for image URLs.
    
    Attributes:
        type: Input type identifier (should be "image_url")
        image_url: URL of the image to download and embed
    """
    type: str
    image_url: str


class ImageBase64Input(BaseModel):
    """
    Input model for base64 encoded images.
    
    Attributes:
        type: Input type identifier (should be "image_base64")
        image_base64: Base64 encoded image string
    """
    type: str
    image_base64: str


class VideoFramesInput(BaseModel):
    """
    Input model for video represented as individual frames.
    
    Attributes:
        type: Input type identifier (should be "video_frames")
        video_frames: List of image frames as URLs or base64 data
    """
    type: str
    video_frames: List[Union[ImageUrlInput, ImageBase64Input]]


class VideoUrlInput(BaseModel):
    """
    Input model for video URLs with segmentation configuration.
    
    Attributes:
        type: Input type identifier (should be "video_url")
        video_url: URL of the video to download and process
        segment_config: Configuration for video frame extraction
    """
    type: str
    video_url: str
    segment_config: dict


class VideoBase64Input(BaseModel):
    """
    Input model for base64 encoded videos.
    
    Attributes:
        type: Input type identifier (should be "video_base64")
        video_base64: Base64 encoded video string
        segment_config: Configuration for video frame extraction
    """
    type: str
    video_base64: str
    segment_config: dict


class VideoFileInput(BaseModel):
    """
    Input model for local video files.
    
    Attributes:
        type: Input type identifier (should be "video_file")
        video_path: Path to the local video file
        segment_config: Configuration for video frame extraction
    """
    type: str
    video_path: str
    segment_config: dict


class FramesBatchInput(BaseModel):
    type: str
    frames_manifest_path: str


# Pydantic models for frames manifest validation
class FrameInfo(BaseModel):
    """Individual frame information in the manifest."""
    frame_number: int = Field(..., ge=0, description="Frame number in the video")
    timestamp: float = Field(..., ge=0.0, description="Timestamp in seconds")
    image_path: Optional[str] = Field(None, description="Absolute path to the frame image file (None for video-based processing)")
    type: str = Field(..., pattern="^(full_frame|detected_crop)$", description="Type of frame")
    frame_interval: Optional[int] = Field(None, ge=1, description="Frame extraction interval used")
    
    # Optional fields for detected crops
    is_detected_crop: Optional[bool] = Field(False, description="Whether this is a detected object crop")
    detection_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Detection confidence score")
    crop_bbox: Optional[List[int]] = Field(None, description="Bounding box coordinates [x1, y1, x2, y2]")
    crop_index: Optional[int] = Field(None, ge=0, description="Crop index for the frame")
    
    @validator('crop_bbox')
    def validate_bbox(cls, v):
        if v is not None:
            if len(v) != 4:
                raise ValueError('crop_bbox must have exactly 4 elements [x1, y1, x2, y2]')
            # Convert floats to integers and ensure they're non-negative
            try:
                v = [int(round(x)) if isinstance(x, (float, int)) else int(x) for x in v]
            except (ValueError, TypeError):
                raise ValueError('crop_bbox values must be numeric')
            if not all(x >= 0 for x in v):
                raise ValueError('crop_bbox values must be non-negative integers')
            if v[0] >= v[2] or v[1] >= v[3]:
                raise ValueError('Invalid bounding box: x1 < x2 and y1 < y2 required')
        return v


class FramesManifest(BaseModel):
    """Complete frames manifest structure."""
    frames: List[FrameInfo] = Field(..., min_items=1, description="List of frame information")
    
    # Optional metadata
    video_metadata: Optional[dict] = Field(None, description="Original video metadata")
    processing_metadata: Optional[dict] = Field(None, description="Processing configuration metadata")
    
    @validator('frames')
    def validate_frames_not_empty(cls, v):
        if not v:
            raise ValueError('frames list cannot be empty')
        return v


class EmbeddingRequest(BaseModel):
    """
    Main request model for embedding generation.
    
    Attributes:
        model: Name of the model to use for embedding generation
        input: Input data (text, image, or video in various formats)
        encoding_format: Format for the returned embeddings
    """
    model: str
    input: Union[
        TextInput,
        ImageUrlInput,
        ImageBase64Input,
        VideoFramesInput,
        VideoUrlInput,
        VideoBase64Input,
        VideoFileInput,
        FramesBatchInput,
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


@app.get("/model/capabilities")
async def get_model_capabilities() -> dict:
    """Expose supported modalities for the loaded model."""
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Model is not initialized")
    return {
        "model": settings.EMBEDDING_MODEL_NAME,
        "modalities": embedding_model.get_supported_modalities(),
        "supports_text": embedding_model.supports_text(),
        "supports_image": embedding_model.supports_image(),
        "supports_video": embedding_model.supports_video(),
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
        if embedding_model is None:
            raise HTTPException(status_code=503, detail="Model is not initialized")

        # logger.debug(f"Creating embedding for request: {request}")
        input_data = request.input
        if input_data.type == "text":
            if isinstance(input_data.text, list):
                embedding = embedding_model.embed_documents(input_data.text)
            else:
                embedding = embedding_model.embed_query(input_data.text)
        elif input_data.type == "image_url":
            if not embedding_model.supports_image():
                raise HTTPException(status_code=400, detail="Image inputs are not supported by the active model")
            embedding = await embedding_model.get_image_embedding_from_url(
                input_data.image_url
            )
        elif input_data.type == "image_base64":
            if not embedding_model.supports_image():
                raise HTTPException(status_code=400, detail="Image inputs are not supported by the active model")
            embedding = embedding_model.get_image_embedding_from_base64(
                input_data.image_base64
            )
        elif input_data.type == "video_frames":
            if not embedding_model.supports_video():
                raise HTTPException(status_code=400, detail="Video inputs are not supported by the active model")
            frames = []
            for frame in input_data.video_frames:
                if frame.type == "image_url":
                    frames.append(await download_image(frame.image_url))
                elif frame.type == "image_base64":
                    frames.append(decode_base64_image(frame.image_base64))
            embedding = embedding_model.get_video_embeddings([frames])
        elif input_data.type == "video_url":
            if not embedding_model.supports_video():
                raise HTTPException(status_code=400, detail="Video inputs are not supported by the active model")
            embedding = await embedding_model.get_video_embedding_from_url(
                input_data.video_url, input_data.segment_config
            )
        elif input_data.type == "video_base64":
            if not embedding_model.supports_video():
                raise HTTPException(status_code=400, detail="Video inputs are not supported by the active model")
            embedding = embedding_model.get_video_embedding_from_base64(
                input_data.video_base64, input_data.segment_config
            )
        elif input_data.type == "video_file":
            if not embedding_model.supports_video():
                raise HTTPException(status_code=400, detail="Video inputs are not supported by the active model")
            embedding = await embedding_model.get_video_embedding_from_file(
                input_data.video_path, input_data.segment_config
            )
        elif input_data.type == "frames_batch":
            if not embedding_model.supports_video():
                raise HTTPException(status_code=400, detail="Video inputs are not supported by the active model")
            embedding = await embedding_model.get_video_embedding_from_frames_manifest(
                input_data.frames_manifest_path
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid input type")

        logger.info("Embedding created successfully")
        return {"embedding": embedding}
    except HTTPException as e:
        logger.error(f"HTTP error creating embedding: {e.detail}")
        raise e
    except FileNotFoundError as e:
        logger.error(f"File not found error creating embedding: {e}")
        raise HTTPException(status_code=404, detail=f"File not found: {e}")
    except ValueError as e:
        logger.error(f"Validation error creating embedding: {e}")
        raise HTTPException(status_code=422, detail=f"Invalid input data: {e}")
    except Exception as e:
        logger.error(f"Error creating embedding: {e}")
        raise HTTPException(
            status_code=500, detail=f"{ErrorMessages.CREATE_EMBEDDING_ERROR}: {e}"
        )
