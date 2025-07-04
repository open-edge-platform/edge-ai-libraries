# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List, Union, Optional, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.common import ErrorMessages, logger, settings
from src.embedding_models import VClipModel, Qwen3Model, QwenEmbeddings
from src.utils import decode_base64_image, download_image

app = FastAPI(title=settings.APP_DISPLAY_NAME, description=settings.APP_DESC)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set the global embedder API to None initially
embedder: Any = None
health_status = False


@app.on_event("startup")
async def startup_event():
    global embedder, health_status

    # Configuration for the vclip and qwen embedding model
    config: dict = {
        "vclip_model_name": settings.IMAGE_EMBEDDING_MODEL_NAME,
        "qwen_model_name": settings.TEXT_EMBEDDING_MODEL_NAME,
        "qwen_sequence_length": 8192,
        "vclip_sequence_length": 77,
    }

    # Load Qwen model if only text embeddings are used, otherwise load VClip model
    if settings.USE_ONLY_TEXT_EMBEDDINGS:
        embedder = QwenEmbeddings(model=Qwen3Model(config))
        logger.debug("Using Qwen model to generate text embeddings only.")
    else:
        embedder = VClipModel(config)
        logger.debug("Using VClip model to generate text and image embeddings.")
        if settings.EMBEDDING_USE_OV:
            await embedder.async_init()
        health_status = embedder.check_health()

    logger.info("Model loaded successfully")


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
    model: Optional[str] = None
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

    def model_post_init(self, __context):
        super().model_post_init(__context)
        if settings.USE_ONLY_TEXT_EMBEDDINGS and self.input.type != "text":
            raise ValueError(
                "Invalid input type. With current configuration of Embedding API Service, only text inputs are allowed."
            )


@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        dict: Dictionary containing the health status.
    """
    return {"status": "healthy"}


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
        input_data = request.input
        if input_data.type == "text":
            if isinstance(input_data.text, list):
                embedding = embedder.embed_documents(input_data.text)
            else:
                embedding = embedder.embed_query(input_data.text)
                    
        elif input_data.type == "image_url":
            embedding = await embedder.get_image_embedding_from_url(
                input_data.image_url
            )
        elif input_data.type == "image_base64":
            embedding = embedder.get_image_embedding_from_base64(
                input_data.image_base64
            )
        elif input_data.type == "video_frames":
            frames = []
            for frame in input_data.video_frames:
                if frame.type == "image_url":
                    frames.append(await download_image(frame.image_url))
                elif frame.type == "image_base64":
                    frames.append(decode_base64_image(frame.image_base64))
            embedding = embedder.get_video_embeddings([frames])
        elif input_data.type == "video_url":
            embedding = await embedder.get_video_embedding_from_url(
                input_data.video_url, input_data.segment_config
            )
        elif input_data.type == "video_base64":
            embedding = embedder.get_video_embedding_from_base64(
                input_data.video_base64, input_data.segment_config
            )
        elif input_data.type == "video_file":
            embedding = await embedder.get_video_embedding_from_file(
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
