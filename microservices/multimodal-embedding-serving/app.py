# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.common import ErrorMessages, logger, settings
from src.models import VClipModel
from src.utils import decode_base64_image, download_image

app = FastAPI(title=settings.APP_DISPLAY_NAME, description=settings.APP_DESC)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the model once
vclip_model = None
health_status = False


@app.on_event("startup")
async def startup_event():
    global vclip_model, health_status
    try:
        cfg = {"model_name": settings.MODEL_NAME}
        vclip_model = VClipModel(cfg)
        if settings.EMBEDDING_USE_OV:
            try:
                await vclip_model.async_init()
            except Exception as e:
                logger.error(f"Error initializing OpenVINO models: {e}")
                if "network" in str(e).lower() or "connection" in str(e).lower():
                    logger.warning("Network error detected. Attempting to continue in offline mode.")
                else:
                    raise
        health_status = vclip_model.check_health()
        logger.info("Model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to initialize model: {e}")
        # Keep the application running, health check will return unhealthy
        vclip_model = None
        health_status = False


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
    elif vclip_model is not None and vclip_model.check_health():
        health_status = True
        return {"status": "healthy"}
    else:
        raise HTTPException(status_code=500, detail="Model is not healthy")


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
        # logger.debug(f"Creating embedding for request: {request}")
        input_data = request.input
        if input_data.type == "text":
            if isinstance(input_data.text, list):
                embedding = vclip_model.embed_documents(input_data.text)
            else:
                embedding = vclip_model.embed_query(input_data.text)
        elif input_data.type == "image_url":
            embedding = await vclip_model.get_image_embedding_from_url(
                input_data.image_url
            )
        elif input_data.type == "image_base64":
            embedding = vclip_model.get_image_embedding_from_base64(
                input_data.image_base64
            )
        elif input_data.type == "video_frames":
            frames = []
            for frame in input_data.video_frames:
                if frame.type == "image_url":
                    frames.append(await download_image(frame.image_url))
                elif frame.type == "image_base64":
                    frames.append(decode_base64_image(frame.image_base64))
            embedding = vclip_model.get_video_embeddings([frames])
        elif input_data.type == "video_url":
            embedding = await vclip_model.get_video_embedding_from_url(
                input_data.video_url, input_data.segment_config
            )
        elif input_data.type == "video_base64":
            embedding = vclip_model.get_video_embedding_from_base64(
                input_data.video_base64, input_data.segment_config
            )
        elif input_data.type == "video_file":
            embedding = await vclip_model.get_video_embedding_from_file(
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
