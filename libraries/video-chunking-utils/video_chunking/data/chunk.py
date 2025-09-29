"""
Chunk data structures for video.
"""
from typing import List, Optional, Any

class ChunkMeta:
    """Base class for video chunks."""
    
    def __init__(self):
        self.desc: str = ""             # Description of the chunk
        self.fps: float = 0             # Frames per second
        self.id: int = 0                # Chunk ID
        self.level: int = 0             # Hierarchy level (0 for micro, 1 for macro, 2 for root)
        self.time_st: float = 0         # Start time in seconds
        self.time_end: float = 0        # End time in seconds
    
    def get_timestamp_desc(self) -> str:
        """
        Get the timestamp description for this chunk.
        
        Returns:
            Formatted timestamp string
        """
        time_description = f"Start time: {round(self.time_st)} sec\nEnd time: {round(self.time_end)} sec"
        return time_description


class MicroChunkMeta(ChunkMeta):
    """Micro chunk representing a level-0 segment of video."""
    
    def __init__(self):
        super().__init__()
        self.desc: str = ""
        self.fps: float = 0


class MacroChunkMeta(ChunkMeta):
    """Macro chunk containing multiple micro chunks."""
    
    def __init__(self):
        super().__init__()
        self.desc: str = ""
        self.fps: float = 0
        self.num_subchunk: int = 0
        self.chunk_list: List[ChunkMeta] = []
