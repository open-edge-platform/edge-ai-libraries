import os
import numpy as np
import logging
from typing import Tuple, List
from functools import lru_cache
from abc import ABC, abstractmethod

from video_chunking.data import MicroChunkMeta
from video_chunking.decoder import (
    BaseVideoDecoder,
    FFmpegVideoDecoder,
    DecordVideoDecoder,
    is_decord_available,
)

logger = logging.getLogger(__name__)


VIDEO_READER_BACKENDS = {
    "decord": DecordVideoDecoder,
    "ffmpeg": FFmpegVideoDecoder,
}

FORCE_CHUNKING_VIDEO_READER = os.getenv("FORCE_CHUNKING_VIDEO_READER", None)

@lru_cache(maxsize=1)
def get_video_reader_backend() -> str:
    if FORCE_CHUNKING_VIDEO_READER is not None:
        video_reader_backend = FORCE_CHUNKING_VIDEO_READER
    else:
        if is_decord_available():
            video_reader_backend = "decord"
        else:
            video_reader_backend = "ffmpeg"
        logger.info(f"To specify video decoder, please use `FORCE_CHUNKING_VIDEO_READER` environment variable"
                    ", available backends: [ffmpeg, decord]")
    logger.info(f"video-chunking using {video_reader_backend} to read video.")
    return video_reader_backend

class BaseChunking(ABC):
    def __init__(
        self,
        sample_fps: int | None = 1,
        max_frame_size: int | None = 512,
    ):
        """Creates a Video Chunking object.
        
        Args:
            sample_fps: Sampling frame rate
            max_frame_size: Longest side size
        """
        self.sample_fps = sample_fps
        self.max_frame_size = max_frame_size
        self.decoder = None
    
    @abstractmethod
    def chunk(self, 
              video_input: str,
              ) -> list[float]:
        """
        Args:
            video_input: the path of video. support "file://", "http://", "https://" and local path.
        """
        return []
    
    @abstractmethod
    def update(self,  **kwargs):
        pass
    
    @abstractmethod
    def process(self) -> list[MicroChunkMeta]:
        '''
        Return chunk metas
        '''
        return []
    
    def format_chunks(self, start_time: float, 
                      end_time: float) -> MicroChunkMeta:
        chunk = MicroChunkMeta()
        chunk.fps = self.sample_fps
        chunk.time_st = start_time
        chunk.time_end = end_time
        chunk.desc = "Micro chunk representing a level-0 segment of video."
        
        return chunk
    
    def _load_decoder(self,
                      video_path: str,
                      ) -> BaseVideoDecoder:
        
        if self.decoder is not None:
            if not self.decoder.video_path == video_path:
                del self.decoder
                self.decoder = None
                
        if self.decoder is None:
            video_reader_backend = get_video_reader_backend()
            try:
                self.decoder = VIDEO_READER_BACKENDS[video_reader_backend](video_path=video_path, sample_fps=self.sample_fps,
                                                                           longest_side_size=self.max_frame_size)
            except Exception as e:
                raise RuntimeError(f"video_reader_backend {video_reader_backend} error, msg: {e} ")
            
        return self.decoder
    
    def read_video_all_frames(self,
                              video_path: str,
                              ) -> Tuple[List[np.ndarray], List[float]]:
        """
        Read all frames at once
        """
        self._load_decoder(video_path)
        
        frames, timestamps = self.decoder.decode_all()
        
        return frames, timestamps
    
    def read_video_next_nframes(self,
                              video_path: str,
                              num_frames: int = 1,
                              ) -> Tuple[List[np.ndarray], List[float]]:
        """
        Read next frame
        """
        self._load_decoder(video_path)
        
        frame, timestamp = self.decoder.decode_next(num_frames)
        
        return frame, timestamp

    def get_video_total_nframes(self, video_path: str) -> int:
        self._load_decoder(video_path)

        return self.decoder.total_frames