import numpy as np

import video_chunking.base_chunk as base_chunk_mod
from video_chunking.base_chunk import BaseChunking


class DummyChunking(BaseChunking):
    def chunk(self, video_input: str):
        return []

    def update(self, **kwargs):
        return None

    def process(self):
        return []


class FakeDecoder:
    def __init__(self, video_path: str, sample_fps: int, longest_side_size: int):
        self.video_path = video_path
        self.sample_fps = sample_fps
        self.longest_side_size = longest_side_size
        self.total_frames = 4

    def decode_all(self):
        return [np.zeros((2, 2, 3), dtype=np.uint8)], [0.0]

    def decode_next(self, num_frames: int):
        return [np.zeros((2, 2, 3), dtype=np.uint8)] * num_frames, [0.0] * num_frames


def test_format_chunks_sets_expected_fields():
    chunker = DummyChunking(sample_fps=2)
    chunk = chunker.format_chunks(start_time=1.0, end_time=3.0)

    assert chunk.fps == 2
    assert chunk.time_st == 1.0
    assert chunk.time_end == 3.0
    assert "Micro chunk" in chunk.desc


def test_load_decoder_reuses_and_reloads(monkeypatch):
    chunker = DummyChunking(sample_fps=1, max_frame_size=128)

    monkeypatch.setattr(base_chunk_mod, "VIDEO_READER_BACKENDS", {"fake": FakeDecoder})
    monkeypatch.setattr(base_chunk_mod, "get_video_reader_backend", lambda: "fake")

    decoder_a = chunker._load_decoder("video_a.mp4")
    decoder_a_again = chunker._load_decoder("video_a.mp4")
    decoder_b = chunker._load_decoder("video_b.mp4")

    assert decoder_a is decoder_a_again
    assert decoder_b is not decoder_a
    assert decoder_b.video_path == "video_b.mp4"
