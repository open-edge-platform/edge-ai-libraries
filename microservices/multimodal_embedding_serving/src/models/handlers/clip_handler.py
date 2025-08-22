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
from typing import List, Union, Dict, Any
import torch
import torch.nn.functional as F
import types
import gc
import openvino as ov
from PIL import Image
import open_clip

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
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=lambda: open_clip.create_model_and_transforms(self.model_name, pretrained=self.pretrained),
            tokenizer_loader=lambda: open_clip.get_tokenizer(self.model_name),
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device
        )
        # Always load preprocessing and tokenizer for OpenVINO inference
        _, _, self.preprocess = open_clip.create_model_and_transforms(
            self.model_name, pretrained=self.pretrained
        )
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
            # Use OpenVINO inference
            text_features = torch.from_numpy(self.ov_text_encoder(tokenized)[0])
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
            image_tensor = torch.stack([self.preprocess(img) for img in images])
        
        if self.use_openvino and self.ov_image_encoder is not None:
            # Use OpenVINO inference
            image_features = torch.from_numpy(self.ov_image_encoder(image_tensor)[0])
        else:
            # Use PyTorch model
            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)
        
        image_features = F.normalize(image_features, dim=-1)
        return image_features
    
    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """Convert CLIP model to OpenVINO format for inference optimization."""
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(exist_ok=True)
        
        # Use provided model and tokenizer, or fallback to instance attributes
        if model is None:
            model = self.model
        if tokenizer is None:
            tokenizer = self.tokenizer
            
        if model is None or tokenizer is None:
            raise RuntimeError("Model and tokenizer must be available for conversion")
        
        model_key = f"{self.model_name}_{self.pretrained}".replace("/", "_").replace("-", "_")
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        # Create sample inputs
        sample_image = torch.randn(1, 3, 224, 224)  # Standard CLIP input size
        sample_text = tokenizer(["sample text"])
        
        # Convert image encoder for OpenVINO optimization
        if not image_encoder_path.exists():
            logger.info(f"Converting CLIP image encoder to OpenVINO: {image_encoder_path}")
            
            # Modify model forward method to encode_image
            original_forward = model.forward
            model.forward = model.encode_image
            
            ov_image_encoder = ov.convert_model(
                model,
                example_input=sample_image,
                input=[-1, 3, sample_image.shape[2], sample_image.shape[3]],
            )
            ov.save_model(ov_image_encoder, image_encoder_path)
            del ov_image_encoder
            gc.collect()
            logger.info(f"Image encoder saved to: {image_encoder_path}")
            
            # Restore original forward method
            model.forward = original_forward
        
        # Convert text encoder for OpenVINO optimization
        if not text_encoder_path.exists():
            logger.info(f"Converting CLIP text encoder to OpenVINO: {text_encoder_path}")
            
            # Modify model forward method to encode_text
            original_forward = model.forward
            model.forward = model.encode_text
            
            ov_text_encoder = ov.convert_model(
                model,
                example_input=sample_text,
                input=[-1, sample_text.shape[1]],
            )
            ov.save_model(ov_text_encoder, text_encoder_path)
            del ov_text_encoder
            gc.collect()
            logger.info(f"Text encoder saved to: {text_encoder_path}")
            
            # Restore original forward method
            model.forward = original_forward
        
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
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # Get embedding dimension from the model
        sample_image = torch.randn(1, 3, 224, 224)
        with torch.no_grad():
            features = self.model.encode_image(sample_image)
        return features.shape[-1]
