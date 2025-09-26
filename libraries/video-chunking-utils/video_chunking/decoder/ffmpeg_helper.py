import numpy as np
from typing import List, Tuple, Optional    

from video_chunking.decoder import BaseVideoDecoder


class FFmpegVideoDecoder(BaseVideoDecoder):
    def __init__(self, video_path: str, sample_fps: float, longest_side_size: Optional[int] = None):
        """
        Initialize video decoder with specified sampling frame rate.
        
        Args:
            video_path: the path of video. support "file://", "http://", "https://" and local path.
            sample_fps: target sampling frame rate (frames per second)
            longest_side_size: resize to ensure longest side is as configured
        """
        import ffmpeg
        self._video_path = self._validate_video_path(video_path)
        self.sample_fps = sample_fps
        self.longest_side_size = longest_side_size
        
        # Get video info
        probe = ffmpeg.probe(video_path)
        video_info = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
        if not video_info:
            raise ValueError("No video stream found")

        self.width = int(video_info['width'])
        self.height = int(video_info['height'])
        self.original_fps = eval(video_info['avg_frame_rate'])
        
        # Try to get total frames and duration
        try:
            self._total_frames = int(video_info.get('nb_frames', 0))
            self._duration = float(video_info.get('duration', 0))
        except (ValueError, TypeError):
            self._total_frames = None
            self._duration = None
        
        # Calculate frame interval (seconds)
        self.frame_interval = 1.0 / sample_fps
        
        # Calculate scale factor
        self.scale_factor = 1
        if longest_side_size is not None:
            self.scale_factor = min(longest_side_size / self.width, longest_side_size / self.height, 1.0)
        self.new_width = int(self.width * self.scale_factor)
        self.new_height = int(self.height * self.scale_factor)
        
        # Initialize process and state variables
        self.process = None
        self._current_frame_index = 0
        self.all_frames_decoded = False
    
    def _validate_video_path(self, video_path):
        if "http://" in video_path or "https://" in video_path:
            pass
        elif "file://" in video_path:
            video_path = video_path[7:]
        else:
            from pathlib import Path
            path = Path(video_path).expanduser().resolve()
            if not str(path).startswith("/"):
                raise NotImplementedError("Unsupported video input, support 'file://', 'http://', 'https://' and local path")
        return video_path
    
    def _initialize_process(self):
        """Initialize the ffmpeg process if not already done."""
        import ffmpeg
        if self.process is None:
            self.process = (
                ffmpeg
                .input(self._video_path)
                .filter('fps', fps=self.sample_fps)
                .filter('scale', self.new_width, self.new_height)
                .output('pipe:', format='rawvideo', pix_fmt='rgb24')
                .run_async(pipe_stdout=True, pipe_stderr=True)
            )
    
    def decode_next(self, num_frames: int = 1) -> Tuple[List[np.ndarray], List[float]]:
        """
        Decode and return the next n frames.
        
        Args:
            num_frames: Number of frames to decode (default: 1)
        
        Returns:
            Two lists:
            - Frame list: video frames (numpy arrays in RGB format)
            - Timestamp list: timestamps (seconds relative to video start)
        """
        if num_frames <= 0:
            return [], []
        
        self._initialize_process()
        
        frames = []
        timestamps = []
        
        # If all frames already decoded, return empty lists
        if self.all_frames_decoded:
            return [], []
        
        # Read requested number of frames
        for _ in range(num_frames):
            # Read frame from ffmpeg process
            in_bytes = self.process.stdout.read(self.new_width * self.new_height * 3)
            if not in_bytes:
                self.all_frames_decoded = True
                self.process.stdout.close()
                self.process.wait()
                break
            
            # Convert to numpy array and calculate timestamp
            frame = np.frombuffer(in_bytes, np.uint8).reshape([self.new_height, self.new_width, 3])
            timestamp = self.get_timestamp_with_frame_index(self._current_frame_index)
            
            frames.append(frame)
            timestamps.append(timestamp)
            self._current_frame_index += 1
        
        return frames, timestamps
    
    def decode_all(self) -> Tuple[List[np.ndarray], List[float]]:
        """
        Decode and return all frames at once.
        
        Returns:
            Two lists:
            - Frame list: video frames (numpy arrays in RGB format)
            - Timestamp list: timestamps (seconds relative to video start)
        """
        self._initialize_process()
        
        frames = []
        timestamps = []
        
        while True:
            # Read frames in chunks for efficiency
            chunk_frames, chunk_timestamps = self.decode_next(10)  # Read 10 frames at a time
            if not chunk_frames:
                break
            frames.extend(chunk_frames)
            timestamps.extend(chunk_timestamps)
        
        return frames, timestamps
    
    def reset(self):
        """Reset the decoder to start from the beginning."""
        if self.process is not None:
            self.process.stdout.close()
            self.process.wait()
            self.process = None
        
        self._current_frame_index = 0
        self.all_frames_decoded = False
    
    def get_video_info(self) -> dict:
        """Get video metadata information."""
        return {
            'video_path': self.video_path,
            'original_width': self.width,
            'original_height': self.height,
            'original_fps': self.original_fps,
            'sample_fps': self.sample_fps,
            'scaled_width': self.new_width,
            'scaled_height': self.new_height,
            'scale_factor': self.scale_factor,
            'longest_side_size': self.longest_side_size,
            'total_frames': self.total_frames,
            'duration': self.duration
        }
    
    def get_timestamp_with_frame_index(self, frame_index: int) -> float:
        """Get timestamp giving frame index."""
        timestamp = frame_index * self.frame_interval
        return timestamp
    
    @property
    def video_path(self) -> str:
        """Get video path."""
        return self._video_path
    
    @property
    def current_frame_index(self) -> int:
        """Get the current frame index (0-based)."""
        return self._current_frame_index
    
    @property
    def total_frames(self) -> Optional[int]:
        """Get total number of frames if available, otherwise None."""
        return self._total_frames
    
    @property
    def duration(self) -> Optional[float]:
        """Get video duration in seconds if available, otherwise None."""
        return self._duration
    
    def __del__(self):
        """Clean up resources when object is destroyed."""
        if self.process is not None:
            try:
                self.process.stdout.close()
                self.process.wait()
            except:
                pass
