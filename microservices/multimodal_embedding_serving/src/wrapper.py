# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Application-level embedding model that wraps the focused model handlers.
This class provides the application-specific functionality like video processing,
URL handling, etc., built on top of the core text/image encoding capabilities.
"""

from typing import List, Union, Dict, Any
import torch
from PIL import Image
import numpy as np

from .models.base import BaseEmbeddingModel
from .utils import (
    decode_base64_image,
    decode_base64_video,
    delete_file,
    download_image,
    download_video,
    extract_video_frames,
    logger,
)


class EmbeddingModel:
    """
    Application-level embedding model that provides high-level functionality
    built on top of the focused model handlers.
    """
    
    def __init__(self, model_handler: BaseEmbeddingModel):
        """
        Initialize with a model handler.
        
        Args:
            model_handler: The focused model handler (CLIP, MobileCLIP, etc.)
        """
        self.handler = model_handler
        self.model_config = model_handler.model_config
        self.device = model_handler.device
        self.use_openvino = model_handler.model_config.get("use_openvino", False)
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single text query.
        
        Args:
            text: Text string to embed
            
        Returns:
            List of embedding values
        """
        embeddings = self.handler.encode_text([text])
        return embeddings[0].tolist()
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple text documents.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding lists
        """
        embeddings = self.handler.encode_text(texts)
        return embeddings.tolist()
    
    def get_embedding_length(self) -> int:
        """Get the length of the embedding vector."""
        return self.handler.get_embedding_dim()
    
    async def get_image_embedding_from_url(self, image_url: str) -> List[float]:
        """
        Get image embedding from a URL.
        
        Args:
            image_url: URL of the image
            
        Returns:
            List of embedding values
        """
        try:
            logger.debug(f"Getting image embedding from URL: {image_url}")
            image_data = await download_image(image_url)
            # Convert numpy array to PIL Image if necessary
            if isinstance(image_data, np.ndarray):
                image_data = Image.fromarray(image_data)
            embeddings = self.handler.encode_image([image_data])
            logger.info("Image embedding extracted successfully from URL")
            return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"Error getting image embedding from URL: {e}")
            raise RuntimeError(f"Failed to get image embedding from URL: {e}")
    
    def get_image_embedding_from_base64(self, image_base64: str) -> List[float]:
        """
        Get image embedding from base64 encoded image.
        
        Args:
            image_base64: Base64 encoded image string
            
        Returns:
            List of embedding values
        """
        try:
            logger.debug("Getting image embedding from base64")
            image_data = decode_base64_image(image_base64)
            embeddings = self.handler.encode_image([image_data])
            logger.info("Image embedding extracted successfully from base64")
            return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"Error getting image embedding from base64: {e}")
            raise RuntimeError(f"Failed to get image embedding from base64: {e}")
    
    def get_video_embeddings(self, frames_batch: List[List[Union[Image.Image, np.ndarray]]]) -> List[List[float]]:
        """
        Get video embeddings from frame batches.
        
        Args:
            frames_batch: List of list of frames in videos
            
        Returns:
            List of frame embedding lists (each frame's embedding as a separate list)
        """
        try:
            logger.debug("Getting video embeddings")
            vid_embs = []
            
            for frames in frames_batch:
                # Convert numpy arrays to PIL Images if necessary
                processed_frames = []
                for frame in frames:
                    if isinstance(frame, np.ndarray):
                        frame = Image.fromarray(frame)
                    processed_frames.append(frame)
                
                # Get embeddings for all frames
                frame_embeddings = self.handler.encode_image(processed_frames)
                
                # Normalize each frame embedding
                frame_embeddings = frame_embeddings / frame_embeddings.norm(dim=-1, keepdim=True)
                
                # Convert to list of lists (one list per frame)
                frame_embs_list = frame_embeddings.tolist()
                vid_embs.extend(frame_embs_list)
            
            logger.info(f"Video embeddings extracted successfully - {len(vid_embs)} frame embeddings")
            return vid_embs
        except Exception as e:
            logger.error(f"Error getting video embeddings: {e}")
            raise RuntimeError(f"Failed to get video embeddings: {e}")
    
    async def get_video_embedding_from_url(self, video_url: str, segment_config: dict = None) -> List[List[float]]:
        """
        Get video embedding from a URL.
        
        Args:
            video_url: URL of the video
            segment_config: Configuration for video segmentation
            
        Returns:
            List of frame embedding lists
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
            raise RuntimeError(f"Failed to get video embedding from URL: {e}")
    
    def get_video_embedding_from_base64(self, video_base64: str, segment_config: dict = None) -> List[List[float]]:
        """
        Get video embedding from base64 encoded video.
        
        Args:
            video_base64: Base64 encoded video string
            segment_config: Configuration for video segmentation
            
        Returns:
            List of frame embedding lists
        """
        try:
            logger.debug("Getting video embedding from base64")
            video_path = decode_base64_video(video_base64)
            clip_images = extract_video_frames(video_path, segment_config)
            delete_file(video_path)
            logger.info("Video embedding extracted successfully from base64")
            return self.get_video_embeddings([clip_images])
        except Exception as e:
            logger.error(f"Error getting video embedding from base64: {e}")
            raise RuntimeError(f"Failed to get video embedding from base64: {e}")
    
    async def get_video_embedding_from_file(self, video_path: str, segment_config: dict = None) -> List[List[float]]:
        """
        Get video embedding from a local file.
        
        Args:
            video_path: Path to the video file
            segment_config: Configuration for video segmentation
            
        Returns:
            List of frame embedding lists
        """
        try:
            logger.debug(f"Getting video embedding from file: {video_path}")
            import os
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            clip_images = extract_video_frames(video_path, segment_config)
            logger.info("Video embedding extracted successfully from file")
            return self.get_video_embeddings([clip_images])
        except Exception as e:
            logger.error(f"Error getting video embedding from file: {e}")
            raise RuntimeError(f"Failed to get video embedding from file: {e}")
    
    def check_health(self) -> bool:
        """
        Check the health of the model.
        
        Returns:
            bool: True if the model is healthy, False otherwise
        """
        try:
            # Perform a simple operation to check if the model is loaded correctly
            self.embed_query("health check")
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
