# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import math
import logging
import asyncio
import threading
import traceback
import uuid
from typing import Dict, List, Tuple, Optional
from PIL import Image

from video_chunking import PeltChunking, UniformChunking
from video_chunking.data import ChunkMeta, MicroChunkMeta, MacroChunkMeta

from video_analyzer.core.settings import settings
from video_analyzer.core.prompts import (
    GLOBAL_PROMPT, 
    GLOBAL_PROMPT_WITH_QUESTION,
    MACRO_CHUNK_PROMPT,
    MACRO_CHUNK_PROMPT_WITH_QUESTION,
    LOCAL_PROMPT, 
    T_MINUS_1_PROMPT
)
from video_analyzer.schemas.summarization import SUMMARIZATION_METHOD_TYPE
from video_analyzer.model_serving import LLM, VLM
from video_analyzer.utils.summarization_utils import remove_brackets, uniform_sample, warn_unused_kwargs
from video_analyzer.utils.logger import logger
from video_analyzer.utils.file_utils import robust_video_reader


class VideoSummarizer:
    """
    Video summarization pipeline that processes videos in a multi-level manner.
    """
    @warn_unused_kwargs
    def __init__(
        self,
        video_path: str,
        vlm_model_name: str,
        llm_model_name: str,
        vlm_base_url: str,
        llm_base_url: str,
        vlm_api_key: Optional[str] = "Empty",
        llm_api_key: Optional[str] = "Empty",
        user_prompt: Optional[str] = None,
        method: Optional[str] = settings.DEFAULT_SUMMARIZATION_METHOD,
        levels: Optional[int] = settings.DEFAULT_LEVELS,
        level_sizes: Optional[list[int]] = settings.DEFAULT_LEVEL_SIZES,
        chunking_method: Optional[str] = settings.DEFAULT_VIDEO_CHUNKING_METHOD,
        process_fps: Optional[float] = settings.DEFAULT_PROCESS_FPS,
        **kwargs,
    ):
        """
        Initialize the video summarizer.

        Args:
            video_path: Path to the video file
            vlm_model_name: Model name for vision-language model
            llm_model_name: Model name for language model
            vlm_base_url: Base URL for remote vision-language model inference
            llm_base_url: Base URL for remote language model
            vlm_api_key: API key for remote vision-language model inference
            llm_api_key: API key for remote language model
            user_prompt: User prompt to guide summarization details
            method: Summarization method, choices: [SIMPLE, USE_VLM_T-1, USE_LLM_T-1, USE_ALL_T-1]
            levels: total levels for hierarchical summarization
            level_sizes: chunk group size for each level
            chunking_method: video chunking algorithm, choices: [pelt, uniform]
            process_fps: Extract frames at process_fps for input video
        """
        self.video_path = video_path
        self.user_prompt = user_prompt

        # Multi-level configurations
        self.total_levels = levels
        self.level_sizes = level_sizes
        if not len(self.level_sizes) == self.total_levels:
            raise AttributeError(f"The configured level sizes ({self.level_sizes}) "
                                 f"should match with total levels: {self.total_levels}")
        
        # Parse processor_kwargs from user's request
        self.chunking_method = chunking_method
        self.process_fps = process_fps

        # Summarization method
        self.method = method
        self.use_t_minus_1_for_vlm = ((self.method == SUMMARIZATION_METHOD_TYPE.USE_ALL_T_1.value) or \
                                      (self.method == SUMMARIZATION_METHOD_TYPE.USE_VLM_T_1.value))
        self.use_t_minus_1_for_llm = ((self.method == SUMMARIZATION_METHOD_TYPE.USE_ALL_T_1.value) or \
                                      (self.method == SUMMARIZATION_METHOD_TYPE.USE_LLM_T_1.value))
        
        # Create a semaphore to limit concurrent requests
        ## use_concurrent: Whether to use concurrent processing for remote requests
        ## max_concurrent: Maximum number of concurrent requests (default: from config)
        self.max_concurrent = settings.MAX_CONCURRENT_REQUESTS
        self.use_concurrent = (self.max_concurrent > 1)
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

        # Thread lock for video reader access to prevent concurrent access issues
        self.vr_lock = threading.RLock()

        # Initialize video reader with lock to prevent concurrent access issues
        with self.vr_lock:
            self.vr = robust_video_reader(self.video_path)
            self.origin_fps = round(self.vr.get_avg_fps())
            self.numFrame = len(self.vr)
            self.length = self.numFrame / self.origin_fps
            
        self.chunk_dict: Dict[Tuple[int, int], ChunkMeta] = {}
        self.chunklist_dict: Dict[int, List[ChunkMeta]] = {}
        
        # Configure module log levels
        # TODO: not effective
        logging.getLogger("video_chunking.pelt_chunk").setLevel(logger.level)
        logging.getLogger("video_chunking.uniform_chunk").setLevel(logger.level)
        
        # Log key parameters
        logger.info(f"Video path: {self.video_path}")
        logger.debug(f"Video frames: {self.numFrame}")
        logger.debug(f"Video length: {self.length} seconds")
        logger.debug(f"Video fps: {self.origin_fps}, will extract frames for summary at FPS: {self.process_fps}")
        logger.debug(f"Vision-language model: {vlm_model_name}, base URL: {vlm_base_url}")
        logger.debug(f"Language model: {llm_model_name}, base URL: {llm_base_url}")
        logger.debug(f"Concurrent processing: {'Enabled' if self.use_concurrent else 'Disabled'}")
        logger.debug(f"Summarization method: {self.method}")
        logger.debug(f"\t[VLM] T-1 promote: {'Enabled' if self.use_t_minus_1_for_vlm else 'Disabled'}")
        logger.debug(f"\t[LLM] T-1 promote: {'Enabled' if self.use_t_minus_1_for_llm else 'Disabled'}")
        logger.debug(f"Total levels: {self.total_levels}, with each level group size: {self.level_sizes}")
        
        # Initialize video chunking method
        if self.chunking_method == PeltChunking.METHOD_NAME:
            logger.debug(f"Average duration for video chunks: "
                         f"[{settings.PELT_CHUNK_CONFIG.min_avg_duration}, {settings.PELT_CHUNK_CONFIG.max_avg_duration}], "
                         f"Minimum duration for each chunk: {settings.PELT_CHUNK_CONFIG.min_chunk_duration}")
            if settings.PELT_CHUNK_CONFIG.sample_fps < 0:
                # -1: use video's original fps
                settings.PELT_CHUNK_CONFIG.sample_fps = self.origin_fps
            logger.debug(f"Video chunk sample FPS: {settings.PELT_CHUNK_CONFIG.sample_fps}")
            self.video_chunker = PeltChunking(**(settings.PELT_CHUNK_CONFIG.model_dump()))
            
        elif self.chunking_method == UniformChunking.METHOD_NAME:
            logger.debug(f"Video chunk duration: {settings.UNIFORM_CHUNK_CONFIG.chunk_duration}")
            self.video_chunker = UniformChunking(**(settings.UNIFORM_CHUNK_CONFIG.model_dump()))
            
        else:
            raise NotImplementedError(f"Unsupported video chunking method: {self.chunking_method}, "
                                      f"choices:[{PeltChunking.METHOD_NAME}, {UniformChunking.METHOD_NAME}]")
        
        logger.info(f"Video chunking method: {self.video_chunker.METHOD_NAME}")
        
        # Initialize LLM and VLM model serving for inference
        self.llm = LLM(
            model_name=llm_model_name,
            api_key=llm_api_key,
            base_url=llm_base_url,
            remove_thinking=settings.LLM_REMOVE_THINKING
        )
        self.vlm = VLM(
            model_name=vlm_model_name,
            api_key=vlm_api_key,
            base_url=vlm_base_url,
            remove_thinking=settings.VLM_REMOVE_THINKING
        )

        # Create chunks from the video
        self.chunking()

    def chunking(self) -> None:
        """
        Create hierarchical chunks from the video.
        """

        # Start processing fro level-0
        level = 0

        # Create micro chunks based on segments
        listMicroChunk = self.video_chunker.chunk(video_input=self.video_path)
        for i, micro_chunk in enumerate(listMicroChunk):
            # for sanity
            if micro_chunk.time_end > self.length:
                logger.warning(f"The end time of chunk-{i} exceeds the length of video, "
                                    f"cut end_time to: {self.length}")
                micro_chunk.time_end = self.length
                if micro_chunk.time_st >= micro_chunk.time_end:
                    logger.warning(f"Invalid chunk at chunk-{i}: start_time = {micro_chunk.time_st}, "
                                        f"end_time = {micro_chunk.time_end}, drop it.")
                    continue
            self.chunk_dict[(micro_chunk.level, micro_chunk.id)] = micro_chunk
        self.chunklist_dict[level] = listMicroChunk
        chunk_level0_fps = listMicroChunk[0].fps
        
        # Start processing next level of chunks
        level += 1
        
        # Create macro chunks by grouping every N micro chunks
        while level < (self.total_levels - 1):
            listPreChunk = self.chunklist_dict[level - 1]
            num_subchunk = self.level_sizes[level]
            
            numMacroChunk = math.ceil(len(listPreChunk) / num_subchunk)
            listMacroChunk = []
            for i in range(numMacroChunk):
                chunk = MacroChunkMeta()
                chunk.fps = chunk_level0_fps
                chunk.time_st = listPreChunk[i * num_subchunk].time_st
                chunk.time_end = listPreChunk[min((i + 1) * num_subchunk, len(listPreChunk)) - 1].time_end
                chunk.desc = ""
                chunk.num_subchunk = num_subchunk
                chunk.chunk_list = listPreChunk[i * num_subchunk: min((i + 1) * num_subchunk, len(listPreChunk))]
                chunk.id = i
                chunk.level = level
                self.chunk_dict[(chunk.level, chunk.id)] = chunk
                listMacroChunk.append(chunk)

            self.chunklist_dict[level] = listMacroChunk
            level += 1

        # Create root chunk containing all macro chunks
        chunk = MacroChunkMeta()
        chunk.fps = chunk_level0_fps
        chunk.time_st = 0
        chunk.time_end = self.chunklist_dict[level - 1][-1].time_end
        chunk.desc = ""
        chunk.num_subchunk = len(self.chunklist_dict[level - 1])
        chunk.chunk_list = self.chunklist_dict[level - 1]
        chunk.id = 0
        chunk.level = level
        self.chunk_dict[(chunk.level, chunk.id)] = chunk
        self.rootChunk = chunk
        self.rootLevel = level
        logger.debug("Chunking complete")
    
    async def summarize(self) -> Tuple[str, Dict[str, str]]:
        """
        Summarize the entire video.

        Returns:
            Tuple containing the job ID and final video summary results dict.
        """
        logger.info(f"Starting summarization for video: {self.video_path}")        
        
        try:
            job_id = str(uuid.uuid4())[-8:]
            logger.debug(f"Generated job ID: {job_id}")
            
            # Process micro chunks (level 0)
            logger.debug("Processing level 0 (micro chunks)")
            chunk_list = self.chunklist_dict[0]
            if self.use_concurrent and not self.use_t_minus_1_for_vlm:
                logger.debug("[Micro level-0] Using concurrent processing")
                
                # Create a coroutine object for each piece of data
                async_tasks = [self.summarize_micro_chunk(chunk) for chunk in chunk_list]

                # TODO: pipeline style with LLM?
                # Execute in parallel and wait for all to complete
                await asyncio.gather(*async_tasks, return_exceptions=False)
            else:
                logger.debug("[Micro level-0] Using sequential processing")
                for chunk in chunk_list:
                    await self.summarize_micro_chunk(chunk)

            # Process macro chunks (level > 0)
            for level in range(1, self.rootLevel):
                logger.debug(f"Processing level {level} (macro chunks)")
                chunk_list = self.chunklist_dict[level]

                if self.use_concurrent and not self.use_t_minus_1_for_llm:
                    logger.debug("[Macro level-{level}] Using concurrent processing")
                    async_tasks = [self.summarize_macro_chunk(chunk) for chunk in chunk_list]
                    await asyncio.gather(*async_tasks, return_exceptions=False)
                else:
                    logger.debug(f"[Macro level-{level}] Using sequential processing")
                    for chunk in chunk_list:
                        await self.summarize_macro_chunk(chunk)

            # Process root chunks (top level)
            logger.debug(f"Processing level {self.rootLevel} (top level)")
            await self.summarize_macro_chunk(self.rootChunk)

            # Get the final summary of this video
            summary = self.rootChunk.desc
            logger.info(f"Summarization completed successfully")

            response = {
                "summary": summary,
                "video_duration": self.length
            }
            
            return job_id, response
        
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            raise RuntimeError(f"Summarization failed: {e}")

    async def summarize_micro_chunk(self, chunk: MicroChunkMeta) -> None:
        """
        Summarize a micro chunk using vision-language model.

        Args:
            chunk: Micro chunk to summarize
        """
        
        # Use semaphore to limit concurrent requests
        async with self._semaphore:
            frames = await self.encode_chunk(chunk)

            # If frames extraction failed, handle the error
            if not frames:
                logger.error(f"Failed to extract frames for micro chunk {chunk.id}")
                chunk.desc = "Error occurred during frame extraction."
                return

            # Prepare question/prompt
            question = LOCAL_PROMPT.format(st_tm=round(chunk.time_st), end_tm=round(chunk.time_end))

            # Add previous chunk context if available and enabled
            if self.use_t_minus_1_for_vlm and chunk.id > 0:
                t_minus_1_chunk = self.chunk_dict[(chunk.level, chunk.id - 1)]
                question = T_MINUS_1_PROMPT.format(
                    dur=round(t_minus_1_chunk.time_end-t_minus_1_chunk.time_st),
                    past_summary=t_minus_1_chunk.desc,
                    st_tm=round(t_minus_1_chunk.time_st),
                    end_tm=round(t_minus_1_chunk.time_end)
                ) + '\n' + question

            # Log input prompt
            logger.debug("<#####> micro chunk input")
            logger.debug(question)

            # Run inference
            answer = await self.vlm.async_infer(frames=frames, question=question)

            # Check for errors
            if chunk.desc.startswith("Error:"):
                logger.error(f"ERROR in model response: {answer}")
            else:
                logger.debug(f"Raw answer from model: {answer}")
            chunk.desc = remove_brackets(answer)

            # Log output
            logger.debug("<#####> micro chunk output")
            logger.debug(chunk.get_timestamp_desc())
            logger.debug(chunk.desc)

            # Check for empty descriptions
            if not chunk.desc or chunk.desc.isspace():
                logger.debug(f"WARNING: Empty chunk description for chunk {chunk.id} at level {chunk.level}")
            else:
                logger.debug(f"Successfully generated description for chunk {chunk.id} at level {chunk.level}")

    async def summarize_macro_chunk(self, chunk: MacroChunkMeta) -> None:
        """
        Summarize a macro chunk using its sub-chunks.

        Args:
            chunk: Macro chunk to summarize
        """
        
        # Use semaphore to limit concurrent requests
        async with self._semaphore:
            subchunk_summaries = []
            for subchunk in chunk.chunk_list:
                subchunk_summaries.append(subchunk.get_timestamp_desc() + '\n' + subchunk.desc)

            # Choose prompt based on chunk level
            if self.user_prompt is not None:
                if self.rootLevel == chunk.level:
                    full_summ_prompt = GLOBAL_PROMPT_WITH_QUESTION.format(question=self.user_prompt)
                else:
                    full_summ_prompt = MACRO_CHUNK_PROMPT_WITH_QUESTION.format(
                        st_tm=round(chunk.time_st),
                        end_tm=round(chunk.time_end),
                        question=self.user_prompt
                    )
            else:
                if self.rootLevel == chunk.level:
                    full_summ_prompt = GLOBAL_PROMPT
                else:
                    full_summ_prompt = MACRO_CHUNK_PROMPT.format(
                        st_tm=round(chunk.time_st),
                        end_tm=round(chunk.time_end)
                    )

            full_summ_prompt += '\n\n>|<\n{}\n>|<'
            prompt = full_summ_prompt.format("\n>|<\n".join(subchunk_summaries))

            if self.use_t_minus_1_for_llm:
                # Add previous macro chunk context if available and enabled
                # Exclude for global chunk
                if chunk.level < self.rootLevel and chunk.id > 0:
                    t_minus_1_macro_chunk = self.chunk_dict[(chunk.level, chunk.id - 1)]
                    prompt = T_MINUS_1_PROMPT.format(
                        dur=round(t_minus_1_macro_chunk.time_end-t_minus_1_macro_chunk.time_st),
                        past_summary=t_minus_1_macro_chunk.desc,
                        st_tm=round(t_minus_1_macro_chunk.time_st),
                        end_tm=round(t_minus_1_macro_chunk.time_end)
                    ) + '\n' + prompt

            # Log input prompt
            logger.debug("<#####> macro chunk input")
            logger.debug(prompt)

            # Run inference
            answer = await self.llm.async_infer(prompt)

            # Check for errors
            if chunk.desc.startswith("Error:"):
                logger.error(f"ERROR in model response: {answer}")
            else:
                logger.debug(f"Raw answer from model: {answer}")
            chunk.desc = remove_brackets(answer)

            # Log output
            logger.debug("<#####> macro chunk output")
            logger.debug(chunk.get_timestamp_desc())
            if self.rootLevel == chunk.level:
                logger.debug("Final summary:\n")
            logger.debug(chunk.desc)
          
    async def encode_chunk(self, chunk: ChunkMeta) -> List[Image.Image]:
        """
        Encode a chunk into a list of frames.

        Args:
            chunk: Chunk to encode (must be level 0)

        Returns:
            List of PIL Image frames
        """
        if not chunk.level == 0:
            raise RuntimeError(f"Only level-0 chunks need to be encoded from video, you are trying to encode a chunk at level {chunk.level}")
        start_frame_index = int(chunk.time_st * self.origin_fps)
        end_frame_index = int(chunk.time_end * self.origin_fps)

        frame_idx = [i for i in range(start_frame_index, end_frame_index, int(self.origin_fps / self.process_fps))]

        if len(frame_idx) > settings.MAX_NUM_FRAMES_PER_CHUNK:
            logger.warning(f"Too many frames, reducing the number of frames to the allowed max frames: {settings.MAX_NUM_FRAMES_PER_CHUNK}")
            frame_idx = uniform_sample(frame_idx, settings.MAX_NUM_FRAMES_PER_CHUNK)

        # Use lock to prevent concurrent access to video reader
        with self.vr_lock:
            try:
                frames = self.vr.get_batch(frame_idx).asnumpy()
                frames = [Image.fromarray(v.astype('uint8')).resize((settings.VIDEO_FRAME_WIDTH, settings.VIDEO_FRAME_HEIGHT)) for v in frames]
                logger.debug(f"Successfully extracted {len(frames)} frames for chunk {chunk.id}")
            except Exception as e:
                logger.error(f"Failed to extract frames for chunk {chunk.id}: {e}")
                # Return empty list in case of error
                return []

        return frames


class ModelConfig:
    """Model configuration class, ensures information is printed only once"""
    
    _instance = None
    _printed = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize configuration"""
        self.VLM_MODEL_NAME = os.getenv("VLM_MODEL_NAME")
        self.LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME")
        self.VLM_BASE_URL = os.getenv("VLM_BASE_URL", "http://0.0.0.0:41091/v1")
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://0.0.0.0:41090/v1")
        self.VLM_API_KEY = os.getenv("VLM_API_KEY", "EMPTY")
        self.LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")
        
        self._print_info()
    
    def _print_info(self):
        """Print model information (executes only once)"""
        if not self._printed:
            logger.info(f"[Model Info] VLM: {self.VLM_MODEL_NAME} from endpoint: {self.VLM_BASE_URL}")
            logger.info(f"[Model Info] LLM: {self.LLM_MODEL_NAME} from endpoint: {self.LLM_BASE_URL}")
            self.__class__._printed = True
    
    def refresh(self):
        """Reprint information (for debugging purposes)"""
        self.__class__._printed = False
        self._print_info()
