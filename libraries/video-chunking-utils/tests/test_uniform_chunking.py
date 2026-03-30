import numpy as np

from video_chunking.uniform_chunk import UniformChunking


class FakeUniformDecoder:
    def __init__(self, total_frames: int):
        self.total_frames = total_frames

    def get_timestamp_with_frame_index(self, index: int) -> float:
        return float(index)


def test_uniform_chunk_generates_expected_segments(monkeypatch):
    chunker = UniformChunking(chunk_duration=2, sample_fps=1)
    chunker.decoder = FakeUniformDecoder(total_frames=5)

    monkeypatch.setattr(chunker, "get_video_total_nframes", lambda _: 5)

    chunks = chunker.chunk("dummy.mp4")

    assert len(chunks) == 2
    assert [(c.id, c.time_st, c.time_end) for c in chunks] == [(0, 0.0, 2.0), (1, 2.0, 4.0)]
    assert all(c.level == 0 for c in chunks)


def test_uniform_update_accepts_single_frame_and_timestamp():
    chunker = UniformChunking(chunk_duration=1, sample_fps=1)
    chunker.decoder = FakeUniformDecoder(total_frames=1)

    chunker.update(np.zeros((1, 1, 3), dtype=np.uint8), 0.0)
    output = chunker.process()

    assert len(output) == 1
    assert output[0].id == 0


def test_uniform_process_clears_internal_buffer():
    chunker = UniformChunking(chunk_duration=10, sample_fps=1)
    chunker.listMicroChunk = [chunker.format_chunks(0.0, 1.0)]

    first = chunker.process()
    second = chunker.process()

    assert len(first) == 1
    assert second == []
