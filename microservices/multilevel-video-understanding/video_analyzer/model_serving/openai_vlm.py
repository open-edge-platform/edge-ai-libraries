# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import base64
import logging
from PIL import Image
from typing import List, Dict, Any
from video_analyzer.utils.logger import logger
from video_analyzer.core.settings import settings

from video_analyzer.model_serving.openai_llm import LLM


class VLM(LLM):
    """
    Vision and language model for multimodal processing with concurrent processing support.
    
    This class provides an interface to interact with OpenAI API-compatible
    models, supporting concurrent requests and configurable parameters.
    
    Args:
        model_name: Name of the language model to use
        api_key: API key for authentication (optional if set in environment)
        base_url: Base URL for the API endpoint (optional for OpenAI-compatible APIs)
        remove_thinking: Whether to remove thinking patterns from responses (optional)
    """
    
    def __init__(
        self,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        # Determine if we're using Kimi or Qwen based on model name
        self.is_kimi = "kimi" in self.model_name.lower()
    
    def infer(self, frames: List[Image.Image], question: str) -> str:
        """
        Run inference on a list of frames with a question, in sync mode

        Args:
            frames: List of PIL Image frames
            question: Text prompt/question to ask about the frames

        Returns:
            Model's response
        """
        if not frames:
            return "Error: Empty frame input"

        # Prepare messages based on model type
        if self.is_kimi:
            msgs = self._prepare_kimi_format(frames, question)
            logger.debug("Using Kimi format for API request")
        else:
            msgs = self._prepare_qwen_format(frames, question)
            logger.debug("Using Qwen format for API request")

        logger.debug(f"Sending request with {len(frames)} frames to model: {self.model_name}")
        logger.debug(f"API base URL: {self.client.base_url}")

        response = self._remote_infer(msgs)
        
        if self.remove_thinking:
            response = self.remove_think_in_response(response)
            
        return response
    
    async def async_infer(self, frames: List[Image.Image], question: str) -> str:
        """
        Run inference on a list of frames with a question, in async mode

        Args:
            frames: List of PIL Image frames
            question: Text prompt/question to ask about the frames

        Returns:
            Model's response
        """
        if not frames:
            return "Error: Empty frame input"

        # Prepare messages based on model type
        if self.is_kimi:
            msgs = self._prepare_kimi_format(frames, question)
            logger.debug("Using Kimi format for API request")
        else:
            msgs = self._prepare_qwen_format(frames, question)
            logger.debug("Using Qwen format for API request")

        logger.debug(f"Sending request with {len(frames)} frames to model: {self.model_name}")

        response = await self._async_remote_infer(msgs)
        
        if self.remove_thinking:
            response = self.remove_think_in_response(response)
        return response

    def _prepare_qwen_format(self, frames: List[Image.Image], question: str) -> List[Dict[str, Any]]:
        """
        Prepare message in Qwen format.

        Args:
            frames: List of PIL Image frames
            question: Text prompt/question to ask about the frames

        Returns:
            List of messages in Qwen format
        """
        # Convert frames to base64 encoded JPEG images
        media_content = []
        for frame in frames:
            buffer = io.BytesIO()
            frame.save(buffer, format="JPEG", quality=settings.JPEG_QUALITY)
            media_content.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))

        # Construct request messages for Qwen format
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "video_url", "video_url": {"url": f"data:video/jpeg;base64,{','.join(media_content)}"}},
                ]
            }
        ]

    def _prepare_kimi_format(self, frames: List[Image.Image], question: str) -> List[Dict[str, Any]]:
        """
        Prepare message in Kimi format.

        Args:
            frames: List of PIL Image frames
            question: Text prompt/question to ask about the frames

        Returns:
            List of messages in Kimi format
        """
        # Convert frames to base64 encoded JPEG images
        image_urls = []
        for frame in frames:
            buffer = io.BytesIO()
            frame.save(buffer, format="JPEG", quality=settings.JPEG_QUALITY)
            base64_encoded_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
            image_urls.append(f"data:image/jpeg;base64,{base64_encoded_image}")

        # Construct request messages for Kimi format
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    *[
                        {"type": "image_url", "image_url": {"url": url}}
                        for url in image_urls
                    ]
                ],
            }
        ]
