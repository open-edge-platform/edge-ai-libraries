# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Base model interface for multimodal embedding models.
"""

from abc import ABC, abstractmethod
from typing import List, Union, Optional, Dict, Any
from PIL import Image
import numpy as np
import torch


class BaseEmbeddingModel(ABC):
    """
    Abstract base class for multimodal embedding models.
    
    This class defines the interface that all model handlers must implement.
    Each handler should focus on the essential functionality of text and image encoding.
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        """
        Initialize the model with configuration.
        
        Args:
            model_config: Dictionary containing model configuration
        """
        self.model_config = model_config
        self.model = None
        self.tokenizer = None
        self.preprocess = None
        self.device = model_config.get("device", "cpu")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov_models")
        
    @abstractmethod
    def load_model(self) -> None:
        """Load the model, tokenizer and preprocessing functions."""
        pass
    
    @abstractmethod
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """
        Encode text into embeddings.
        
        Args:
            texts: Single text string or list of text strings
            
        Returns:
            Text embeddings as torch.Tensor
        """
        pass
    
    @abstractmethod
    def encode_image(self, images: Union[Image.Image, List[Image.Image], torch.Tensor]) -> torch.Tensor:
        """
        Encode images into embeddings.
        
        Args:
            images: Single PIL Image, list of PIL Images, or preprocessed tensor
            
        Returns:
            Image embeddings as torch.Tensor
        """
        pass
    
    @abstractmethod
    def convert_to_openvino(self, ov_models_dir: str) -> tuple:
        """
        Convert the model to OpenVINO format.
        
        Args:
            ov_models_dir: Directory to save OpenVINO models
            
        Returns:
            Tuple of (image_encoder_path, text_encoder_path)
        """
        pass
    
    def get_embedding_dim(self) -> int:
        """Get the dimension of the embeddings."""
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        # This should be implemented by subclasses if needed
        return 512  # Default value
    
    def preprocess_image(self, image: Union[Image.Image, np.ndarray]) -> torch.Tensor:
        """
        Preprocess image for model input.
        
        Args:
            image: PIL Image or numpy array
            
        Returns:
            Preprocessed image tensor
        """
        if self.preprocess is None:
            raise RuntimeError("Preprocessing function not available. Call load_model() first.")
        
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        
        return self.preprocess(image)
