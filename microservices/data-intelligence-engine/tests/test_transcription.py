# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Transcribing a recording in the background, and what that makes findable.

An audio file has no vector of its own -- no model embeds sound -- so the
transcript is the whole of what a query can match. The job runs after ingest
and may be retried, so most properties here are about a second run: it must
replace the transcript rather than append one, must not revert an ingest that
landed in between, and a failure must be visible on the asset.
"""

from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

import config
from assetlib.content import asset_key
from core.content import (
    AUDIO,
    ROLE_AUDIO,
    ROLE_IMAGE,
    ROLE_L2_TRANSCRIPT,
    TEXT,
    ContentBlock,
    ContentStream,
)
from core.indexer import MultimodalIndexer
from core.multimodal import asr, coverage, registry, transcription
from core.multimodal.asr import Segment

from tests.test_captioning import FakeLibrary, pool_with


class FakeTranscriber:
    def __init__(self, segments=None, error=None):
        self.segments = segments if segments is not None else [
            Segment(0.0, 3.1, "不排除购房者可以在互联网上下单。"),
            Segment(3.1, 5.0, "行业集中度加速提高。"),
        ]
        self.error = error
        self.calls = 0

    def transcribe(self, path):
        self.calls += 1
        if self.error:
            raise asr.TranscriptionError(self.error)
        return self.segments


def _stream(asset_id="a1", role=ROLE_AUDIO, blocks=None, **metadata):
    media = ContentBlock(
        block_id=f"{asset_id}:0",
        kind=AUDIO,
        media_key="file:///tmp/a1.wav",
        caption="a1",
        metadata={"role": role},
    )
    return ContentStream(
        asset_id=asset_id,
        blocks=[media] + list(blocks or []),
        metadata={"file_name": "a1.wav", "asset_id": asset_id, **metadata},
    )


def _setup(stream=None):
    stream = stream or _stream()
    asset = SimpleNamespace(
        asset_id=stream.asset_id,
        content=stream,
        cached=stream,
        content_source_id="object-1",
        content_key=asset_key(stream.asset_id),
        media_path=lambda _key, _suffix=".wav": nullcontext("/tmp/a1.wav"),
    )
    return FakeLibrary(asset, stream), asset


def _stored(library, asset):
    return ContentStream.from_record(library.content_store.records[asset.content_key])


def _transcripts(stream):
    prefix = transcription.transcript_block_prefix(stream.asset_id)
    return [block for block in stream.ordered() if block.block_id.startswith(prefix)]


@pytest.fixture(autouse=True)
def _asr_enabled(monkeypatch):
    monkeypatch.setattr(config, "ASR_ENABLED", True)


# --- the job --------------------------------------------------------------------


def test_speech_becomes_timed_transcript_blocks_pointing_back_at_the_recording():
    library, asset = _setup()
    library.asset_pools = {"p": pool_with("a1", gme={ROLE_L2_TRANSCRIPT})}

    status = transcription.transcribe_asset(library, "a1", FakeTranscriber())

    blocks = _transcripts(_stored(library, asset))
    assert status == transcription.STATUS_COMPLETED
    assert [block.block_id for block in blocks] == ["a1:transcript:0", "a1:transcript:1"]
    assert all(block.kind == TEXT for block in blocks)
    assert blocks[0].text == "不排除购房者可以在互联网上下单。"
    assert blocks[0].metadata == {
        "role": ROLE_L2_TRANSCRIPT,
        "source_block_id": "a1:0",
        "t_start_ms": 0,
        "t_end_ms": 3100,
    }
    assert blocks[1].metadata["t_start_ms"] == 3100
    assert library.changed == ["a1"], "the pools must re-sync for the new blocks"
    assert library.changed_sources == ["gme"]


def test_a_transcript_no_source_takes_re_opens_nothing():
    library, asset = _setup()
    library.asset_pools = {"p": pool_with("a1", viclip={"short_video"})}

    transcription.transcribe_asset(library, "a1", FakeTranscriber())

    assert library.changed == []


def test_a_rerun_replaces_the_transcript_rather_than_adding_one():
    old = ContentBlock(
        "a1:transcript:0", kind=TEXT, text="old", reading_order=1,
        metadata={"role": ROLE_L2_TRANSCRIPT},
    )
    stale = ContentBlock(
        "a1:transcript:5", kind=TEXT, text="from a longer earlier run", reading_order=2,
        metadata={"role": ROLE_L2_TRANSCRIPT},
    )
    library, asset = _setup(_stream(blocks=[old, stale]))

    transcription.transcribe_asset(library, "a1", FakeTranscriber())

    blocks = _transcripts(_stored(library, asset))
    assert [block.block_id for block in blocks] == ["a1:transcript:0", "a1:transcript:1"]
    assert blocks[0].text != "old"


def test_a_completed_asset_is_not_sent_to_the_model_again():
    library, asset = _setup()
    transcriber = FakeTranscriber()
    transcription.transcribe_asset(library, "a1", transcriber)

    status = transcription.transcribe_asset(library, "a1", transcriber)

    assert status == transcription.STATUS_COMPLETED
    assert transcriber.calls == 1


def test_the_stream_is_re_read_so_a_concurrent_ingest_is_not_reverted():
    library, asset = _setup()
    reingested = _stream(blocks=[ContentBlock("a1:extra", kind=TEXT, text="later")])
    library.content_store.records[asset.content_key] = reingested.to_record()

    transcription.transcribe_asset(library, "a1", FakeTranscriber())

    ids = {block.block_id for block in _stored(library, asset).blocks}
    assert {"a1:0", "a1:extra", "a1:transcript:0"} <= ids


def test_a_failure_is_recorded_on_the_asset_and_changes_no_blocks():
    library, asset = _setup()

    status = transcription.transcribe_asset(
        library, "a1", FakeTranscriber(error="ffmpeg could not decode")
    )

    stored = _stored(library, asset)
    assert status == transcription.STATUS_FAILED
    assert [block.block_id for block in stored.blocks] == ["a1:0"]
    assert "ffmpeg could not decode" in stored.metadata["transcript_error"]
    assert library.changed == []


def test_silence_completes_with_no_blocks():
    library, asset = _setup()

    status = transcription.transcribe_asset(library, "a1", FakeTranscriber(segments=[]))

    assert status == transcription.STATUS_COMPLETED
    assert _transcripts(_stored(library, asset)) == []


def test_only_audio_is_transcribed():
    library, asset = _setup(_stream(role=ROLE_IMAGE))
    transcriber = FakeTranscriber()

    status = transcription.transcribe_asset(library, "a1", transcriber)

    assert status == transcription.STATUS_SKIPPED
    assert transcriber.calls == 0
    assert not transcription.needs_transcript(_stream(role=ROLE_IMAGE))
    assert transcription.needs_transcript(_stream())


def test_disabled_asr_skips_without_writing(monkeypatch):
    monkeypatch.setattr(config, "ASR_ENABLED", False)
    library, asset = _setup()

    status = transcription.transcribe_asset(library, "a1", FakeTranscriber())

    assert status == transcription.STATUS_SKIPPED
    assert library.content_store.writes == 0
    assert not transcription.needs_transcript(_stream())
    found = transcription.transcript_status(_stream())
    assert found["transcript_status"] == "skipped"
    assert found["transcript_error"] == transcription.ASR_DISABLED


def test_the_reported_status_counts_segments():
    library, asset = _setup()
    assert transcription.transcript_status(_stream())["transcript_status"] == "pending"

    transcription.transcribe_asset(library, "a1", FakeTranscriber(), now=1.0)

    found = transcription.transcript_status(_stored(library, asset))
    assert found == {
        "transcript_status": "completed",
        "transcript_error": None,
        "transcript_updated_at": 1.0,
        "transcript_segments": 2,
    }


# --- windowing ------------------------------------------------------------------


def test_short_audio_is_one_window():
    audio = np.ones(asr.SAMPLE_RATE * 3, dtype=np.float32)

    assert asr.windows(audio) == [(0, audio.size)]


def test_long_audio_is_cut_at_its_quietest_moment_within_thirty_seconds():
    rate = asr.SAMPLE_RATE
    audio = np.ones(rate * 70, dtype=np.float32)
    audio[int(rate * 27.0):int(rate * 27.3)] = 0.0  # a pause, inside the search region

    ranges = asr.windows(audio)

    assert ranges[0][0] == 0
    assert 27.0 * rate <= ranges[0][1] <= 27.3 * rate
    assert all(end - start <= asr.WINDOW_SECONDS * rate for start, end in ranges)
    assert ranges[-1][1] == audio.size
    assert all(a[1] == b[0] for a, b in zip(ranges, ranges[1:])), "no gaps, no overlap"


def test_segments_of_sixty_seconds_hold_several_model_windows():
    """A block may span 60 s; what reaches Whisper never exceeds 30 s."""
    rate = asr.SAMPLE_RATE
    audio = np.ones(rate * 150, dtype=np.float32)
    audio[int(rate * 57.0):int(rate * 57.3)] = 0.0

    segments = asr.windows(audio, max_seconds=60)

    assert 57.0 * rate <= segments[0][1] <= 57.3 * rate
    assert all(end - start <= 60 * rate for start, end in segments)
    assert segments[-1][1] == audio.size
    first = audio[segments[0][0]:segments[0][1]]
    assert len(asr.windows(first)) == 2
    assert all(end - start <= asr.WINDOW_SECONDS * rate for start, end in asr.windows(first))


def test_window_text_is_joined_without_spaces_between_cjk():
    assert asr.join_text(["行业集中度加速提高。", "资本市场"]) == "行业集中度加速提高。资本市场"
    assert asr.join_text(["hello there.", "", "General Kenobi"]) == "hello there. General Kenobi"


# --- what makes a recording findable --------------------------------------------


class _Gme:
    dimension = 4
    supported_roles = frozenset({ROLE_IMAGE, ROLE_L2_TRANSCRIPT})


def _transcript_block():
    return ContentBlock(
        "a1:transcript:0", kind=TEXT, text="hi",
        metadata={"role": ROLE_L2_TRANSCRIPT},
    )


@pytest.mark.parametrize("kinds", [["audio"], ["image", "text"], ["text"], None])
def test_a_gme_source_embeds_the_transcript_and_not_the_sound(kinds):
    """`["audio"]` is how a user asks for recordings; text still selects it too."""
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.configuration = {"block_kinds": kinds} if kinds else {}
    projection._embedding = _Gme()

    assert projection.covers(_transcript_block())
    assert not projection.covers(_stream().blocks[0])


def test_an_image_only_source_does_not_take_transcripts():
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.configuration = {"block_kinds": ["image"]}
    projection._embedding = _Gme()

    assert not projection.covers(_transcript_block())


def test_audio_asset_scope_resolves_to_gme_with_transcript_routing():
    resolved = registry.resolve({"asset_types": ["audio"]})

    assert resolved.model.name == "gme_qwen2vl"
    assert resolved.params == {
        "asset_types": ["audio"], "block_kinds": ["text"], "block_roles": [ROLE_L2_TRANSCRIPT],
    }


def test_audio_asset_scope_with_a_model_that_cannot_embed_transcripts_is_refused():
    with pytest.raises(ValueError, match="l2_transcript"):
        registry.resolve({
            "embedding_model": "viclip-b-fp16",
            "asset_types": ["audio"],
        })


def test_an_audio_source_can_explicitly_keep_the_advanced_audio_kind_alias():
    resolved = registry.resolve({"asset_types": ["audio"], "block_kinds": ["audio"]})
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.configuration = resolved.params
    projection._embedding = _Gme()

    assert resolved.params["block_kinds"] == ["audio"]
    assert projection.covers(_transcript_block())
    assert not projection.covers(_stream().blocks[0])


def test_default_image_routing_does_not_take_audio_transcripts_despite_gme_capability():
    resolved = registry.resolve({"asset_types": ["image"]})
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.configuration = resolved.params
    projection._embedding = _Gme()

    assert ROLE_L2_TRANSCRIPT in projection._embedding.supported_roles
    assert not projection.covers(_transcript_block())


def _pool(roles):
    projection = MultimodalIndexer.__new__(MultimodalIndexer)
    projection.configuration = {}
    projection._embedding = SimpleNamespace(supported_roles=frozenset(roles))
    projection.source = SimpleNamespace(source_id="gme")
    return SimpleNamespace(
        asset_ids=["a1"],
        projections=[projection],
        unavailable_sources={},
        source_statuses={
            "gme": SimpleNamespace(
                status="ready", error="", indexed_asset_ids=["a1"], stale_asset_ids=[]
            )
        },
    )


def _coverage(stream, roles=(ROLE_L2_TRANSCRIPT,)):
    library = SimpleNamespace(asset_pools={"p": _pool(roles)})
    return coverage.embedding_coverage(library, "a1", stream)


def test_audio_is_covered_by_a_source_that_embeds_transcripts():
    done = _stream(transcript_status="completed")

    assert _coverage(done).status == coverage.READY
    assert _coverage(_stream()).status == coverage.PENDING, "no transcript yet"
    failed = _stream(transcript_status="failed", transcript_error="boom")
    assert _coverage(failed).status == coverage.FAILED


def test_audio_with_no_transcript_source_says_how_to_fix_it():
    found = _coverage(_stream(transcript_status="completed"), roles=(ROLE_IMAGE,))

    assert found.status == coverage.NO_SOURCE
    assert "transcript" in found.reason


def test_audio_coverage_respects_an_audio_only_source():
    library = SimpleNamespace(asset_pools={"p": _pool((ROLE_L2_TRANSCRIPT,))})
    library.asset_pools["p"].projections[0].configuration = {"block_kinds": ["audio"]}

    found = coverage.embedding_coverage(library, "a1", _stream(transcript_status="completed"))

    assert found.status == coverage.READY
