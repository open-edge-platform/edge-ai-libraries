# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import re
import base64
from PIL import Image
from typing import List, Dict, Any, Tuple
from video_analyzer.utils.logger import logger
from video_analyzer.utils.summarization_utils import redact_base64
from video_analyzer.core.settings import settings

from video_analyzer.model_serving.openai_llm import LLM
import math


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
        individual_frames_in_prompt: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.video_format = settings.VLM_VIDEO_FORMAT

        # Determine if we're using Kimi or Qwen based on model name
        self.individual_frames_in_prompt = "kimi" in self.model_name.lower() or individual_frames_in_prompt

        # Qwen2-VL image token calculation parameters
        self.spatial_patch_size = 14  # Qwen2-VL uses 14x14 patches
        self.temporal_patch_size = 2  # Video temporal merge size
    
    def infer(self, frames: List[Image.Image], content: str|List[Dict[str, Any]]) -> str:
        """
        Run inference on a list of frames with a content, in sync mode

        Args:
            frames: List of PIL Image frames
            content: 
                Option1. Text prompt to process
                Option2. List of contents with user's prompts to process

        Returns:
            Model's response
        """
        if not frames:
            return "Error: Empty frame input"

        # An explicit video format takes priority over model-name heuristics.
        if self.video_format == "ovms":
            msgs = self._prepare_ovms_format(frames, content)
            logger.debug("Using OVMS video frame array format for API request")
        elif self.individual_frames_in_prompt:
            msgs = self._prepare_individual_frames_format(frames, content)
            logger.debug("Using individual frames format for API request")
        else:
            msgs = self._prepare_qwen_format(frames, content)
            logger.debug("Using Qwen format for API request")

        logger.debug("Sending multimodal request to model")
        logger.debug("Sending multimodal request")
        logger.debug("Using configured multimodal API endpoint")

        # Calculate and accumulate image tokens
        image_tokens = self._calculate_image_tokens(frames)
        self.total_image_tokens += image_tokens

        response = self._remote_infer(msgs)

        if self.remove_thinking:
            response = self.remove_think_in_response(response)

        return response
    
    async def async_infer(self, frames: List[Image.Image], content: str|List[Dict[str, Any]]) -> str:
        """
        Run inference on a list of frames with a content, in async mode

        Args:
            frames: List of PIL Image frames
            content: 
                Option1. Text prompt to process
                Option2. List of contents with user's prompts to process

        Returns:
            Model's response
        """
        if not frames:
            return "Error: Empty frame input"

        # An explicit video format takes priority over model-name heuristics.
        if self.video_format == "ovms":
            msgs = self._prepare_ovms_format(frames, content)
            logger.debug("Using OVMS video frame array format for API request")
        elif self.individual_frames_in_prompt:
            msgs = self._prepare_individual_frames_format(frames, content)
            logger.debug("Using individual frames format for API request")
        else:
            msgs = self._prepare_qwen_format(frames, content)
            logger.debug("Using Qwen format for API request")

        logger.debug("Sending multimodal request to model")
        logger.debug("Sending multimodal request")
        logger.debug("Using configured multimodal API endpoint")

        # Calculate and accumulate image tokens
        image_tokens = self._calculate_image_tokens(frames)
        self.total_image_tokens += image_tokens

        response = await self._async_remote_infer(msgs)

        if self.remove_thinking:
            response = self.remove_think_in_response(response)
        return response

    @staticmethod
    def parse_multimodal_prompt(prompt: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Split a unified prompt into interleaved text and media parts, supporting only
        base64-embedded data URLs for images and videos.

        Supported media tokens (case-insensitive):
        - data:image/jpeg;base64,
        - data:video/jpeg;base64,

        Everything outside these tokens is treated as text. If the prompt contains
        external references (file://, http://, https://), this method raises an error
        because non-base64 media is not supported here.

        Args:
            prompt: The unified prompt string, can be multimodal(interleaved image-text or video-text) or pure text

        Returns:
            (content, is_multimodal)
            - content: A list of content parts like
              [{"type":"text","text":"..."}, {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}, ...]
            - is_multimodal: True if any image/video tokens were found; False for pure text
        """
        # Reject external references for now
        if re.search(r"\b(?:file|https?)://", prompt, re.IGNORECASE):
            raise NotImplementedError("Unsupported external references: file|http|https, "
                                      "only base64 data URLs are supported (data:image/jpeg;base64, data:video/jpeg;base64)")

        content: List[Dict[str, Any]] = []
        is_multimodal = False

        # Match only the explicitly supported base64 media tokens
        pattern = re.compile(
            r"(?P<url>data:(?:image|video)/jpeg;base64,[^\s\n]+)",
            re.IGNORECASE,
        )

        pos = 0
        for m in pattern.finditer(prompt):
            before = prompt[pos:m.start()]
            url = m.group('url')

            # Emit preceding text (trimmed) if any
            text_chunk = before.strip()
            if text_chunk:
                content.append({"type": "text", "text": text_chunk})

            # Emit media by type
            if url.lower().startswith("data:image/jpeg;base64,"):
                content.append({"type": "image_url", "image_url": {"url": url}})
            elif url.lower().startswith("data:video/jpeg;base64,"):
                content.append({"type": "video_url", "video_url": {"url": url}})
            is_multimodal = True

            pos = m.end()

        # Trailing text
        tail = prompt[pos:].strip()
        if tail:
            content.append({"type": "text", "text": tail})

        # If no media found, treat entire prompt as plain text and return is_multimodal=False
        if not is_multimodal:
            return ([{"type": "text", "text": prompt}], False)

        return (content, True)

    def _prepare_qwen_format(self, frames: List[Image.Image], content: str|List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare message in Qwen format.

        Args:
            frames: List of PIL Image frames
            content: 
                Option1. Text prompt to process
                Option2. List of contents with user's prompts to process

        Returns:
            List of messages in Qwen format
        """
        # Convert frames to base64 encoded JPEG images
        frames_b64 = []
        for frame in frames:
            buffer = io.BytesIO()
            frame.save(buffer, format="JPEG", quality=settings.JPEG_QUALITY)
            frames_b64.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))
        
        media_content = [{"type": "video_url", "video_url": {"url": f"data:video/jpeg;base64,{','.join(frames_b64)}"}}]

        # Construct request messages for Qwen format
        if isinstance(content, str):
            content, is_multimodal = self.parse_multimodal_prompt(content)
            logger.debug(f"Unified prompt parsed as multimodal: {is_multimodal}")
        content.extend(media_content)
        
        # Message
        return [{"role": "user", "content": content}]

    def _prepare_ovms_format(self, frames: List[Image.Image], content: str|List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Encode each video as an ordered array of JPEG data URIs for OVMS.

        Args:
            frames: Between 1 and 1024 equally sized frames with equal channel counts.
            content: Text or content parts; embedded JPEG video sequences are adapted too.

        Returns:
            User message with array-valued video URLs and unchanged image/text parts.

        Raises:
            ValueError: Frame dimensions, frame count, or video encoding is invalid.
        """
        if not 1 <= len(frames) <= 1024:
            raise ValueError("OVMS video input requires between 1 and 1024 frames")
        first_frame = frames[0]
        if any(
            frame.size != first_frame.size
            or len(frame.getbands()) != len(first_frame.getbands())
            for frame in frames
        ):
            raise ValueError("OVMS video frames must have equal dimensions and channel counts")

        # Copy the list because the shared builder appends the extracted video.
        prompt = content if isinstance(content, str) else list(content)
        messages = self._prepare_qwen_format(frames, prompt)
        parts = messages[0]["content"]
        for index, part in enumerate(parts):
            if part.get("type") != "video_url":
                continue
            video = part["video_url"]
            url = video["url"]
            if isinstance(url, str) and url.lower().startswith("data:video/jpeg;base64,"):
                encoded_frames = url.split(",", 1)[1].split(",")
                frame_urls = [f"data:image/jpeg;base64,{frame}" for frame in encoded_frames]
            elif isinstance(url, list):
                frame_urls = list(url)
            else:
                raise ValueError("OVMS video input requires a JPEG sequence or JPEG frame array")

            if not 1 <= len(frame_urls) <= 1024:
                raise ValueError("OVMS video input requires between 1 and 1024 frames")
            prefix = "data:image/jpeg;base64,"
            if any(
                not isinstance(frame, str)
                or not frame.lower().startswith(prefix)
                or not frame[len(prefix):]
                for frame in frame_urls
            ):
                raise ValueError("OVMS video frames must be nonempty JPEG data URIs")
            parts[index] = {**part, "video_url": {**video, "url": frame_urls}}
        return messages

    def _prepare_individual_frames_format(self, frames: List[Image.Image], content: str|List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare message in individual frames format.

        Args:
            frames: List of PIL Image frames
            content: 
                Option1. Text prompt to process
                Option2. List of contents with user's prompts to process

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
        
        media_content = [
                {"type": "image_url", "image_url": {"url": url}} for url in image_urls
            ]

        # Construct request messages for Kimi format
        if isinstance(content, str):
            content, is_multimodal = self.parse_multimodal_prompt(content)
            logger.debug(f"Unified prompt parsed as multimodal: {is_multimodal}")
        content.extend(media_content)
            
        # Message
        return [{"role": "user", "content": content}]

    def _calculate_image_tokens(self, frames: List[Image.Image]) -> int:
        """
        Calculate image tokens for Qwen2-VL based on frame count and dimensions.

        Qwen2-VL token calculation:
        - Spatial: Each frame is divided into patches (patch_size=14)
        - Temporal: Video frames are merged (merge_size=2)
        - Formula: ceil(num_frames / temporal_patch_size) * ceil(H / spatial_patch_size) * ceil(W / spatial_patch_size)

        Args:
            frames: List of PIL Image frames

        Returns:
            Number of image tokens
        """
        if not frames:
            return 0

        num_frames = len(frames)

        # Get dimensions from first frame (assuming all frames have same size)
        width, height = frames[0].size

        # Calculate spatial tokens per frame
        spatial_tokens_per_frame = math.ceil(height / self.spatial_patch_size) * math.ceil(width / self.spatial_patch_size)

        # Calculate temporal merged frame count
        temporal_merged_frames = math.ceil(num_frames / self.temporal_patch_size)

        # Total image tokens
        image_tokens = temporal_merged_frames * spatial_tokens_per_frame

        logger.debug(f"Image token calculation: {num_frames} frames ({width}x{height}), "
                    f"spatial_tokens={spatial_tokens_per_frame}/frame, "
                    f"temporal_merged={temporal_merged_frames}, "
                    f"total_image_tokens={image_tokens}")

        return image_tokens
