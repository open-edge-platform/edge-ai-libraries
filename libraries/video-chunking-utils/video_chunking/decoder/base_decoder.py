from abc import ABC, abstractmethod
import numpy as np
from typing import List, Tuple, Optional


def is_decord_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("decord") is not None

def is_ffmpeg_available() -> bool:
    import importlib.util
    import shutil

    # check ffmpeg-python
    def is_ffmpeg_python_available() -> bool:
        return importlib.util.find_spec("ffmpeg") is not None

    def is_ffmpeg_executable_available() -> bool:
        return shutil.which("ffmpeg") is not None
    
    return is_ffmpeg_python_available() and is_ffmpeg_executable_available()

class BaseVideoDecoder(ABC):
    """
    Abstract base class for video decoders.
    Defines the interface that all video decoder implementations must follow.
    """
    
    @abstractmethod
    def __init__(self, video_path: str, sample_fps: float, longest_side_size: Optional[int] = None):
        """
        Initialize video decoder with specified parameters.
        
        Args:
            video_path: the path of video. support "file://", "http://", "https://" and local path.
            sample_fps: target sampling frame rate (frames per second)
            longest_side_size: Optional resize to ensure longest side is as configured
        """
        pass
    
    @abstractmethod
    def decode_next(self, num_frames: int = 1) -> Tuple[List[np.ndarray], List[float]]:
        """
        Decode and return the next n frames.
        
        Args:
            num_frames: Number of frames to decode (default: 1)
        
        Returns:
            Two lists:
            - Frame list: video frames (numpy arrays)
            - Timestamp list: timestamps (seconds relative to video start)
        """
        pass
    
    @abstractmethod
    def decode_all(self) -> Tuple[List[np.ndarray], List[float]]:
        """
        Decode and return all frames at once.
        
        Returns:
            Two lists:
            - Frame list: video frames (numpy arrays)
            - Timestamp list: timestamps (seconds relative to video start)
        """
        pass
    
    @abstractmethod
    def reset(self):
        """
        Reset the decoder to start from the beginning.
        """
        pass
    
    @abstractmethod
    def get_video_info(self) -> dict:
        """
        Get video metadata information.
        
        Returns:
            Dictionary containing video information (width, height, original_fps, etc.)
        """
        pass
    
    def __iter__(self):
        """Make the decoder iterable."""
        self._iter_index = 0
        return self
    
    def __next__(self) -> Tuple[np.ndarray, float]:
        """
        Get next frame for iteration.
        
        Returns:
            Tuple of (frame, timestamp)
            
        Raises:
            StopIteration: When no more frames are available
        """
        frames, timestamps = self.decode_next(1)
        if not frames:
            raise StopIteration
        return frames[0], timestamps[0]

    @abstractmethod
    def get_timestamp_with_frame_index(self, frame_index: int) -> float:
        """Get timestamp giving frame index."""
        pass

    @property
    @abstractmethod
    def video_path(self) -> str:
        """Get video path."""
        pass
    
    @property
    @abstractmethod
    def current_frame_index(self) -> int:
        """Get the current frame index (0-based)."""
        pass
    
    @property
    @abstractmethod
    def total_frames(self) -> Optional[int]:
        """Get total number of frames if available, otherwise None."""
        pass
    
    @property
    @abstractmethod
    def duration(self) -> Optional[float]:
        """Get video duration in seconds if available, otherwise None."""
        pass
