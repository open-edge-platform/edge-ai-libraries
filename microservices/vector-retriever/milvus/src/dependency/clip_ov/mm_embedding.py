
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import io
import shutil
import logging
from pathlib import Path
from PIL import Image

from .clip_model_utils import download_model, convert_model, load_model
from .tokenizer import tokenize
from .bert_tokenizer import tokenize_bert
from .utils import preprocess_image



logger = logging.getLogger("mm_embedding")
console_handler = logging.StreamHandler()
logger.addHandler(console_handler)


DEVICE = os.getenv("DEVICE", "CPU")
LOCAL_EMBED_MODEL_ID = os.getenv("LOCAL_EMBED_MODEL_ID", "CLIP-ViT-H-14")
MODEL_DIR = "/home/user/models"

class EmbeddingModel:
    def __init__(self):
        self.model_id = LOCAL_EMBED_MODEL_ID
        self.model_path = MODEL_DIR
        self.device = DEVICE
        self.text_model = None
        self.image_model = None
        self.text_ireq = None
        self.image_ireq = None
        self.load_model()
        self.tokenizer = self.get_tokenizer()

    def get_tokenizer(self):
        if 'CLIP' in self.model_id:
            if "CN" in self.model_id:
                logger.debug("Using Chinese-CLIP tokenizer")
                return tokenize_bert
            else:
                return tokenize
        else:
            raise NotImplementedError(f"Tokenizer for model {self.model_id} not implemented")

    def load_model(self):
        # default model paths
        model_name = "-".join(self.model_id.split("-")[1:]) 
        image_encoder_path = f"{self.model_path}/{self.model_id}/{model_name.lower().replace('-','_')}_visual.xml"
        text_encoder_path = f"{self.model_path}/{self.model_id}/{model_name.lower().replace('-','_')}_text.xml"
        if not os.path.exists(image_encoder_path):
            download_model(self.model_id, self.model_path)
            image_encoder_path, text_encoder_path = convert_model(self.model_id, self.model_path)
        else:
            print(f"Model already exists at {self.model_path}. Skipping download.")

        self.image_model = load_model(image_encoder_path, self.device)
        self.text_model = load_model(text_encoder_path, self.device)

        self.image_ireq = self.image_model.create_infer_request()
        self.text_ireq = self.text_model.create_infer_request()

    def get_image_embedding(self, image):
        embedding = self.image_ireq.infer({'x': image[None]}).to_tuple()[0]
        return embedding
    
    def get_text_embedding(self, text):
        tokens = self.tokenizer(text)
        embedding = self.text_ireq.infer(tokens).to_tuple()[0]
        return embedding
    
    def get_model_id(self):
        return self.model_id
    
    def get_model_path(self):
        return self.model_path
    
    def get_embedding_dim(self):
        return self.image_model.outputs[0].shape[1]
