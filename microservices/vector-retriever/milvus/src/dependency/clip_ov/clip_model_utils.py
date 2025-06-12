# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import torch
import open_clip
import cn_clip.clip as cn_clip
from cn_clip.clip import load_from_name
import openvino as ov
import openvino.properties.hint as hints
import openvino_tokenizers
from pathlib import Path

# Constants
DEVICE = os.getenv("DEVICE", "CPU")
CN_CLIP_URL = "https://clip-cn-beijing.oss-cn-beijing.aliyuncs.com/checkpoints/clip_cn_vit-h-14.pt"
OPEN_CLIP_MODEL_FILE = "open_clip_pytorch_model.bin"
CN_CLIP_MODEL_FILE = "clip_cn_vit-h-14.pt"

class TextEncoder(torch.nn.Module):
    """Custom text encoder wrapper for OpenVINO conversion."""
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, text):
        return self.model.encode_text(text)

def download_model(model_name: str, model_path: str) -> None:
    """Download the specified model if it does not already exist."""
    command = []
    model_path = os.path.join(model_path, model_name)
    if "CN" not in model_name and "CLIP" in model_name:
        model_file = OPEN_CLIP_MODEL_FILE
        if os.path.exists(os.path.join(model_path, model_file)):
            print(f"Model already exists at {model_path}. Skipping download.")
            return
        command = [
            "huggingface-cli", "download", "laion/CLIP-ViT-H-14-laion2B-s32B-b79K",
            model_file, "--local-dir", model_path
        ]
    elif "CN" in model_name and "CLIP" in model_name:
        model_file = CN_CLIP_MODEL_FILE
        if os.path.exists(os.path.join(model_path, model_file)):
            print(f"Model already exists at {model_path}. Skipping download.")
            return
        command = [
            "wget", "--tries=5", "--timeout=30", "--continue", "--no-check-certificate",
            "-O", os.path.join(model_path, model_file), CN_CLIP_URL
        ]
    else:
        raise ValueError(f"Unsupported model name: {model_name}")
    
    os.makedirs(model_path, exist_ok=True)
    try:
        print(f"Downloading {model_name} to {model_path}")
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(result.stdout)
        print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Command failed with return code {e.returncode}")
        print(f"Error output: {e.stderr}")
        raise

def convert_model(model_name: str, model_path: str) -> tuple[str, str]:
    """Convert the specified model to OpenVINO IR format."""
    if "CN" not in model_name and "CLIP" in model_name:
        model_id = "-".join(model_name.split("-")[1:])  # CLIP-ViT-H-14 to ViT-H-14
        model_path = os.path.join(model_path, model_name)
        image_encoder_path = f"{model_path}/{model_id.lower().replace('-','_')}_visual.xml"
        text_encoder_path = f"{model_path}/{model_id.lower().replace('-','_')}_text.xml"
        if not os.path.exists(model_path):
            print(f"Model path {model_path} does not exist.")
            raise FileNotFoundError(f"Model path {model_path} does not exist.")
        
        model, _, preprocess = open_clip.create_model_and_transforms(model_id, pretrained=f'{model_path}/open_clip_pytorch_model.bin')

        print('Converting image encoder to OpenVINO IR...')
        image_input = {"x": torch.randn(
            1, 3, 224, 224, dtype=torch.float32)}
        openclip_image_encoder = ov.convert_model(
            model.visual, example_input=image_input, input=(1, 3, 224, 224))
        
        ov.save_model(openclip_image_encoder, image_encoder_path)
        # convert text transformer
        print('Converting text encoder to OpenVINO IR...')
        t = TextEncoder(model)
        token_input = {"text": torch.randint(low=0, high=49407, size=(1, 77))}
        # openclip_text_encoder = ov.convert_model(t, example_input=token_input, input=(10,77))
        openclip_text_encoder = ov.convert_model(
            t, example_input=token_input, input=(1, 77))
        
        ov.save_model(openclip_text_encoder, text_encoder_path)
        print(f'All done. Please check {model_path} to find IRs')

    elif "CN" in model_name and "CLIP" in model_name:
        model_id = "-".join(model_name.split("-")[2:])  # CN-CLIP-ViT-H-14 to ViT-H-14
        model_path = os.path.join(model_path, model_name)
        image_encoder_path = f"{model_path}/{model_id.lower().replace('-','_')}_visual.xml"
        text_encoder_path = f"{model_path}/{model_id.lower().replace('-','_')}_text.xml"
        if not os.path.exists(model_path):
            print(f"Model path {model_path} does not exist.")
            raise FileNotFoundError(f"Model path {model_path} does not exist.")
        
        model, preprocess = load_from_name(model_id, device="cpu", download_root=model_path)
        
        text_model = TextEncoder(model)

        token_input = cn_clip.tokenize([""], context_length=52).int()

        clip_text_encoder = ov.convert_model(
            text_model, example_input=token_input, input=(1, 77))
        
        ov.save_model(clip_text_encoder,
                      f"{model_path}/{model_id.lower().replace('-','_')}_text.xml")
        
        image_input = {"x": torch.randn(
            1, 3, 224, 224, dtype=torch.float32)}
        clip_image_encoder = ov.convert_model(
            model.visual, example_input=image_input, input=(1, 3, 224, 224))
        ov.save_model(clip_image_encoder,
                      f"{model_path}/{model_id.lower().replace('-','_')}_visual.xml")
    else:
        print(f"Unsupported model name: {model_name}")
        raise ValueError(f"Unsupported model name: {model_name}")
    
    return image_encoder_path, text_encoder_path

def load_model(model_path: str, device: str = 'CPU', throughputmode: bool = False):
    """Load an OpenVINO model."""
    if not model_path or not Path(model_path).exists():
        return None
    core = ov.Core()
    if throughputmode:
        core.set_property(device, {hints.performance_mode: hints.PerformanceMode.THROUGHPUT})
    model = core.read_model(model_path)
    return core.compile_model(model, device.upper())

def load_bert_tokenizer(tokenizer_path: str = None):
    """Load a BERT tokenizer model."""
    if tokenizer_path and Path(tokenizer_path).exists():
        tokenizer = ov.compile_model(tokenizer_path, device_name='CPU')
        return lambda text: tokenizer([text])
    return None