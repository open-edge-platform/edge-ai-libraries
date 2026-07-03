# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import math
import logging
import asyncio
import threading
import traceback
import uuid
from typing import Dict, List, Tuple, Optional, Any
from PIL import Image
from fastapi import HTTPException, status

from video_chunking import PeltChunking, UniformChunking
from video_chunking.data import ChunkMeta, MicroChunkMeta, MacroChunkMeta
from video_analyzer.schemas.summarization import ErrorResponse

from video_analyzer.core.settings import settings
from video_analyzer.prompts.prompt_builder import assign_global_prompt, assign_macro_prompt, assign_local_prompt, assign_t_minus_prompt
from video_analyzer.schemas.summarization import SUMMARIZATION_METHOD_TYPE
from video_analyzer.model_serving import LLM, VLM
from video_analyzer.utils.summarization_utils import remove_brackets, uniform_sample, warn_unused_kwargs, redact_base64
from video_analyzer.utils.logger import logger
from video_analyzer.utils.file_utils import robust_video_reader
from video_analyzer.utils.subtitle_utils import load_subtitles, extract_subtitles_for_chunk
from video_analyzer.schemas.summarization import TASKNAME


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
        video_subtitles: Optional[Dict[str, str]] = None,
        method: Optional[str] = settings.DEFAULT_SUMMARIZATION_METHOD,
        levels: Optional[int] = settings.DEFAULT_LEVELS,
        level_sizes: Optional[list[int]] = settings.DEFAULT_LEVEL_SIZES,
        chunking_method: Optional[str] = settings.DEFAULT_VIDEO_CHUNKING_METHOD,
        process_fps: Optional[float] = settings.DEFAULT_PROCESS_FPS,
        task: Optional[str] = TASKNAME.SUMMARY.value,
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
            video_subtitles: Video subtitles, this should follow SubRip format. Accept video_subtitles as:
                             - HTTP/HTTPS URL to an .srt file (preferred for containers): {"url": str}
                             - Inline SRT text for short videos: {"text": str}
                             - Base64+gzip SRT payload for long videos: {"b64gzip": str}
            method: Summarization method, choices: [SIMPLE, USE_VLM_T-1, USE_LLM_T-1, USE_ALL_T-1]
            levels: total levels for hierarchical summarization
            level_sizes: chunk group size for each level, -1 means using single group at the level.
            chunking_method: video chunking algorithm, choices: [pelt, uniform]
            process_fps: Extract frames at process_fps for input video
        """
        self.video_path = video_path
        self.subtitles = None
        self.user_prompt = user_prompt
        self.task = task
        logger.info(f"Start video understanding with task: {self.task}")

        # Multi-level configurations
        self.total_levels = levels
        self.level_sizes = level_sizes
        if not isinstance(self.total_levels, int) or self.total_levels < 1:
            raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ErrorResponse(
                        error_message=f"Summarization failed!",
                        details=f"Invalid levels is specified, levels must be integer and at least 1, got: {self.total_levels}"
                    ).model_dump()
                )
        if not len(self.level_sizes) == self.total_levels:
            raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ErrorResponse(
                        error_message=f"Summarization failed!",
                        details=f"The configured level sizes ({self.level_sizes}) "
                                f"should match with total levels: {self.total_levels}"
                    ).model_dump()
                )
        
        # Parse processor_kwargs from user's request
        self.chunking_method = chunking_method
        self.process_fps = process_fps

        # Parse subtitles (if has)
        if video_subtitles is not None:
            logger.debug(f"Received video subtitles from request: {video_subtitles}")
            try:
                # size guard
                max_bytes = settings.MAX_SUBTITLE_BYTES
                self.subtitles = load_subtitles(video_subtitles, max_bytes)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to load subtitles: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ErrorResponse(
                        error_message="Summarization failed!",
                        details=f"Invalid subtitles input: {e}"
                    ).model_dump()
                )

        # Detect caption-only mode: no video file but subtitles provided
        self.caption_only = ((video_path is None or str(video_path).lower() == "none") and
                            video_subtitles is not None and self.subtitles is not None)

        # Validate process_fps (relaxed validation for caption-only mode)
        if not self.caption_only:
            # Normal video mode: process_fps must be positive
            if not isinstance(self.process_fps, (int, float)) or self.process_fps <= 0:
                raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ErrorResponse(
                            error_message=f"Summarization failed!",
                            details=f"Invalid process_fps is specified: ({self.process_fps}) "
                        ).model_dump()
                    )
        else:
            # Caption-only mode: process_fps not used, set to dummy value
            if self.process_fps <= 0:
                logger.debug(f"Caption-only mode: process_fps={self.process_fps} (ignored)")
                self.process_fps = 1.0  # Dummy value

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

        # Initialize video reader or use caption-only mode
        if not self.caption_only:
            # Normal video mode: open video file
            with self.vr_lock:
                self.vr = robust_video_reader(self.video_path)
                self.origin_fps = round(self.vr.get_avg_fps())
                self.numFrame = len(self.vr)
                self.length = self.numFrame / self.origin_fps
        else:
            # Caption-only mode: estimate duration from subtitles
            logger.info("Running in caption-only mode (no video file)")
            self.vr = None
            self.origin_fps = 1.0  # Default value
            self.numFrame = 0
            # Estimate duration from last subtitle timestamp
            if self.subtitles:
                self.length = max(sub['end'] for sub in self.subtitles) if self.subtitles else 60.0
            else:
                self.length = 60.0  # Default 1 minute if no subtitles
            logger.info(f"Estimated duration from subtitles: {self.length:.2f} seconds")
            
        if self.total_levels == 1:
            logger.warning("Received only 1 level in configuration, will be degraded to a generic single level video summarization method that only"
                        "uses extracted frames to summarize over the overall video contents...")
            level_sizes = [-1] # single group for the only level
            
        if level_sizes[0] == -1:
            # Reset chunk duration to cover the full video
            settings.UNIFORM_CHUNK_CONFIG.chunk_duration = self.length + 1
            self.chunking_method = UniformChunking.METHOD_NAME
            
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
        
        # Initialize video chunking method (skip in caption-only mode)
        if not self.caption_only:
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
                raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ErrorResponse(
                            error_message=f"Summarization failed!",
                            details=f"Unsupported video chunking method: {self.chunking_method}, "
                                    f"choices:[{PeltChunking.METHOD_NAME}, {UniformChunking.METHOD_NAME}]"
                        ).model_dump()
                    )

            logger.info(f"Video chunking method: {self.video_chunker.METHOD_NAME}")
        else:
            # Caption-only mode: no video chunker needed
            self.video_chunker = None
            logger.info("Caption-only mode: skipping video chunker initialization")
        
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

        # Create micro chunks based on segments or subtitles (caption-only mode)
        if self.caption_only:
            # Caption-only mode: create chunks from subtitle timestamps
            logger.info("Creating chunks from subtitles (caption-only mode)")
            listMicroChunk = []
            for i, subtitle in enumerate(self.subtitles):
                micro_chunk = MicroChunkMeta()
                micro_chunk.id = i
                micro_chunk.level = 0
                micro_chunk.time_st = subtitle['start']
                micro_chunk.time_end = subtitle['end']
                micro_chunk.fps = 1.0  # No video FPS in caption-only mode
                micro_chunk.desc = ""
                listMicroChunk.append(micro_chunk)
                self.chunk_dict[(micro_chunk.level, micro_chunk.id)] = micro_chunk
            logger.info(f"Created {len(listMicroChunk)} chunks from subtitles with multi-level settings: {self.level_sizes}.")
            chunk_level0_fps = 1.0
        else:
            # Normal video mode: use video chunker
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
            chunk_level0_fps = listMicroChunk[0].fps if listMicroChunk else 1.0

        self.chunklist_dict[level] = listMicroChunk
        
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

        if self.total_levels > 1:
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
        else:
            # only single level
            self.rootLevel = 0
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
            
            # total_levels = 1, degrading as a generic VLM summarization method
            if self.rootLevel == 0:
                if len(self.chunklist_dict[0]) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ErrorResponse(
                            error_message="Summarization failed",
                            details="Specify total levels = 1, but got several chunks in level-0, this is not allowed!"
                        ).model_dump()
                    )
                await self.summarize_micro_chunk(self.chunklist_dict[0][0])
                logger.debug("Return summarization with single level and single inference!!")

                single_summary = self.chunklist_dict[0][0].desc
                # Check for errors in single-level result
                if single_summary.startswith("Error:"):
                    logger.error(f"Single-level summarization failed: {single_summary}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=ErrorResponse(
                            error_message="Summarization failed",
                            details=single_summary
                        ).model_dump()
                    )

                # 收集 token 统计 - 合并 VLM 和 LLM 的统计
                vlm_usage = self.vlm.get_token_usage()
                llm_usage = self.llm.get_token_usage()
                token_usage = {
                    "prompt_tokens": vlm_usage.get("prompt_tokens", 0) + llm_usage.get("prompt_tokens", 0),
                    "image_tokens": vlm_usage.get("image_tokens", 0) + llm_usage.get("image_tokens", 0),
                    "completion_tokens": vlm_usage.get("completion_tokens", 0) + llm_usage.get("completion_tokens", 0),
                    "total_tokens": vlm_usage.get("total_tokens", 0) + llm_usage.get("total_tokens", 0),
                }

                # Directly return the description of the single level summarization result
                response = {
                    "summary": single_summary,
                    "video_duration": self.length,
                    "usage": token_usage
                }
                return job_id, response
            
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
            # Check for errors — propagate as HTTP 500 so callers can retry or mark as failed
            if summary.startswith("Error:"):
                logger.error(f"Summarization failed: {summary}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=ErrorResponse(
                        error_message="Summarization failed",
                        details=summary
                    ).model_dump()
                )
            else:
                logger.info(f"Summarization completed successfully")

            # 收集 token 统计 - 合并 VLM 和 LLM 的统计
            vlm_usage = self.vlm.get_token_usage()
            llm_usage = self.llm.get_token_usage()
            token_usage = {
                "prompt_tokens": vlm_usage.get("prompt_tokens", 0) + llm_usage.get("prompt_tokens", 0),
                "image_tokens": vlm_usage.get("image_tokens", 0) + llm_usage.get("image_tokens", 0),
                "completion_tokens": vlm_usage.get("completion_tokens", 0) + llm_usage.get("completion_tokens", 0),
                "total_tokens": vlm_usage.get("total_tokens", 0) + llm_usage.get("total_tokens", 0),
            }

            response = {
                "summary": summary,
                "video_duration": self.length,
                "usage": token_usage
            }

            return job_id, response
        
        except HTTPException:
            # Re-raise HTTPException as-is (already has proper status code)
            raise
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            logger.error(f"Error details: {traceback.format_exc()}")

            # Provide detailed error response based on exception type
            error_details = str(e)
            error_traceback = traceback.format_exc()

            # Detect specific error types and provide helpful messages
            if "video_reader_backend" in error_details or "decord error" in error_details:
                error_message = "Video decoding failed"
                details = (
                    f"The video file appears to be corrupted or in an unsupported format. "
                    f"Common causes:\n"
                    f"  1. Video clip starts from a non-keyframe (damaged header)\n"
                    f"  2. Incomplete video file (still being written)\n"
                    f"  3. Unsupported codec or format\n\n"
                    f"Error: {error_details}\n\n"
                    f"Suggestion: Ensure video clips are properly extracted with keyframes, "
                    f"or try re-encoding the video with: ffmpeg -i input.mp4 -c:v libx264 -crf 23 output.mp4"
                )
            elif "No such file" in error_details or "FileNotFoundError" in error_details:
                error_message = "Video file not found"
                details = f"The specified video file could not be accessed: {error_details}"
            elif "timeout" in error_details.lower() or "timed out" in error_details.lower():
                error_message = "Request timeout"
                details = f"The summarization request took too long to complete: {error_details}"
            elif "OutOfMemoryError" in error_details or "CUDA out of memory" in error_details:
                error_message = "Out of memory"
                details = f"Insufficient memory to process the video: {error_details}"
            else:
                error_message = "Summarization failed"
                details = f"An unexpected error occurred during summarization:\n{error_details}"

            # Include last 3 lines of traceback for debugging
            traceback_lines = error_traceback.split('\n')
            relevant_traceback = '\n'.join([line for line in traceback_lines[-10:] if line.strip()])

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorResponse(
                    error_message=error_message,
                    details=f"{details}\n\nDebug traceback:\n{relevant_traceback}"
                ).model_dump()
            )

    async def summarize_micro_chunk(self, chunk: MicroChunkMeta) -> None:
        """
        Summarize a micro chunk using vision-language model or subtitle text (caption-only mode).

        Args:
            chunk: Micro chunk to summarize
        """

        # Use semaphore to limit concurrent requests
        async with self._semaphore:
            # Caption-only mode: use subtitle text directly, skip VLM
            if self.caption_only:
                subtitle = await self._get_subtitle(chunk)
                if subtitle and subtitle.strip():
                    chunk.desc = subtitle.strip()
                else:
                    chunk.desc = "无事件描述"
                logger.debug(f"Caption-only mode: using subtitle text for chunk {chunk.id}")
                logger.debug(f"Subtitle content: {chunk.desc[:100]}...")
                return

            # Normal video mode: extract frames and use VLM
            frames = await self.encode_chunk(chunk)
            subtitle = await self._get_subtitle(chunk)

            # If frames extraction failed, handle the error
            if not frames:
                logger.error(f"Failed to extract frames for micro chunk {chunk.id}")
                chunk.desc = "Error occurred during frame extraction."
                return

            # Prepare question/prompt
            question = assign_local_prompt(task=self.task,
                                           st_tm=round(chunk.time_st),
                                           end_tm=round(chunk.time_end),
                                           question=self.user_prompt,
                                           chunk_subtitle=subtitle)

            # Add previous chunk context if available and enabled
            if self.use_t_minus_1_for_vlm and chunk.id > 0:
                t_minus_1_chunk = self.chunk_dict[(chunk.level, chunk.id - 1)]
                question = assign_t_minus_prompt(
                    task=self.task,
                    dur=round(t_minus_1_chunk.time_end-t_minus_1_chunk.time_st),
                    past_summary=t_minus_1_chunk.desc,
                    st_tm=round(t_minus_1_chunk.time_st),
                    end_tm=round(t_minus_1_chunk.time_end)
                ) + '\n' + question

            # Log input prompt
            logger.debug("<#####> micro chunk input")
            logger.debug(redact_base64(question))

            # Run inference
            answer = await self.vlm.async_infer(frames=frames, content=question)

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
        subtitle = await self._get_subtitle(chunk)
        
        # Use semaphore to limit concurrent requests
        async with self._semaphore:
            subchunk_summaries = []
            for subchunk in chunk.chunk_list:
                subchunk_summaries.append(subchunk.get_timestamp_desc() + '\n' + subchunk.desc)

            prompt = await self._build_macro_prompt(chunk=chunk, subtitle=subtitle, subchunk_summaries=subchunk_summaries)

            # Log input prompt
            logger.debug("<#####> macro chunk input")
            logger.debug(redact_base64(prompt))

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
        # Clamp to valid range
        last_valid_index = self.numFrame - 1
        start_frame_index = max(0, min(start_frame_index, last_valid_index))
        end_frame_index = max(0, min(end_frame_index, last_valid_index))

        frame_idx = [i for i in range(start_frame_index, end_frame_index, int(self.origin_fps / self.process_fps))]

        # Always include first and last frame for better action recognition
        if start_frame_index not in frame_idx:
            frame_idx.insert(0, start_frame_index)
        if end_frame_index not in frame_idx:
            frame_idx.append(end_frame_index)

        if len(frame_idx) > settings.MAX_NUM_FRAMES_PER_CHUNK:
            logger.warning(f"Too many frames, reducing the number of frames to the allowed max frames: {settings.MAX_NUM_FRAMES_PER_CHUNK}")
            # Reserve 2 slots for first and last frame, sample the rest from middle
            if settings.MAX_NUM_FRAMES_PER_CHUNK > 2:
                middle_frames = uniform_sample(frame_idx[1:-1], settings.MAX_NUM_FRAMES_PER_CHUNK - 2)
                frame_idx = [frame_idx[0]] + middle_frames + [frame_idx[-1]]
            else:
                frame_idx = [frame_idx[0], frame_idx[-1]]

        # Use lock to prevent concurrent access to video reader
        with self.vr_lock:
            try:
                raw_frames = self.vr.get_batch(frame_idx).asnumpy()
                raw_images = [Image.fromarray(v.astype('uint8')) for v in raw_frames]
                frames = [img.resize((settings.VIDEO_FRAME_WIDTH, settings.VIDEO_FRAME_HEIGHT)) for img in raw_images]
                logger.debug(f"Successfully extracted {len(frames)} frames for chunk {chunk.id}")
            except Exception as e:
                logger.error(f"Failed to extract frames for chunk {chunk.id}: {e}")
                # Return empty list in case of error
                return []

        # # Debug: save sampled frames to disk
        # try:
        #     video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        #     debug_dir = f"/tmp/video-summary-debug/{video_name}/chunk-{chunk.id}"
        #     os.makedirs(debug_dir, exist_ok=True)
        #     for i, (idx, raw_img, resized_img) in enumerate(zip(frame_idx, raw_images, frames)):
        #         resized_img.save(os.path.join(debug_dir, f"frame_{i:02d}_idx{idx}_resized.jpg"))
        #     logger.info(f"Debug frames saved to {debug_dir} ({len(frames)} frames, indices: {frame_idx})")
        # except Exception as e:
        #     logger.warning(f"Failed to save debug frames: {e}")

        return frames
    
    async def _get_subtitle(self, chunk: ChunkMeta) -> str | None:
        if self.subtitles is None:
            return None
        
        if len(self.subtitles) == 0:
            return None
        
        # Extract corresponding subtitles
        chunk_subtitles = extract_subtitles_for_chunk(chunk, self.subtitles, overlap_threshold=0.5)
        
        return chunk_subtitles['full_text']

    async def _build_macro_prompt(self, chunk, subtitle: Optional[str], subchunk_summaries: List[str]) -> str:
        """
        Build the macro/global prompt for a chunk, support optional user prompt and subtitles.
        """
        # Case switch dimensions:
        # is_global_level: bool
        is_global_level = (self.rootLevel == chunk.level)

        match is_global_level:
            # Global level
            case True:
                full_summ_prompt = assign_global_prompt(
                    task=self.task,
                    question=self.user_prompt,
                    chunk_subtitle=subtitle
                )
            # Macro level (non-global)
            case False:
                full_summ_prompt = assign_macro_prompt(
                    task=self.task,
                    st_tm=round(chunk.time_st),
                    end_tm=round(chunk.time_end),
                    question=self.user_prompt,
                    chunk_subtitle=subtitle
                )

        # Attach subchunk summaries
        full_summ_prompt += '\n\n>|<\n{}\n>|<'
        prompt = full_summ_prompt.format("\n>|<\n".join(subchunk_summaries))

        # Optional T-1 context for LLM (non-global levels)
        if self.use_t_minus_1_for_llm and (chunk.level < self.rootLevel) and (chunk.id > 0):
            t_minus_1_macro_chunk = self.chunk_dict[(chunk.level, chunk.id - 1)]
            prompt = assign_t_minus_prompt(
                dur=round(t_minus_1_macro_chunk.time_end - t_minus_1_macro_chunk.time_st),
                past_summary=t_minus_1_macro_chunk.desc,
                st_tm=round(t_minus_1_macro_chunk.time_st),
                end_tm=round(t_minus_1_macro_chunk.time_end)
            ) + '\n' + prompt

        return prompt

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
