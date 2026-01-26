# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import gc
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch

# Disable SDPA to avoid compatibility issues with older model versions
os.environ["TRANSFORMERS_DISABLE_SDPA"] = "1"

try:
    import openvino as ov
    import openvino.opset13 as opset13
except ImportError:
    import openvino as ov
    import openvino.runtime.opset13 as opset13

from huggingface_hub import snapshot_download
from transformers import AutoProcessor, AutoModelForCausalLM, AutoModel

try:
    from transformers.modeling_utils import PreTrainedModel
    if not hasattr(PreTrainedModel, '_supports_sdpa'):
        PreTrainedModel._supports_sdpa = False
except Exception as e:
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(f"Could not patch PreTrainedModel: {e}")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Model file names for Florence-2
IMAGE_EMBEDDING_NAME = "image_embedding.xml"
TEXT_EMBEDDING_NAME = "text_embedding.xml"
ENCODER_NAME = "encoder.xml"
DECODER_NAME = "decoder.xml"

core = ov.Core()


class ModelConverter:
    """Unified model converter for PyTorch to OpenVINO IR conversion"""
    
    SUPPORTED_PRECISIONS = ["fp32", "fp16", "int8","int4"]
    SUPPORTED_DEVICES = ["cpu", "gpu","npu", "auto"]
    FLORENCE2_IDENTIFIERS = ["florence", "Florence"]
    
    def __init__(
        self,
        model_name: str,
        download_path: str,
        precision: str = "fp32",
        device: str = "cpu"
    ):
        """
        Initialize the model converter.
        
        Args:
            model_name: HuggingFace model identifier
            download_path: Path to download and save converted models
            precision: Model precision (fp32, fp16, int8)
            device: Target device (cpu, gpu, auto)
        """
        self.model_name = model_name
        self.download_path = Path(download_path) / model_name
        self.precision = self._validate_precision(precision)
        self.device = self._validate_device(device)
        self.orig_model_dir = self.download_path / "chkpt"
        self.is_florence2 = any(f in model_name for f in self.FLORENCE2_IDENTIFIERS)
        
        # Create directories
        self.download_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Model Converter initialized")
        logger.info(f"  Model: {model_name}")
        logger.info(f"  Path: {self.download_path}")
        logger.info(f"  Precision: {self.precision}")
        logger.info(f"  Device: {self.device}")
        logger.info(f"  Type: {'Florence-2' if self.is_florence2 else 'Generic'}")
    
    @staticmethod
    def _validate_precision(precision: str) -> str:
        """Validate precision setting"""
        precision = precision.lower()
        if precision not in ModelConverter.SUPPORTED_PRECISIONS:
            raise ValueError(f"Unsupported precision: {precision}. Supported: {ModelConverter.SUPPORTED_PRECISIONS}")
        return precision
    
    @staticmethod
    def _validate_device(device: str) -> str:
        """Validate device setting"""
        device = device.lower()
        if device not in ModelConverter.SUPPORTED_DEVICES:
            raise ValueError(f"Unsupported device: {device}. Supported: {ModelConverter.SUPPORTED_DEVICES}")
        return device
    
    @staticmethod
    def cleanup_torchscript_cache():
        """Clean up TorchScript cache to free memory"""
        torch._C._jit_clear_class_registry()
        torch.jit._recursive.concrete_type_store = torch.jit._recursive.ConcreteTypeStore()
        torch.jit._state._clear_class_state()
        gc.collect()
    
    def download_model(self) -> Path:
        """Download model from HuggingFace Hub"""
        if not self.orig_model_dir.exists():
            logger.info(f"Downloading model: {self.model_name}")
            try:
                snapshot_download(repo_id=self.model_name, local_dir=self.orig_model_dir)
                logger.info(f"Model downloaded successfully")
            except Exception as e:
                logger.error(f"Failed to download model: {e}")
                raise
        else:
            logger.info(f"Model already exists")
        
        return self.orig_model_dir
    
    def _patch_florence2_modeling_file(self):
        """Patch Florence-2 modeling file to remove flash attention dependencies and add _supports_sdpa"""
        modeling_file = self.orig_model_dir / "modeling_florence2.py"
        orig_modeling_file = self.orig_model_dir / f"orig_{modeling_file.name}"
        
        if not orig_modeling_file.exists() and modeling_file.exists():
            modeling_file.rename(orig_modeling_file)
            with orig_modeling_file.open("r") as f:
                content = f.read()
            
            # Remove flash attention dependencies
            content = content.replace("if is_flash_attn_2_available():", "")
            content = content.replace("    from flash_attn.bert_padding import index_first_axis, pad_input, unpad_input", "")
            content = content.replace("    from flash_attn import flash_attn_func, flash_attn_varlen_func", "")
            
            # Add _supports_sdpa attribute to Florence2ForConditionalGeneration class
            # Simple approach: add it right after the class definition line
            content = content.replace(
                "class Florence2ForConditionalGeneration(PreTrainedModel):",
                "class Florence2ForConditionalGeneration(PreTrainedModel):\n    _supports_sdpa = False"
            )
            
            with modeling_file.open("w") as f:
                f.write(content)
            
            logger.info("Modeling file patched (removed flash attention, added _supports_sdpa)")
    
    def convert_model(self, model: torch.nn.Module, example_input: Any, output_path: Path, model_name: str = "model") -> bool:
        """Convert PyTorch model to OpenVINO IR format"""
        try:
            output_path = Path(output_path)
            
            if output_path.exists():
                logger.info(f"Found converted {model_name}")
                return True
            
            logger.info(f"Converting {model_name}...")
            
            with torch.no_grad():
                ov_model = ov.convert_model(model, example_input=example_input)
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            ov_model = self._apply_precision(ov_model)
            ov.save_model(ov_model, output_path)
            
            del ov_model
            del model
            self.cleanup_torchscript_cache()
            
            logger.info(f"{model_name} conversion finished")
            return True
            
        except Exception as e:
            logger.error(f"Failed to convert {model_name}: {e}")
            raise RuntimeError(f"Conversion failed: {e}")
    
    def _apply_precision(self, ov_model: ov.Model) -> ov.Model:
        """Apply precision transformations"""
        if self.precision == "fp16":
            logger.info("Applying FP16 precision...")
            try:
                from openvino.tools.mo import compress_model_transformation
                ov_model = compress_model_transformation(ov_model)
                logger.info("FP16 precision applied")
            except Exception as e:
                logger.warning(f"Could not apply FP16: {e}")
        
        return ov_model
    
    def convert_generic_model(self) -> bool:
        """Convert a generic PyTorch/Transformers model"""
        try:
            logger.info(f"Loading model: {self.model_name}")
            
            # Download model
            self.download_model()
            
            # Load model
            model = AutoModel.from_pretrained(self.orig_model_dir, trust_remote_code=True)
            model.eval()
            
            # Create example input
            example_input = torch.randn(1, 128, 768)
            
            # Convert model
            output_path = self.download_path / "model.xml"
            success = self.convert_model(model, example_input, output_path, "model")
            
            if success:
                logger.info(f"Generic model conversion completed")
            
            return success
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            raise RuntimeError(f"Conversion failed: {e}")
    
    def convert_florence2(self) -> bool:
        """Convert Florence-2 vision-language model"""
        try:
            # Check if already converted
            required_files = [IMAGE_EMBEDDING_NAME, TEXT_EMBEDDING_NAME, ENCODER_NAME, DECODER_NAME]
            
            if all((self.download_path / f).exists() for f in required_files):
                logger.info(f"{self.model_name} already converted")
                return True
            
            logger.info(f"{self.model_name} conversion started")
            
            # Download model
            self.download_model()
            self._patch_florence2_modeling_file()
            
            # Load model and processor with error handling for _supports_sdpa
            logger.info("Loading original model...")
            try:
                model = AutoModelForCausalLM.from_pretrained(self.orig_model_dir, trust_remote_code=True)
            except AttributeError as e:
                if "_supports_sdpa" in str(e):
                    logger.info("Applying post-load _supports_sdpa fix...")
                    # Patch the config to disable attention implementation checks
                    import sys
                    from transformers import PreTrainedModel
                    
                    # Add the attribute to the PreTrainedModel class if not present
                    if not hasattr(PreTrainedModel, '_supports_sdpa'):
                        PreTrainedModel._supports_sdpa = False
                    
                    # Also set environment variable
                    os.environ["TRANSFORMERS_NO_ADAPTIVE_ATTENTION_TIME_LIMIT"] = "1"
                    
                    # Try loading again
                    model = AutoModelForCausalLM.from_pretrained(
                        self.orig_model_dir, 
                        trust_remote_code=True,
                        attn_implementation="eager"
                    )
                else:
                    raise
            
            # Ensure the model has _supports_sdpa attribute
            if not hasattr(model, '_supports_sdpa'):
                model._supports_sdpa = False
            
            processor = AutoProcessor.from_pretrained(self.orig_model_dir, trust_remote_code=True)
            
            # Save processor and config
            processor.save_pretrained(self.download_path)
            model.config.save_pretrained(self.download_path)
            logger.info("Original model loaded")
            
            # Convert components
            success = True
            success &= self._convert_florence2_image_embedding(model, processor)
            success &= self._convert_florence2_text_embedding(model)
            success &= self._convert_florence2_encoder(model)
            success &= self._convert_florence2_decoder(model)
            
            # Cleanup
            del model
            self.cleanup_torchscript_cache()
            
            if success:
                logger.info(f"Florence-2 conversion completed")
            
            return success
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}", exc_info=True)
            raise RuntimeError(f"Conversion failed: {e}")
    
    def _convert_florence2_image_embedding(self, model, processor) -> bool:
        """Convert image embedding component"""
        output_path = self.download_path / IMAGE_EMBEDDING_NAME
        
        if output_path.exists():
            logger.info(f"Found converted image embedding")
            return True
        
        try:
            logger.info(f"Converting image embedding...")
            
            model._orig_forward = model.forward
            model.forward = model._encode_image
            
            image_size = processor.image_processor.crop_size
            example_input = torch.zeros([1, 3, image_size["height"], image_size["width"]])
            
            ov_model = ov.convert_model(
                model,
                example_input=example_input,
                input=[-1, 3, image_size["height"], image_size["width"]]
            )
            
            ov_model = self._apply_precision(ov_model)
            ov.save_model(ov_model, output_path)
            
            del ov_model
            self.cleanup_torchscript_cache()
            
            logger.info(f"Image embedding conversion finished")
            return True
            
        except Exception as e:
            logger.error(f"Image embedding conversion failed: {e}")
            raise RuntimeError(f"Image embedding conversion failed: {e}")
    
    def _convert_florence2_text_embedding(self, model) -> bool:
        """Convert text embedding component"""
        output_path = self.download_path / TEXT_EMBEDDING_NAME
        
        if output_path.exists():
            logger.info(f"Found converted text embedding")
            return True
        
        try:
            logger.info(f"Converting text embedding...")
            
            text_embedding = model.get_input_embeddings()
            example_input = torch.ones([2, 2], dtype=torch.long)
            
            ov_model = ov.convert_model(text_embedding, example_input=example_input)
            ov_model = self._apply_precision(ov_model)
            ov.save_model(ov_model, output_path)
            
            del ov_model
            self.cleanup_torchscript_cache()
            
            logger.info(f"Text embedding conversion finished")
            return True
            
        except Exception as e:
            logger.error(f"Text embedding conversion failed: {e}")
            raise RuntimeError(f"Text embedding conversion failed: {e}")
    
    def _convert_florence2_encoder(self, model) -> bool:
        """Convert encoder component"""
        output_path = self.download_path / ENCODER_NAME
        
        if output_path.exists():
            logger.info(f"Found converted encoder")
            return True
        
        try:
            logger.info(f"Converting encoder...")
            
            encoder = model.get_encoder()
            example_input = {
                "inputs_embeds": torch.zeros([1, 590, model.config.text_config.d_model]),
                "attention_mask": torch.ones([1, 590])
            }
            
            ov_model = ov.convert_model(encoder, example_input=example_input)
            ov_model = self._apply_precision(ov_model)
            ov.save_model(ov_model, output_path)
            
            del ov_model
            self.cleanup_torchscript_cache()
            
            logger.info(f"Encoder conversion finished")
            return True
            
        except Exception as e:
            logger.error(f"Encoder conversion failed: {e}")
            raise RuntimeError(f"Encoder conversion failed: {e}")
    
    def _convert_florence2_decoder(self, model) -> bool:
        """Convert decoder component"""
        output_path = self.download_path / DECODER_NAME
        
        if output_path.exists():
            logger.info(f"Found converted decoder")
            return True
        
        try:
            logger.info(f"Converting decoder...")
            
            # Get the actual decoder from the language_model.model
            decoder = model.language_model.model.decoder
            
            # Create a simple wrapper to just call the decoder
            class DecoderWrapper(torch.nn.Module):
                def __init__(self, decoder_module, config):
                    super().__init__()
                    self.decoder = decoder_module
                    self.config = config
                
                def forward(self, input_ids, encoder_hidden_states, attention_mask=None):
                    outputs = self.decoder(
                        input_ids=input_ids,
                        encoder_hidden_states=encoder_hidden_states,
                        encoder_attention_mask=attention_mask,
                        use_cache=False,
                        return_dict=True
                    )
                    return outputs.last_hidden_state
            
            decoder_wrapper = DecoderWrapper(decoder, model.language_model.model.config)
            decoder_wrapper.eval()
            
            # Create example inputs
            example_input = {
                "input_ids": torch.ones([1, 1], dtype=torch.long),
                "encoder_hidden_states": torch.randn([1, 591, model.language_model.model.config.d_model]),
                "attention_mask": torch.ones([1, 591], dtype=torch.long),
            }
            
            # Convert model
            ov_model = ov.convert_model(decoder_wrapper, example_input=example_input)
            ov_model = self._apply_precision(ov_model)
            ov.save_model(ov_model, output_path)
            
            del ov_model
            del decoder_wrapper
            self.cleanup_torchscript_cache()
            
            logger.info(f"Decoder conversion finished")
            return True
            
        except Exception as e:
            logger.error(f"Decoder conversion failed: {e}")
            raise RuntimeError(f"Decoder conversion failed: {e}")
    
    def convert(self) -> bool:
        """Perform model conversion"""
        try:            
            if self.is_florence2:
                success = self.convert_florence2()
            else:
                success = self.convert_generic_model()
            
            if success:
                logger.info("Conversion completed successfully!")
                logger.info(f"Output directory: {self.download_path}")
                
                # Remove original model checkpoint directory to save space
                if self.orig_model_dir.exists():
                    logger.info(f"Removing original model checkpoint: {self.orig_model_dir}")
                    import shutil
                    try:
                        shutil.rmtree(self.orig_model_dir)
                        logger.info("Checkpoint directory removed successfully")
                    except Exception as e:
                        logger.warning(f"Could not remove checkpoint directory: {e}")
                
            else:
                logger.error(f"Conversion failed! {success}")
            
            return success
            
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise RuntimeError(f"Conversion failed: {e}")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="Unified Model Conversion Script for OpenVINO",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--model-name",
        type=str,
        required=True,
        help="HuggingFace model identifier (e.g., 'microsoft/Florence-2-base-ft')"
    )
    
    parser.add_argument(
        "--download-path",
        type=str,
        default="./models",
        help="Path to download and save converted models (default: ./models)"
    )
    
    parser.add_argument(
        "--precision",
        type=str,
        default="fp32",
        choices=ModelConverter.SUPPORTED_PRECISIONS,
        help=f"Model precision: {', '.join(ModelConverter.SUPPORTED_PRECISIONS)} (default: fp32)"
    )
    
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=ModelConverter.SUPPORTED_DEVICES,
        help=f"Target device: {', '.join(ModelConverter.SUPPORTED_DEVICES)} (default: cpu)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args()


def main():
    """Main conversion workflow"""
    args = parse_arguments()
    
    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        # Initialize converter
        converter = ModelConverter(
            model_name=args.model_name,
            download_path=args.download_path,
            precision=args.precision,
            device=args.device
        )
        
        # Perform conversion
        success = converter.convert()
        
        return 0 if success else 1
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
