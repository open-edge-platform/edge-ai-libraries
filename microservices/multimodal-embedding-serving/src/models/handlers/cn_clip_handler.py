# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
CN-CLIP model handler implementation.

This module provides a handler for CN-CLIP (Chinese CLIP) models, which are
specifically designed and trained for Chinese language and multimodal tasks.
CN-CLIP extends the CLIP architecture to better handle Chinese text and
Chinese-English cross-modal understanding.

Key features of CN-CLIP:
- Optimized for Chinese language understanding
- Cross-lingual capabilities (Chinese-English)
- Enhanced performance on Chinese multimodal datasets
- Support for traditional Chinese text processing
- Cultural context awareness in visual understanding

The handler supports various CN-CLIP model sizes and includes OpenVINO
optimization for efficient deployment in Chinese language applications.
"""

from pathlib import Path
from typing import List, Union, Dict, Any, Optional
import time
import numpy as np
import torch
import torch.nn.functional as F
import gc
import os
import openvino as ov
from PIL import Image
import cn_clip.clip as cn_clip
from cn_clip.clip import load_from_name, available_models

from ..base import BaseEmbeddingModel
from ...utils import logger, ParallelImagePreprocessor
from ..utils import (
    check_and_convert_openvino_models,
    load_openvino_models,
    AsyncBatchInference,
)


class TextEncoder(torch.nn.Module):
    """
    Custom text encoder wrapper for OpenVINO conversion.
    
    This wrapper class encapsulates the CN-CLIP text encoder to provide
    a clean interface for OpenVINO model conversion. It handles the specific
    requirements of the CN-CLIP text encoding pipeline for conversion.
    
    Args:
        model: The CN-CLIP model containing the text encoder
    """
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, text):
        return self.model.encode_text(text)


class CNClipHandler(BaseEmbeddingModel):
    """
    Handler for CN-CLIP models using cn_clip library.
    Supports Chinese text understanding with CLIP-style image-text matching.
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        self.model_name = model_config["model_name"]
        self.pretrained = model_config.get("pretrained", "")
        self.use_openvino = model_config.get("use_openvino", False)
        self.device = model_config.get("device", "CPU")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov-models")
        
        # OpenVINO models
        self.ov_image_encoder = None
        self.ov_text_encoder = None
        self._embedding_dim: Optional[int] = None
        infer_batch_size = model_config.get("infer_batch_size", os.getenv("INFER_BATCH_SIZE", 64))
        self.preprocess_shape = (infer_batch_size, 3, 224, 224)  # Default shape for CN-CLIP image encoder input
        self._preprocess_workers = model_config.get("preprocess_workers", os.getenv("PREPROCESS_WORKERS", min(16, (os.cpu_count() or 4) * 2)))
        self.async_infer = None
        self.parallel_preprocessor: Optional[ParallelImagePreprocessor] = None
        
    def load_model(self) -> None:
        """Load CN-CLIP model using cn_clip."""
        try:
            logger.info(f"Loading CN-CLIP model: {self.model_name}")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Load CN-CLIP model
                self.model, self.preprocess = load_from_name(
                    self.model_name, 
                    device="cpu"
                )
                self.tokenizer = cn_clip.tokenize  # Use standard CN-CLIP tokenizer
                
                self.model.eval()
                logger.info(f"CN-CLIP model {self.model_name} loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load CN-CLIP model {self.model_name}: {e}")
            raise
    
    def _load_openvino_models(self) -> None:
        """Load OpenVINO compiled models. Convert if they don't exist."""
        # Use shared utility to check/convert and load models
        model_key = f"cn_clip_{self.model_name}".replace("/", "_").replace("-", "_")
        
        # Create a model loader that returns 3 values to match the utility function expectation
        def cn_clip_model_loader():
            model, preprocess = load_from_name(self.model_name, device="cpu")
            # Return model as first element, preprocess as second, None as third
            # The utility function will extract just the model with model, _, _ = model_loader()
            return model, preprocess, None
        
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=cn_clip_model_loader,
            tokenizer_loader=lambda: cn_clip.tokenize,
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device, self.preprocess_shape
        )
        
        # Load preprocessing and tokenizer for OpenVINO inference
        _, self.preprocess = load_from_name(self.model_name, device="cpu")
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

        self.tokenizer = cn_clip.tokenize
        logger.info(f"CN-CLIP OpenVINO models loaded successfully on device: {self.device}")
    
    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """
        Convert CN-CLIP model to OpenVINO format.
        
        Args:
            ov_models_dir: Directory to save OpenVINO models
            model: Pre-loaded model (optional, will load if None)
            tokenizer: Pre-loaded tokenizer (optional, will use default if None)
            
        Returns:
            Tuple of (image_encoder_path, text_encoder_path)
        """
        logger.info(f"Converting CN-CLIP model {self.model_name} to OpenVINO format")
        
        # Create output directory
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(parents=True, exist_ok=True)
        
        # Create file paths that match what the utility function expects
        model_key = f"cn_clip_{self.model_name}".replace("/", "_").replace("-", "_")
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        # Use provided model or load if not available
        if model is None:
            model, preprocess = load_from_name(self.model_name, device="cpu")
        else:
            # Model was passed from the utility function, it should just be the model object
            # Load preprocess separately since we need it
            _, preprocess = load_from_name(self.model_name, device="cpu")
        
        # Use provided tokenizer or default
        if tokenizer is None:
            tokenizer = cn_clip.tokenize
        
        # Convert image encoder
        logger.info("Converting image encoder to OpenVINO IR...")
        
        image_input = torch.randn(1, 3, 224, 224, dtype=torch.float32)
        ov_image_encoder = ov.convert_model(
            model.visual, 
            example_input=image_input, 
            input=(-1, 3, 224, 224)  # Use dynamic batch size (-1) for image encoder
        )
        ov.save_model(ov_image_encoder, image_encoder_path)
        
        # Convert text encoder
        logger.info("Converting text encoder to OpenVINO IR...")
        
        text_model = TextEncoder(model)
        # Use standard CN-CLIP tokenization for dummy input
        token_input = tokenizer(["test"])
        
        ov_text_encoder = ov.convert_model(
            text_model, 
            example_input=token_input, 
            input=(-1, 52)  # Use dynamic batch size (-1) for text encoder
        )
        ov.save_model(ov_text_encoder, text_encoder_path)
        
        logger.info(f"CN-CLIP model converted successfully. Files saved as:")
        logger.info(f"  Image encoder: {image_encoder_path}")
        logger.info(f"  Text encoder: {text_encoder_path}")
        return str(image_encoder_path), str(text_encoder_path)
    
    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """
        Encode text into embeddings.
        
        Args:
            texts: Single text string or list of text strings
            
        Returns:
            Text embeddings as torch.Tensor
        """
        if isinstance(texts, str):
            texts = [texts]
        
        if self.use_openvino:
            return self._encode_text_openvino(texts)
        else:
            return self._encode_text_pytorch(texts)
    
    def _encode_text_pytorch(self, texts: List[str]) -> torch.Tensor:
        """Encode text using PyTorch model."""
        with torch.no_grad():
            # Use standard CN-CLIP tokenization (default context_length=52)
            text_tokens = self.tokenizer(texts)
            text_features = self.model.encode_text(text_tokens)
            # Normalize features
            text_features = F.normalize(text_features, p=2, dim=1)
        return text_features
    
    def _encode_text_openvino(self, texts: List[str]) -> torch.Tensor:
        """Encode text using OpenVINO model."""
        text_tokens = self.tokenizer(texts)
        # Use OpenVINO inference with infer_new_request for thread safety
        result = self.ov_text_encoder.infer_new_request({self.ov_text_encoder.inputs[0]: text_tokens.numpy()})
        text_features = torch.from_numpy(result[self.ov_text_encoder.outputs[0]])
        # Convert to torch tensor and normalize
        text_features = F.normalize(text_features, p=2, dim=1)
        return text_features
    
    def encode_image(self, images: Union[Image.Image, List[Image.Image]], metrics_out: bool = False) -> Union[Dict[str, Any], torch.Tensor]:
        """
        Encode images into embeddings.
        
        Args:
            images: Single PIL Image or list of PIL Images
            metrics_out: If True, return a dict with embeddings and timing metrics
                         (only applicable for OpenVINO path with PIL images)
            
        Returns:
            Image embeddings as torch.Tensor, or a metrics dict if metrics_out=True
        """
        if isinstance(images, Image.Image):
            images = [images]
        total_images = len(images)
        
        if self.use_openvino:
            logger.info(f"====AsyncInferQueue====")
            preprocess_stream = self.parallel_preprocessor.preprocess_stream(images)
            try:
                infer_start = time.perf_counter()
                embeddings = self.async_infer.infer_stream(
                    batch_generator=preprocess_stream, total_images=total_images
                )
                infer_end = time.perf_counter()
            finally:
                preprocess_stream.close()

            image_features = F.normalize(torch.from_numpy(embeddings), dim=-1)

        else:
            infer_start = time.perf_counter()
            with torch.no_grad():
                image_tensor = torch.stack([self.preprocess(img) for img in images])
                image_features = self.model.encode_image(image_tensor)
            image_features = F.normalize(image_features, dim=-1)
            infer_end = time.perf_counter()
        
        if metrics_out:
            return {
                "embeddings": image_features,
                "inference_time_s": infer_end - infer_start,
                "processed_images": total_images,
            }
        return image_features


    def get_embedding_dim(self) -> int:
        """Get the embedding dimension."""
        if self._embedding_dim is not None:
            return self._embedding_dim

        if self.preprocess is None:
            raise RuntimeError("Preprocessing pipeline not initialized. Call load_model() first.")

        image_size = self._get_preprocess_image_size()

        if self.use_openvino:
            if self.async_infer is None:
                raise RuntimeError("OpenVINO async inference not initialized. Call load_model() first.")

            dummy_image = Image.fromarray(np.random.randint(0, 255, (image_size, image_size, 3), dtype=np.uint8))
            dummy_np = np.array(self.preprocess(dummy_image))[np.newaxis]  # [1, C, H, W]
            result = self.async_infer.infer(dummy_np)
            self._embedding_dim = int(result.shape[-1])
        else:
            if self.model is None:
                raise RuntimeError("Model not loaded. Call load_model() first.")

            with torch.no_grad():
                dummy_text = self.tokenizer(["test"])
                dummy_features = self.model.encode_text(dummy_text)
                self._embedding_dim = dummy_features.shape[1]

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
    
    def get_supported_image_formats(self) -> List[str]:
        """Get supported image formats."""
        return ["RGB", "RGBA", "L"]
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if hasattr(self, 'model') and self.model is not None:
            del self.model
        if hasattr(self, 'preprocess') and self.preprocess is not None:
            del self.preprocess
        if hasattr(self, 'tokenizer') and self.tokenizer is not None:
            del self.tokenizer
        
        # Clean up OpenVINO models
        if self.ov_image_encoder is not None:
            del self.ov_image_encoder
        if self.ov_text_encoder is not None:
            del self.ov_text_encoder
        
        # Force garbage collection
        gc.collect()
        logger.info("CN-CLIP model cleanup completed")
