# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
CLIP model handler implementation.

This module provides a handler for CLIP (Contrastive Language-Image Pre-training) models
using the open_clip library. CLIP models learn joint representations of text and images
through contrastive learning, enabling cross-modal understanding and similarity calculations.

The handler supports various CLIP architectures including:
- ViT-B-32: Vision Transformer with Base size and 32x32 patch size
- ViT-B-16: Vision Transformer with Base size and 16x16 patch size  
- ViT-L-14: Vision Transformer with Large size and 14x14 patch size
- ViT-H-14: Vision Transformer with Huge size and 14x14 patch size

The implementation includes support for OpenVINO optimization to improve inference
performance on Intel hardware.
"""

from pathlib import Path
from typing import List, Union, Dict, Any, Optional
import torch
import torch.nn.functional as F
import types
import gc
import json
import openvino as ov
from PIL import Image
import open_clip
import shutil

from ..base import BaseEmbeddingModel
from ...utils import logger
from ..utils import (
    check_and_convert_openvino_models,
    load_openvino_models,
)


class CLIPHandler(BaseEmbeddingModel):
    """
    Handler for CLIP models using the open_clip library.
    
    This class implements the BaseEmbeddingModel interface for CLIP models,
    providing text and image encoding capabilities. It supports both PyTorch
    and OpenVINO inference modes for optimal performance.
    
    Attributes:
        model_name: CLIP model architecture name (e.g., "ViT-B-32")
        pretrained: Pretrained checkpoint identifier  
        use_openvino: Whether to use OpenVINO optimization
        device: Target device for inference
        ov_models_dir: Directory for OpenVINO model storage
        ov_image_encoder: Compiled OpenVINO image encoder (if using OpenVINO)
        ov_text_encoder: Compiled OpenVINO text encoder (if using OpenVINO)
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        """
        Initialize CLIP handler with model configuration.
        
        Args:
            model_config: Dictionary containing CLIP model configuration including:
                - model_name: CLIP architecture name (e.g., "ViT-B-32")
                - pretrained: Pretrained checkpoint identifier
                - device: Target device for inference (default: "CPU")
                - use_openvino: Whether to use OpenVINO optimization (default: False)
                - ov_models_dir: Directory for OpenVINO models (default: "ov-models")
        """
        super().__init__(model_config)
        self.model_name = model_config["model_name"]
        self.pretrained = model_config["pretrained"]
        self.use_openvino = model_config.get("use_openvino", False)
        self.device = model_config.get("device", "CPU")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov-models")
        
        # OpenVINO models
        self.ov_image_encoder = None
        self.ov_text_encoder = None
        self._embedding_dim: Optional[int] = None
        
    def load_model(self) -> None:
        """
        Load CLIP model and associated components.
        
        Loads the CLIP model, tokenizer, and preprocessing functions using the
        open_clip library. If OpenVINO optimization is enabled, loads the
        compiled OpenVINO models instead of the PyTorch model.
        
        The loading process includes:
        - Model and preprocessing pipeline initialization
        - Tokenizer setup for text processing
        - OpenVINO model compilation (if enabled)
        - Model validation and configuration
        
        Raises:
            Exception: If model loading fails for any reason
        """
        try:
            self._embedding_dim = None
            logger.info(f"Loading CLIP model: {self.model_name} with pretrained: {self.pretrained}")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Load CLIP models using open_clip
                self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                    self.model_name, 
                    pretrained=self.pretrained
                )
                self.tokenizer = open_clip.get_tokenizer(self.model_name)
                
                self.model.eval()
                logger.info(f"CLIP model {self.model_name} loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load CLIP model {self.model_name}: {e}")
            raise
    
    def _load_openvino_models(self) -> None:
        """
        Load OpenVINO compiled models with automatic conversion if needed.
        
        This method handles the complete OpenVINO loading pipeline:
        - Checks for existing converted models
        - Performs conversion if models don't exist
        - Loads and compiles models for the target device
        - Sets up preprocessing and tokenizer components
        
        The method uses shared utilities to ensure consistent conversion
        across different model types and handles cleanup to free memory.
        """
        # Use shared utility to check/convert and load models
        model_key = f"{self.model_name}_{self.pretrained}".replace("/", "_").replace("-", "_")
        
        # For OpenVINO conversion, pass None for model and tokenizer loaders since
        # Optimum Intel will handle model loading internally to avoid multiple downloads
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=None,  # Don't pre-load model for Optimum Intel conversion
            tokenizer_loader=None,  # Don't pre-load tokenizer for Optimum Intel conversion  
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device
        )
        # Create model structure WITHOUT downloading weights to get preprocessing
        # This leverages OpenCLIP's built-in preprocessing configuration
        _, _, self.preprocess = open_clip.create_model_and_transforms(
            self.model_name, 
            pretrained=self.pretrained,
            load_weights=False,  # KEY: Don't download weights, just get preprocessing!
            device='cpu'  # Lightweight since no weights loaded
        )
        
        # Get tokenizer (lightweight operation)
        self.tokenizer = open_clip.get_tokenizer(self.model_name)
        logger.info(f"CLIP OpenVINO models loaded successfully on device: {self.device}")
    
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """
        Encode text using CLIP text encoder.
        
        Processes input text through tokenization and the CLIP text encoder
        to produce normalized embedding vectors. Supports both PyTorch and
        OpenVINO inference modes.
        
        Args:
            texts: Single text string or list of text strings to encode
            
        Returns:
            Normalized text embeddings with shape [1, embedding_dim] for single text
            or [batch_size, embedding_dim] for multiple texts
            
        Note:
            Text embeddings are L2-normalized to enable cosine similarity calculations
            with image embeddings.
        """
        if isinstance(texts, str):
            texts = [texts]
        
        tokenized = self.tokenizer(texts)
        
        if self.use_openvino and self.ov_text_encoder is not None:
            # Use OpenVINO inference with infer_new_request for thread safety
            result = self.ov_text_encoder.infer_new_request({self.ov_text_encoder.inputs[0]: tokenized})
            text_features = torch.from_numpy(result[self.ov_text_encoder.outputs[0]])
        else:
            # Use PyTorch model
            with torch.no_grad():
                text_features = self.model.encode_text(tokenized)
        
        text_features = F.normalize(text_features, dim=-1)
        return text_features
    
    def encode_image(self, images: Union[Image.Image, List[Image.Image], torch.Tensor]) -> torch.Tensor:
        """
        Encode images using CLIP image encoder.
        
        Processes input images through preprocessing and the CLIP image encoder
        to produce normalized embedding vectors. Supports both PyTorch and
        OpenVINO inference modes.
        
        Args:
            images: Input images in one of the following formats:
                - Single PIL Image
                - List of PIL Images
                - Preprocessed tensor with shape [batch_size, channels, height, width]
                
        Returns:
            Normalized image embeddings with shape [1, embedding_dim] for single image
            or [batch_size, embedding_dim] for multiple images
            
        Note:
            Image embeddings are L2-normalized to enable cosine similarity calculations
            with text embeddings. Images are automatically preprocessed if needed.
        """
        if isinstance(images, torch.Tensor):
            image_tensor = images
        elif isinstance(images, Image.Image):
            image_tensor = self.preprocess(images).unsqueeze(0)
        else:  # List of images
            logger.debug(f"Preprocessing {len(images)} list of images for CLIP")
            image_tensor = torch.stack([self.preprocess(img) for img in images])
        
        if self.use_openvino and self.ov_image_encoder is not None:
            # Use OpenVINO inference with infer_new_request for thread safety
            result = self.ov_image_encoder.infer_new_request({self.ov_image_encoder.inputs[0]: image_tensor})
            image_features = torch.from_numpy(result[self.ov_image_encoder.outputs[0]])
        else:
            # Use PyTorch model
            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)
        
        image_features = F.normalize(image_features, dim=-1)
        logger.debug(f"CLIP image_features shape: {image_features.shape}")
        return image_features
    
    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """Convert CLIP model to OpenVINO format using Optimum Intel for robust conversion."""
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(exist_ok=True)
        
        model_key = f"{self.model_name}_{self.pretrained}".replace("/", "_").replace("-", "_")
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        logger.info(f"OpenVINO models directory: {ov_models_path}")
        logger.info(f"Model key: {model_key}")
        logger.info(f"Expected image encoder path: {image_encoder_path}")
        logger.info(f"Expected text encoder path: {text_encoder_path}")
        
        # Check if models already exist
        if image_encoder_path.exists() and text_encoder_path.exists():
            logger.info(f"Reusing existing OpenVINO models from persistent volume: {ov_models_path}")
            return str(image_encoder_path), str(text_encoder_path)
        
        # Use Optimum Intel with OpenCLIP's native HuggingFace support (recommended)
        logger.info("Attempting conversion using Optimum Intel with OpenCLIP HuggingFace support...")
        try:
            from optimum.intel import OVModelOpenCLIPText, OVModelOpenCLIPVisual
            from open_clip.pretrained import get_pretrained_cfg
            from huggingface_hub import HfFolder
            import os
            
            # Use HuggingFace's default cache directory instead of creating our own
            # This leverages existing caching and avoids redundant downloads
            default_cache_dir = os.environ.get('HF_HOME') or os.path.expanduser('~/.cache/huggingface/hub')
            logger.info(f"Using HuggingFace default cache directory: {default_cache_dir}")
            
            # Use OpenCLIP's native HuggingFace Hub detection
            logger.info(f"Checking for HuggingFace Hub support for {self.model_name}:{self.pretrained}")
            pretrained_cfg = get_pretrained_cfg(self.model_name, self.pretrained)
            hf_hub_id = pretrained_cfg.get('hf_hub', '')
            
            if hf_hub_id:
                logger.info(f"Found HuggingFace Hub mapping: {hf_hub_id}")
                
                # Clean up the hf_hub_id (remove trailing slashes)
                hf_hub_id = hf_hub_id.rstrip('/')
                
                # Use Optimum Intel directly with the HuggingFace model ID
                logger.info(f"Converting {hf_hub_id} using Optimum Intel...")
                
                visual_model = OVModelOpenCLIPVisual.from_pretrained(
                    hf_hub_id, export=True, trust_remote_code=True, cache_dir=default_cache_dir
                )
                text_model = OVModelOpenCLIPText.from_pretrained(
                    hf_hub_id, export=True, trust_remote_code=True, cache_dir=default_cache_dir
                )
                
                # Save the converted models directly to the target directory
                visual_model.save_pretrained(ov_models_path)
                text_model.save_pretrained(ov_models_path)
                
                # Optimum Intel saves as openvino_model_vision.xml and openvino_model_text.xml
                # Rename to expected paths
                optimum_vision_path = ov_models_path / "openvino_model_vision.xml"
                optimum_text_path = ov_models_path / "openvino_model_text.xml"
                optimum_vision_bin = ov_models_path / "openvino_model_vision.bin"
                optimum_text_bin = ov_models_path / "openvino_model_text.bin"
                
                if optimum_vision_path.exists() and optimum_text_path.exists():
                    # Rename files to expected names
                    shutil.move(str(optimum_vision_path), str(image_encoder_path))
                    shutil.move(str(optimum_vision_bin), str(image_encoder_path.with_suffix('.bin')))
                    shutil.move(str(optimum_text_path), str(text_encoder_path))
                    shutil.move(str(optimum_text_bin), str(text_encoder_path.with_suffix('.bin')))
                    
                    logger.info("Successfully converted using Optimum Intel with OpenCLIP native HF mapping")
                    return str(image_encoder_path), str(text_encoder_path)
                else:
                    logger.error(f"Optimum Intel conversion succeeded but models not found at expected paths")
                    logger.error(f"Expected: {optimum_vision_path}, {optimum_text_path}")
                    logger.error(f"Directory contents: {list(ov_models_path.glob('*'))}")
                    raise RuntimeError("Models not saved to expected Optimum Intel paths")
            else:
                logger.error(f"No HuggingFace Hub mapping found for {self.model_name}:{self.pretrained}")
                raise RuntimeError("Model does not have HuggingFace Hub support - OpenVINO conversion requires HF Hub mapping")
                
        except ImportError:
            logger.error("Optimum Intel not available. Please install optimum-intel to use OpenVINO conversion.")
            raise RuntimeError("Optimum Intel not installed - required for OpenVINO conversion")
        except Exception as e:
            logger.error(f"Optimum Intel conversion failed: {e}")
            raise RuntimeError(f"OpenVINO conversion failed: {e}")
        
        return str(image_encoder_path), str(text_encoder_path)
    
    def get_embedding_dim(self) -> int:
        """
        Get the embedding dimension for CLIP models.
        
        Determines the dimensionality of the embedding vectors produced by
        this CLIP model by running a test inference with a sample image.
        
        Returns:
            Integer representing the embedding dimension (typically 512, 768, or 1024)
            
        Raises:
            RuntimeError: If model is not loaded yet
            
        Note:
            This method performs a forward pass with a dummy input to determine
            the actual embedding dimension of the loaded model.
        """
        if self._embedding_dim is not None:
            return self._embedding_dim

        if self.preprocess is None:
            raise RuntimeError("Preprocessing pipeline not initialized. Call load_model() first.")

        image_size = self._get_preprocess_image_size()
        dummy_image = Image.new("RGB", (image_size, image_size), color=0)
        image_tensor = self.preprocess(dummy_image).unsqueeze(0)

        if self.use_openvino:
            if self.ov_image_encoder is None:
                raise RuntimeError("OpenVINO image encoder not initialized. Call load_model() first.")

            input_data = image_tensor.detach().cpu().numpy()
            result = self.ov_image_encoder.infer_new_request({self.ov_image_encoder.inputs[0]: input_data})
            output_array = next(iter(result.values()))
            if hasattr(output_array, "to_numpy"):
                output_array = output_array.to_numpy()
            self._embedding_dim = int(output_array.shape[-1])
        else:
            if self.model is None:
                raise RuntimeError("Model not loaded. Call load_model() first.")

            try:
                sample_param = next(self.model.parameters())
                device = sample_param.device
                dtype = sample_param.dtype
            except StopIteration:
                device = torch.device("cpu")
                dtype = torch.float32

            image_tensor = image_tensor.to(device=device, dtype=dtype)
            with torch.no_grad():
                features = self.model.encode_image(image_tensor)
            self._embedding_dim = int(features.shape[-1])

        return self._embedding_dim

    def _get_preprocess_image_size(self) -> int:
        """Infer the expected image resolution from the preprocess pipeline."""
        default_size = 224

        if self.preprocess is None:
            return default_size

        transforms = getattr(self.preprocess, "transforms", None)
        if not transforms:
            return default_size

        for transform in transforms:
            size = getattr(transform, "size", None)
            if size is None:
                continue

            if isinstance(size, (tuple, list)) and len(size) > 0:
                return int(size[0])
            if isinstance(size, int):
                return int(size)

        return default_size
