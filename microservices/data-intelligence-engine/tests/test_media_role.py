# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A media file is graded on ingest, and a grade with no pipeline still ingests.

Grading is what separates a clip a vision model can read whole from a recording
that would have to be cut up first. It happens at extraction, before anything
has been called, because the whole point is to decide *whether* to call.

The asymmetry worth testing is at the bottom of this file: a role with no
pipeline must still produce a stored, listed, findable asset. "We cannot
describe this yet" and "this failed" are different states, and only one of them
should cost the user their upload.
"""

import os
import tempfile

from core import extractor
from core.content import (
    AUDIO,
    IMAGE,
    ROLE_AUDIO,
    ROLE_IMAGE,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    VIDEO,
)


class FakeBlobWriter:
    def __init__(self):
        self.written = []

    def __call__(self, data, content_type=None):
        self.written.append((data, content_type))
        return f"blobs/{len(self.written)}"


def _file(name: str, data: bytes = b"\x00\x01") -> str:
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def _durations(monkeypatch, seconds):
    monkeypatch.setattr(extractor, "video_duration", lambda _path: seconds)


# --- grading ------------------------------------------------------------------


def test_an_image_is_graded_without_asking_anything_about_duration():
    assert extractor.media_role("/w/cat.jpg", IMAGE) == ROLE_IMAGE
    assert extractor.media_role("/w/note.m4a", AUDIO) == ROLE_AUDIO


def test_a_clip_inside_the_limit_is_short_and_one_past_it_is_long(monkeypatch):
    _durations(monkeypatch, 59.9)
    assert extractor.media_role("/w/clip.mp4", VIDEO) == ROLE_SHORT_VIDEO

    _durations(monkeypatch, 60.1)
    assert extractor.media_role("/w/clip.mp4", VIDEO) == ROLE_LONG_VIDEO


def test_a_video_of_unknown_duration_is_long_rather_than_short(monkeypatch):
    """The costs of the two mistakes are not comparable.

    Guessing short sends an unbounded recording to a vision model; guessing
    long leaves a clip undescribed. So an unreadable duration grades long.
    """
    _durations(monkeypatch, None)
    assert extractor.media_role("/w/mystery.mp4", VIDEO) == ROLE_LONG_VIDEO


def test_a_document_has_no_role_at_all():
    assert extractor.media_role("/w/report.pdf") == ""


# --- what the grade puts on the block -----------------------------------------


def test_a_clip_carries_its_role_and_duration_and_nothing_about_support(monkeypatch):
    """The block says what the file is, never what the engine can do with it.

    Support changes when a source is configured; a flag written at ingest would
    be wrong from then on and would need every asset re-ingested to correct.
    """
    _durations(monkeypatch, 12.5)
    stream = extractor.extract_media(_file("clip.mp4"), "a1", FakeBlobWriter())

    metadata = stream.blocks[0].metadata
    assert metadata["role"] == ROLE_SHORT_VIDEO
    assert metadata["duration_s"] == 12.5
    assert set(metadata) == {"content_type", "byte_size", "role", "duration_s"}


def test_a_long_recording_is_marked_exactly_like_a_short_one_except_for_its_role(monkeypatch):
    _durations(monkeypatch, 3600.0)
    long = extractor.extract_media(_file("long.mp4"), "a2", FakeBlobWriter())
    _durations(monkeypatch, 5.0)
    short = extractor.extract_media(_file("short.mp4"), "a2", FakeBlobWriter())

    assert long.blocks[0].metadata["role"] == ROLE_LONG_VIDEO
    assert set(long.blocks[0].metadata) == set(short.blocks[0].metadata)
    assert set(long.metadata) == set(short.metadata), "no 'unsupported' marker anywhere"


def test_a_long_recording_is_still_stored_with_its_name_as_the_caption(monkeypatch):
    """Whether the bytes and the name survive does not depend on any model."""
    _durations(monkeypatch, 3600.0)
    writer = FakeBlobWriter()

    stream = extractor.extract_media(_file("kitchen-fall-2026.mp4"), "a3", writer)

    assert writer.written == [], "the file is the asset; nothing is copied"
    assert stream.blocks[0].media_key.startswith("file://")
    assert stream.blocks[0].media_key.endswith("kitchen-fall-2026.mp4")
    assert stream.blocks[0].caption == "kitchen fall 2026"


def test_an_image_block_carries_no_duration(monkeypatch):
    """A still has no duration, and inventing a zero would read as one."""
    stream = extractor.extract_media(_file("cat.jpg"), "a4", FakeBlobWriter())

    assert stream.blocks[0].metadata["role"] == ROLE_IMAGE
    assert "duration_s" not in stream.blocks[0].metadata


def test_the_role_reaches_a_node_through_the_metadata_whitelist(monkeypatch):
    """Grading is useless if it stops at the content record.

    `layout_metadata` is what a projection stamps on a node, and it used to
    drop `metadata` entirely -- so a retrieved clip could not be told from a
    retrieved page.
    """
    _durations(monkeypatch, 8.0)
    stream = extractor.extract_media(_file("clip.mp4"), "a5", FakeBlobWriter())

    layout = stream.blocks[0].layout_metadata()
    assert layout["role"] == ROLE_SHORT_VIDEO
    assert layout["duration_s"] == 8.0


def test_block_metadata_outside_the_whitelist_does_not_reach_a_node():
    """Metadata is free-form; a vector store's columns are not."""
    from core.content import ContentBlock

    block = ContentBlock(
        block_id="b1",
        metadata={"role": "l2_caption", "byte_size": 999, "content_type": "video/mp4"},
    )

    layout = block.layout_metadata()
    assert layout["role"] == "l2_caption"
    assert "byte_size" not in layout
    assert "content_type" not in layout
