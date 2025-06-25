# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Dict, List

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as T
from torch import Tensor
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, model_validator
from transformers import (
    AutoModel,
    AutoProcessor,
    AutoTokenizer,
)

from src.common import logger

toPIL = T.ToPILImage()

class QwenEmbeddings(BaseModel, Embeddings):
    """Embedding API to embed documents and query for Qwen model."""

    model: Any

    @model_validator(mode="before")
    @classmethod
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that open_clip and torch libraries are installed."""
        try:
            # Use the provided model if present
            if "model" not in values:
                raise ValueError("Model must be provided during initialization.")

        except ImportError:
            raise ImportError("Please ensure CLIP model is loaded")
        return values

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        text_features = self.model.get_text_embeddings(texts)
        return text_features.detach().numpy().tolist()

    def embed_query(self, text: str) -> List[float]:
        logger.debug(f"Embedding query: {text}")
        task = "Given a search query, retrieve most relevant passages from video summary that answers the query"
        instruct_query = self.model.get_detailed_instruct(task, text)
        result: List[List[float]] = self.embed_documents([instruct_query])

        return result



class Qwen3Model(nn.Module):
    # Qwen3 600M Params embedding model
    def __init__(self, cfg):
        logger.info("Initializing Qwen3 embedding model . . .")
        super().__init__()

        self.model_name = cfg.get("qwen_model_name", "Qwen/Qwen3-Embedding-0.6B")
        self.max_length = cfg.get("qwen_sequence_length", 8192)

        self.model = AutoModel.from_pretrained(self.model_name)
        self.processor = AutoProcessor.from_pretrained(self.model_name, use_fast=True)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, padding_side="left")

    def _last_token_pool(self, last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[
                torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths
            ]

    def get_detailed_instruct(self, task_description: str, query: str) -> str:
        return f"Instruct: {task_description}\nQuery:{query}"

    def get_text_embeddings(self, texts: list[str]) -> Tensor:
        """
        Input is a list of texts.
        Process texts with the configured max sequence length.
        """
        logger.debug(f"Generating text embeddings for: {texts}")
        text_inputs = self.tokenizer(
            texts,
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )

        text_inputs.to(self.model.device)
        output = self.model(**text_inputs)

        logger.debug(f"Input text shape: {text_inputs['input_ids'].shape}")

        embeddings = self._last_token_pool(output.last_hidden_state, text_inputs["attention_mask"])
        logger.debug(f"Embeddings shape: {embeddings.shape}")

        embeddings = F.normalize(embeddings, p=2, dim=1)
        logger.debug(f"Normalized embeddings: {embeddings}")

        return embeddings

