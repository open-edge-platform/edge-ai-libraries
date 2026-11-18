# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Hard versions packed from text: content identity, numbering, lookup."""

from __future__ import annotations

import pytest

from src.rsd.model_based import settings
from src.rsd.model_based.format import write_rcv
from src.rsd.model_based.hard_version import (
    build_hard_bundle,
    content_hash,
    find_hard_version,
    next_version,
    prompt_text,
)
from src.rsd.model_based.validate import validate_against_runtime

from ._fake_backbone import FakeRuntime

pytestmark = pytest.mark.unit

MODEL = "qwen3-0.6b"


def _pack(version, text="Pick one.", labels=("local", "cloud"), threshold=0.7):
    return build_hard_bundle(
        FakeRuntime(), model=MODEL, version=version, text=text, labels=list(labels),
        threshold=threshold,
    )


def test_content_hash_covers_text_labels_and_threshold():
    base = content_hash("Pick one.", ["local", "cloud"], 0.7)
    assert base == content_hash("Pick one.", ["local", "cloud"], 0.7)
    assert base == content_hash("  Pick one.\n", ["local", "cloud"], 0.7)  # stored stripped
    assert base != content_hash("Pick two.", ["local", "cloud"], 0.7)
    assert base != content_hash("Pick one.", ["cloud", "local"], 0.7)
    assert base != content_hash("Pick one.", ["local", "cloud"], 0.8)


def test_next_version_counts_packaged_and_artifact_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_DEFAULT_PROMPT_DIR", tmp_path / "prompts")
    artifacts = tmp_path / "artifacts"
    assert next_version(MODEL, artifacts) == "v1"
    (tmp_path / "prompts" / MODEL).mkdir(parents=True)
    (tmp_path / "prompts" / MODEL / "v1.rcv").write_bytes(b"")
    assert next_version(MODEL, artifacts) == "v2"
    (artifacts / MODEL).mkdir(parents=True)
    (artifacts / MODEL / "v7.rcv").write_bytes(b"")
    (artifacts / MODEL / "notes.txt").write_bytes(b"")
    assert next_version(MODEL, artifacts) == "v8"


def test_find_hard_version_matches_content_and_skips_bad_files(tmp_path):
    directory = tmp_path / MODEL
    directory.mkdir()
    (directory / "v2.rcv").write_bytes(b"not an rcv")
    write_rcv(directory / "v3.rcv", _pack("v3"))
    found = content_hash("Pick one.", ["local", "cloud"], 0.7)
    assert find_hard_version(MODEL, tmp_path, found) == "v3"
    other = content_hash("Other", ["local", "cloud"], 0.7)
    assert find_hard_version(MODEL, tmp_path, other) is None


def test_packed_version_passes_its_own_backbone_checks():
    bundle = _pack("v2", labels=("local", "cloud", "planning"))
    assert bundle.prompt.endswith("A: local\nB: cloud\nC: planning")
    report = validate_against_runtime(bundle, FakeRuntime(), backbone=MODEL)
    assert report["L1"] == report["L2"] == "ok"
    assert report["L3_min_cos"] == pytest.approx(1.0)
    assert report["hard_head_min_cos"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"text": " "}, "empty"),
        ({"labels": ["only"]}, "2-26 labels"),
    ],
)
def test_invalid_content_is_rejected(kwargs, match):
    params = {"text": "Pick one.", "labels": ["local", "cloud"], **kwargs}
    with pytest.raises(ValueError, match=match):
        build_hard_bundle(FakeRuntime(), model=MODEL, version="v2", threshold=0.7, **params)


def test_prompt_text_reads_back_the_text_without_the_answer_key():
    bundle = _pack("v2", text="  Pick one:\n- local: easy\n- cloud: hard\n\n")
    assert prompt_text(bundle) == "Pick one:\n- local: easy\n- cloud: hard"  # stored stripped
    assert content_hash(prompt_text(bundle), ["local", "cloud"], 0.7) == bundle.meta["content_hash"]
