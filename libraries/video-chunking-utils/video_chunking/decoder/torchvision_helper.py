import numpy as np
from torchvision.io import read_video
from torchvision.transforms import functional as F
from typing import List, Tuple, Optional

from video_chunking.decoder import BaseVideoDecoder


class TorchVisionVideoDecoder(BaseVideoDecoder):
    def __init__(self, video_path: str, sample_fps: float, longest_side_size: Optional[int] = None):
        """
        Initialize torchvision video decoder with specified sampling frame rate.
        
        Args:
            video_path: Path to video file
            sample_fps: Target sampling frame rate (frames per second)
            longest_side_size: resize to ensure longest side is as configured
        """
        
        self._video_path = video_path
        self.sample_fps = sample_fps
        self.longest_side_size = longest_side_size
        
        # Read entire video
        self.video_frames, _, info = read_video(video_path, pts_unit='sec', output_format='TCHW')
        
        # Get video information
        self.original_fps = info['video_fps']
        self._total_frames = len(self.video_frames)
        self._duration = self._total_frames / self.original_fps if self._total_frames else None
        
        # Get original dimensions from first frame
        first_frame = self.video_frames[0]
        _, self.original_height, self.original_width = first_frame.shape
        
        # Calculate resize parameters if needed
        self.resize_size = None
        if longest_side_size is not None:
            max_side = max(self.original_height, self.original_width)
            if max_side > longest_side_size:
                scale = longest_side_size / max_side
                new_height = int(self.original_height * scale)
                new_width = int(self.original_width * scale)
                self.resize_size = (new_height, new_width)
                self.scaled_height, self.scaled_width = self.resize_size
            else:
                self.scaled_height, self.scaled_width = self.original_height, self.original_width
        else:
            self.scaled_height, self.scaled_width = self.original_height, self.original_width
        
        # Calculate sampling parameters
        self.sample_interval = 1.0 / sample_fps
        self.frame_interval = 1.0 / self.original_fps
        
        # Precompute all target timestamps
        self.target_timestamps = [self.get_timestamp_with_frame_index(i) for i in range(int(self._duration * sample_fps) + 1)]
        
        # Precompute frame indices for each target timestamp
        self.target_frame_indices = []
        for target_ts in self.target_timestamps:
            frame_idx = int(target_ts * self.original_fps)
            if frame_idx < self._total_frames:
                self.target_frame_indices.append(frame_idx)
        
        self.total_sampled_frames = len(self.target_frame_indices)
        
        # Initialize state variables
        self._current_sample_index = 0
        self._current_frame_index = 0
        self._resize_transform = F.resize if self.resize_size else None
    
    def _process_frame(self, frame):
        """Process a single frame (resize and convert format)."""
        from torchvision.transforms import functional as F
        
        if self.resize_size is not None:
            frame = F.resize(frame.unsqueeze(0), self.resize_size, 
                           interpolation=F.InterpolationMode.BILINEAR)
            frame = frame.squeeze(0)
        
        # Convert from CHW to HWC and then to numpy
        return frame.numpy().transpose(1, 2, 0)
    
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
        
        # Calculate end index
        end_index = min(self._current_sample_index + num_frames, self.total_sampled_frames)
        
        frames = []
        timestamps = []
        
        for sample_idx in range(self._current_sample_index, end_index):
            frame_idx = self.target_frame_indices[sample_idx]
            
            if frame_idx < self._total_frames:
                frame = self.video_frames[frame_idx]
                processed_frame = self._process_frame(frame)
                
                frames.append(processed_frame)
                timestamps.append(self.target_timestamps[sample_idx])
                
                # Update the current frame index to the last processed frame
                self._current_frame_index = frame_idx
        
        # Update state
        self._current_sample_index = end_index
        
        return frames, timestamps
    
    def decode_all(self) -> Tuple[List[np.ndarray], List[float]]:
        """
        Decode and return all frames at target FPS.
        
        Returns:
            Two lists:
            - Frame list: video frames (numpy arrays in RGB format)
            - Timestamp list: timestamps (seconds relative to video start)
        """
        frames = []
        timestamps = []
        
        for sample_idx in range(self.total_sampled_frames):
            frame_idx = self.target_frame_indices[sample_idx]
            
            if frame_idx < self._total_frames:
                frame = self.video_frames[frame_idx]
                processed_frame = self._process_frame(frame)
                
                frames.append(processed_frame)
                timestamps.append(self.target_timestamps[sample_idx])
        
        # Update state
        self._current_sample_index = self.total_sampled_frames
        self._current_frame_index = self.target_frame_indices[-1] if self.target_frame_indices else 0
        
        return frames, timestamps
    
    def reset(self):
        """Reset the decoder to start from the beginning."""
        self._current_sample_index = 0
        self._current_frame_index = 0
    
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
            'sample_interval': self.sample_interval,
            'frame_interval': self.frame_interval
        }
    
    def get_timestamp_with_frame_index(self, frame_index: int) -> float:
        """Get timestamp giving frame index."""
        timestamp = frame_index * self.sample_interval
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
        # Torch tensors will be automatically garbage collected
        pass