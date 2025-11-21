# A Python Module for Video Chunking Utils

## Introduction
This is a Python module designed for video chunking. It allows users to split video files into smaller, manageable segments. The module is designed to be easily installable via pip and can be used in various applications such as video processing, analysis, and content delivery.

## Installation
To install the module, simply run the following command in your terminal:
```bash
cd ./video-chunking-utils
pip install .
```
> Note: If you are using a virtual environment, you can install the module within the environment to avoid conflicts with other packages.

## Usage
Once installed, you can use the module in your Python scripts. 

### Method: Uniform Chunking

```python
from video_chunking import UniformChunking

# Specify the input video file and output directory
input_video = "input.mp4"
## also support http(s) video file
# input_video = "https://videos.pexels.com/video-files/5992517/5992517-hd_1920_1080_30fps.mp4"

# Chunk the video
# 10 seconds per chunk
video_chunker = UniformChunking(chunk_duration=10)
micro_chunks_list = video_chunker.chunk(input_video)
for i, micro_chunk in enumerate(micro_chunks_list):
    print(f'[chunk-{i}]{micro_chunk.time_st}-{micro_chunk.time_end}')
print(f"Total {len(micro_chunks_list)} chunks are generated.")
```

### Method:  Pelt Chunking

```python
from video_chunking import PeltChunking

# Specify the input video file and output directory
input_video = "input.mp4"

# Chunk the video based on scene switch
# average 10~45 seconds per chunk
video_chunker = PeltChunking(sample_fps=5, max_frame_size=512,
                             min_avg_duration=10,
                             max_avg_duration=45)
micro_chunks_list = video_chunker.chunk(input_video)
for i, micro_chunk in enumerate(micro_chunks_list):
    print(f'[chunk-{i}]{micro_chunk.time_st}-{micro_chunk.time_end}')
print(f"Total {len(micro_chunks_list)} chunks are generated.")
```

### ChunkMeta Data Structure
The `MicroChunkMeta` serves as a class for video chunks return type, providing metadata for each chunk. It defines several attributes that describe the properties of a video chunk.

```python
from video_chunking.data import MicroChunkMeta
```
**Attributes:**
- **desc:** str
A description of the chunk (e.g., a brief summary or purpose of the chunk).

- **fps:** float
The frames per second (FPS) of the video in the chunk.

- **id:** int
A unique identifier for the chunk.

- **level:** int
The hierarchy level of the chunk (e.g., 0 for micro, 1 for macro, 2 for root).

- **time_st:** float
The start time of the chunk in seconds.

- **time_end:** float
The end time of the chunk in seconds.

## Other Resources

- [Release Notes](./release-notes.md): Information on the latest release, improvements, and bug fixes.
