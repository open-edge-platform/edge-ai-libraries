import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("ruptures")
pytest.importorskip("skimage")

from video_chunking.pelt_chunk import PeltChunking


def test_pelt_update_rejects_invalid_input_types():
    chunker = PeltChunking(sample_fps=1)

    with pytest.raises(RuntimeError, match="Invalid input type"):
        chunker.update(frame=np.zeros((2, 2, 3), dtype=np.uint8), timestamp=[0.0])


def test_pelt_update_collects_scores_with_mocked_features(monkeypatch):
    chunker = PeltChunking(sample_fps=1)

    monkeypatch.setattr(chunker, "_init_frame_set", lambda frame: {"value": frame})
    monkeypatch.setattr(chunker, "_calculate_differences", lambda cur, pre: (1.0, 2.0, 3.0))

    chunker.update(frame=[1, 2], timestamp=[0.0, 1.0])

    assert chunker.timestamps == [0.0, 1.0]
    assert chunker.diff_scores == [(1.0, 2.0, 3.0)]
    assert chunker.pre_frame == {"value": 2}


def test_pelt_detect_segments_without_breakpoints(monkeypatch):
    class FakePelt:
        def __init__(self, model: str, min_size: float):
            self.model = model
            self.min_size = min_size

        def fit(self, values):
            return self

        def predict(self, pen: float):
            return []

    chunker = PeltChunking(sample_fps=1)
    monkeypatch.setattr("video_chunking.pelt_chunk.rpt.Pelt", FakePelt)

    segments = chunker._detect_segments(
        combined_scores=np.array([0.1, 0.2]),
        timestamps=[0.0, 1.0, 2.0],
        min_size=1,
        pen=5,
    )

    assert segments == [0.0, 2.0]


def test_pelt_process_returns_chunk_list(monkeypatch):
    chunker = PeltChunking(sample_fps=1, min_avg_duration=0, max_avg_duration=100, max_iteration=1)
    chunker.timestamps = [0.0, 1.0, 2.0]
    chunker.diff_scores = [(0.1, 0.2, 0.3), (0.2, 0.3, 0.4)]

    monkeypatch.setattr(chunker, "_normalize_and_combine", lambda diffs: np.array([0.1, 0.2]))
    monkeypatch.setattr(chunker, "_detect_segments", lambda *args, **kwargs: [0.0, 1.0, 2.0])

    chunks = chunker.process()

    assert len(chunks) == 2
    assert [(c.id, c.time_st, c.time_end) for c in chunks] == [(0, 0.0, 1.0), (1, 1.0, 2.0)]
    assert chunker.timestamps == []
    assert chunker.diff_scores == []
