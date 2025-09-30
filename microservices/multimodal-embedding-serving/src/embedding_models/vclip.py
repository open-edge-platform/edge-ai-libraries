# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
from pathlib import Path
from typing import List, Union

import numpy as np
import openvino as ov
import openvino.properties.hint as hints
import torch
from einops import rearrange
from fastapi import HTTPException
from PIL import Image
from transformers import AutoProcessor, AutoTokenizer, CLIPModel
from src.common import ErrorMessages, logger, settings
from src.utils import (
    decode_base64_image,
    decode_base64_video,
    delete_file,
    download_image,
    download_video,
    extract_video_frames,
)


class VClipModel:
    """
    A class to handle video CLIP (Contrastive Language-Image Pretraining) model operations.

    Attributes:
        num_frm (int): Number of frames.
        model_name (str): Name of the pre-trained model.
        clip (CLIPModel): The CLIP model instance.
        processor (AutoProcessor): The processor for handling image inputs.
        tokenizer (AutoTokenizer): The tokenizer for handling text inputs.

    Methods:
        embed_query(texts):
            Embeds a list of text queries into text features.
            Args:
                texts (list of str): List of text queries.
            Returns:
                torch.Tensor: Text features tensor.

        get_embedding_length():
            Gets the length of the embedding vector.
            Returns:
                int: Length of the embedding vector.

        get_image_embeddings(images):
            Embeds a list of images into image features.
            Args:
                images (list of PIL.Image or np.ndarray): List of images.
            Returns:
                torch.Tensor: Image features tensor.

        get_video_embeddings(frames_batch):
            Embeds a batch of video frames into video features.
            Args:
                frames_batch (list of list of PIL.Image or np.ndarray): List of list of frames in videos.
            Returns:
                torch.Tensor: Video features tensor.
    """

    def __init__(self, cfg: dict) -> None:
        """
        Initializes the VClipModel with the given configuration.

        Args:
            cfg (dict): Configuration dictionary containing model name.
        """
        self.model_name = cfg.get("vclip_model_name")
        # Create paths for local storage
        flattened_model_name = self.model_name.replace("/", "_")
        self.ov_dir = Path(settings.EMBEDDING_MODEL_PATH)
        self.ov_dir.mkdir(parents=True, exist_ok=True)

        self.processor_dir = self.ov_dir / f"{flattened_model_name}_processor"
        self.tokenizer_dir = self.ov_dir / f"{flattened_model_name}_tokenizer"
        self.model_dir = self.ov_dir / f"{flattened_model_name}_model"

        # Try to load from local storage, fall back to online if not available
        try:
            logger.info(f"Attempting to load models from local storage at {self.ov_dir}")
            if self.model_dir.exists():
                self.clip = CLIPModel.from_pretrained(str(self.model_dir))
            else:
                self.clip = CLIPModel.from_pretrained(self.model_name)
                self.clip.save_pretrained(str(self.model_dir))
                logger.info(f"Saved model to {self.model_dir}")

            if self.processor_dir.exists():
                self.processor = AutoProcessor.from_pretrained(str(self.processor_dir))
            else:
                self.processor = AutoProcessor.from_pretrained(self.model_name)
                self.processor.save_pretrained(str(self.processor_dir))
                logger.info(f"Saved processor to {self.processor_dir}")

            if self.tokenizer_dir.exists():
                self.tokenizer = AutoTokenizer.from_pretrained(str(self.tokenizer_dir))
            else:
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self.tokenizer.save_pretrained(str(self.tokenizer_dir))
                logger.info(f"Saved tokenizer to {self.tokenizer_dir}")

        except Exception as e:
            logger.error(f"Error loading models locally: {e}. Attempting to download from HuggingFace.")
            # Fallback to online loading
            self.clip = CLIPModel.from_pretrained(self.model_name)
            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

            # Try to save them for future use
            try:
                self.clip.save_pretrained(str(self.model_dir))
                self.processor.save_pretrained(str(self.processor_dir))
                self.tokenizer.save_pretrained(str(self.tokenizer_dir))
                logger.info(f"Downloaded and saved models to {self.ov_dir}")
            except Exception as save_error:
                logger.error(f"Failed to save models locally: {save_error}")

        self.text_model = None
        self.image_model = None

    async def async_init(self):
        """
        Asynchronous initialization for the VClipModel.
        """
        flattened_model_name = self.model_name.replace("/", "_")
        text_model_path = self.ov_dir / f"{flattened_model_name}_text.xml"
        image_model_path = self.ov_dir / f"{flattened_model_name}_image.xml"

        if not text_model_path.exists() or not image_model_path.exists():
            logger.info(
                f"Model files for model {self.model_name} not found in {self.ov_dir}. Converting and saving the models"
            )
            await self.download_convert_clip_model(text_model_path, image_model_path)
        core = ov.Core()
        core.set_property(
            settings.EMBEDDING_DEVICE,
            {hints.execution_mode: hints.ExecutionMode.PERFORMANCE},
        )
        self.text_model = core.compile_model(
            model=text_model_path,
            device_name=settings.EMBEDDING_DEVICE,
            config={hints.performance_mode(): hints.PerformanceMode.THROUGHPUT},
        )
        logger.info(
            f"Compiled model for device: {settings.EMBEDDING_DEVICE} with performance hint: THROUGHPUT"
        )
        self.image_model = core.compile_model(
            model=image_model_path,
            device_name=settings.EMBEDDING_DEVICE,
            config={hints.performance_mode(): hints.PerformanceMode.THROUGHPUT},
        )

    async def download_convert_clip_model(self, text_model_path, image_model_path):
        """
        The model currently uses PyTorch. To get an IR, you need to use Model Conversion API. `ov.convert_model` function accepts PyTorch model object and example input and converts it to OpenVINO Model instance, that is ready to load on device using `ov.compile_model` or can be saved on disk using `ov.save_model`.
        To separate model on text and image parts, we overload forward method with `get_text_features` and `get_image_features` methods respectively. Internally, PyTorch conversion to OpenVINO involves TorchScript tracing. For achieving better conversion results, we need to guarantee that model can be successfully traced. `model.config.torchscript = True` parameters allows to prepare HuggingFace models for TorchScript tracing.
        """

        query = "just a sample text"
        image_path = Path(__file__).parent.parent / "sample" / "sample_image.jpg"
        image = Image.open(image_path)
        im_tensor = np.array(image)
        inputs = self.processor(text=[query], images=[im_tensor], return_tensors="pt")
        self.clip.config.torchscript = True
        self.clip.forward = self.clip.get_text_features
        text_ov_model = ov.convert_model(
            self.clip,
            example_input={
                "input_ids": inputs.input_ids,
                "attention_mask": inputs.attention_mask,
            },
        )
        crops_info = (
            self.processor.image_processor.crop_size.values()
            if hasattr(self.processor, "image_processor")
            else self.processor.feature_extractor.crop_size.values()
        )
        self.clip.forward = self.clip.get_image_features
        image_ov_model = ov.convert_model(
            self.clip,
            example_input={"pixel_values": inputs.pixel_values},
            # input=[64, 3, *crops_info],
        )
        ov.save_model(text_ov_model, text_model_path)
        ov.save_model(image_ov_model, image_model_path)

    def get_text_features(self, texts: List[str]) -> torch.Tensor:
        """
        Gets text features from the CLIP model.

        Args:
            texts (list of str): List of text queries.

        Returns:
            torch.Tensor: Text features tensor.

        Raises:
            RuntimeError: If there is an error during the text feature extraction process.
        """
        try:
            logger.debug(f"Getting text features for texts: {texts}")
            text_inputs = self.tokenizer(
                texts, padding=True, truncation=True, return_tensors="pt"
            )
            # # Convert BatchEncoding to dictionary
            if settings.EMBEDDING_USE_OV:
                text_inputs = {k: v for k, v in text_inputs.items()}
                text_features = self.text_model(text_inputs)[self.text_model.output()]
            else:
                text_features = self.clip.get_text_features(**text_inputs)
            logger.info("Text features extracted successfully")
            return text_features
        except Exception as e:
            logger.error(f"Error getting text features: {e}")
            raise RuntimeError(f"{ErrorMessages.GET_TEXT_FEATURES_ERROR}: {e}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embeds a list of text documents into text features.

        Args:
            texts (List[str]): List of text documents.

        Returns:
            List[List[float]]: List of text features.

        Raises:
            RuntimeError: If there is an error during the embedding process.
        """
        try:
            logger.debug(f"Embedding documents: {texts}")
            text_features = self.get_text_features(texts)
            logger.info("Documents embedded successfully")
            return text_features.tolist()
        except Exception as e:
            logger.error(f"Error embedding documents: {e}")
            raise RuntimeError(f"{ErrorMessages.EMBED_DOCUMENTS_ERROR}: {e}")

    def embed_query(self, text: str) -> List[float]:
        """
        Embeds a single text query into text features.

        Args:
            text (str): Text query.

        Returns:
            List[float]: Text features.

        Raises:
            RuntimeError: If there is an error during the embedding process.
        """
        try:
            logger.debug(f"Embedding query: {text}")
            text_features = self.get_text_features([text])
            logger.info("Query embedded successfully")
            return text_features.tolist()[0]
        except Exception as e:
            logger.error(f"Error embedding query: {e}")
            raise RuntimeError(f"{ErrorMessages.EMBED_QUERY_ERROR}: {e}")

    def get_embedding_length(self) -> int:
        """
        Gets the length of the embedding vector.

        Returns:
            int: Length of the embedding vector.
        """
        text_features = self.get_text_features(["sample_text"])
        return text_features.shape[1]

    def get_image_embeddings(
        self, images: List[Union[Image.Image, np.ndarray]]
    ) -> torch.Tensor:
        """
        Gets image features from the CLIP model.

        Args:
            images (list of PIL.Image or np.ndarray): List of images.

        Returns:
            torch.Tensor: Image features tensor.

        Raises:
            RuntimeError: If there is an error during the image feature extraction process.
        """
        try:
            logger.debug("Getting image embeddings")
            image_inputs = self.processor(images=images, return_tensors="pt")
            if settings.EMBEDDING_USE_OV:
                # Convert BatchEncoding to dictionary
                image_inputs = {k: v for k, v in image_inputs.items()}
                image_features = self.image_model(image_inputs)[
                    self.image_model.output()
                ]
            else:
                image_features = self.clip.get_image_features(**image_inputs)
            logger.info("Image embeddings extracted successfully")
            return image_features
        except Exception as e:
            logger.error(f"Error getting image embeddings: {e}")
            raise RuntimeError(f"{ErrorMessages.GET_IMAGE_EMBEDDINGS_ERROR}: {e}")

    def get_video_embeddings(
        self, frames_batch: List[List[Union[Image.Image, np.ndarray]]]
    ) -> torch.Tensor:
        """
        Gets video features from the CLIP model.

        Args:
            frames_batch (list of list of PIL.Image or np.ndarray): List of list of frames in videos.

        Returns:
            torch.Tensor: Video features tensor.

        Raises:
            RuntimeError: If there is an error during the video feature extraction process.
        """
        try:
            logger.debug("Getting video embeddings")
            start_time = time.time()
            self.batch_size = len(frames_batch)
            vid_embs = []
            total_frames = 0
            for frames in frames_batch:
                total_frames += len(frames)
                frame_embeddings = self.get_image_embeddings(frames)
                frame_embeddings = rearrange(
                    frame_embeddings, "(b n) d -> b n d", b=len(frames_batch)
                )
                if settings.EMBEDDING_USE_OV:
                    frame_embeddings = torch.tensor(frame_embeddings)
                # Normalize, mean aggregate and return normalized video_embeddings
                frame_embeddings = frame_embeddings / frame_embeddings.norm(
                    dim=-1, keepdim=True
                )
                video_embeddings = frame_embeddings.mean(dim=1)
                video_embeddings = video_embeddings / video_embeddings.norm(
                    dim=-1, keepdim=True
                )
                vid_embs.append(video_embeddings)
            end_time = time.time()
            logger.info(
                f"Processed {total_frames} frames in {end_time - start_time:.2f} seconds"
            )
            logger.info("Video embeddings extracted successfully")
            return torch.cat(vid_embs, dim=0).tolist()[0]
        except Exception as e:
            logger.error(f"Error getting video embeddings: {e}")
            raise RuntimeError(f"{ErrorMessages.GET_VIDEO_EMBEDDINGS_ERROR}: {e}")

    async def get_image_embedding_from_url(self, image_url: str) -> List[float]:
        """
        Gets image features from a URL.

        Args:
            image_url (str): URL of the image.

        Returns:
            List[float]: Image features.

        Raises:
            RuntimeError: If there is an error during the image feature extraction process.
        """
        try:
            logger.debug(f"Getting image embedding from URL: {image_url}")
            image_data = await download_image(image_url)
            logger.info("Image embedding extracted successfully from URL")
            return self.get_image_embeddings([image_data]).tolist()[0]
        except Exception as e:
            logger.error(f"Error getting image embedding from URL: {e}")
            raise RuntimeError(
                f"{ErrorMessages.GET_IMAGE_EMBEDDING_FROM_URL_ERROR}: {e}"
            )

    def get_image_embedding_from_base64(self, image_base64: str) -> List[float]:
        """
        Gets image features from a base64 encoded image.

        Args:
            image_base64 (str): Base64 encoded image string.

        Returns:
            List[float]: Image features.

        Raises:
            RuntimeError: If there is an error during the image feature extraction process.
        """
        try:
            logger.debug("Getting image embedding from base64")
            image_data = decode_base64_image(image_base64)
            logger.info("Image embedding extracted successfully from base64")
            return self.get_image_embeddings([image_data]).tolist()[0]
        except Exception as e:
            logger.error(f"Error getting image embedding from base64: {e}")
            raise RuntimeError(
                f"{ErrorMessages.GET_IMAGE_EMBEDDING_FROM_BASE64_ERROR}: {e}"
            )

    async def get_video_embedding_from_url(
        self, video_url: str, segment_config: dict = None
    ) -> List[float]:
        """
        Gets video features from a URL.

        Args:
            video_url (str): URL of the video.
            segment_config (dict, optional): Configuration for video segmentation. Defaults to None.

        Returns:
            List[float]: Video features.

        Raises:
            RuntimeError: If there is an error during the video feature extraction process.
        """
        try:
            logger.debug(f"Getting video embedding from URL: {video_url}")
            video_path = await download_video(video_url)
            clip_images = extract_video_frames(video_path, segment_config)
            delete_file(video_path)
            logger.info("Video embedding extracted successfully from URL")
            return self.get_video_embeddings([clip_images])
        except Exception as e:
            logger.error(f"Error getting video embedding from URL: {e}")
            raise RuntimeError(
                f"{ErrorMessages.GET_VIDEO_EMBEDDING_FROM_URL_ERROR}: {e}"
            )

    def get_video_embedding_from_base64(
        self, video_base64: str, segment_config: dict = None
    ) -> List[float]:
        """
        Gets video features from a base64 encoded video.

        Args:
            video_base64 (str): Base64 encoded video string.
            segment_config (dict): Configuration for video segmentation. Defaults to None.

        Returns:
            List[float]: Video features.

        Raises:
            RuntimeError: If there is an error during the video feature extraction process.
        """
        try:
            logger.debug("Getting video embedding from base64")
            video_path = decode_base64_video(video_base64)
            clip_images = extract_video_frames(video_path, segment_config)
            delete_file(video_path)
            logger.info("frames extracted successfully from base64")
            return self.get_video_embeddings([clip_images])
        except Exception as e:
            logger.error(f"Error getting video embedding from base64: {e}")
            raise RuntimeError(
                f"{ErrorMessages.GET_VIDEO_EMBEDDING_FROM_BASE64_ERROR}: {e}"
            )

    async def get_video_embedding_from_file(
        self, video_path: str, segment_config: dict = None
    ) -> List[float]:
        """
        Gets video features from a local file.

        Args:
            video_path (str): Path to the video file.
            segment_config (dict, optional): Configuration for video segmentation. Defaults to None.

        Returns:
            List[float]: Video features.

        Raises:
            RuntimeError: If there is an error during the video feature extraction process.
        """
        try:
            logger.debug(f"Getting video embedding from file: {video_path}")
            if not os.path.exists(video_path):
                raise HTTPException(
                    status_code=400, detail=f"Video file not found: {video_path}"
                )
            clip_images = extract_video_frames(video_path, segment_config)
            logger.info("Video embedding extracted successfully from file")
            return self.get_video_embeddings([clip_images])
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"Error getting video embedding from file: {e}")
            raise RuntimeError(
                f"{ErrorMessages.GET_VIDEO_EMBEDDING_FROM_FILE_ERROR}: {e}"
            )

    def check_health(self) -> bool:
        """
        Checks the health of the VClipModel.

        Returns:
            bool: True if the model is healthy, False otherwise.
        """
        try:
            # Perform a simple operation to check if the model is loaded correctly
            self.get_text_features(["health_check"])
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
