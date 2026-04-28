# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SigLIP model handler implementation.

This module provides a handler for SigLIP (Sigmoid Loss for Language-Image Pre-training)
models, which use a sigmoid-based loss function instead of the traditional softmax
approach used in CLIP. This change allows for better scalability and often improved
performance on large-scale datasets.

SigLIP models offer several advantages:
- More efficient training with sigmoid loss
- Better performance on image-text retrieval tasks
- Improved scalability for large batch sizes
- Enhanced robustness in multimodal understanding

The handler supports various SigLIP architectures and includes OpenVINO optimization
for efficient inference deployment.
"""

import os
from pathlib import Path
import time
from typing import List, Optional, Union, Dict, Any
import numpy as np
import torch
import torch.nn.functional as F
import types
import gc
import openvino as ov
from PIL import Image
import open_clip

from ..base import BaseEmbeddingModel
from ...utils import logger, ParallelImagePreprocessor
from ..utils import (
    check_and_convert_openvino_models,
    load_openvino_models,
    AsyncBatchInference,
)


class SigLIPHandler(BaseEmbeddingModel):
    """
    Handler for SigLIP models using the open_clip library.
    
    This class implements the BaseEmbeddingModel interface for SigLIP models,
    providing sigmoid-based contrastive learning for text and image encoding.
    SigLIP's sigmoid approach offers improved training efficiency and often
    better performance compared to traditional softmax-based approaches.
    
    The handler follows the established initialization patterns and supports
    both PyTorch and OpenVINO inference modes for optimal performance across
    different deployment scenarios.
    
    Attributes:
        model_name: SigLIP model architecture name
        pretrained: Pretrained checkpoint identifier
        use_openvino: Whether to use OpenVINO optimization
        device: Target device for inference
        ov_models_dir: Directory for OpenVINO model storage
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        self.model_name = model_config["model_name"]
        self.pretrained = model_config["pretrained"]
        self.image_size = model_config.get("image_size", 224)
        self.use_openvino = model_config.get("use_openvino", False)
        self.device = model_config.get("device", "CPU")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov-models")
        
        # OpenVINO models
        self.ov_image_encoder = None
        self.ov_text_encoder = None

        self._embedding_dim: Optional[int] = None
        infer_batch_size = model_config.get("infer_batch_size", os.getenv("INFER_BATCH_SIZE", 64))
        self.preprocess_shape = (infer_batch_size, 3, self.image_size, self.image_size)  # Default shape for CLIP image encoder input
        self._preprocess_workers = model_config.get("preprocess_workers", os.getenv("PREPROCESS_WORKERS", min(16, (os.cpu_count() or 4) * 2)))
        self.async_infer = None
        self.parallel_preprocessor: Optional[ParallelImagePreprocessor] = None
        
    def load_model(self) -> None:
        """Load SigLIP model using open_clip."""
        try:
            logger.info(f"Loading SigLIP model: {self.model_name} with pretrained: {self.pretrained}")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Use optimized initialization for SigLIP models
                self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                    self.model_name, 
                    pretrained=self.pretrained
                )
                self.tokenizer = open_clip.get_tokenizer(self.model_name)
                
                self.model.eval()
                logger.info(f"SigLIP model {self.model_name} loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load SigLIP model {self.model_name}: {e}")
            raise
    
    def _load_openvino_models(self) -> None:
        """Load OpenVINO compiled models. Convert if they don't exist."""
        model_key = f"{self.model_name}_{self.pretrained}".replace("/", "_").replace("-", "_")
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=lambda: open_clip.create_model_and_transforms(self.model_name, pretrained=self.pretrained),
            tokenizer_loader=lambda: open_clip.get_tokenizer(self.model_name),
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device, self.preprocess_shape
        )
        # Always load preprocessing and tokenizer for OpenVINO inference
        _, _, self.preprocess = open_clip.create_model_and_transforms(
            self.model_name, pretrained=self.pretrained
        )
        
        self.parallel_preprocessor = ParallelImagePreprocessor(
            preprocess_fn=self.preprocess,
            max_workers=self._preprocess_workers,
            preprocess_shape=self.preprocess_shape
        )
        embedding_dim = int(self.ov_image_encoder.output().get_partial_shape()[-1].to_string())
        logger.info(f"Encoder o/p dimension: {embedding_dim}")
        self.async_infer = AsyncBatchInference(
            compiled_model=self.ov_image_encoder,
            embedding_dim=embedding_dim,
            preprocess_shape=self.preprocess_shape
        )

        self.tokenizer = open_clip.get_tokenizer(self.model_name)
        logger.info(f"SigLIP OpenVINO models loaded successfully on device: {self.device}")
    
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """Encode text using SigLIP text encoder."""
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
    
    def encode_image(self, images: Union[Image.Image, List[Image.Image]], metrics_out: bool = False) -> Union[Dict[str, Any], torch.Tensor]:
        """Encode images using SigLIP image encoder."""

        if isinstance(images, Image.Image):
            images = [images]
        total_images = len(images)
        if self.use_openvino and self.ov_image_encoder is not None:
            # Use OpenVINO inference with infer_new_request for thread safety

            logger.info(f"====AsyncInferQueue====")
            preprocess_stream = self.parallel_preprocessor.preprocess_stream(images)
            try:
                infer_start = time.perf_counter()
                embeddings = self.async_infer.infer_stream(batch_generator=preprocess_stream, total_images=total_images)
                infer_end = time.perf_counter()
            finally:
                preprocess_stream.close()
                del images

            logger.info(f"Inference time for batch of {total_images} images: {infer_end - infer_start:.4f} seconds")

            if metrics_out:
                return {
                    "embeddings": embeddings,
                    "inference_time_s": infer_end - infer_start,
                    "processed_images": total_images
                }
            image_features = torch.from_numpy(embeddings)
        else:
            # Use PyTorch model
            with torch.no_grad():
                if isinstance(images, Image.Image):
                    images = [images]
                inputs = self.processor(images=images, return_tensors="pt")
                pixel_values = inputs.pixel_values
                image_features = self.model.encode_image(pixel_values)      
        
        image_features = F.normalize(image_features, dim=-1)
        return image_features
    
    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """Convert SigLIP model to OpenVINO format for inference optimization."""
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
        sample_image = torch.randn(1, 3, self.image_size, self.image_size)
        sample_text = tokenizer(["sample text"])
        
        # Convert image encoder for OpenVINO optimization
        if not image_encoder_path.exists():
            logger.info(f"Converting SigLIP image encoder to OpenVINO: {image_encoder_path}")
            
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
            logger.info(f"Converting SigLIP text encoder to OpenVINO: {text_encoder_path}")
            
            # Modify model forward method to encode_text
            original_forward = model.forward
            model.forward = model.encode_text
            
            try:
                ov_text_encoder = ov.convert_model(
                    model,
                    example_input=sample_text,
                    input=[-1, sample_text.shape[1]],
                )
            except Exception as conversion_error:
                logger.warning(
                    "Default conversion path for SigLIP text encoder failed, retrying with TorchScript trace: %s",
                    conversion_error,
                )

                class _TextWrapper(torch.nn.Module):
                    """Simple wrapper to expose encode_text as a forward method."""

                    def __init__(self, base_model: torch.nn.Module):
                        super().__init__()
                        self.base_model = base_model

                    def forward(self, text: torch.Tensor) -> torch.Tensor:  # pragma: no cover - simple wrapper
                        return self.base_model.encode_text(text)

                wrapper = _TextWrapper(model).eval()
                traced_text = torch.jit.trace(wrapper, sample_text, check_trace=False)
                traced_text.eval()
                ov_text_encoder = ov.convert_model(traced_text)
                del traced_text, wrapper
                logger.info("SigLIP text encoder conversion succeeded via TorchScript trace fallback")
            finally:
                model.forward = original_forward
                gc.collect()
            
            ov.save_model(ov_text_encoder, text_encoder_path)
            del ov_text_encoder
            gc.collect()
            logger.info(f"Text encoder saved to: {text_encoder_path}")
            
        
        return str(image_encoder_path), str(text_encoder_path)
    
    def get_embedding_dim(self) -> int:
        """Get the embedding dimension for SigLIP models."""
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # Get embedding dimension from the model
        sample_image = torch.randn(1, 3, self.image_size, self.image_size)
        with torch.no_grad():
            features = self.model.encode_image(sample_image)
        return features.shape[-1]
