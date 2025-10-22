# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as T
from einops import rearrange
from torch import Tensor
from transformers import AutoModel, AutoProcessor, AutoTokenizer

from src.common import logger

toPIL = T.ToPILImage()


class Qwen3(nn.Module):
    # Qwen3 600M Params embedding model
    def __init__(self, cfg):
        logger.info("Initializing Qwen3 embedding model . . .")
        super().__init__()

        self.model_name = cfg.get("qwen_model_name", "Qwen/Qwen3-Embedding-0.6B")
        self.max_length = cfg.get("qwen_sequence_length", 8192)
        self._dimensions = cfg.get("qwen_vector_dimensions", 1024)

        self.model = AutoModel.from_pretrained(self.model_name)

        logger.debug(f"Model: {self.model}")
        self.processor = AutoProcessor.from_pretrained(self.model_name, use_fast=True)
        logger.debug(f"Processor: {self.processor}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, padding_side="left")

    def get_embedding_dimensions(self) -> int:
        """Returns the dimensions of the embeddings."""
        return self._dimensions

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
        input_tokens = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )

        input_tokens.to(self.model.device)
        with torch.no_grad():
            output = self.model(**input_tokens)
            logger.debug(f"Output: {output}")
            logger.debug(f"Input text shape: {input_tokens['input_ids'].shape}")
            logger.debug(f"Output shape: {output.last_hidden_state.shape}")

            embeddings = self._last_token_pool(
                output.last_hidden_state, input_tokens["attention_mask"]
            )
            logger.debug(f"Embeddings shape: {embeddings.shape}")
            logger.debug(f"Embeddings: {embeddings}")

            embeddings = F.normalize(embeddings, p=2, dim=1)
            logger.debug(f"Normalized embeddings: {embeddings}")

        return embeddings


class vCLIP(nn.Module):
    def __init__(self, cfg, multi_modal: bool = True):
        logger.info("Initializing vclip model . . .")
        super().__init__()

        self.model_name = cfg.get("vclip_model_name", "openai/clip-vit-base-patch32")
        self.num_frm = cfg.get("vclip_num_frame", 64)
        self.max_length = cfg.get("clip_sequence_length", 77)
        self._dimensions = cfg.get("clip_vector_dimensions", 512)

        self.clip = AutoModel.from_pretrained(self.model_name)
        self.processor = AutoProcessor.from_pretrained(self.model_name, use_fast=True)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

    def get_embedding_dimensions(self) -> int:
        """Returns the dimensions of the embeddings."""
        return self._dimensions

    def get_text_embeddings(self, texts):
        """
        Input is list of texts.
        Process texts with the configured max sequence length.
        """
        input_tokens = self.tokenizer(
            texts,
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        text_features = self.clip.get_text_features(**input_tokens)
        text_features = F.normalize(text_features, p=2, dim=1)
        return text_features

    def get_image_embeddings(self, images):
        """Input is list of images."""

        image_inputs = self.processor(images=images, return_tensors="pt")
        image_features = self.clip.get_image_features(**image_inputs)
        return image_features

    def get_video_embeddings(self, frames_batch):
        """Input is list of list of frames in video."""
        self.batch_size = len(frames_batch)
        vid_embs = []
        for frames in frames_batch:
            frame_embeddings = self.get_image_embeddings(frames)
            frame_embeddings = rearrange(frame_embeddings, "(b n) d -> b n d", b=len(frames_batch))
            # Normalize, mean aggregate and return normalized video_embeddings
            frame_embeddings = frame_embeddings / frame_embeddings.norm(dim=-1, keepdim=True)
            video_embeddings = frame_embeddings.mean(dim=1)
            video_embeddings = video_embeddings / video_embeddings.norm(dim=-1, keepdim=True)
            vid_embs.append(video_embeddings)
        return torch.cat(vid_embs, dim=0)
