# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Opt-in speaker options: whole-file diarization, speaker profiles, speaker embeddings.

The default request path (no speaker fields, models.diarization.mode=chunk) must
behave exactly as before; those cases are covered alongside the new behaviour.
"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

for _mod in [
    "torch", "torch.serialization", "torch.torch_version",
    "pyannote", "pyannote.audio", "pyannote.audio.core", "pyannote.audio.core.task",
    "openvino", "openvino_genai",
    "librosa", "soundfile", "sounddevice",
    "whisper", "whispercpp",
]:
    sys.modules.setdefault(_mod, MagicMock())

from fastapi import HTTPException  # noqa: E402

from components.asr.diarization.speaker_profiles import (  # noqa: E402
    SpeakerProfileError,
    build_speaker_options,
    match_speakers,
    parse_speaker_profiles,
)


def _profiles(*items):
    return json.dumps([{"label": label, "embedding": emb} for label, emb in items])


def _options(**kwargs):
    defaults = {"configured_mode": "chunk", "configured_threshold": 0.5, "voice_enrollment_enabled": False}
    return build_speaker_options(**{**defaults, **kwargs})


# ── parsing and validation ──────────────────────────────────────────────────

@pytest.mark.tier1
def test_no_speaker_fields_keep_default_behaviour():
    assert _options() is None
    assert _options(mode="chunk") is not None  # explicit mode is honoured, but stays chunk
    assert _options(mode="chunk").file_mode is False


@pytest.mark.tier1
def test_configured_file_mode_applies_without_fields():
    options = _options(configured_mode="file")
    assert options is not None and options.file_mode
    assert options.labels_requested is False


@pytest.mark.tier1
def test_profiles_are_normalised():
    profiles = parse_speaker_profiles(_profiles(("Doctor", [3, 4])))
    assert profiles[0].label == "Doctor"
    np.testing.assert_allclose(profiles[0].embedding, [0.6, 0.8], rtol=1e-6)


@pytest.mark.tier1
@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"label": "Doctor"}),
        json.dumps([{"label": "", "embedding": [1.0]}]),
        json.dumps([{"label": "Doctor", "embedding": []}]),
        json.dumps([{"label": "Doctor", "embedding": ["a"]}]),
        json.dumps([{"label": "Doctor", "embedding": [0.0, 0.0]}]),
        json.dumps([{"label": "Doctor", "embedding": [True, 1.0]}]),
        _profiles(("Doctor", [1.0, 0.0]), ("Nurse", [1.0, 0.0, 0.0])),
        json.dumps([{"label": "x", "embedding": [1.0]}] * 33),
    ],
)
def test_invalid_profiles_are_rejected(raw):
    with pytest.raises(SpeakerProfileError):
        parse_speaker_profiles(raw)


@pytest.mark.tier1
@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "bogus"},
        {"num_speakers": 2},  # counts need file mode
        {"mode": "file", "num_speakers": 2, "max_speakers": 3},
        {"mode": "file", "min_speakers": 3, "max_speakers": 2},
        {"mode": "file", "num_speakers": 0},
        {"mode": "file", "speaker_match_threshold": 1.5},
        {"unknown_speaker_label": "x" * 65},
    ],
)
def test_invalid_options_are_rejected(kwargs):
    with pytest.raises(SpeakerProfileError):
        _options(**kwargs)


@pytest.mark.tier1
def test_profiles_in_chunk_mode_conflict_with_voice_enrollment():
    with pytest.raises(SpeakerProfileError):
        _options(speaker_profiles=_profiles(("Doctor", [1.0, 0.0])), voice_enrollment_enabled=True)
    assert _options(
        mode="file", speaker_profiles=_profiles(("Doctor", [1.0, 0.0])), voice_enrollment_enabled=True
    ).file_mode


# ── matching ────────────────────────────────────────────────────────────────

@pytest.mark.tier1
def test_match_is_one_to_one_best_first_and_thresholded():
    profiles = parse_speaker_profiles(_profiles(("Doctor", [1.0, 0.0]), ("Nurse", [0.0, 1.0])))
    speakers = {
        "SPEAKER_00": np.array([0.9, 0.1]),   # Doctor
        "SPEAKER_01": np.array([0.95, 0.2]),  # also Doctor-like, but closer -> wins Doctor
        "SPEAKER_02": np.array([-1.0, 0.0]),  # matches nobody
    }
    matches = match_speakers(speakers, profiles, threshold=0.5)
    assert matches["SPEAKER_00"][0] == "Doctor"
    assert "SPEAKER_01" not in matches  # Doctor already taken; Nurse similarity too low
    assert "SPEAKER_02" not in matches


@pytest.mark.tier1
def test_several_samples_per_label_use_the_best():
    profiles = parse_speaker_profiles(_profiles(("Doctor", [1.0, 0.0]), ("Doctor", [0.0, 1.0])))
    matches = match_speakers({"SPEAKER_00": np.array([0.1, 1.0])}, profiles, threshold=0.5)
    assert matches["SPEAKER_00"][0] == "Doctor"
    assert matches["SPEAKER_00"][1] > 0.99


@pytest.mark.tier1
def test_embedding_size_mismatch_is_an_error():
    profiles = parse_speaker_profiles(_profiles(("Doctor", [1.0, 0.0])))
    with pytest.raises(SpeakerProfileError, match="speaker-embedding"):
        match_speakers({"SPEAKER_00": np.array([1.0, 0.0, 0.0])}, profiles, threshold=0.5)


# ── ASRComponent ────────────────────────────────────────────────────────────

class _FakeASR:
    """Per-chunk Whisper segments, times relative to the chunk."""

    def __init__(self, by_chunk):
        self.by_chunk = by_chunk

    def transcribe(self, chunk_path, temperature=0.0, language=None):
        return {"text": "", "segments": [dict(s) for s in self.by_chunk[chunk_path]]}


class _FakeDiarizer:
    voice_enrollment_enabled = False

    def __init__(self, file_result=None, chunk_results=None):
        self.file_result = file_result
        self.chunk_results = chunk_results or {}
        self.file_calls = []
        self.chunk_calls = []

    def diarize_file(self, audio_path, **kwargs):
        self.file_calls.append((audio_path, kwargs))
        return self.file_result

    def diarize(self, chunk_path, session_id=None):
        self.chunk_calls.append(chunk_path)
        return self.chunk_results[chunk_path]


def _component(asr_mod, diarizer, asr, options, tmp_path):
    comp = asr_mod.ASRComponent.__new__(asr_mod.ASRComponent)
    comp.session_id = "s1"
    comp.speaker_scope_id = "s1"
    comp.temperature = 0.0
    comp.enable_diarization = True
    comp.pyannote_diarizer = diarizer
    comp.asr = asr
    comp.all_segments = []
    comp.hallucination_phrase_filter = False
    comp._hallucination_phrases = set()
    comp.repetition_penalty = 1.0
    comp.speaker_options = options
    comp._file_diarization = None
    comp._file_speakers = None
    comp._file_matches = {}
    return comp


CHUNKS = [
    {"chunk_path": "c0.wav", "start_time": 0.0, "end_time": 10.0, "chunk_index": 0},
    {"chunk_path": "c1.wav", "start_time": 10.0, "end_time": 20.0, "chunk_index": 1},
]
WHISPER = {
    "c0.wav": [{"start": 0.0, "end": 4.0, "text": "Good morning, what brings you in?"},
               {"start": 5.5, "end": 9.0, "text": "I have a headache."}],
    "c1.wav": [{"start": 0.0, "end": 1.5, "text": "Since yesterday."},
               {"start": 2.5, "end": 8.0, "text": "Let me check your temperature."}],
}


@pytest.fixture
def asr_mod(tmp_path):
    import components.asr_component as module

    with (
        patch.object(module, "get_session_dir", return_value=str(tmp_path)),
        patch.object(module, "IDENTITY_ENABLED", False),
        patch.object(module.ASRComponent, "_speaker_identity_store", None),
    ):
        yield module


@pytest.mark.tier1
def test_file_mode_labels_speakers_consistently_across_chunks(asr_mod, tmp_path):
    turns = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
        {"start": 5.0, "end": 12.0, "speaker": "SPEAKER_01"},
        {"start": 12.0, "end": 20.0, "speaker": "SPEAKER_00"},
    ]
    embeddings = {"SPEAKER_00": np.array([0.9, 0.1]), "SPEAKER_01": np.array([0.0, 1.0])}
    diarizer = _FakeDiarizer(file_result=(turns, embeddings))
    options = _options(
        mode="file", num_speakers=2, unknown_speaker_label="Patient",
        speaker_profiles=_profiles(("Doctor", [1.0, 0.0])),
    )
    comp = _component(asr_mod, diarizer, _FakeASR(WHISPER), options, tmp_path)

    with (
        patch("components.ffmpeg.audio_preprocessing.get_audio_duration", return_value=20.0),
        patch("components.ffmpeg.audio_preprocessing.process_audio_segment",
              return_value={"chunk_path": "upload.wav", "passthrough": True}),
    ):
        comp.prepare_file_diarization("upload.wav")
        chunks = list(comp.process(iter(CHUNKS)))

    segments = [s for c in chunks for s in c["segments"]]
    assert [s["speaker_label"] for s in segments] == ["Doctor", "Patient", "Patient", "Doctor"]
    assert [s["speaker"] for s in segments] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_01", "SPEAKER_00"]
    assert [s["is_primary"] for s in segments] == [True, False, False, True]
    assert segments[0]["speaker_similarity"] > 0.9 and "speaker_similarity" not in segments[1]
    assert diarizer.file_calls == [("upload.wav", {"num_speakers": 2, "min_speakers": None, "max_speakers": None})]
    assert diarizer.chunk_calls == []
    summary = {s["speaker"]: s for s in comp.speaker_summary()}
    assert summary["SPEAKER_00"]["duration"] == 13.0 and summary["SPEAKER_00"]["speaker_label"] == "Doctor"
    assert summary["SPEAKER_01"]["speaker_label"] == "Patient"


@pytest.mark.tier1
def test_default_chunk_mode_is_unchanged(asr_mod, tmp_path):
    chunk_turns = {
        "c0.wav": ([{"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
                    {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"}], {}),
        "c1.wav": ([{"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"}], {}),
    }
    diarizer = _FakeDiarizer(chunk_results=chunk_turns)
    comp = _component(asr_mod, diarizer, _FakeASR(WHISPER), None, tmp_path)

    comp.prepare_file_diarization("upload.wav")  # no-op without options
    chunks = list(comp.process(iter(CHUNKS)))

    segments = [s for c in chunks for s in c["segments"]]
    assert diarizer.file_calls == []
    assert diarizer.chunk_calls == ["c0.wav", "c1.wav"]
    assert [s["speaker"] for s in segments] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00", "SPEAKER_00"]
    assert all(set(s) == {"text", "start", "end", "speaker", "is_primary"} for s in segments)
    assert comp.speaker_summary() is None


@pytest.mark.tier1
def test_chunk_mode_profiles_label_each_chunk(asr_mod, tmp_path):
    chunk_turns = {
        "c0.wav": ([{"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
                    {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"}],
                   {"SPEAKER_00": np.array([1.0, 0.0]), "SPEAKER_01": np.array([0.0, 1.0])}),
        # pyannote's local labels swap in the next chunk; the profile label follows the voice.
        "c1.wav": ([{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
                    {"start": 2.0, "end": 10.0, "speaker": "SPEAKER_01"}],
                   {"SPEAKER_00": np.array([0.0, 1.0]), "SPEAKER_01": np.array([1.0, 0.1])}),
    }
    options = _options(speaker_profiles=_profiles(("Doctor", [1.0, 0.0])), unknown_speaker_label="Patient")
    comp = _component(asr_mod, _FakeDiarizer(chunk_results=chunk_turns), _FakeASR(WHISPER), options, tmp_path)

    segments = [s for c in comp.process(iter(CHUNKS)) for s in c["segments"]]
    assert [s["speaker_label"] for s in segments] == ["Doctor", "Patient", "Patient", "Doctor"]
    assert [s["is_primary"] for s in segments] == [False] * 4  # kiosk identity store is untouched


# ── API layer ───────────────────────────────────────────────────────────────

def _api_cfg(diarization: bool, mode: str = "chunk"):
    return SimpleNamespace(models=SimpleNamespace(
        asr=SimpleNamespace(diarization=diarization),
        diarization=SimpleNamespace(
            mode=mode, speaker_match_threshold=0.5, voice_enrollment_enabled=False,
            name="pyannote/speaker-diarization-community-1",
        ),
    ))


@pytest.mark.tier1
def test_speaker_fields_need_diarization():
    import api.openai_endpoints as endpoints

    with patch.object(endpoints, "config", _api_cfg(diarization=False)):
        with pytest.raises(HTTPException) as exc:
            endpoints._speaker_options(None, mode="file")
        assert exc.value.status_code == 400
        # A deployment default of mode=file is ignored when diarization is off.
    with patch.object(endpoints, "config", _api_cfg(diarization=False, mode="file")):
        assert endpoints._speaker_options(None, mode=None) is None
    with patch.object(endpoints, "config", _api_cfg(diarization=True)):
        assert endpoints._speaker_options(None, mode=None) is None
        with pytest.raises(HTTPException) as exc:
            endpoints._speaker_options(False, mode="file")
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            endpoints._speaker_options(None, speaker_profiles="nope")
        assert exc.value.status_code == 400


@pytest.mark.tier1
def test_auto_language_means_detect():
    from dto.transcription_dto import validate_transcription_options

    assert validate_transcription_options(temperature=0.0, language="auto")[0] is None
    assert validate_transcription_options(temperature=0.0, language="AUTO")[0] is None
    assert validate_transcription_options(temperature=0.0, language="en")[0] == "en"


@pytest.mark.tier1
def test_verbose_segment_carries_speaker_label():
    from pipeline import Pipeline

    pipeline = Pipeline.__new__(Pipeline)
    pipeline.temperature = 0.0
    segment = {"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_00", "is_primary": True,
               "speaker_label": "Doctor", "speaker_similarity": 0.8}
    verbose = pipeline._build_verbose_segment(0, segment, include_speaker=True)
    assert verbose["speaker_label"] == "Doctor" and verbose["speaker_similarity"] == 0.8
    plain = pipeline._build_verbose_segment(0, {"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_00"},
                                            include_speaker=True)
    assert "speaker_label" not in plain and "is_primary" not in plain


@pytest.mark.tier1
def test_speaker_embedding_endpoint(tmp_path):
    import api.custom_endpoints as endpoints

    diarizer = MagicMock()
    diarizer.compute_speaker_embedding.return_value = np.array([0.6, 0.8], dtype=np.float32)
    common = (
        patch.object(endpoints, "config", _api_cfg(diarization=True)),
        patch.object(endpoints, "save_audio_file", return_value=("s.wav", str(tmp_path / "s.wav"))),
        patch.object(endpoints, "get_session_dir", return_value=str(tmp_path / "session")),
        patch("components.ffmpeg.audio_preprocessing.process_audio_segment",
              return_value={"chunk_path": str(tmp_path / "s.wav"), "passthrough": True}),
        patch("components.asr_component.ASRComponent.get_shared_diarizer", return_value=diarizer),
    )
    with common[0], common[1], common[2], common[3], common[4], \
            patch("components.ffmpeg.audio_preprocessing.get_audio_duration", return_value=4.0), \
            patch.object(endpoints.shutil, "rmtree") as rmtree:
        response = endpoints.speaker_embedding(file=MagicMock())
    body = json.loads(response.body)
    assert body["dim"] == 2 and body["embedding"] == [0.6, 0.8] and body["duration"] == 4.0
    assert body["model"] == "pyannote/speaker-diarization-community-1"
    rmtree.assert_called_once()  # the sample is never kept

    with common[0], common[1], common[2], common[3], common[4], \
            patch("components.ffmpeg.audio_preprocessing.get_audio_duration", return_value=0.5), \
            patch.object(endpoints.shutil, "rmtree"):
        with pytest.raises(HTTPException) as exc:
            endpoints.speaker_embedding(file=MagicMock())
    assert exc.value.status_code == 400

    diarizer.compute_speaker_embedding.return_value = None
    with common[0], common[1], common[2], common[3], common[4], \
            patch("components.ffmpeg.audio_preprocessing.get_audio_duration", return_value=4.0), \
            patch.object(endpoints.shutil, "rmtree"):
        with pytest.raises(HTTPException) as exc:
            endpoints.speaker_embedding(file=MagicMock())
    assert exc.value.status_code == 422

    with patch.object(endpoints, "config", _api_cfg(diarization=False)):
        with pytest.raises(HTTPException) as exc:
            endpoints.speaker_embedding(file=MagicMock())
    assert exc.value.status_code == 400
