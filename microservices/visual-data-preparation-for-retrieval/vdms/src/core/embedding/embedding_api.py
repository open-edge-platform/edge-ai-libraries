# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, List

import numpy as np
import torchvision.transforms as T
from decord import VideoReader, cpu
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, model_validator

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
        return text_features.detach().numpy()

    def embed_query(self, text: str) -> List[float]:
        logger.debug(f"Embedding query: {text}")
        task = "Given a search query, retrieve relevant passages from video summary that answers the query"
        instruct_query = self.model.get_detailed_instruct(task, text)
        result: List[List[float]] = self.embed_documents([instruct_query])

        return result


