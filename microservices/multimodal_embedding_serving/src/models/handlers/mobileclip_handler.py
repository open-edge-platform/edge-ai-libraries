# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MobileCLIP model handler implementation.
"""

from pathlib import Path
from typing import List, Union, Dict, Any
import torch
import torch.nn.functional as F
import types
import gc
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
    """Apply forward pass for SE block - required for MobileCLIP conversion."""
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
    Handler for MobileCLIP models using mobileclip library.
    Follows the initialization pattern from the MobileCLIP notebook.
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
                # Download model if URL is provided
                if self.url:
                    model_dir = Path("checkpoints")
                    model_dir.mkdir(exist_ok=True)
                    
                    # Download model file if it doesn't exist
                    model_path = model_dir / Path(self.url).name
                    if not model_path.exists():
                        logger.info(f"Downloading MobileCLIP model from {self.url}")
                        import requests
                        response = requests.get(self.url)
                        response.raise_for_status()
                        with open(model_path, 'wb') as f:
                            f.write(response.content)
                        logger.info(f"Model downloaded to {model_path}")
                    
                    # Load model with local checkpoint
                    self.model, _, self.preprocess = mobileclip.create_model_and_transforms(
                        self.model_name, 
                        pretrained=str(model_path)
                    )
                else:
                    # Load model with pretrained path
                    self.model, _, self.preprocess = mobileclip.create_model_and_transforms(
                        self.model_name, 
                        pretrained=self.pretrained
                    )
                
                self.tokenizer = mobileclip.get_tokenizer(self.model_name)
                self.model.eval()
                logger.info(f"MobileCLIP model {self.model_name} loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load MobileCLIP model {self.model_name}: {e}")
            raise
    
    def _load_openvino_models(self) -> None:
        """Load OpenVINO compiled models. Convert if they don't exist."""
        model_key = f"{self.model_name}".replace("/", "_").replace("-", "_")
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=lambda: mobileclip.create_model_and_transforms(self.model_name, pretrained=self.pretrained),
            tokenizer_loader=lambda: mobileclip.get_tokenizer(self.model_name),
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir,
            logger=logger,
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device
        )
        # Always load preprocessing and tokenizer for OpenVINO inference
        _, _, self.preprocess = mobileclip.create_model_and_transforms(
            self.model_name, pretrained=self.pretrained
        )
        self.tokenizer = mobileclip.get_tokenizer(self.model_name)
        logger.info(f"MobileCLIP OpenVINO models loaded successfully on device: {self.device}")
    
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """Encode text using MobileCLIP text encoder."""
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
        """Encode images using MobileCLIP image encoder."""
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
        """Convert MobileCLIP model to OpenVINO format following the notebook pattern."""
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(exist_ok=True)
        
        # Use provided model and tokenizer, or fallback to instance attributes
        if model is None:
            model = self.model
        if tokenizer is None:
            tokenizer = self.tokenizer
            
        if model is None or tokenizer is None:
            raise RuntimeError("Model and tokenizer must be available for conversion")
        
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
