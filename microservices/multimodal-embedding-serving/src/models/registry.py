# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model registry and factory implementation.

This module implements the factory pattern for creating model handlers.
It maintains a registry of available model handler classes and provides
convenience functions for model creation and management.

The registry supports various multimodal embedding models including:
- CLIP models (OpenAI CLIP and variants)
- MobileCLIP (Apple's mobile-optimized CLIP)
- SigLIP (Google's sigmoid-based CLIP)
- BLIP2 (Salesforce's vision-language model)
- CN-CLIP (Chinese CLIP variant)

Each model type has its own handler class that implements the BaseEmbeddingModel
interface, providing consistent text and image encoding capabilities.
"""

from typing import Dict, Type
from .base import BaseEmbeddingModel
from .handlers import (
    CLIPHandler,
    CNClipHandler,
    MobileCLIPHandler,
    SigLIPHandler,
    BLIP2Handler,
    BLIP2TransformersHandler,
    QwenEmbeddingHandler,
)
from .config import get_model_config, list_available_models
from ..utils import logger


# Registry mapping handler class names to actual classes
MODEL_HANDLER_REGISTRY: Dict[str, Type[BaseEmbeddingModel]] = {
    "CLIPHandler": CLIPHandler,
    "CNClipHandler": CNClipHandler,
    "MobileCLIPHandler": MobileCLIPHandler,
    "SigLIPHandler": SigLIPHandler,
    "BLIP2Handler": BLIP2Handler,
    "BLIP2TransformersHandler": BLIP2TransformersHandler,
    "QwenEmbeddingHandler": QwenEmbeddingHandler,
}


class ModelFactory:
    """
    Factory class for creating model handlers using the factory pattern.
    
    This class provides static methods for creating appropriate model handlers
    based on model configuration. It abstracts the complexity of model
    instantiation and provides a unified interface for model creation.
    
    The factory supports:
    - Dynamic model handler selection based on configuration
    - Optional parameter overrides for device, OpenVINO settings
    - Model validation and error handling
    - Registry-based handler lookup
    """

    @staticmethod
    def create_model(model_id: str, device=None, ov_models_dir=None, use_openvino=None) -> BaseEmbeddingModel:
        """
        Create a model handler for the specified model with optional parameter overrides.

        This method creates and configures a model handler based on the model ID
        and optional runtime parameters. It handles model configuration lookup,
        handler class resolution, and instance creation with proper error handling.

        Args:
            model_id: Model identifier (e.g., "CLIP/clip-vit-b-16" or "clip-vit-b-16")
            device: Target device for inference ("CPU", "GPU", etc.). If None, uses config default
            ov_models_dir: Directory for OpenVINO model files. If None, uses config default  
            use_openvino: Whether to use OpenVINO optimization. If None, uses config default

        Returns:
            Configured model handler instance ready for loading and inference

        Raises:
            ValueError: If model ID is invalid or handler class is not found
            Exception: If model handler creation fails for any other reason
        """
        try:
            # Get model configuration with possible overrides
            config = get_model_config(
                model_id,
                device=device,
                ov_models_dir=ov_models_dir,
                use_openvino=use_openvino,
            )
            handler_class_name = config["handler_class"]

            # Get handler class from registry
            if handler_class_name not in MODEL_HANDLER_REGISTRY:
                raise ValueError(
                    f"Handler class {handler_class_name} not found in registry"
                )

            handler_class = MODEL_HANDLER_REGISTRY[handler_class_name]

            # Create and return handler instance
            logger.info(
                f"Creating {handler_class_name} for model {model_id} with config: {config}"
            )
            return handler_class(config)

        except Exception as e:
            logger.error(f"Failed to create model handler for {model_id}: {e}")
            raise

    @staticmethod
    def list_models() -> Dict[str, list]:
        """
        List all available models grouped by model type.

        Returns:
            Dictionary mapping model types to lists of available model names.
            For example: {"CLIP": ["clip-vit-b-16", "clip-vit-l-14"], "MobileCLIP": [...]}
        """
        return list_available_models()


    @staticmethod
    def is_model_supported(model_id: str) -> bool:
        """
        Check if a model identifier is supported by the factory.

        Args:
            model_id: Model identifier to validate

        Returns:
            True if the model is supported and can be created, False otherwise
        """
        """
        Check if a model is supported.

        Args:
            model_id (str): Model identifier

        Returns:
            bool: True if model is supported, False otherwise
        """
        try:
            get_model_config(model_id)
            return True
        except ValueError:
            return False


def get_model_handler(model_id: str = None, device=None, ov_models_dir=None, use_openvino=None) -> BaseEmbeddingModel:
    """
    Convenience function to get a configured model handler.

    This function provides a simplified interface for creating model handlers
    with optional parameter overrides. If no model ID is provided, it uses
    the default model from configuration.

    Args:
        model_id: Model identifier. If None, uses the default model from configuration
        device: Target device for inference. If None, uses config default
        ov_models_dir: Directory for OpenVINO model files. If None, uses config default
        use_openvino: Whether to use OpenVINO optimization. If None, uses config default

    Returns:
        Configured model handler instance ready for use

    Example:
        
        # Use specific model with custom device
        handler = get_model_handler("CLIP/clip-vit-b-16", device="GPU")
        
        # Enable OpenVINO optimization
        handler = get_model_handler("MobileCLIP/mobileclip_s0", use_openvino=True)
    """

    return ModelFactory.create_model(
        model_id,
        device=device,
        ov_models_dir=ov_models_dir,
        use_openvino=use_openvino,
    )


def register_model_handler(name: str, handler_class: Type[BaseEmbeddingModel]) -> None:
    """
    Register a new model handler class in the factory registry.

    This function allows dynamic registration of new model handler classes,
    enabling extensibility for custom model implementations. The registered
    handler must implement the BaseEmbeddingModel interface.

    Args:
        name: Unique name for the handler class (used in model configurations)
        handler_class: Handler class that implements BaseEmbeddingModel interface

    Example:
        class CustomHandler(BaseEmbeddingModel):
            # Implementation here
            pass
            
        register_model_handler("CustomHandler", CustomHandler)
    """
    MODEL_HANDLER_REGISTRY[name] = handler_class
    logger.info(f"Registered model handler: {name}")


def create_model_handler(model_id: str) -> BaseEmbeddingModel:
    """
    Create a model handler using default configuration (backward compatibility).

    This function is maintained for backward compatibility with older code
    that doesn't need parameter overrides. For new code, prefer using
    get_model_handler() which provides more flexibility.

    Args:
        model_id: Model identifier string

    Returns:
        Model handler instance with default configuration
    """
    return get_model_handler(model_id)
