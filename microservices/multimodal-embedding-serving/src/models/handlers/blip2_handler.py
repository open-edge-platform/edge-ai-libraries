# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
BLIP-2 model handler implementation.
"""

from pathlib import Path
from typing import List, Union, Dict, Any
import torch
import torch.nn.functional as F
import types
import gc
import openvino as ov
from PIL import Image

from ..base import BaseEmbeddingModel
from ...utils import logger
from ..utils import (
    check_and_convert_openvino_models,
    load_openvino_models,
)


class Blip2Model(torch.nn.Module):
    """Custom BLIP-2 model wrapper for embedding extraction."""
    
    def __init__(self, ln_vision, visual_encoder, query_tokens, q_former, vision_proj, text_proj, tokenizer):
        super().__init__()
        self.ln_vision = ln_vision
        self.visual_encoder = visual_encoder
        self.query_tokens = query_tokens
        self.q_former = q_former
        self.vision_proj = vision_proj
        self.text_proj = text_proj
        self.tok = tokenizer

    def encode_image(self, image):
        image_embeds_frozen = self.ln_vision(self.visual_encoder(image))
        image_embeds_frozen = image_embeds_frozen.float()
        image_atts = torch.ones(image_embeds_frozen.size()[:-1], dtype=torch.long)
        query_tokens = self.query_tokens.expand(image_embeds_frozen.shape[0], -1, -1)

        query_output = self.q_former.bert(
            query_embeds=query_tokens,
            encoder_hidden_states=image_embeds_frozen,
            encoder_attention_mask=image_atts,
            return_dict=True,
        )
        image_embeds = query_output.last_hidden_state
        image_features = self.vision_proj(image_embeds)

        return image_features

    def encode_text(self, input_ids, attention_mask):
        text_output = self.q_former.bert(
            input_ids,
            attention_mask=attention_mask,
            return_dict=True,
        )
        text_embeds = text_output.last_hidden_state
        text_features = self.text_proj(text_embeds)
        return text_features

    def tokenizer(self, text_descriptions):
        if isinstance(text_descriptions, str):
            text_descriptions = [text_descriptions]
        input_ids = self.tok(text_descriptions, return_tensors="pt", padding=True).input_ids
        attention_mask = self.tok(text_descriptions, return_tensors="pt", padding=True).attention_mask
        return {"input_ids": input_ids, "attention_mask": attention_mask}


class BLIP2Handler(BaseEmbeddingModel):
    """
    Handler for BLIP-2 models using lavis library.
    Follows the initialization pattern from the MobileCLIP notebook.
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
        
    def load_model(self) -> None:
        """Load BLIP-2 model using lavis."""
        try:
            logger.info(f"Loading BLIP-2 model: {self.model_name} with pretrained: {self.pretrained}")
            
            if self.use_openvino:
                # Load OpenVINO models
                self._load_openvino_models()
            else:
                # Import lavis here to avoid dependency issues if not installed
                from lavis.models import load_model_and_preprocess
                
                # Follow the notebook pattern for BLIP-2 models
                model, vis_processors, txt_processors = load_model_and_preprocess(
                    name=self.model_name, 
                    model_type=self.pretrained, 
                    is_eval=True
                )
                
                # Create custom BLIP-2 wrapper
                self.model = Blip2Model(
                    model.ln_vision, 
                    model.visual_encoder, 
                    model.query_tokens, 
                    model.Qformer, 
                    model.vision_proj, 
                    model.text_proj, 
                    model.tokenizer
                )
                
                self.preprocess = vis_processors["eval"]
                self.tokenizer = self.model.tokenizer
                
                self.model.eval()
                logger.info(f"BLIP-2 model {self.model_name} loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load BLIP-2 model {self.model_name}: {e}")
            raise
    
    def _load_openvino_models(self) -> None:
        """Load OpenVINO compiled models. Convert if they don't exist."""
        model_key = f"{self.model_name}_{self.pretrained}".replace("/", "_").replace("-", "_")
        image_encoder_path, text_encoder_path = check_and_convert_openvino_models(
            model_key=model_key,
            model_loader=lambda: self._load_lavis_model_and_preprocess(),
            tokenizer_loader=lambda: self._load_lavis_tokenizer(),
            convert_func=self.convert_to_openvino,
            ov_models_dir=self.ov_models_dir
        )
        self.ov_image_encoder, self.ov_text_encoder = load_openvino_models(
            image_encoder_path, text_encoder_path, self.device
        )
        # Always load preprocessing and tokenizer for OpenVINO inference
        model, vis_processors, _ = self._load_lavis_model_and_preprocess()
        self.preprocess = vis_processors["eval"]
        self.tokenizer = lambda texts: {
            "input_ids": model.tokenizer(texts, return_tensors="pt", padding=True).input_ids,
            "attention_mask": model.tokenizer(texts, return_tensors="pt", padding=True).attention_mask
        }
        logger.info(f"BLIP-2 OpenVINO models loaded successfully on device: {self.device}")

    def _load_lavis_model_and_preprocess(self):
        from lavis.models import load_model_and_preprocess
        return load_model_and_preprocess(
            name=self.model_name,
            model_type=self.pretrained,
            is_eval=True
        )

    def _load_lavis_tokenizer(self):
        model, _, _ = self._load_lavis_model_and_preprocess()
        return lambda texts: {
            "input_ids": model.tokenizer(texts, return_tensors="pt", padding=True).input_ids,
            "attention_mask": model.tokenizer(texts, return_tensors="pt", padding=True).attention_mask
        }

    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        """Encode text using BLIP-2 text encoder."""
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
                text_features = self.model.encode_text(
                    tokenized["input_ids"], 
                    tokenized["attention_mask"]
                )
        
        text_features = F.normalize(text_features, dim=-1)
        return text_features
    
    def encode_image(self, images: Union[Image.Image, List[Image.Image], torch.Tensor]) -> torch.Tensor:
        """Encode images using BLIP-2 image encoder."""
        if isinstance(images, torch.Tensor):
            image_tensor = images
        elif isinstance(images, Image.Image):
            image_tensor = self.preprocess(images).unsqueeze(0)
        else:  # List of images
            image_tensor = torch.stack([self.preprocess(img) for img in images])
        
        if self.use_openvino and self.ov_image_encoder is not None:
            # Use OpenVINO inference with infer_new_request for thread safety
            result = self.ov_image_encoder.infer_new_request({self.ov_image_encoder.inputs[0]: image_tensor})
            image_features = torch.from_numpy(result[self.ov_image_encoder.outputs[0]])
        else:
            # Use PyTorch model
            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)
        
        image_features = F.normalize(image_features, dim=-1)
        return image_features

    def convert_to_openvino(self, ov_models_dir: str, model=None, tokenizer=None) -> tuple:
        """Convert BLIP-2 model to OpenVINO format following the notebook pattern."""
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
        
        # Convert image encoder following the notebook pattern
        if not image_encoder_path.exists():
            logger.info(f"Converting BLIP-2 image encoder to OpenVINO: {image_encoder_path}")
            
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
        
        # Convert text encoder following the notebook pattern
        if not text_encoder_path.exists():
            logger.info(f"Converting BLIP-2 text encoder to OpenVINO: {text_encoder_path}")
            
            # Modify model forward method to encode_text
            original_forward = model.forward
            model.forward = model.encode_text
            
            # For BLIP-2, use the special conversion approach from the notebook
            ov_text_encoder = ov.convert_model(
                model,
                example_input=sample_text
            )
            ov.save_model(ov_text_encoder, text_encoder_path)
            del ov_text_encoder
            gc.collect()
            logger.info(f"Text encoder saved to: {text_encoder_path}")
            
            # Restore original forward method
            model.forward = original_forward
        
        return str(image_encoder_path), str(text_encoder_path)
    
    def get_embedding_dim(self) -> int:
        """Get the embedding dimension for BLIP-2 models."""
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # Get embedding dimension from the model
        sample_image = torch.randn(1, 3, self.image_size, self.image_size)
        with torch.no_grad():
            features = self.model.encode_image(sample_image)
        return features.shape[-1]
