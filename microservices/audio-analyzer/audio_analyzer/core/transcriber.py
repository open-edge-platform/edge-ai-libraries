# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import multiprocessing
import math
import traceback
import time
import uuid
from pathlib import Path
from typing import Optional, Tuple

from audio_analyzer.core.settings import settings
from audio_analyzer.schemas.types import DeviceType, WhisperModel, TranscriptionBackend
from audio_analyzer.utils.hardware_utils import is_intel_gpu_available
from audio_analyzer.utils.logger import logger
from audio_analyzer.utils.model_manager import ModelManager

class TranscriptionService:
    """
    Service for transcribing audio using Whisper models.
    
    Supports both whispercpp (for CPU) and OpenVINO-Genai based inferences (for GPU).
    """

    # Experimental optimal thread discount factor for each model type. 
    # Thread count will be kept less than the total number of CPU cores available.
    OPTIMAL_THREAD_DISCOUNT_FACTOR = {
        WhisperModel.TINY: 0.18,
        WhisperModel.TINY_EN: 0.18,
        WhisperModel.BASE: 0.25,
        WhisperModel.BASE_EN: 0.25,
        WhisperModel.SMALL: 0.4,
        WhisperModel.SMALL_EN: 0.4,
        WhisperModel.MEDIUM: 0.5,
        WhisperModel.MEDIUM_EN: 0.5,
        WhisperModel.LARGE_V1: 0.7,
        WhisperModel.LARGE_V2: 0.7,
        WhisperModel.LARGE_V3: 0.7
    }

    DEFAULT_N_THREADS = 4     # Default number of threads employed for whisper models
    DEFAULT_N_PROCESSORS = 1  # Default number of processors/chunks for parallel processing
    MAX_N_PROCESSORS = 8

    def __init__(self, model_name: Optional[str] = None, device: Optional[DeviceType] = None):
        """
        Initialize the transcription service.
        
        Args:
            model_name: Name of the Whisper model to use
            device: Device to use for inference ('cpu', 'gpu', or 'auto')
        """
        logger.debug("Initializing TranscriptionService")
        self.model = None
        self.model_name = WhisperModel(model_name.lower()) if model_name else settings.DEFAULT_WHISPER_MODEL
        self.device_type = DeviceType(device.lower()) if device else settings.DEFAULT_DEVICE
        logger.debug(f"Using model: {self.model_name.value} on device: {self.device_type.value}")

        self.num_cores = multiprocessing.cpu_count()

        self.backend = self._determine_backend()
        logger.info(f"Selected transcription backend: {self.backend}")

    def _determine_backend(self) -> TranscriptionBackend:
        """
        Determine which backend to use based on device type and available modules.
        
        Returns:
            The appropriate transcription backend
        """
        logger.debug("Determining appropriate transcription backend")
        if self.device_type == DeviceType.CPU:
            logger.info("CPU device selected, using whisper.cpp backend")
            return TranscriptionBackend.WHISPER_CPP
        
        elif self.device_type == DeviceType.GPU:
            # Check if openvino is available and model is downloaded
            logger.debug("Checking for OpenVINO and GPU model availability")
            if (importlib.util.find_spec("openvino") and 
                ModelManager.is_model_downloaded(self.model_name, use_gpu=True)):
                logger.info("OpenVINO and required model found, using OpenVINO backend")
                return TranscriptionBackend.OPENVINO
            else:
                # Fall back to WhisperCPP if OpenVINO is not available
                logger.warning("OpenVINO not found or required OpenVINO model not downloaded, falling back to whisper.cpp on CPU")
                return TranscriptionBackend.WHISPER_CPP
            
        else:  # DeviceType.AUTO
            logger.debug("Auto device detection requested")
            # Check if Intel GPU is available and the model is downloaded for GPU
            if is_intel_gpu_available() and ModelManager.is_model_downloaded(self.model_name, use_gpu=True):
                logger.info("Intel GPU detected and required OpenVINO model available, using OpenVINO backend")
                return TranscriptionBackend.OPENVINO
                
            # Fall back to WisperCPP
            logger.warning("No compatible GPU detected or required model not available, falling back to Whisper.cpp backend on CPU")
            return TranscriptionBackend.WHISPER_CPP

    def _load_model(self):
        """
        Load the appropriate Whisper model based on the backend.
        """
        if self.model is not None:
            logger.debug("Model already loaded, skipping initialization")
            return
            
        logger.info(f"Loading model: {self.model_name.value} using backend: {self.backend}")
        try:
            if self.backend == TranscriptionBackend.WHISPER_CPP:
                logger.debug("Initializing whispercpp model")
                from pywhispercpp.model import Model
                
                # Get the path to the downloaded GGML model
                model_path = ModelManager.get_model_path(self.model_name.value, use_gpu=False)
                
                if not model_path.is_file():
                    raise FileNotFoundError(f"GGML model file not found at {model_path}")
                
                # set the number of threads by multiplying the core count with the optimal thread discount factor
                thread_discount_factor: float = self.OPTIMAL_THREAD_DISCOUNT_FACTOR.get(self.model_name, 1.0)
                thread_count: int = math.ceil(self.num_cores * thread_discount_factor)

                # set number of threads to be at least 1; Max value: thread count or number of cores - 1, whichever is smaller
                n_threads: int = min(max(1, self.num_cores-1), max(thread_count, self.DEFAULT_N_THREADS))
                logger.debug(f"Using {n_threads} threads for CPU inference based on model size and core count: {self.model_name.value}")

                self.model = Model(str(model_path), n_threads=n_threads)
                logger.info("whispercpp model loaded successfully")
            else: 
                logger.debug("Initializing OpenVINO Whisper model")
                import openvino as ov
                from transformers import AutoProcessor
                
                # Get the path to the downloaded model directory
                model_path = ModelManager.get_model_path(self.model_name.value, use_gpu=True)
                
                if not model_path.is_dir():
                    raise FileNotFoundError(f"OpenVINO model not found at {model_path}")
                
                logger.debug("Initializing OpenVINO Core")
                core = ov.Core()
                
                compute_type = "FP16" if settings.USE_FP16 else "FP32"
                logger.debug(f"Using compute type: {compute_type}")
                
                encoder_path = model_path / "encoder_model.xml"
                decoder_path = model_path / "decoder_model.xml"
                
                if not encoder_path.is_file() or not decoder_path.is_file():
                    raise FileNotFoundError(f"OpenVINO model files not found at {model_path}")
                
                # Load models with OpenVINO
                encoder_model = core.read_model(encoder_path)
                decoder_model = core.read_model(decoder_path)
                
                encoder_compiled = core.compile_model(encoder_model, "GPU")
                decoder_compiled = core.compile_model(decoder_model, "GPU")
            
                processor = AutoProcessor.from_pretrained(str(model_path))
                
                self.model = {
                    "encoder": encoder_compiled,
                    "decoder": decoder_compiled,
                    "processor": processor
                }
                
                logger.info("OpenVINO Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            raise RuntimeError(f"Failed to load transcription model: {e}")

    async def transcribe(
        self, 
        audio_path: Path, 
        language: Optional[str] = None,
        include_timestamps: bool = True,
        video_duration: Optional[float] = None
    ) -> Tuple[str, Path]:
        """
        Transcribe audio using the selected backend.
        
        Args:
            audio_path: Path to the audio file
            language: Language code for transcription (optional)
            include_timestamps: Whether to include timestamps in the output
            video_duration: Duration of the video in seconds (optional)
            
        Returns:
            Tuple containing the job ID and path to the transcription file
        """
        logger.info(f"Starting transcription for audio: {audio_path}")
        logger.debug(f"Transcription parameters - language: {language}, include_timestamps: {include_timestamps}, video_duration: {video_duration}")
        
        try:
            self._load_model()
            
            job_id = str(uuid.uuid4())[-8:]
            logger.debug(f"Generated job ID: {job_id}")
            
            output_dir = Path(settings.OUTPUT_DIR / "transcript")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract audio file name without extension
            audio_filename = audio_path.stem
            
            # Define output paths with audio filename directly concatenated with job_id
            srt_path = output_dir / f"{audio_filename}-{job_id}.srt"
            txt_path = output_dir / f"{audio_filename}-{job_id}.txt"
            logger.debug(f"Output paths - SRT: {srt_path}, TXT: {txt_path}")
            
            # Choose the appropriate transcription method based on backend
            if self.backend == TranscriptionBackend.WHISPER_CPP:
                logger.info("Using whispercpp backend for transcription")
                await self._transcribe_with_whisper_cpp(
                    audio_path, 
                    srt_path, 
                    txt_path, 
                    language, 
                    include_timestamps,
                    video_duration
                )
            else:
                logger.info("Using OpenVINO backend for transcription")
                await self._transcribe_with_openvino(
                    audio_path, 
                    srt_path, 
                    txt_path, 
                    language, 
                    include_timestamps
                )
            
            output_path = srt_path if include_timestamps else txt_path
            logger.info(f"Transcription completed successfully. Output at: {output_path}")
            
            return job_id, output_path
        
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            raise RuntimeError(f"Transcription failed: {e}")
    
    async def _transcribe_with_whisper_cpp(
        self,
        audio_path: Path,
        srt_path: Path,
        txt_path: Path,
        language: Optional[str],
        include_timestamps: bool,
        video_duration: Optional[float] = None
    ) -> None:
        """
        Transcribe using whisper.cpp backend with pywhispercpp package.
        
        Args:
            audio_path: Path to the audio file
            srt_path: Output path for SRT file
            txt_path: Output path for text file
            language: Language code
            include_timestamps: Whether to include timestamps
            video_duration: Duration of the video in seconds
        """
        logger.debug("Preparing whispercpp transcription parameters")
        
        try:
            from pywhispercpp.utils import output_srt, output_txt
            
            lang_code = language or settings.TRANSCRIPT_LANGUAGE
            params = {}
            
            if lang_code:
                params["language"] = lang_code
                logger.debug(f"Set language to: {lang_code}")
            
            # Calculate optimal number of processors based on video duration and core count
            # Each processor will handle at least 1 minute (60 seconds) of audio
            if video_duration and video_duration > 0:
                # Minimum value : 1 processor; Max value : 8 processors or number of cores whichever is smaller
                n_processors = max(1, min(self.num_cores, min(self.MAX_N_PROCESSORS, int(video_duration // 60))))
                logger.debug(f"Using {n_processors} processors based on video duration of {video_duration:.2f} seconds")
            else:
                # Default to 1 processor if duration is unknown
                n_processors = self.DEFAULT_N_PROCESSORS
                logger.debug(f"Using default {n_processors} processor(s) as video duration is unknown")
            
            params["beam_search"] = {"beam_size": 5, "patience": 1.5}  # Use small beam size for faster inference
            params["greedy"] = {"best_of": 1}    # Only consider one candidate

            # perform transcription
            logger.debug(f"Starting whispercpp transcription with {n_processors} processors")
            start_time = time.time()
            segments = self.model.transcribe(
                str(audio_path),
                n_processors=n_processors,
                **params
            )
            
            output_txt(segments, str(txt_path))
            logger.debug(f"Text file written to: {txt_path}")
            
            # If timestamps are required, generate SRT file
            if include_timestamps:
                output_srt(segments, str(srt_path))
                logger.debug(f"SRT file written to: {srt_path}")
            
            elapsed_time = time.time() - start_time
            logger.debug(f"whispercpp transcription completed successfully in {elapsed_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error in whispercpp transcription: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            raise

    async def _transcribe_with_openvino(
        self,
        audio_path: Path,
        srt_path: Path,
        txt_path: Path,
        language: Optional[str],
        include_timestamps: bool
    ) -> None:
        """
        Transcribe using OpenVINO backend with WhisperPipeline from openvino-genai package.
        
        Args:
            audio_path: Path to the audio file
            srt_path: Output path for SRT file
            txt_path: Output path for text file
            language: Language code
            include_timestamps: Whether to include timestamps
        """
        
        try:
            start_time = time.time()
            from openvino_genai import WhisperPipeline
            
            # Initialize the WhisperPipeline with pre-loaded model components
            logger.debug("Initializing OpenVINO-Genai WhisperPipeline with pre-loaded model components")
            pipeline = WhisperPipeline(
                encoder=self.model["encoder"],
                decoder=self.model["decoder"],
                processor=self.model["processor"]
            )
            
            # Perform transcription
            logger.debug(f"Starting transcription of {audio_path}")
            result = pipeline(
                str(audio_path),
                language=language or settings.TRANSCRIPT_LANGUAGE,
                return_timestamps=include_timestamps
            )
            
            full_text = result.get("text", "")
            with open(txt_path, "w", encoding="utf-8") as txt_file:
                txt_file.write(full_text)
            logger.debug(f"Text file written to: {txt_path}")
            
            # If timestamps are required, generate SRT file
            if include_timestamps:
                from pywhispercpp.utils import to_timestamp
                
                # Get segments with timestamps
                segments = result.get("segments", [])
                
                # Generate SRT content
                srt_content = ""
                for i, segment in enumerate(segments, 1):
                    start_time = segment.get("start", 0)
                    end_time = segment.get("end", start_time + 1)
                    text = segment.get("text", "").strip()
                    
                    # Format timestamps to - HH:MM:SS,mmm
                    start_formatted = to_timestamp(start_time)
                    end_formatted = to_timestamp(end_time)

                    # Create SRT entry
                    srt_content += f"{i}\n{start_formatted} --> {end_formatted}\n{text}\n\n"
                
                # Write SRT file
                with open(srt_path, "w", encoding="utf-8") as srt_file:
                    srt_file.write(srt_content)
                logger.debug(f"SRT file written to: {srt_path}")
                
            elapsed_time = time.time() - start_time
            logger.debug(f"OpenVINO transcription completed in {elapsed_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error in OpenVINO transcription: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            raise