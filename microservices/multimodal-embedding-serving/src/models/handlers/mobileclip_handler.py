# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MobileCLIP model handler implementation.

This module provides a handler for MobileCLIP models, which are mobile-optimized
versions of CLIP designed for efficient inference on resource-constrained devices.
MobileCLIP models offer a good balance between performance and computational efficiency.

The handler supports various MobileCLIP architectures including:
- mobileclip_s0: Small model variant optimized for mobile devices
- mobileclip_s1: Balanced model with improved accuracy  
- mobileclip_s2: Enhanced model with better performance
- mobileclip_b: Base model with standard capabilities
- mobileclip_blt: Base model with lightweight transformer

The implementation includes support for OpenVINO optimization and follows
the initialization patterns established in the MobileCLIP examples.
"""

from pathlib import Path
from typing import List, Union, Dict, Any
import torch
import torch.nn.functional as F
import types
import gc
import requests
import openvino as ov
from PIL import Image
import mobileclip

from ..base import BaseEmbeddingModel
from ...utils import logger
from ..utils import (
    check_and_convert_openvino_models,
    load_openvino_models,
)


def se_block_forward(self, inputs):
    """
    Apply forward pass for SE (Squeeze-and-Excitation) block.
    
    This function is required for MobileCLIP OpenVINO conversion and implements
    the Squeeze-and-Excitation mechanism that adaptively recalibrates channel-wise
    feature responses by explicitly modeling interdependencies between channels.
    
    Args:
        inputs: Input tensor with shape [batch_size, channels, height, width]
        
    Returns:
        Recalibrated feature tensor with same shape as input
        
    Note:
        This function patches the SE block forward method for proper OpenVINO
        conversion compatibility with MobileCLIP models.
    """
    b, c, h, w = inputs.size()
    x = F.avg_pool2d(inputs, kernel_size=[8, 8])
    x = self.reduce(x)
    x = F.relu(x)
    x = self.expand(x)
    x = torch.sigmoid(x)
    x = x.view(-1, c, 1, 1)
    return inputs * x


class MobileCLIPHandler(BaseEmbeddingModel):
    """
    Handler for MobileCLIP models using the mobileclip library.
    
    This class implements the BaseEmbeddingModel interface for MobileCLIP models,
    providing optimized text and image encoding for mobile and edge devices.
    The handler follows standard initialization patterns for MobileCLIP models.
    
    MobileCLIP models are designed for efficiency while maintaining good accuracy,
    making them suitable for deployment scenarios with limited computational resources.
    
    Attributes:
        model_name: MobileCLIP model variant name (e.g., "mobileclip_s0")
        pretrained: Path to pretrained checkpoint file
        url: URL for downloading model checkpoints if needed
        image_size: Input image size for the model (typically 256)
        use_openvino: Whether to use OpenVINO optimization
        device: Target device for inference
        ov_models_dir: Directory for OpenVINO model storage
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        self.model_name = model_config["model_name"]
        self.pretrained = model_config["pretrained"]
        self.url = model_config.get("url")
        self.image_size = model_config.get("image_size", 256)
        self.use_openvino = model_config.get("use_openvino", False)
        self.device = model_config.get("device", "CPU")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov-models")
        
        # OpenVINO models
        self.ov_image_encoder = None
        self.ov_text_encoder = None
        
    def load_model(self) -> None:
        """Load MobileCLIP model using mobileclip library."""
        try:
            logger.info(f"Loading MobileCLIP model: {self.model_name} from {self.pretrained}")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Download model if URL is provided and use ov_models_dir for storage
                model_path = self._ensure_model_available()
                
                # Load model with downloaded checkpoint
                self.model, _, self.preprocess = mobileclip.create_model_and_transforms(
                    self.model_name, 
                    pretrained=str(model_path)
                )
                
                self.tokenizer = mobileclip.get_tokenizer(self.model_name)
                self.model.eval()
                logger.info(f"MobileCLIP model {self.model_name} loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load MobileCLIP model {self.model_name}: {e}")
            raise
    
    def _ensure_model_available(self) -> Path:
        """
        Ensure MobileCLIP model is available for loading.
        
        Downloads the model from URL if provided, or uses the pretrained path.
        Uses the ov_models_dir as storage location which has write permissions.
        
        Returns:
            Path to the model checkpoint file
        """
        if self.url:
            # Use ov_models_dir for model storage (writable directory)
            model_dir = Path(self.ov_models_dir) / "mobileclip_checkpoints"
            model_dir.mkdir(parents=True, exist_ok=True)
            
            # Download model file if it doesn't exist
            model_filename = Path(self.url).name
            model_path = model_dir / model_filename
            
            if not model_path.exists():
                logger.info(f"Downloading MobileCLIP model from {self.url}")
                response = requests.get(self.url)
                response.raise_for_status()
                with open(model_path, 'wb') as f:
                    f.write(response.content)
                logger.info(f"Model downloaded to {model_path}")
            else:
                logger.info(f"Using cached model from {model_path}")
            
            return model_path
        else:
            # If no URL, try to use the pretrained path directly
            # But first check if it's a relative path that needs to be in ov_models_dir
            pretrained_path = Path(self.pretrained)
            if not pretrained_path.is_absolute():
                # Convert relative path to be inside ov_models_dir
                model_path = Path(self.ov_models_dir) / "mobileclip_checkpoints" / pretrained_path.name
                if not model_path.exists():
                    raise FileNotFoundError(
                        f"Model checkpoint not found at {model_path}. "
                        f"Please provide a valid URL in the model configuration or "
                        f"ensure the checkpoint is available in {model_path.parent}"
                    )
                return model_path
            else:
                return pretrained_path
    
    def _load_openvino_models(self) -> None:
        """Load OpenVINO compiled models. Convert if they don't exist."""
        model_key = f"{self.model_name}".replace("/", "_").replace("-", "_")
        
        # Ensure model is available for OpenVINO conversion
        model_path = self._ensure_model_available()
        
        # Create lambda functions that use the correct model path
        def load_model_with_path():
            return mobileclip.create_model_and_transforms(self.model_name, pretrained=str(model_path))
        
        def load_tokenizer():
            return mobileclip.get_tokenizer(self.model_name)
        
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=load_model_with_path,
            tokenizer_loader=load_tokenizer,
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device
        )
        # Always load preprocessing and tokenizer for OpenVINO inference
        _, _, self.preprocess = mobileclip.create_model_and_transforms(
            self.model_name, pretrained=str(model_path)
        )
        self.tokenizer = mobileclip.get_tokenizer(self.model_name)
        logger.info(f"MobileCLIP OpenVINO models loaded successfully on device: {self.device}")
    
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """Encode text using MobileCLIP text encoder."""
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
        """Encode images using MobileCLIP image encoder."""
        if isinstance(images, torch.Tensor):
            image_tensor = images
        elif isinstance(images, Image.Image):
            image_tensor = self.preprocess(images).unsqueeze(0)
        else:  # List of images
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
        return image_features
    
    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """Convert MobileCLIP model to OpenVINO format for inference optimization."""
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(exist_ok=True)
        
        # Use provided model and tokenizer, or load with proper model path
        if model is None or tokenizer is None:
            # Ensure model is available for conversion
            model_path = self._ensure_model_available()
            model, _, _ = mobileclip.create_model_and_transforms(
                self.model_name, 
                pretrained=str(model_path)
            )
            tokenizer = mobileclip.get_tokenizer(self.model_name)
        
        model_key = f"{self.model_name}".replace("/", "_").replace("-", "_")
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        # Create sample inputs
        sample_image = torch.randn(1, 3, self.image_size, self.image_size)
        sample_text = tokenizer(["sample text"])
        
        # Convert image encoder
        if not image_encoder_path.exists():
            logger.info(f"Converting MobileCLIP image encoder to OpenVINO: {image_encoder_path}")
            
            # Apply SE block fix for mobileclip_s models
            if "mobileclip_s" in self.model_name:
                model.image_encoder.model.conv_exp.se.forward = types.MethodType(
                    se_block_forward, 
                    model.image_encoder.model.conv_exp.se
                )
            
            # Set forward method to encode_image
            original_forward = model.forward
            model.forward = model.encode_image
            
            ov_image_encoder = ov.convert_model(
                model,
                example_input=sample_image,
                input=[-1, 3, sample_image.shape[2], sample_image.shape[3]],
            )
            ov.save_model(ov_image_encoder, image_encoder_path)
            
            # Restore original forward
            model.forward = original_forward
            del ov_image_encoder
            gc.collect()
            logger.info(f"Image encoder saved to: {image_encoder_path}")
        
        # Convert text encoder  
        if not text_encoder_path.exists():
            logger.info(f"Converting MobileCLIP text encoder to OpenVINO: {text_encoder_path}")
            
            # Set forward method to encode_text
            original_forward = model.forward
            model.forward = model.encode_text
            
            ov_text_encoder = ov.convert_model(
                model,
                example_input=sample_text,
            )
            ov.save_model(ov_text_encoder, text_encoder_path)
            
            # Restore original forward
            model.forward = original_forward
            del ov_text_encoder
            gc.collect()
            logger.info(f"Text encoder saved to: {text_encoder_path}")
        
        return str(image_encoder_path), str(text_encoder_path)
    
    def get_embedding_dim(self) -> int:
        """Get the embedding dimension for MobileCLIP models."""
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # Get embedding dimension from the model
        sample_image = torch.randn(1, 3, self.image_size, self.image_size)
        with torch.no_grad():
            features = self.model.encode_image(sample_image)
        return features.shape[-1]
