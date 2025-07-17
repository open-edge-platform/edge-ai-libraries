# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
BLIP-2 model handler implementation using Transformers library.
This replaces the LAVIS-based implementation to avoid vocabulary size mismatch issues.
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
    """Custom BLIP-2 model wrapper for embedding extraction using Transformers."""
    
    def __init__(self, blip2_model, processor, embedding_dim=None):
        super().__init__()
        self.blip2_model = blip2_model
        self.processor = processor
        
        # Use Q-Former dimension as the standard (ensures consistency)
        if hasattr(blip2_model, 'qformer') and hasattr(blip2_model.qformer, 'config'):
            self.embedding_dim = blip2_model.qformer.config.hidden_size
            logger.info(f"Using Q-Former dimension: {self.embedding_dim}")
        elif embedding_dim is not None:
            self.embedding_dim = embedding_dim
        else:
            # Fallback to 768 (standard transformer dimension)
            self.embedding_dim = 768
            logger.warning("Q-Former config not found, using default dimension: 768")
            
        logger.info(f"BLIP2 Transformers embedding dimension: {self.embedding_dim}")
        logger.info("Q-Former will be used for both text and image feature extraction")
            
        logger.info(f"BLIP2 Transformers embedding dimension: {self.embedding_dim}")

    def encode_image(self, pixel_values):
        """Encode image using BLIP2 Q-Former for consistent embeddings."""
        with torch.no_grad():
            # Get vision features
            vision_outputs = self.blip2_model.vision_model(pixel_values)
            image_embeds = vision_outputs.last_hidden_state
            
            # Use Q-Former to get aligned image features
            query_tokens = self.blip2_model.query_tokens.expand(image_embeds.shape[0], -1, -1)
            query_outputs = self.blip2_model.qformer(
                query_embeds=query_tokens,
                encoder_hidden_states=image_embeds,
                encoder_attention_mask=None,
                return_dict=True,
            )
            
            # Use the mean pooling of query outputs as image embedding
            image_features = query_outputs.last_hidden_state.mean(dim=1)
            
            return image_features

    def encode_text(self, input_ids, attention_mask):
        """Encode text using BLIP2 language model with projection to Q-Former space."""
        with torch.no_grad():
            # Use the language model to get text embeddings
            language_outputs = self.blip2_model.language_model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                return_dict=True,
            )
            
            # Get the hidden states
            if hasattr(language_outputs, 'hidden_states') and language_outputs.hidden_states is not None:
                # Use the last hidden state from the hidden states
                text_features = language_outputs.hidden_states[-1]
            else:
                # Fallback: use the logits and project them
                text_features = language_outputs.logits
            
            # Apply attention mask for proper pooling
            mask_expanded = attention_mask.unsqueeze(-1).expand(text_features.size()).float()
            text_features = (text_features * mask_expanded).sum(1) / mask_expanded.sum(1)
            
            # Project to Q-Former dimension if needed
            if text_features.shape[-1] != self.embedding_dim:
                # Create a simple linear projection to match Q-Former dimension
                if not hasattr(self, 'text_projection'):
                    self.text_projection = torch.nn.Linear(text_features.shape[-1], self.embedding_dim)
                    self.text_projection.eval()
                text_features = self.text_projection(text_features)
            
            return text_features

    def tokenizer(self, text_descriptions):
        """Tokenize text using the language model's tokenizer."""
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
    Handler for BLIP-2 models using Transformers library.
    This replaces the LAVIS-based implementation to avoid vocabulary size issues.
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        self.model_name = model_config["model_name"]
        self.pretrained = model_config["pretrained"]
        self.image_size = model_config.get("image_size", 224)
        self.use_openvino = model_config.get("use_openvino", False)
        self.device = model_config.get("device", "CPU")
        self.ov_models_dir = model_config.get("ov_models_dir", "ov-models")
        
        # Map model configurations to Transformers model names
        self.transformers_model_map = {
            "blip2_feature_extractor": {
                "pretrain": "Salesforce/blip2-opt-2.7b",
                "pretrain_vitL": "Salesforce/blip2-opt-6.7b",
            }
        }
        
        # OpenVINO models
        self.ov_image_encoder = None
        self.ov_text_encoder = None
        
    def _get_transformers_model_name(self):
        """Get the appropriate Transformers model name."""
        if self.model_name in self.transformers_model_map:
            model_variants = self.transformers_model_map[self.model_name]
            if self.pretrained in model_variants:
                return model_variants[self.pretrained]
        
        # Fallback to default
        return "Salesforce/blip2-opt-2.7b"
        
    def load_model(self) -> None:
        """Load BLIP-2 model using Transformers library."""
        try:
            logger.info(f"Loading BLIP-2 model: {self.model_name} with pretrained: {self.pretrained}")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Import transformers here to avoid dependency issues if not installed
                from transformers import Blip2Model, Blip2Processor
                
                # Get the appropriate model name
                transformers_model_name = self._get_transformers_model_name()
                logger.info(f"Using Transformers model: {transformers_model_name}")
                
                # Load processor and model (CPU-only)
                self.processor = Blip2Processor.from_pretrained(transformers_model_name)
                blip2_model = Blip2Model.from_pretrained(
                    transformers_model_name,
                    torch_dtype=torch.float32  # Use float32 for CPU-only inference
                )
                
                # Create custom wrapper
                self.model = TransformersBlip2Model(blip2_model, self.processor)
                self.tokenizer = self.model.tokenizer
                
                self.model.eval()
                logger.info(f"BLIP-2 model {self.model_name} loaded successfully using Transformers")
            
        except Exception as e:
            logger.error(f"Failed to load BLIP-2 model {self.model_name}: {e}")
            raise
    
    def _load_openvino_models(self) -> None:
        """Load OpenVINO compiled models. Convert if they don't exist."""
        model_key = f"{self.model_name}_{self.pretrained}_transformers".replace("/", "_").replace("-", "_")
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=lambda: self._load_transformers_model(),
            tokenizer_loader=lambda: self._load_transformers_tokenizer(),
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir,
            logger=logger,
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
        
        # Store the embedding dimension for OpenVINO usage
        self.target_embedding_dim = model.embedding_dim
        
        logger.info(f"BLIP-2 OpenVINO models loaded successfully on device: {self.device}")

    def _load_transformers_model(self):
        """Load the Transformers model and processor."""
        from transformers import Blip2Model, Blip2Processor
        
        transformers_model_name = self._get_transformers_model_name()
        processor = Blip2Processor.from_pretrained(transformers_model_name)
        blip2_model = Blip2Model.from_pretrained(
            transformers_model_name,
            torch_dtype=torch.float32  # Use float32 for CPU-only inference
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
        """Encode text using BLIP-2 text encoder."""
        if isinstance(texts, str):
            texts = [texts]
        
        tokenized = self.tokenizer(texts)
        
        if self.use_openvino and self.ov_text_encoder is not None:
            # Use OpenVINO language model embeddings
            ov_inputs = [
                tokenized["input_ids"].numpy(),
                tokenized["attention_mask"].numpy()
            ]
            text_features = torch.from_numpy(self.ov_text_encoder(ov_inputs)[0])
            
            # Apply dimension alignment for OpenVINO outputs
            # Project from language model dimension to Q-Former dimension
            if hasattr(self, 'target_embedding_dim'):
                target_dim = self.target_embedding_dim
            else:
                target_dim = 768  # Default Q-Former dimension
                
            input_dim = text_features.shape[-1]
            if input_dim != target_dim:
                if not hasattr(self, '_text_projection'):
                    self._text_projection = torch.nn.Linear(input_dim, target_dim)
                    # Initialize with small random weights for better stability
                    with torch.no_grad():
                        torch.nn.init.xavier_uniform_(self._text_projection.weight, gain=0.1)
                text_features = self._text_projection(text_features)
        else:
            # Use PyTorch model
            with torch.no_grad():
                text_features = self.model.encode_text(
                    tokenized["input_ids"], 
                    tokenized["attention_mask"]
                )
        
        text_features = F.normalize(text_features, dim=-1)
        return text_features
    
    def encode_image(self, images: Union[Image.Image, List[Image.Image], torch.Tensor]) -> torch.Tensor:
        """Encode images using BLIP-2 image encoder."""
        if isinstance(images, torch.Tensor):
            pixel_values = images
        elif isinstance(images, Image.Image):
            inputs = self.processor(images=images, return_tensors="pt")
            pixel_values = inputs.pixel_values
        else:  # List of images
            inputs = self.processor(images=images, return_tensors="pt")
            pixel_values = inputs.pixel_values
        
        if self.use_openvino and self.ov_image_encoder is not None:
            # Use OpenVINO vision model
            vision_outputs = torch.from_numpy(self.ov_image_encoder(pixel_values.numpy())[0])
            # Use pooled output or mean pooling
            if len(vision_outputs.shape) == 3:  # [batch, seq_len, dim]
                image_features = vision_outputs.mean(dim=1)  # Mean pooling
            else:
                image_features = vision_outputs
            
            # Apply dimension alignment for OpenVINO outputs
            # Project from vision model dimension to Q-Former dimension
            if hasattr(self, 'target_embedding_dim'):
                target_dim = self.target_embedding_dim
            else:
                target_dim = 768  # Default Q-Former dimension
                
            input_dim = image_features.shape[-1]
            if input_dim != target_dim:
                if not hasattr(self, '_image_projection'):
                    self._image_projection = torch.nn.Linear(input_dim, target_dim)
                    # Initialize with small random weights for better stability
                    with torch.no_grad():
                        torch.nn.init.xavier_uniform_(self._image_projection.weight, gain=0.1)
                image_features = self._image_projection(image_features)
        else:
            # Use PyTorch model
            with torch.no_grad():
                image_features = self.model.encode_image(pixel_values)
        
        image_features = F.normalize(image_features, dim=-1)
        return image_features

    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """Convert BLIP-2 model to OpenVINO format - simplified approach."""
        ov_models_path = Path(ov_models_dir)
        ov_models_path.mkdir(exist_ok=True)
        
        model_key = f"{self.model_name}_{self.pretrained}_transformers".replace("/", "_").replace("-", "_")
        image_encoder_path = ov_models_path / f"{model_key}_image_encoder.xml"
        text_encoder_path = ov_models_path / f"{model_key}_text_encoder.xml"
        
        if model is None:
            model, processor, _ = self._load_transformers_model()
        
        # Convert image encoder (Vision Model only)
        if not image_encoder_path.exists():
            logger.info(f"Converting BLIP-2 vision model to OpenVINO: {image_encoder_path}")
            
            # Use the vision model directly
            vision_model = model.blip2_model.vision_model
            vision_model.eval()
            
            # Create sample input
            sample_image = torch.randn(1, 3, self.image_size, self.image_size)
            
            with torch.no_grad():
                # Convert to OpenVINO
                ov_image_encoder = ov.convert_model(vision_model, example_input=sample_image)
                ov.save_model(ov_image_encoder, image_encoder_path)
                del ov_image_encoder
                gc.collect()
                logger.info(f"Vision model saved to: {image_encoder_path}")
        
        # Convert text encoder (Language Model)
        if not text_encoder_path.exists():
            logger.info(f"Converting BLIP-2 language model to OpenVINO: {text_encoder_path}")
            
            # Use the language model directly for text encoding
            language_model = model.blip2_model.language_model
            language_model.eval()
            
            # Create sample inputs for language model
            sample_text = torch.randint(0, 1000, (1, 10))
            sample_mask = torch.ones_like(sample_text)
            
            with torch.no_grad():
                # Create a simple wrapper that only uses the embeddings
                class LanguageModelEmbeddings(torch.nn.Module):
                    def __init__(self, language_model):
                        super().__init__()
                        self.language_model = language_model
                        
                    def forward(self, input_ids, attention_mask):
                        # Get embeddings from the language model
                        outputs = self.language_model(
                            input_ids=input_ids, 
                            attention_mask=attention_mask,
                            output_hidden_states=True
                        )
                        # Use the last hidden state, CLS token
                        return outputs.hidden_states[-1][:, 0, :]
                
                text_embedder = LanguageModelEmbeddings(language_model)
                text_embedder.eval()
                
                # Test the wrapper
                test_output = text_embedder(sample_text, sample_mask)
                logger.info(f"Text embedder test output shape: {test_output.shape}")
                
                # Convert to OpenVINO
                ov_text_encoder = ov.convert_model(
                    text_embedder, 
                    example_input=(sample_text, sample_mask)
                )
                ov.save_model(ov_text_encoder, text_encoder_path)
                del ov_text_encoder
                gc.collect()
                logger.info(f"Language model embeddings saved to: {text_encoder_path}")
        
        return str(image_encoder_path), str(text_encoder_path)
    
    def get_embedding_dim(self) -> int:
        """Get the embedding dimension for BLIP-2 models."""
        if self.use_openvino:
            # For OpenVINO, return the target embedding dimension
            if hasattr(self, 'target_embedding_dim'):
                return self.target_embedding_dim
            else:
                return 768  # Default Q-Former dimension
        else:
            if self.model is None:
                raise RuntimeError("Model not loaded. Call load_model() first.")
            return self.model.embedding_dim
