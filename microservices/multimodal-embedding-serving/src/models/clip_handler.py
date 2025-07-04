# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
CLIP model handler implementation.
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

from .base import BaseEmbeddingModel
from ..common import logger


class CLIPHandler(BaseEmbeddingModel):
    """
    Handler for CLIP models using open_clip library.
    Follows the initialization pattern from the MobileCLIP notebook.
    """
    
    def __init__(self, model_config: Dict[str, Any]):
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
        """Load CLIP model using open_clip."""
        try:
            logger.info(f"Loading CLIP model: {self.model_name} with pretrained: {self.pretrained}")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Follow the notebook pattern for CLIP models
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
        """Load OpenVINO compiled models."""
        ov_models_path = Path(self.ov_models_dir)
        model_key = f"{self.model_name}_{self.pretrained}".replace("/", "_").replace("-", "_")
        
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        if not image_encoder_path.exists() or not text_encoder_path.exists():
            raise FileNotFoundError(
                f"OpenVINO models not found at {image_encoder_path} or {text_encoder_path}. "
                "Please convert the model first using convert_to_openvino()"
            )
        
        # Load OpenVINO models
        core = ov.Core()
        self.ov_image_encoder = core.compile_model(image_encoder_path, self.device)
        self.ov_text_encoder = core.compile_model(text_encoder_path, self.device)
        
        # Still need preprocessing and tokenizer
        _, _, self.preprocess = open_clip.create_model_and_transforms(
            self.model_name, pretrained=self.pretrained
        )
        self.tokenizer = open_clip.get_tokenizer(self.model_name)
        
        logger.info(f"CLIP OpenVINO models loaded successfully on device: {self.device}")
    
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """Encode text using CLIP text encoder."""
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
        """Encode images using CLIP image encoder."""
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
    
    def convert_to_openvino(self, ov_models_dir: str) -> tuple:
        """Convert CLIP model to OpenVINO format."""
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(exist_ok=True)
        
        model_key = f"{self.model_name}_{self.pretrained}".replace("/", "_").replace("-", "_")
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        # Create sample inputs
        sample_image = torch.randn(1, 3, 224, 224)  # Standard CLIP input size
        sample_text = self.tokenizer(["sample text"])
        
        # Convert image encoder
        if not image_encoder_path.exists():
            logger.info(f"Converting CLIP image encoder to OpenVINO: {image_encoder_path}")
            
            # Create a wrapper for image encoder
            class ImageEncoderWrapper(torch.nn.Module):
                def __init__(self, model):
                    super().__init__()
                    self.model = model
                
                def forward(self, x):
                    return self.model.encode_image(x)
            
            image_wrapper = ImageEncoderWrapper(self.model)
            ov_image_encoder = ov.convert_model(
                image_wrapper,
                example_input=sample_image,
                input=[-1, 3, sample_image.shape[2], sample_image.shape[3]],
            )
            ov.save_model(ov_image_encoder, image_encoder_path)
            del ov_image_encoder
            gc.collect()
            logger.info(f"Image encoder saved to: {image_encoder_path}")
        
        # Convert text encoder  
        if not text_encoder_path.exists():
            logger.info(f"Converting CLIP text encoder to OpenVINO: {text_encoder_path}")
            
            # Create a wrapper for text encoder
            class TextEncoderWrapper(torch.nn.Module):
                def __init__(self, model):
                    super().__init__()
                    self.model = model
                
                def forward(self, input_ids):
                    return self.model.encode_text(input_ids)
            
            text_wrapper = TextEncoderWrapper(self.model)
            ov_text_encoder = ov.convert_model(
                text_wrapper,
                example_input=sample_text,
            )
            ov.save_model(ov_text_encoder, text_encoder_path)
            del ov_text_encoder
            gc.collect()
            logger.info(f"Text encoder saved to: {text_encoder_path}")
        
        return str(image_encoder_path), str(text_encoder_path)
    
    def get_embedding_dim(self) -> int:
        """Get the embedding dimension for CLIP models."""
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # Get embedding dimension from the model
        sample_image = torch.randn(1, 3, 224, 224)
        with torch.no_grad():
            features = self.model.encode_image(sample_image)
        return features.shape[-1]
