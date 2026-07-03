import re
import os
import io
import base64
import gzip
from typing import List, Dict, Optional
import requests

from video_chunking.data import ChunkMeta

'''
RST example:

1
00:00:01,067 --> 00:00:04,994
Everybody! Central Perk
is proud to present...

2
00:00:05,205 --> 00:00:09,141
(Rachel:)...the music of Miss Phoebe Buffay.

3
00:00:11,711 --> 00:00:12,700
Thanks.

4
00:00:13,179 --> 00:00:16,637
I wanna start with a song
that's about that moment...

5
00:00:16,850 --> 00:00:21,184
(Phoebe:)...when you suddenly realize
what life is really all about.

6
00:00:21,388 --> 00:00:23,788
Okay, here we go.
...
'''

def parse_timestamp(timestamp_str):
    """Convert a timestamp string to seconds"""
    # format: 00:00:01,067
    time_part, millis_part = timestamp_str.split(',')
    hours, minutes, seconds = map(int, time_part.split(':'))
    millis = int(millis_part)
    total_seconds = hours * 3600 + minutes * 60 + seconds + millis / 1000.0
    return total_seconds

def parse_subtitle_text(content: str) -> List[Dict]:
    """Parse SRT text content into a list of subtitle dicts."""
    subtitles = []
    # Regex for blocks: Number\nStart --> End\nText (until next block)
    pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\d+\n|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    # Validate SubRip format (must have at least one valid block)
    if not matches:
        raise ValueError("Invalid subtitles format: expected SubRip (SRT) with "
                         "numbered blocks and 'HH:MM:SS,mmm --> HH:MM:SS,mmm' timestamps")

    for match in matches:
        subtitle_id = int(match[0])
        start_time = parse_timestamp(match[1])
        end_time = parse_timestamp(match[2])
        text = match[3].strip()
        subtitles.append({
            'id': subtitle_id,
            'start': start_time,
            'end': end_time,
            'text': text
        })
    return subtitles

def load_subtitles(input, max_bytes: int = 10 * 1024 * 1024) -> List[Dict]:
    """
    Load subtitles from:
      - dict: {"url": str} | {"text": str} | {"b64gzip": str}
      - local file path: str
    Returns a parsed list of subtitle entries.
    """
    def _assert_size(s: str):
        if len(s.encode("utf-8")) > max_bytes:
            raise ValueError(f"Subtitle payload too large (> {max_bytes} bytes)")

    # dict input
    if isinstance(input, dict):
        if "url" in input and input["url"]:
            url = input["url"]
            if not url.startswith(("http://", "https://")):
                raise ValueError("Subtitle URL must be http/https")

            # Stream download with size cap
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                buf = io.BytesIO()
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    buf.write(chunk)
                    if buf.tell() > max_bytes:
                        raise ValueError(f"Subtitle download exceeds {max_bytes} bytes")
                content = buf.getvalue().decode("utf-8", errors="replace")
                return parse_subtitle_text(content)

        if "b64gzip" in input and input["b64gzip"]:
            raw = base64.b64decode(input["b64gzip"])
            content = gzip.decompress(raw).decode("utf-8", errors="replace")
            _assert_size(content)
            return parse_subtitle_text(content)

        if "text" in input and input["text"]:
            content = input["text"]
            _assert_size(content)
            return parse_subtitle_text(content)

        # Empty or unsupported dict
        return []

    # string input as local file path
    if isinstance(input, str):
        # Read local file and parse
        if not os.path.exists(input):
            raise FileNotFoundError(f"Subtitle file not found: {input}")
        with open(input, 'r', encoding='utf-8') as f:
            content = f.read()
        _assert_size(content)
        return parse_subtitle_text(content)

    raise TypeError("Unsupported subtitles input type. Expect dict or str.")

def parse_subtitle_file(filename, root_dir=None):
    """Parse subtitle file and return subtitle list
    Return:
    
    [
        {
            'id':
            'start':
            'end':
            'text':
        },
        ...
    ]
    """
    
    if root_dir is not None:
        filename = os.path.join(root_dir, filename)
    
    subtitles = []
    
    with open(filename, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Use regular expressions to match subtitle blocks
    # Format: Number\nStart Time --> End Time\nContent
    pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\d+\n|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    for match in matches:
        subtitle_id = int(match[0])
        start_time = parse_timestamp(match[1])
        end_time = parse_timestamp(match[2])
        text = match[3].strip()
        
        subtitles.append({
            'id': subtitle_id,
            'start': start_time,
            'end': end_time,
            'text': text
        })
    
    return subtitles

def calculate_overlap_ratio(seg_start, seg_end, sub_start, sub_end):
    """Calculate the time range overlap ratio"""
    overlap_start = max(seg_start, sub_start)
    overlap_end = min(seg_end, sub_end)
    
    if overlap_start >= overlap_end:
        return 0.0
    
    overlap_duration = overlap_end - overlap_start
    subtitle_duration = sub_end - sub_start
    
    return overlap_duration / subtitle_duration

def extract_subtitles_for_chunk(chunk: ChunkMeta, subtitles: list, overlap_threshold=0.5):
    
    seg_start = chunk.time_st
    seg_end = chunk.time_end
    
    chunk_texts = []
    
    for index, subtitle in enumerate(subtitles):
        sub_start = subtitle['start']
        sub_end = subtitle['end']
        
        # Calculate overlap ratio
        overlap_ratio = calculate_overlap_ratio(seg_start, seg_end, sub_start, sub_end)
        
        # If the overlap ratio exceeds the threshold, it is considered to be the subtitle of the chunk.
        if overlap_ratio > overlap_threshold:
            chunk_texts.append({
                'id': subtitle['id'],
                'text': subtitle['text'],
                'overlap_ratio': overlap_ratio
            })
        
        if sub_start > seg_end:
            break
    
    # Sort by subtitle ID
    chunk_texts.sort(key=lambda x: x['id'])
    
    chunk_subtitles = {
        'start_time': seg_start,
        'end_time': seg_end,
        'subtitles': chunk_texts,
        'full_text': '\n'.join([sub['text'] for sub in chunk_texts])
    }
    
    return chunk_subtitles

def format_time(seconds):
    """Format seconds as a time string"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
