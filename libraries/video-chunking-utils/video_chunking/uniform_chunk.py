import logging
import numpy as np

from video_chunking.data import MicroChunkMeta
from video_chunking.base_chunk import BaseChunking

logger = logging.getLogger(__name__)


class UniformChunking(BaseChunking):
    
    METHOD_NAME = "uniform"

    def __init__(
        self,
        chunk_duration: float = 10,
        **kwargs
    ):
        """Creates a Video Chunking object.
        Args:
            chunk_duration: duration for each chunk
        """
        super().__init__(**kwargs)
        
        self.chunk_duration = chunk_duration
        
        self.frame_id = 0
        self.chunk_id = 0
        
        # Store all micro chunk metas that are not consumed in process()
        self.listMicroChunk = []
        
        # The end time of previous chunk
        self.pre_time_segment = 0
        
    
    def chunk(self,
              video_input: str,
              ) -> list[MicroChunkMeta]:
        """
        Process video chunking with video_input
        Args:
            video_input: the path of video. support "file://", "http://", "https://" and local path.
        Return:
            list[MicroChunkMeta], A list of micro chunk metadata
        """        
        total_frames = self.get_video_total_nframes(video_input)
        dummy_frames = [np.zeros(1) for _ in range(total_frames)]
        timestamps = [self.decoder.get_timestamp_with_frame_index(i) for i in range(total_frames)]
        self.update(dummy_frames, timestamps)
        
        # Achieve end of video, start to detect change points
        # return all micro chunks
        return self.process()
    
    def update(self, 
               frames: np.ndarray | list[np.ndarray],
               timestamps: float | list[float]):
        """
        Uniformly sample frames for each chunk
        """
        if isinstance(frames, np.ndarray):
            frames = [frames]
        if isinstance(frames, float):
            timestamps = [timestamps]

        for (dummy_frame, timestamp) in zip(frames, timestamps):
            chunk_id = int(timestamp // self.chunk_duration)
            
            if (chunk_id != self.chunk_id) or \
                (self.frame_id == (self.decoder.total_frames - 1)):
                # Coming new chunk OR flush remaining frames in last chunk
                
                # close current chunk
                micro_chunk = self.format_chunks(start_time=self.pre_time_segment, end_time=timestamp)
                micro_chunk.id = self.chunk_id
                micro_chunk.level = 0
                self.listMicroChunk.append(micro_chunk)
                self.pre_time_segment = timestamp
                
                # then start a new chunk
                self.chunk_id = chunk_id

            self.frame_id += 1
    
    def process(self) -> list[MicroChunkMeta]:
        """
        Return:
            list[MicroChunkMeta], A list of micro chunk metadata
        """
        # TODO: flush remaining frames
        publish_metas = self.listMicroChunk
        self.listMicroChunk = []
        
        return publish_metas
        