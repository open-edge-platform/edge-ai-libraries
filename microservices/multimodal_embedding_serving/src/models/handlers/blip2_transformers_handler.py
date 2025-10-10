# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
BLIP-2 model handler implementation using Transformers library.

This module provides an alternative BLIP-2 handler that uses the Hugging Face
Transformers library instead of the LAVIS framework. This implementation helps
avoid vocabulary size mismatch issues and provides better compatibility with
standard PyTorch workflows.

The Transformers-based implementation offers:
- Better integration with Hugging Face ecosystem
- Simplified model loading and configuration
- Improved stability and error handling
- Consistent tokenization and preprocessing
- Enhanced OpenVINO conversion support
- Projection layers for semantic search (768D → 256D) matching LAVIS behavior

IMPORTANT: For semantic search/retrieval tasks, this handler uses projection layers
to reduce embeddings from 768D (Q-Former) to 256D (projected space). This matches
the LAVIS implementation and is CRITICAL for good search quality. The projection
layers are specifically trained during BLIP-2's contrastive learning phase.

The handler maintains the same interface as other model handlers while providing
BLIP-2's advanced vision-language capabilities through the Q-Former architecture.
"""

from pathlib import Path
from typing import List, Union, Dict, Any
import torch
import torch.nn.functional as F
import gc
import openvino as ov
from PIL import Image

from ..base import BaseEmbeddingModel
from ...utils import logger
from ..utils import (
    check_and_convert_openvino_models,
    load_openvino_models,
)


class TransformersBlip2Model(torch.nn.Module):
    """
    Custom BLIP-2 model wrapper for embedding extraction using Transformers library.
    
    This wrapper provides a unified interface for BLIP-2 models loaded through
    the Hugging Face Transformers library. It handles the Q-Former architecture
    and ensures consistent embedding dimensions across text and image modalities.
    
    This implementation uses projection layers from Blip2ForImageTextRetrieval to
    reduce embeddings from 768D to 256D. This matches LAVIS behavior and is
    essential for good semantic search quality.
    
    The wrapper manages:
    - Q-Former based feature alignment
    - Projection layers for semantic search (768D → 256D)
    - Consistent embedding dimensionality (256D)
    - Text and image encoding workflows
    - Tokenization and preprocessing
    
    Args:
        blip2_model: The loaded BLIP-2 model from Transformers (must have projection layers)
        processor: Associated processor for text and image preprocessing
    """
    
    def __init__(self, blip2_model, processor):
        super().__init__()
        self.blip2_model = blip2_model
        self.processor = processor
        
        # Verify model has projection layers (required for semantic search)
        if not hasattr(blip2_model, 'vision_projection'):
            raise ValueError(
                "Model must have projection layers for semantic search. "
                "Use Blip2ForImageTextRetrieval model."
            )
        
        # Get embedding dimensions from model config
        self.qformer_dim = blip2_model.config.qformer_config.hidden_size  # 768
        self.embedding_dim = blip2_model.config.image_text_hidden_size    # 256
        
        logger.info(f"BLIP-2 model initialized for semantic search")
        logger.info(f"Q-Former dimension: {self.qformer_dim}D")
        logger.info(f"Projected dimension: {self.embedding_dim}D (matches LAVIS)")

    def encode_image(self, pixel_values):
        """
        Encode image using BLIP2 with projection for semantic search.
        
        Processes images through the vision model and Q-Former to produce
        aligned embeddings, then applies the vision_projection layer to reduce
        from 768D to 256D, matching LAVIS image_embeds_proj behavior.
        
        Process flow:
        1. Vision Model → vision features
        2. Q-Former → query-based features (768D)
        3. Projection → compact embeddings (256D)
        4. Mean pooling → final image embedding
        5. Normalization → unit vector for cosine similarity
        
        Args:
            pixel_values: Preprocessed image tensor
            
        Returns:
            Image embeddings (256D)
        """
        with torch.no_grad():
            # Get vision features
            vision_outputs = self.blip2_model.vision_model(pixel_values)
            image_embeds = vision_outputs.last_hidden_state
            
            # Create attention mask for vision embeddings
            image_attention_mask = torch.ones(
                image_embeds.size()[:-1], 
                dtype=torch.long, 
                device=image_embeds.device
            )
            
            # Use Q-Former to get aligned image features
            query_tokens = self.blip2_model.query_tokens.expand(image_embeds.shape[0], -1, -1)
            query_outputs = self.blip2_model.qformer(
                query_embeds=query_tokens,
                encoder_hidden_states=image_embeds,
                encoder_attention_mask=image_attention_mask,
                return_dict=True,
            )
            
            # Get Q-Former output (768D)
            image_features = query_outputs.last_hidden_state
            
            # Apply projection (768D → 256D for semantic search)
            image_features = self.blip2_model.vision_projection(image_features)
            
            # Mean pool over query tokens
            image_features = image_features.mean(dim=1)
            
            # Normalize for cosine similarity (like LAVIS)
            image_features = F.normalize(image_features, dim=-1)
            
            return image_features

    def encode_text(self, input_ids, attention_mask):
        """
        Encode text using BLIP2 with projection for semantic search.
        
        Processes text through embeddings and Q-Former to produce aligned embeddings,
        then applies the text_projection layer to reduce from 768D to 256D,
        matching LAVIS text_embeds_proj behavior.
        
        Process flow:
        1. Text Embeddings → token embeddings
        2. Q-Former → query-based features (768D)
        3. Projection → compact embeddings (256D)
        4. [CLS] token → final text embedding
        5. Normalization → unit vector for cosine similarity
        
        Args:
            input_ids: Tokenized input text tensor
            attention_mask: Attention mask for the input
            
        Returns:
            Text embeddings (256D)
        """
        with torch.no_grad():
            # Use Blip2ForImageTextRetrieval path
            query_embeds = self.blip2_model.embeddings(input_ids=input_ids)
            
            # Process through Q-Former (without cross-attention to image)
            text_outputs = self.blip2_model.qformer(
                query_embeds=query_embeds,
                query_length=0,
                attention_mask=attention_mask,
                return_dict=True,
            )
            
            # Get Q-Former output (768D)
            text_features = text_outputs.last_hidden_state
            
            # Apply projection (768D → 256D) using [CLS] token
            text_features = self.blip2_model.text_projection(text_features[:, 0, :])
            
            # Normalize for cosine similarity (like LAVIS)
            text_features = F.normalize(text_features, dim=-1)
            
            return text_features

    def tokenizer(self, text_descriptions):
        """
        Tokenize text using the language model's tokenizer.
        
        Provides a consistent tokenization interface that handles both
        single strings and lists of text descriptions. Uses the underlying
        language model's tokenizer with appropriate padding and truncation.
        
        Args:
            text_descriptions: Single text string or list of text strings
            
        Returns:
            Dictionary containing input_ids and attention_mask tensors
        """
        if isinstance(text_descriptions, str):
            text_descriptions = [text_descriptions]
        
        # Use the language model's tokenizer directly
        inputs = self.processor.tokenizer(
            text_descriptions, 
            return_tensors="pt", 
            padding=True, 
            truncation=True,
            max_length=77  # Common max length for multimodal models
        )
        return {
            "input_ids": inputs.input_ids,
            "attention_mask": inputs.attention_mask
        }


class BLIP2TransformersHandler(BaseEmbeddingModel):
    """
    Handler for BLIP-2 models using the Hugging Face Transformers library.
    
    This handler provides an implementation optimized for semantic search/retrieval
    tasks using BLIP-2's projection layers (768D → 256D). It uses the Hugging Face
    Transformers library for better integration with the ecosystem and improved
    stability.
    
    This implementation always uses projection layers to match LAVIS behavior,
    which is essential for good search quality in semantic search applications.
    
    Key features:
    - Transformers-based model loading and processing
    - Projection layers for semantic search (768D → 256D, matches LAVIS)
    - Automatic retrieval model selection
    - Improved tokenization and preprocessing
    - Enhanced OpenVINO conversion support
    - Better error handling and stability
    
    Attributes:
        model_name: BLIP-2 model variant identifier
        pretrained: Pretrained checkpoint specification
        image_size: Input image dimensions
        use_openvino: Whether to use OpenVINO optimization
        device: Target device for inference
        retrieval_model_map: Mapping to retrieval-specific models with projections
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        self.model_name = model_config["model_name"]
        self.pretrained = model_config["pretrained"]
        self.image_size = model_config.get("image_size", 224)
        self.use_openvino = model_config.get("use_openvino", False)
        self.device = model_config.get("device", "CPU")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov-models")
        
        # Map to retrieval-specific model with projection layers
        # This model includes vision_projection and text_projection (768D → 256D)
        # Note: Both pretrain and pretrain_vitL use the same HuggingFace model
        self.retrieval_model = "Salesforce/blip2-itm-vit-g"  # ITM = Image-Text Matching
        
        # OpenVINO models
        self.ov_image_encoder = None
        self.ov_text_encoder = None
        
    def _get_transformers_model_name(self):
        """
        Get the appropriate Transformers model name for the current configuration.
        
        Returns the Hugging Face retrieval model identifier with projection layers.
        All BLIP-2 variants (pretrain, pretrain_vitL) use the same retrieval model
        since they differ only in vision encoder size, which is handled internally.
        
        Returns:
            str: Hugging Face model identifier with projection layers
        """
        # Always use the same retrieval model with projection layers
        logger.info(f"Using retrieval model with projection layers: {self.retrieval_model}")
        return self.retrieval_model
        
    def load_model(self) -> None:
        """
        Load BLIP-2 model using the Transformers library.
        
        Initializes the BLIP-2 retrieval model with projection layers from Hugging Face
        Transformers. The model includes vision_projection and text_projection layers
        (768D → 256D) for optimal semantic search quality.
        
        The loading process includes:
        - Retrieval model variant selection
        - Processor and tokenizer initialization
        - Custom wrapper creation for consistent interface
        - OpenVINO model compilation (if enabled)
        
        Raises:
            Exception: If model loading fails for any reason
        """
        try:
            logger.info(f"Loading BLIP-2 retrieval model: {self.model_name} ({self.pretrained})")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Get the retrieval model name
                transformers_model_name = self._get_transformers_model_name()
                logger.info(f"Using Transformers model: {transformers_model_name}")
                
                # Load retrieval model with projection layers
                from transformers import Blip2ForImageTextRetrieval, Blip2Processor
                
                logger.info("Loading Blip2ForImageTextRetrieval with projection layers...")
                self.processor = Blip2Processor.from_pretrained(transformers_model_name)
                blip2_model = Blip2ForImageTextRetrieval.from_pretrained(
                    transformers_model_name,
                    torch_dtype=torch.float32
                )
                
                # Create custom wrapper
                self.model = TransformersBlip2Model(blip2_model, self.processor)
                self.tokenizer = self.model.tokenizer
                
                self.model.eval()
                logger.info(f"BLIP-2 model loaded successfully")
                logger.info(f"Embedding dimension: {self.model.embedding_dim}D (256D for semantic search)")
            
        except Exception as e:
            logger.error(f"Failed to load BLIP-2 model {self.model_name}: {e}")
            raise
    
    def _load_openvino_models(self) -> None:
        """Load OpenVINO compiled models. Convert if they don't exist."""
        model_key = f"{self.model_name}_{self.pretrained}_transformers_retrieval".replace("/", "_").replace("-", "_")
        
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=lambda: self._load_transformers_model(),
            tokenizer_loader=lambda: self._load_transformers_tokenizer(),
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device
        )
        # Always load preprocessing and tokenizer for OpenVINO inference
        model, processor, _ = self._load_transformers_model()
        self.processor = processor
        # Create a simplified tokenizer for OpenVINO
        self.tokenizer = lambda texts: {
            "input_ids": processor(text=texts, return_tensors="pt", padding=True, truncation=True).input_ids,
            "attention_mask": processor(text=texts, return_tensors="pt", padding=True, truncation=True).attention_mask
        }
        
        logger.info(f"BLIP-2 OpenVINO models loaded on device: {self.device}")
        logger.info(f"Embedding dimension: 256D (includes projection + normalization)")

    def _load_transformers_model(self):
        """Load the Transformers retrieval model and processor."""
        transformers_model_name = self._get_transformers_model_name()
        
        # Load retrieval model with projection layers
        from transformers import Blip2ForImageTextRetrieval, Blip2Processor
        
        processor = Blip2Processor.from_pretrained(transformers_model_name)
        blip2_model = Blip2ForImageTextRetrieval.from_pretrained(
            transformers_model_name,
            torch_dtype=torch.float32
        )
        
        model = TransformersBlip2Model(blip2_model, processor)
        # Return 3 values to match the expected interface (model, vis_processor, txt_processor)
        return model, processor, processor

    def _load_transformers_tokenizer(self):
        """Load the Transformers tokenizer."""
        model, processor, _ = self._load_transformers_model()
        return lambda texts: {
            "input_ids": processor(text=texts, return_tensors="pt", padding=True, truncation=True).input_ids,
            "attention_mask": processor(text=texts, return_tensors="pt", padding=True, truncation=True).attention_mask
        }

    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """
        Encode text using BLIP-2 text encoder with projection.
        
        Returns 256D embeddings for semantic search.
        """
        if isinstance(texts, str):
            texts = [texts]
        
        tokenized = self.tokenizer(texts)
        
        if self.use_openvino and self.ov_text_encoder is not None:
            # Use OpenVINO text encoder with infer_new_request for thread safety
            # The converted model already includes Q-Former + projection + normalization
            result = self.ov_text_encoder.infer_new_request({
                self.ov_text_encoder.inputs[0]: tokenized["input_ids"].numpy(),
                self.ov_text_encoder.inputs[1]: tokenized["attention_mask"].numpy()
            })
            text_features = torch.from_numpy(result[self.ov_text_encoder.outputs[0]])
        else:
            # Use PyTorch model (already includes projection + normalization)
            text_features = self.model.encode_text(
                tokenized["input_ids"], 
                tokenized["attention_mask"]
            )
        
        return text_features
    
    def encode_image(self, images: Union[Image.Image, List[Image.Image], torch.Tensor]) -> torch.Tensor:
        """
        Encode images using BLIP-2 image encoder with projection.
        
        Returns 256D embeddings for semantic search.
        """
        if isinstance(images, torch.Tensor):
            pixel_values = images
        elif isinstance(images, Image.Image):
            inputs = self.processor(images=images, return_tensors="pt")
            pixel_values = inputs.pixel_values
        else:  # List of images
            inputs = self.processor(images=images, return_tensors="pt")
            pixel_values = inputs.pixel_values
        
        if self.use_openvino and self.ov_image_encoder is not None:
            # Use OpenVINO image encoder with infer_new_request for thread safety
            # The converted model already includes Q-Former + projection + normalization
            result = self.ov_image_encoder.infer_new_request({
                self.ov_image_encoder.inputs[0]: pixel_values.numpy()
            })
            image_features = torch.from_numpy(result[self.ov_image_encoder.outputs[0]])
        else:
            # Use PyTorch model (already includes projection + normalization)
            image_features = self.model.encode_image(pixel_values)
        
        return image_features

    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """Convert BLIP-2 retrieval model to OpenVINO format."""
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(exist_ok=True)
        
        model_key = f"{self.model_name}_{self.pretrained}_transformers_retrieval".replace("/", "_").replace("-", "_")
        
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        if model is None:
            model, processor, _ = self._load_transformers_model()
        
        logger.info(f"Converting BLIP-2 retrieval model to OpenVINO...")
        
        # Convert image encoder (for retrieval model)
        if not image_encoder_path.exists():
            logger.info(f"Converting BLIP-2 image encoder to OpenVINO: {image_encoder_path}")
            
            # Create sample input
            sample_image = torch.randn(1, 3, self.image_size, self.image_size)
            
            with torch.no_grad():
                # Create a wrapper that uses the model's encode_image path
                class ImageEncoderWrapper(torch.nn.Module):
                    def __init__(self, wrapper_model):
                        super().__init__()
                        self.wrapper_model = wrapper_model
                        
                    def forward(self, pixel_values):
                        # Use the wrapper's encode_image method directly
                        return self.wrapper_model.encode_image(pixel_values)
                
                image_encoder_wrapper = ImageEncoderWrapper(model)
                image_encoder_wrapper.eval()
                
                # Test the wrapper
                test_output = image_encoder_wrapper(sample_image)
                logger.info(f"Image encoder test output shape: {test_output.shape}")
                
                # Convert to OpenVINO
                ov_image_encoder = ov.convert_model(image_encoder_wrapper, example_input=sample_image)
                ov.save_model(ov_image_encoder, image_encoder_path)
                del ov_image_encoder
                gc.collect()
                logger.info(f"Image encoder saved to: {image_encoder_path}")
        
        # Convert text encoder (for retrieval model)
        if not text_encoder_path.exists():
            logger.info(f"Converting BLIP-2 text encoder to OpenVINO: {text_encoder_path}")
            
            # For retrieval model, wrap the encode_text method
            # Create sample inputs for text encoding
            sample_text = torch.randint(0, 1000, (1, 10))
            sample_mask = torch.ones_like(sample_text)
            
            with torch.no_grad():
                # Create a wrapper that uses the model's encode_text path
                class TextEncoderWrapper(torch.nn.Module):
                    def __init__(self, wrapper_model):
                        super().__init__()
                        self.wrapper_model = wrapper_model
                        
                    def forward(self, input_ids, attention_mask):
                        # Use the wrapper's encode_text method directly
                        return self.wrapper_model.encode_text(input_ids, attention_mask)
                
                text_encoder_wrapper = TextEncoderWrapper(model)
                text_encoder_wrapper.eval()
                
                # Test the wrapper
                test_output = text_encoder_wrapper(sample_text, sample_mask)
                logger.info(f"Text encoder test output shape: {test_output.shape}")
                
                # Convert to OpenVINO
                ov_text_encoder = ov.convert_model(
                    text_encoder_wrapper, 
                    example_input=(sample_text, sample_mask)
                )
                ov.save_model(ov_text_encoder, text_encoder_path)
                del ov_text_encoder
                gc.collect()
                logger.info(f"Text encoder saved to: {text_encoder_path}")
        
        return str(image_encoder_path), str(text_encoder_path)
    
    def get_embedding_dim(self) -> int:
        """Get the embedding dimension for BLIP-2 models."""
        # Always 256D for retrieval model (includes projection)
        if self.use_openvino:
            return 256
        else:
            if self.model is None:
                raise RuntimeError("Model not loaded. Call load_model() first.")
            return self.model.embedding_dim
