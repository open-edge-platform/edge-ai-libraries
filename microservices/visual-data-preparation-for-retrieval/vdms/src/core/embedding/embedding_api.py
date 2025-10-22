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


class vCLIPEmbeddings(BaseModel, Embeddings):
    """Embedding API to embed documents, video and query for vCLIP model."""

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
            raise ImportError("Please ensure Qwen model is loaded")
        return values

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # model_device = next(self.model.clip.parameters()).device
        text_features = self.model.get_text_embeddings(texts)

        return text_features.detach().numpy()

    def embed_query(self, text: str) -> List[float]:
        embedding: List[float] = []
        result: List[List[float]] = self.embed_documents([text])

        if len(result) != 0:
            embedding = result[0]

        return embedding

    def embed_video(self, paths: List[str], **kwargs: Any) -> List[List[float]]:
        # Open images directly as PIL images

        video_features = []
        try:
            for vid_path in sorted(paths):
                # Encode the video to get the embeddings
                model_device = next(self.model.parameters()).device
                # Preprocess the video for the model
                clip_images = self.load_video_for_vclip(
                    vid_path,
                    num_frm=self.model.num_frm,
                    start_time=kwargs.get("start_time", None),
                    clip_duration=kwargs.get("clip_duration", None),
                )
                embeddings_tensor = self.model.get_video_embeddings([clip_images])

                # Convert tensor to list and add to the video_features list
                embeddings_list = embeddings_tensor.tolist()

                video_features.append(embeddings_list)

        except Exception as ex:
            logger.error(ex)
            raise ex

        return video_features

    def load_video_for_vclip(self, vid_path, num_frm=4, **kwargs):
        # Load video with VideoReader
        import decord

        decord.bridge.set_bridge("torch")
        vr = VideoReader(vid_path, ctx=cpu(0))
        fps = vr.get_avg_fps()
        num_frames = len(vr)
        start_idx = int(fps * kwargs.get("start_time", [0])[0])
        end_idx = start_idx + int(fps * kwargs.get("clip_duration", [num_frames])[0])

        frame_idx = np.linspace(
            start_idx, end_idx, num=num_frm, endpoint=False, dtype=int
        )  # Uniform sampling
        clip_images = []

        # read images
        temp_frms = vr.get_batch(frame_idx.astype(int).tolist())
        for idx in range(temp_frms.shape[0]):
            im = temp_frms[idx]  # H W C
            clip_images.append(toPIL(im.permute(2, 0, 1)))

        return clip_images
