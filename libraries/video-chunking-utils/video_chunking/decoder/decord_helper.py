import os
import logging
import numpy as np
import threading
from decord import VideoReader, cpu
from urllib.parse import urlparse
import requests
import tempfile
from typing import List, Tuple, Optional

from video_chunking.decoder import BaseVideoDecoder

DECORD_NUM_THREADS = int(os.environ.get('DECORD_NUM_THREADS', 0))
vr_lock = threading.RLock()
logger = logging.getLogger(__name__)

class DecordVideoDecoder(BaseVideoDecoder):
    def __init__(self, video_path: str, sample_fps: float, longest_side_size: Optional[int] = None):
        """
        Initialize decord video decoder with specified sampling frame rate.
        
        Args:
            video_path: the path of video. support "file://", "http://", "https://".
            sample_fps: target sampling frame rate (frames per second)
            longest_side_size: resize to ensure longest side is as configured
        """
        
        self._video_path = self._validate_video_path(video_path)
        self.sample_fps = sample_fps
        self.longest_side_size = longest_side_size
        
        # Initialize video reader without resize first to get original info
        # use lock to prevent concurrent access issues
        with vr_lock:
            self.vr = self.robust_video_reader(self._video_path, ctx=cpu(0), num_threads=DECORD_NUM_THREADS)
            # Get video information
            self.original_fps = self.vr.get_avg_fps()
            self._total_frames = len(self.vr)
            self._duration = self._total_frames / self.original_fps if self._total_frames else None
            # Get original dimensions from first frame
            first_frame = self.vr[0].asnumpy()
            
        self.original_height, self.original_width = first_frame.shape[:2]
        
        # Calculate resize parameters if needed
        self.resize_size = None
        if longest_side_size is not None:
            max_side = max(self.original_height, self.original_width)
            if max_side > longest_side_size:
                scale = longest_side_size / max_side
                new_height = int(self.original_height * scale)
                new_width = int(self.original_width * scale)
                self.resize_size = (new_width, new_height)  # decord uses (width, height)
        
        # Reinitialize video reader with resize if needed
        if self.resize_size is not None:
            with vr_lock:
                self.vr = self.robust_video_reader(
                    self._video_path, 
                    ctx=cpu(0), 
                    num_threads=DECORD_NUM_THREADS, 
                    width=self.resize_size[0], 
                    height=self.resize_size[1]
                )
            self.scaled_width, self.scaled_height = self.resize_size
        else:
            self.scaled_width, self.scaled_height = self.original_width, self.original_height
        
        # Calculate sampling parameters
        self.sample_interval = self.original_fps / sample_fps
        self.total_sampled_frames = int(self._total_frames // self.sample_interval)
        
        # Initialize state variables
        self._current_frame_index = 0
        self._current_sample_index = 0
    
    def _validate_video_path(self, video_path):
        # TODO: validate `https://`
        if "http://" in video_path or "https://" in video_path:
            pass
        elif "file://" in video_path:
            pass
        else:
            from pathlib import Path
            path = Path(video_path).expanduser().resolve()
            if not str(path).startswith("/"):
                raise NotImplementedError("Unsupported video input, support 'file://', 'http://', 'https://' and local path")
        return video_path
    
    @staticmethod
    def robust_video_reader(url, ctx=cpu(0), width=-1, height=-1, num_threads=0, verify_ssl=True):
        """
        Robust video loading functions, supporting HTTPS.
        """
        # For local file and HTTP files, directly use decord
        if not urlparse(url).scheme in ['https']:
            return VideoReader(url, ctx=ctx, width=width, height=height, num_threads=num_threads)
        
        # For HTTPS URL, download first
        response = requests.get(url, stream=True, verify=verify_ssl, timeout=30)
        response.raise_for_status()
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_path = temp_file.name
        
        vr = VideoReader(temp_path, ctx=ctx, width=width, height=height, num_threads=num_threads)
        
        # Clean up temporary files
        os.unlink(temp_path)
        
        return vr

    def decode_next(self, num_frames: int = 1) -> Tuple[List[np.ndarray], List[float]]:
        """
        Decode and return the next n frames at target FPS.
        
        Args:
            num_frames: Number of frames to decode (default: 1)
        
        Returns:
            Two lists:
            - Frame list: video frames (numpy arrays in RGB format)
            - Timestamp list: timestamps (seconds relative to video start)
        """
        if num_frames <= 0:
            return [], []
        
        if self._current_sample_index >= self.total_sampled_frames:
            return [], []
        
        # Calculate frame indices to sample
        end_index = min(self._current_sample_index + num_frames, self.total_sampled_frames)
        frame_indices = []
        
        for i in range(self._current_sample_index, end_index):
            frame_idx = int(i * self.sample_interval)
            frame_indices.append(frame_idx)
        
        if not frame_indices:
            return [], []
        
        with vr_lock:
            try:
                frames = self.vr.get_batch(frame_indices).asnumpy()
                logger.debug('num frames:', len(frames))
            except Exception as e:
                logger.error(f"Error extracting frames: {str(e)}")
                # Return empty list in case of error
                return [], []
        
        # Get timestamps for the frames
        timestamps = []
        for frame_idx in frame_indices:
            # decord returns timestamps in seconds for each frame
            timestamp = self.get_timestamp_with_frame_index(frame_idx)
            timestamps.append(timestamp)
        
        # Update state
        frames_list = [frames[i] for i in range(len(frames))]
        self._current_sample_index += len(frames_list)
        self._current_frame_index = frame_indices[-1] + 1 if frame_indices else self._current_frame_index
        
        return frames_list, timestamps
    
    def decode_all(self) -> Tuple[List[np.ndarray], List[float]]:
        """
        Decode and return all frames at target FPS.
        
        Returns:
            Two lists:
            - Frame list: video frames (numpy arrays in RGB format)
            - Timestamp list: timestamps (seconds relative to video start)
        """
        # Calculate all frame indices to sample
        frame_indices = [int(i * self.sample_interval) for i in range(self.total_sampled_frames)]
        
        if not frame_indices:
            return [], []
        
        # Get all frames at once
        with vr_lock:
            try:
                frames = self.vr.get_batch(frame_indices).asnumpy()
                logger.debug('num frames:', len(frames))
            except Exception as e:
                logger.error(f"Error extracting frames: {str(e)}")
                # Return empty list in case of error
                return [], []
        
        # Get timestamps for all frames
        timestamps = [idx / self.original_fps for idx in frame_indices]
        
        # Update state
        self._current_sample_index = self.total_sampled_frames
        self._current_frame_index = frame_indices[-1] + 1 if frame_indices else 0
        
        return [frames[i] for i in range(len(frames))], timestamps
    
    def reset(self):
        """Reset the decoder to start from the beginning."""
        self._current_frame_index = 0
        self._current_sample_index = 0
    
    def get_video_info(self) -> dict:
        """Get video metadata information."""
        return {
            'video_path': self.video_path,
            'original_width': self.original_width,
            'original_height': self.original_height,
            'original_fps': self.original_fps,
            'sample_fps': self.sample_fps,
            'scaled_width': self.scaled_width,
            'scaled_height': self.scaled_height,
            'longest_side_size': self.longest_side_size,
            'total_frames': self.total_frames,
            'total_sampled_frames': self.total_sampled_frames,
            'duration': self.duration,
            'sample_interval': self.sample_interval
        }
    
    def get_timestamp_with_frame_index(self, frame_index: int) -> float:
        """Get timestamp giving frame index."""
        timestamp = frame_index / self.original_fps
        return timestamp
    
    @property
    def video_path(self) -> str:
        """Get video path."""
        return self._video_path
    
    @property
    def current_frame_index(self) -> int:
        """Get the current original frame index (0-based)."""
        return self._current_frame_index
    
    @property
    def current_sample_index(self) -> int:
        """Get the current sampled frame index (0-based)."""
        return self._current_sample_index
    
    @property
    def total_frames(self) -> Optional[int]:
        """Get total number of original frames."""
        return self._total_frames
    
    @property
    def duration(self) -> Optional[float]:
        """Get video duration in seconds."""
        return self._duration
    
    def __del__(self):
        """Clean up resources when object is destroyed."""
        if hasattr(self, 'vr'):
            try:
                with vr_lock:
                    del self.vr
            except Exception as e:
                print(f"Clean up resources: wait failed with unexpected error: {e}")
