# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import asyncio
from typing import List, Dict, Any, Optional
from openai import OpenAI, AsyncOpenAI

from video_analyzer.core.settings import settings
from video_analyzer.utils.logger import logger


class LLM:
    """
    Language model for text processing with concurrent processing support.
    
    This class provides an interface to interact with OpenAI API-compatible
    language models, supporting concurrent requests and configurable parameters.
    
    Args:
        model_name: Name of the language model to use
        api_key: API key for authentication (optional if set in environment)
        base_url: Base URL for the API endpoint (optional for OpenAI-compatible APIs)
        remove_thinking: Whether to remove thinking patterns from responses (optional)
    """
    
    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        remove_thinking: Optional[bool] = False,
    ):
        self.model_name = model_name

        # Use default values from config if parameters are None
        self.api_key = api_key
        self.base_url = base_url
        self.remove_thinking = remove_thinking
        logger.debug(f"Remove thinking: {'Enabled' if self.remove_thinking else 'Disabled'}")

        # Concurrency settings
        self.timeout = settings.REQUEST_TIMEOUT
        self.max_retries = settings.MAX_RETRIES
        self.temperature = settings.DEFAULT_TEMPERATURE
        
        # Use remote inference
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        
        logger.debug(f"Using remote inference serving with model: {model_name} from endpoint: {self.base_url}")
    
    def infer(self, prompt: str) -> str:
        """
        Run inference on a text prompt, in sync mode

        Args:
            prompt: Text prompt to process

        Returns:
            Model's response
        """
        
        # Construct messages for the API
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
        
        response = self._remote_infer(msgs)
        
        if self.remove_thinking:
            response = self.remove_think_in_response(response)
            
        return response
    
    async def async_infer(self, prompt: str) -> str:
        """
        Run inference on a text prompt, in async mode

        Args:
            prompt: Text prompt to process

        Returns:
            Model's response
        """
        
        # Construct messages for the API
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
        
        response = await self._async_remote_infer(msgs)
        
        if self.remove_thinking:
            response = self.remove_think_in_response(response)
            
        return response
    
    def _remote_infer(self, messages: List[Dict[str, Any]]) -> str:
        """
        Run remote inference using OpenAI API.

        Args:
            messages: messages with user's prompts to process

        Returns:
            Model's response
        """
        retry_count = 0

        while retry_count < self.max_retries:
            try:
                logger.debug(f"Sending request to remote LLM: {self.model_name} (attempt {retry_count+1}/{self.max_retries})")
                logger.debug(f"API base URL: {self.base_url}")

                # Call the API
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=self.temperature,
                    timeout=self.timeout,
                )

                content = response.choices[0].message.content.strip()
                logger.debug(f"Successfully received response from remote LLM")
                return content

            except Exception as e:
                logger.error(f"ERROR in API call(URL: {self.base_url}) (attempt {retry_count+1}): {str(e)}")
                retry_count += 1
                if retry_count >= self.max_retries:
                    error_msg = f"Error: API call(URL: {self.base_url}) failed after {self.max_retries} attempts. Last error: {str(e)}"
                    logger.error(error_msg)
                    return error_msg
                
    async def _async_remote_infer(self, messages: List[Dict[str, Any]]) -> str:
        """
        Run remote inference asynchronously using OpenAI API.

        Args:
            messages: messages with user's prompts to process

        Returns:
            Model's response
        """
        retry_count = 0

        while retry_count < self.max_retries:
            try:
                logger.debug(f"Sending async request to remote LLM: {self.model_name} (attempt {retry_count+1}/{self.max_retries})")

                # Call the API
                response = await self.async_client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=self.temperature,
                    timeout=self.timeout,
                )

                content = response.choices[0].message.content.strip()
                logger.debug(f"Successfully received async response from remote LLM")
                return content

            except Exception as e:
                logger.error(f"ERROR in async API call (attempt {retry_count+1}): {str(e)}")
                retry_count += 1
                if retry_count >= self.max_retries:
                    error_msg = f"Error: API call failed after {self.max_retries} attempts. Last error: {str(e)}"
                    logger.error(error_msg)
                    return error_msg
                # Wait before retrying
                await asyncio.sleep(1)

    @staticmethod
    def remove_think_in_response(response: str) -> str:
        index = response.rfind("</think>")
        if index > 0:
            response = response[index:]
            response = response.replace("</think>\n\n", "").replace("</think>", "")
        return response