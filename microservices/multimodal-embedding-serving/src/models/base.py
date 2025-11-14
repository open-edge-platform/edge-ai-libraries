# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Base model interface for multimodal embedding models.

This module defines the abstract base class that all multimodal embedding model
handlers must implement. It provides a consistent interface for text and image
encoding operations across different model architectures.

The base class handles common initialization patterns and defines the contract
that all model handlers must follow, ensuring interoperability and consistent
behavior across different model types.
"""

from abc import ABC, abstractmethod
from typing import List, Union, Optional, Dict, Any
from PIL import Image
import numpy as np
import torch


class BaseEmbeddingModel(ABC):
    """
    Abstract base class for multimodal embedding models.
    
    This class defines the interface that all model handlers must implement
    for consistent text and image encoding capabilities. Each handler should
    focus on the essential functionality of multimodal embedding generation
    while maintaining compatibility with OpenVINO optimization.
    
    The class provides common initialization patterns and abstract methods
    that must be implemented by concrete model handlers. It supports both
    PyTorch and OpenVINO inference modes.
    
    Attributes:
        model_config: Configuration dictionary for the model
        model: The underlying model instance (PyTorch or OpenVINO)
        tokenizer: Tokenizer for text processing
        preprocess: Image preprocessing function
        device: Target device for inference
        ov_models_dir: Directory for OpenVINO model storage
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        """
        Initialize the model with configuration.
        
        Sets up common attributes shared across all model handlers including
        device settings, model paths, and OpenVINO configuration.
        
        Args:
            model_config: Dictionary containing model configuration including:
                - device: Target device for inference (default: "cpu")
                - ov_models_dir: Directory for OpenVINO models (default: "ov_models")
                - use_openvino: Whether to use OpenVINO optimization
                - modalities: Optional iterable of supported modalities
                - Other model-specific parameters
        """
        self.model_config = model_config
        self.model = None
        self.tokenizer = None
        self.preprocess = None
        self.device = model_config.get("device", "cpu")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov_models")
        default_modalities = {"text", "image"}
        config_modalities = model_config.get("modalities")
        if config_modalities:
            self.supported_modalities = set(config_modalities)
        else:
            self.supported_modalities = default_modalities
        
    @abstractmethod
    def load_model(self) -> None:
        """
        Load the model, tokenizer and preprocessing functions.
        
        This method must be implemented by concrete handlers to load their
        specific model architecture. It should handle both PyTorch and
        OpenVINO loading modes based on the use_openvino configuration.
        
        The implementation should:
        - Load the model weights and architecture
        - Initialize the tokenizer for text processing
        - Set up image preprocessing functions
        - Handle OpenVINO conversion if enabled
        
        Raises:
            RuntimeError: If model loading fails
        """
        pass
    
    @abstractmethod
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """
        Encode text into embeddings.
        
        Converts input text strings into high-dimensional embedding vectors
        that capture semantic meaning. The embeddings are typically normalized
        and can be used for similarity calculations with other text or image embeddings.
        
        Args:
            texts: Single text string or list of text strings to encode
            
        Returns:
            Normalized text embeddings as torch.Tensor with shape:
            - [embedding_dim] for single text
            - [batch_size, embedding_dim] for multiple texts
            
        Note:
            The implementation should handle tokenization and ensure
            consistent output dimensions regardless of input length.
        """
        pass

    @abstractmethod
    def encode_image(self, images: Union[Image.Image, List[Image.Image], torch.Tensor]) -> torch.Tensor:
        """
        Encode images into embeddings.
        
        Converts input images into high-dimensional embedding vectors that
        capture visual features. The embeddings are typically normalized and
        can be used for similarity calculations with text or other image embeddings.
        
        Args:
            images: Input images in one of the following formats:
                - Single PIL Image
                - List of PIL Images  
                - Preprocessed tensor with shape [batch_size, channels, height, width]
            
        Returns:
            Normalized image embeddings as torch.Tensor with shape:
            - [embedding_dim] for single image
            - [batch_size, embedding_dim] for multiple images
            
        Note:
            The implementation should handle image preprocessing if needed
            and ensure consistent output dimensions.
        """
        pass

    @abstractmethod
    def convert_to_openvino(self, ov_models_dir: str) -> tuple:
        """
        Convert the model to OpenVINO format for optimized inference.
        
        Converts the PyTorch model to OpenVINO Intermediate Representation (IR)
        format for improved inference performance. This typically involves
        converting separate image and text encoders.
        
        Args:
            ov_models_dir: Directory to save the converted OpenVINO model files
            
        Returns:
            Tuple of (image_encoder_path, text_encoder_path) pointing to the
            saved OpenVINO IR model files (.xml and .bin)
            
        Note:
            The conversion process may require example inputs to trace the model.
            The implementation should handle model preparation and cleanup.
        """
        pass

    # ----------------------------------------------------------------------
    # Optional capability hooks
    # ----------------------------------------------------------------------

    def supports_text(self) -> bool:
        """Return True if the handler can produce text embeddings."""
        return "text" in self.supported_modalities

    def supports_image(self) -> bool:
        """Return True if the handler can produce image embeddings."""
        return "image" in self.supported_modalities

    def supports_video(self) -> bool:
        """Return True if the handler can consume video inputs (via image pathway)."""
        return "video" in self.supported_modalities or self.supports_image()

    def prepare_query(self, text: str) -> str:
        """
        Optional preprocessing hook for single query text.

        Handlers can override this to implement instruction wrapping or
        other normalization. The default implementation returns the text
        unchanged to maintain backwards compatibility.
        """
        return text

    def prepare_documents(self, texts: List[str]) -> List[str]:
        """
        Optional preprocessing hook for batches of documents.

        The default implementation returns the incoming list unchanged.
        """
        return texts
    
    def get_embedding_dim(self) -> int:
        """
        Get the dimension of the embeddings produced by this model.
        
        Returns:
            Integer representing the dimensionality of the embedding vectors.
            Common dimensions include 512, 768, 1024, etc.
            
        Raises:
            RuntimeError: If model is not loaded yet
            
        Note:
            This method provides a default implementation returning 512.
            Subclasses should override this to return the actual embedding
            dimension of their specific model architecture.
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        # This should be implemented by subclasses if needed
        return 512  # Default value

    def preprocess_image(self, image: Union[Image.Image, np.ndarray]) -> torch.Tensor:
        """
        Preprocess image for model input.
        
        Applies the necessary preprocessing transformations to prepare images
        for the model. This typically includes resizing, normalization, and
        tensor conversion.
        
        Args:
            image: Input image as PIL Image or numpy array
            
        Returns:
            Preprocessed image tensor ready for model input
            
        Raises:
            RuntimeError: If preprocessing function is not available
            
        Note:
            The preprocessing function should be initialized during load_model().
            Different models may have different preprocessing requirements.
        """
        if self.preprocess is None:
            raise RuntimeError("Preprocessing function not available. Call load_model() first.")
        
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        
        return self.preprocess(image)
