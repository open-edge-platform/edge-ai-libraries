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
import json
import os
from pydantic import ValidationError

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
        self.supported_modalities = set(model_handler.supported_modalities)
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single text query.
        
        Args:
            text: Text string to embed
            
        Returns:
            List of embedding values
        """
        prepared_text = self.handler.prepare_query(text)
        embeddings = self.handler.encode_text([prepared_text])
        return embeddings[0].tolist()
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple text documents.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding lists
        """
        prepared_texts = self.handler.prepare_documents(texts)
        embeddings = self.handler.encode_text(prepared_texts)
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
        if not self.handler.supports_image():
            raise RuntimeError("Image embeddings are not supported by the active model")
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
        if not self.handler.supports_image():
            raise RuntimeError("Image embeddings are not supported by the active model")
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
        if not self.handler.supports_video():
            raise RuntimeError("Video embeddings are not supported by the active model")
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
        if not self.handler.supports_video():
            raise RuntimeError("Video embeddings are not supported by the active model")
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
        if not self.handler.supports_video():
            raise RuntimeError("Video embeddings are not supported by the active model")
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
        if not self.handler.supports_video():
            raise RuntimeError("Video embeddings are not supported by the active model")
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
    
    async def get_video_embedding_from_frames_manifest(self, manifest_path: str) -> List[List[float]]:
        """
        Get video embedding from frames manifest file.
        
        Supports two modes:
        1. Individual frame images: Traditional mode where each frame is a separate image file
        2. Video-based processing: New mode where manifest specifies frames to extract from a video file
        
        Args:
            manifest_path: Path to the frames manifest JSON file
            
        Returns:
            List of frame embedding lists (one per frame/crop)
            
        Raises:
            FileNotFoundError: If manifest file doesn't exist (404)
            ValueError: If manifest structure is invalid (422) 
            RuntimeError: For other processing errors (500)
        """
        if not self.handler.supports_video():
            raise RuntimeError("Video embeddings are not supported by the active model")
        try:
            logger.debug(f"Getting video embedding from frames manifest: {manifest_path}")
            
            # Validate manifest file exists
            if not os.path.exists(manifest_path):
                raise FileNotFoundError(f"Frames manifest file not found: {manifest_path}")
            
            # Load and validate manifest structure
            try:
                with open(manifest_path, 'r') as f:
                    manifest_data = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in manifest file: {e}")
            
            # Import here to avoid circular imports
            try:
                from .app import FramesManifest
                manifest = FramesManifest(**manifest_data)
            except ImportError:
                # Fallback validation if import fails
                if not isinstance(manifest_data, dict) or "frames" not in manifest_data:
                    raise ValueError("Invalid manifest format: must be a JSON object with 'frames' key")
                if not isinstance(manifest_data["frames"], list) or len(manifest_data["frames"]) == 0:
                    raise ValueError("Invalid manifest format: 'frames' must be a non-empty list")
                manifest = manifest_data
            except ValidationError as e:
                raise ValueError(f"Invalid manifest structure: {e}")
            
            # Check if this is a video-based manifest (has video_path) or image-based manifest
            video_path = manifest_data.get("video_path")
            frames_list = manifest.frames if hasattr(manifest, 'frames') else manifest_data["frames"]
            
            if video_path and os.path.exists(video_path):
                # VIDEO-BASED PROCESSING: Extract specific frames from video file
                logger.info(f"Processing video-based manifest with {len(frames_list)} frames from: {video_path}")
                
                # Extract the specific frames using video processing
                from .utils import extract_video_frames
                
                # Check if this is an optimized manifest with unique frame numbers
                if "total_metadata_entries" in manifest_data and "frame_metadata_map" in manifest_data:
                    # OPTIMIZED MANIFEST: Use the deduplicated frames for extraction
                    logger.info(f"Processing optimized video-based manifest with {len(frames_list)} unique frames "
                               f"(from {manifest_data['total_metadata_entries']} total metadata entries)")
                    
                    # Extract unique frame numbers from the deduplicated frames list
                    frame_numbers = []
                    for frame_info in frames_list:
                        if hasattr(frame_info, 'frame_number'):
                            frame_numbers.append(frame_info.frame_number)
                        elif isinstance(frame_info, dict):
                            frame_numbers.append(frame_info.get("frame_number", 0))
                else:
                    # LEGACY MANIFEST: Extract frame numbers from all frames (may contain duplicates)
                    logger.info(f"Processing legacy video-based manifest with {len(frames_list)} frames")
                    
                    frame_numbers = []
                    seen_frames = set()
                    
                    for frame_info in frames_list:
                        frame_num = None
                        if hasattr(frame_info, 'frame_number'):
                            frame_num = frame_info.frame_number
                        elif isinstance(frame_info, dict):
                            frame_num = frame_info.get("frame_number", 0)
                        
                        # Deduplicate frame numbers to avoid extracting the same frame multiple times
                        if frame_num is not None and frame_num not in seen_frames:
                            frame_numbers.append(frame_num)
                            seen_frames.add(frame_num)
                    
                    logger.info(f"Deduplicated to {len(frame_numbers)} unique frames for extraction")
                
                # Create segment config with specific frame indices
                segment_config = {
                    "frame_indexes": frame_numbers,
                    "startOffsetSec": 0,
                    "clip_duration": -1  # Process entire video
                }
                
                # Extract specified frames from video
                extracted_frames = extract_video_frames(video_path, segment_config)
                
                if not extracted_frames:
                    raise ValueError(f"No frames could be extracted from video: {video_path}")
                
                # For optimized manifests, process both frames and detected crops efficiently
                if "total_metadata_entries" in manifest_data and "frame_metadata_map" in manifest_data:
                    logger.info("Processing frames and detected crops using saved image files (optimal approach)...")
                    
                    # Use image-based processing for all entries (frames + crops) since VDMS DataPrep
                    # already saved both full frames and crop images as files in shared temp storage
                    all_frame_metadata = manifest_data.get("all_frame_metadata", [])
                    
                    images = []
                    valid_entries = []
                    
                    logger.info(f"Loading {len(all_frame_metadata)} image files (frames + crops) from shared temp storage")
                    
                    for i, metadata_entry in enumerate(all_frame_metadata):
                        image_path = metadata_entry.get("image_path")
                        frame_type = metadata_entry.get("type", "full_frame")
                        
                        if image_path is None:
                            logger.warning(f"Entry {i} has no image_path, skipping")
                            continue
                            
                        if not os.path.exists(image_path):
                            logger.warning(f"Image file not found: {image_path}, skipping")
                            continue
                        
                        try:
                            # Load the image file (works for both full frames and crops)
                            image = Image.open(image_path)
                            image.verify()  # Validate image
                            image = Image.open(image_path)  # Reload after verify
                            images.append(image)
                            valid_entries.append(metadata_entry)
                            
                            # Debug log for first few images
                            if len(images) <= 5:
                                logger.debug(f"Loaded {frame_type} image: {os.path.basename(image_path)}")
                                
                        except Exception as e:
                            logger.warning(f"Failed to load image {image_path}: {e}, skipping")
                            continue
                    
                    if not images:
                        raise ValueError("No valid images found in optimized manifest")
                    
                    # Batch encode all images at once (most efficient approach)
                    logger.info(f"Generating embeddings for {len(images)} images using batch processing...")
                    embeddings = self.handler.encode_image(images)
                    
                    # Normalize embeddings
                    embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
                    
                    # Convert to list of lists
                    embeddings_list = embeddings.tolist()
                    
                    # Count frame types for logging
                    frame_count = sum(1 for entry in valid_entries if entry.get("type") == "full_frame")
                    crop_count = sum(1 for entry in valid_entries if entry.get("type") == "detected_crop")
                    
                    logger.info(f"Optimal processing complete - {len(embeddings_list)} total embeddings "
                               f"({frame_count} frames + {crop_count} crops) loaded from saved files")
                    return embeddings_list
                else:
                    # Legacy behavior: direct mapping
                    embeddings_list = self.get_video_embeddings([extracted_frames])
                    logger.info(f"Video-based manifest processing complete - {len(embeddings_list)} frame embeddings")
                    return embeddings_list
                
            else:
                # IMAGE-BASED PROCESSING: Traditional mode with individual frame image files
                logger.info(f"Processing image-based manifest with {len(frames_list)} frame images")
                
                images = []
                valid_frames = []
                
                for i, frame_info in enumerate(frames_list):
                    # Handle both Pydantic model and dict formats
                    if hasattr(frame_info, 'image_path'):
                        image_path = frame_info.image_path
                        frame_data = frame_info.dict() if hasattr(frame_info, 'dict') else frame_info
                    else:
                        if not isinstance(frame_info, dict):
                            logger.warning(f"Invalid frame info at index {i}: not a dict, skipping")
                            continue
                        image_path = frame_info.get("image_path")
                        frame_data = frame_info
                    
                    # Skip frames with no image path (these are meant for video-based processing)
                    if image_path is None:
                        logger.debug(f"Frame {i} has no image_path (video-based frame), skipping in image-based processing")
                        continue
                    
                    if not os.path.exists(image_path):
                        logger.warning(f"Frame image not found: {image_path}, skipping")
                        continue
                    
                    try:
                        image = Image.open(image_path)
                        # Validate image can be loaded
                        image.verify()
                        # Reload image for processing (verify() closes the file)
                        image = Image.open(image_path)
                        images.append(image)
                        valid_frames.append(frame_data)
                    except Exception as e:
                        logger.warning(f"Failed to load frame image {image_path}: {e}, skipping")
                        continue
                
                if not images:
                    raise ValueError("No valid frame images found in manifest")
                
                # Batch encode all images at once (more efficient)
                embeddings = self.handler.encode_image(images)
                
                # Normalize embeddings
                embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
                
                # Convert to list of lists
                embeddings_list = embeddings.tolist()
                
                logger.info(f"Image-based manifest processing complete - {len(embeddings_list)} frame embeddings")
                return embeddings_list
            
        except FileNotFoundError:
            # Re-raise FileNotFoundError as-is (will become 404)
            raise
        except ValueError:
            # Re-raise ValueError as-is (will become 422)
            raise
        except Exception as e:
            logger.error(f"Error getting video embedding from frames manifest: {e}")
            raise RuntimeError(f"Failed to get video embedding from frames manifest: {e}")
    
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

    def get_supported_modalities(self) -> List[str]:
        """Return sorted list of supported modalities."""
        return sorted(self.supported_modalities)

    def supports_text(self) -> bool:
        return self.handler.supports_text()

    def supports_image(self) -> bool:
        return self.handler.supports_image()

    def supports_video(self) -> bool:
        return self.handler.supports_video()
