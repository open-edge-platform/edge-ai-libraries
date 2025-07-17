# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model registry and factory implementation.
Implements the factory pattern for creating model handlers.
"""

from typing import Dict, Type
from .base import BaseEmbeddingModel
from .handlers import CLIPHandler, MobileCLIPHandler, SigLIPHandler, BLIP2Handler
from .handlers.blip2_transformers_handler import BLIP2TransformersHandler
from .config import get_model_config, list_available_models, get_default_model
from ..utils import logger


# Registry mapping handler class names to actual classes
MODEL_HANDLER_REGISTRY: Dict[str, Type[BaseEmbeddingModel]] = {
    "CLIPHandler": CLIPHandler,
    "MobileCLIPHandler": MobileCLIPHandler,
    "SigLIPHandler": SigLIPHandler,
    "BLIP2Handler": BLIP2Handler,
    "BLIP2TransformersHandler": BLIP2TransformersHandler,
}


class ModelFactory:
    """
    Factory class for creating model handlers.
    Implements the factory pattern to create appropriate model handlers
    based on model configuration.
    """

    @staticmethod
    def create_model(model_id: str, device=None, ov_models_dir=None, use_openvino=None) -> BaseEmbeddingModel:
        """
        Create a model handler for the specified model, with optional OpenVINO params.

        Args:
            model_id (str): Model identifier (e.g., "CLIP/clip-vit-b-16")
            device (str, optional): Device for inference (e.g., "CPU")
            ov_models_dir (str, optional): Directory for OpenVINO models
            use_openvino (bool, optional): Whether to use OpenVINO

        Returns:
            BaseEmbeddingModel: Model handler instance

        Raises:
            ValueError: If model or handler class is not found
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
        List all available models.

        Returns:
            Dict[str, list]: Dictionary with model types as keys and model names as values
        """
        return list_available_models()

    @staticmethod
    def get_default() -> str:
        """
        Get the default model identifier.

        Returns:
            str: Default model identifier
        """
        return get_default_model()

    @staticmethod
    def is_model_supported(model_id: str) -> bool:
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
    Convenience function to get a model handler, with OpenVINO params.

    Args:
        model_id (str, optional): Model identifier. If None, uses default model.
        device (str, optional): Device for inference (e.g., "CPU")
        ov_models_dir (str, optional): Directory for OpenVINO models
        use_openvino (bool, optional): Whether to use OpenVINO

    Returns:
        BaseEmbeddingModel: Model handler instance
    """
    if model_id is None:
        model_id = ModelFactory.get_default()

    return ModelFactory.create_model(
        model_id,
        device=device,
        ov_models_dir=ov_models_dir,
        use_openvino=use_openvino,
    )


def register_model_handler(name: str, handler_class: Type[BaseEmbeddingModel]) -> None:
    """
    Register a new model handler class.

    Args:
        name (str): Name of the handler class
        handler_class (Type[BaseEmbeddingModel]): Handler class
    """
    MODEL_HANDLER_REGISTRY[name] = handler_class
    logger.info(f"Registered model handler: {name}")


# For backward compatibility
def create_model_handler(model_id: str) -> BaseEmbeddingModel:
    """
    Create a model handler (backward compatibility function).

    Args:
        model_id (str): Model identifier

    Returns:
        BaseEmbeddingModel: Model handler instance
    """
    return get_model_handler(model_id)
