# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ``.rcv`` classifier-version format (no OpenVINO)."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path
import zlib

import numpy as np
import pytest

from src.rsd.model_based import format as rcv
from src.rsd.model_based.bundle import ClassifierBundle
from src.rsd.model_based.format import RcvFormatError, decode_rcv, encode_rcv, read_rcv, write_rcv

HIDDEN = 16
PROBES = ["你好", "What is 2+2?", "def f(): pass"]


def _meta(**overrides):
    meta = {
        "model_name": "Qwen/Qwen3.5-2B",
        "version": "v2",
        "created": "2026-10-16T00:00:00Z",
        "hidden": HIDDEN,
        "fp_probes": PROBES,
        "fp_ref": "hf-fp32",
        "fp_token_ids": [101, 102, 103],
        "num_classes": 12,
        "class_semantics": {str(i): f"bucket {i}" for i in range(12)},
        "class_zones": [1] * 6 + [0] * 6,
        "zone_names": ["local", "cloud"],
        "threshold": 0.5,
        "text_max_tokens": 2040,
        "truncation_side": "left",
        "render": {"template": "raw", "wrap": "", "truncation": "left", "padding": {"between_soft_and_query": 64}},
    }
    meta.update(overrides)
    return meta


# Soft versions are token form: the canonical qwen35-2b vocabulary ids.
SOFT_TOKEN_IDS = list(range(248077, 248085))
LABEL_TOKEN_IDS = list(range(248085, 248097))


def _soft(**meta_overrides) -> ClassifierBundle:
    rng = np.random.default_rng(0)
    overrides = {"soft_token_ids": SOFT_TOKEN_IDS, "label_token_ids": LABEL_TOKEN_IDS}
    overrides.update(meta_overrides)
    return ClassifierBundle(
        kind="soft",
        prompt=rng.standard_normal((8, HIDDEN)).astype(np.float32),
        head_weight=rng.standard_normal((12, HIDDEN)).astype(np.float32),
        head_bias=rng.standard_normal(12).astype(np.float32),
        fp_hidden=rng.standard_normal((len(PROBES), HIDDEN)).astype(np.float32),
        meta=_meta(**overrides),
    )


def _hard(**meta_overrides) -> ClassifierBundle:
    rng = np.random.default_rng(1)
    meta = _meta(
        version="v3",
        num_classes=2,
        class_semantics=["E", "H"],
        class_zones=None,
        zone_names=None,
        threshold=0.7,
        label_tokens=["E", "H"],
        label_token_ids=[36, 39],
        content_hash="sha256:abc",
        render={"template": "qwen_chat", "system": "prompt", "user": "query"},
    )
    meta.update(meta_overrides)
    meta = {k: v for k, v in meta.items() if v is not None}
    return ClassifierBundle(
        kind="hard",
        prompt="判断任务难易，只输出 E 或 H。",
        head_weight=rng.standard_normal((2, HIDDEN)).astype(np.float32),
        head_bias=np.zeros(2, dtype=np.float32),
        fp_hidden=rng.standard_normal((len(PROBES), HIDDEN)).astype(np.float32),
        meta=meta,
    )


def _refresh_file_crc(data: bytes) -> bytes:
    buf = bytearray(data)
    struct.pack_into("<I", buf, len(buf) - 4, zlib.crc32(bytes(buf[:-4])) & 0xFFFFFFFF)
    return bytes(buf)


def _refresh_header_crc(data: bytes) -> bytes:
    buf = bytearray(data)
    struct.pack_into("<I", buf, 60, zlib.crc32(bytes(buf[:60])) & 0xFFFFFFFF)
    return _refresh_file_crc(bytes(buf))


def _entry(data: bytes, slot: int):
    return rcv._ENTRY.unpack_from(data, rcv.HEADER_SIZE + slot * rcv.ENTRY_SIZE)


# -- 1. round trip -----------------------------------------------------------


@pytest.mark.parametrize("make", [_soft, _hard])
def test_round_trip(make):
    bundle = make()
    back = decode_rcv(encode_rcv(bundle))
    assert back.kind == bundle.kind
    if bundle.kind == "soft":
        np.testing.assert_array_equal(back.prompt, bundle.prompt)
    else:
        assert back.prompt == bundle.prompt
    for name in ("head_weight", "head_bias", "fp_hidden"):
        np.testing.assert_array_equal(getattr(back, name), getattr(bundle, name))
    assert back.meta.keys() == bundle.meta.keys()
    for key, value in bundle.meta.items():
        if isinstance(value, float):
            assert back.meta[key] == pytest.approx(value)  # stored as f32
        else:
            assert back.meta[key] == value, key


def test_write_and_read_file(tmp_path):
    path = write_rcv(tmp_path / "v2.rcv", _soft())
    assert read_rcv(path).version == "v2"
    assert not list(tmp_path.glob(".*.tmp"))  # temp file cleaned up


def test_written_file_is_world_readable(tmp_path):
    path = write_rcv(tmp_path / "v2.rcv", _soft())
    assert path.stat().st_mode & 0o777 == 0o644


def test_refuses_to_overwrite(tmp_path):
    path = write_rcv(tmp_path / "v2.rcv", _soft())
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_rcv(path, _hard())
    assert path.read_bytes() == before


def test_bundle_routing_fields():
    soft = decode_rcv(encode_rcv(_soft()))
    assert soft.class_zones == [1] * 6 + [0] * 6
    assert (soft.zone_names, soft.threshold) == (["local", "cloud"], 0.5)
    hard = decode_rcv(encode_rcv(_hard()))
    assert hard.class_zones is None  # one zone per class
    assert (hard.zone_names, hard.threshold) == (["E", "H"], pytest.approx(0.7))


def test_hard_class_names_and_answer_codes_are_separate():
    # A multi-class hard version: users name the classes, the head rows belong to codes.
    bundle = _hard(
        num_classes=3,
        class_semantics=["local", "cloud", "planning"],
        label_tokens=["A", "B", "C"],
        label_token_ids=[32, 33, 34],
    )
    bundle = ClassifierBundle(
        "hard", bundle.prompt, np.zeros((3, HIDDEN)), np.zeros(3), bundle.fp_hidden, bundle.meta
    )
    back = decode_rcv(encode_rcv(bundle))
    assert back.zone_names == ["local", "cloud", "planning"]
    assert back.meta["label_tokens"] == ["A", "B", "C"]


def test_bundle_is_read_only():
    bundle = decode_rcv(encode_rcv(_soft()))
    with pytest.raises(ValueError):
        bundle.head_weight[0, 0] = 1.0
    with pytest.raises(TypeError):
        bundle.meta["threshold"] = 0.3


# -- 2. byte layout ----------------------------------------------------------


@pytest.mark.parametrize("make,kind_code", [(_soft, 0), (_hard, 1)])
def test_byte_layout(make, kind_code):
    data = encode_rcv(make())
    (magic, major, minor, flags, n, table_off, meta_off, meta_len, payload_off, file_len, kind, reserved, _hcrc) = (
        rcv._HEADER.unpack_from(data, 0)
    )
    assert (magic, major, minor, flags, n) == (b"RCVF", 1, 0, 0, 8)
    assert table_off == 64 and meta_off == 64 + 8 * 48 == 448
    assert payload_off % 64 == 0 and payload_off >= meta_off + meta_len
    assert file_len == len(data)
    assert data[56] == kind == kind_code and reserved == b"\x00\x00\x00"
    assert b"\x04kind" not in data[meta_off : meta_off + meta_len]  # kind is not metadata

    for slot in range(8):
        slot_id, dtype, ndim, eflags, d0, d1, d2, d3, off, length, scrc, res = _entry(data, slot)
        assert slot_id == slot and eflags == 0 and res == 0
        if slot < 4:
            assert off % 64 == 0 and length > 0
            assert zlib.crc32(data[off : off + length]) & 0xFFFFFFFF == scrc
        else:
            assert (dtype, ndim, d0, d1, d2, d3, off, length, scrc) == (0,) * 9


# -- 3. slot alignment -------------------------------------------------------


def test_soft_and_hard_share_slot_meaning():
    soft, hard = encode_rcv(_soft()), encode_rcv(_hard())
    assert _entry(soft, 0)[1] == rcv.DT_F32 and _entry(hard, 0)[1] == rcv.DT_UTF8
    for slot in (1, 2, 3):
        assert _entry(soft, slot)[1] == _entry(hard, slot)[1] == rcv.DT_F32


def test_misnumbered_slot_is_rejected():
    buf = bytearray(encode_rcv(_soft()))
    struct.pack_into("<H", buf, rcv.HEADER_SIZE + 2 * rcv.ENTRY_SIZE, 5)
    with pytest.raises(RcvFormatError, match="claims slot"):
        decode_rcv(_refresh_file_crc(bytes(buf)))


def test_prompt_dtype_must_match_kind():
    buf = bytearray(encode_rcv(_hard()))
    buf[56] = 0  # relabel a hard file as soft: slot 0 is utf8, not f32
    with pytest.raises(RcvFormatError, match="must be f32"):
        decode_rcv(_refresh_header_crc(bytes(buf)))


def test_required_slot_cannot_be_empty():
    buf = bytearray(encode_rcv(_soft()))
    struct.pack_into("<HBBI4IQQII", buf, rcv.HEADER_SIZE + 3 * rcv.ENTRY_SIZE, 3, *([0] * 11))
    with pytest.raises(RcvFormatError, match="slot 3"):
        decode_rcv(_refresh_file_crc(bytes(buf)))


# -- 4. tampering ------------------------------------------------------------


def test_header_tamper_detected():
    buf = bytearray(encode_rcv(_soft()))
    buf[6] ^= 1  # minor
    with pytest.raises(RcvFormatError, match="header CRC"):
        decode_rcv(bytes(buf))


def test_payload_tamper_detected_by_file_and_section_crc():
    data = encode_rcv(_soft())
    off = _entry(data, 1)[8]
    buf = bytearray(data)
    buf[off] ^= 0xFF
    with pytest.raises(RcvFormatError, match="file CRC"):
        decode_rcv(bytes(buf))
    with pytest.raises(RcvFormatError, match="section CRC"):
        decode_rcv(_refresh_file_crc(bytes(buf)))


def test_truncation_detected():
    data = encode_rcv(_soft())
    for cut in (1, 100, 5000):
        with pytest.raises(RcvFormatError):
            decode_rcv(data[:-cut])


def test_bad_magic():
    with pytest.raises(RcvFormatError, match="magic"):
        decode_rcv(b"NOPE" + encode_rcv(_soft())[4:])


# -- 5. semantic checks ------------------------------------------------------


@pytest.mark.parametrize(
    "bundle_fn,match",
    [
        (lambda: _soft(model_name=None), "model_name"),
        (lambda: _soft(hidden=HIDDEN + 1), "head_weight shape"),
        (lambda: _soft(class_labels=[0, 1, 2]), "class_labels"),
        (lambda: _soft(threshold=1.5), "threshold"),
        (lambda: _soft(threshold=None), "threshold"),
        (lambda: _soft(class_zones=[0, 1] * 5), "class_zones must have"),
        (lambda: _soft(class_zones=[0] * 6 + [2] * 6), "zones 0..Z-1"),
        (lambda: _soft(class_zones=[0] * 12), "zones 0..Z-1"),
        (lambda: _soft(zone_names=["local"]), "zone_names"),
        (lambda: _soft(zone_names=["local", "local"]), "zone_names"),
        (lambda: _soft(class_zones=None), "zone_names needs class_zones"),
        (lambda: _soft(class_zones=None, zone_names=None), "class_semantics must name"),
        (lambda: _hard(class_zones=[0, 1], zone_names=["E", "H"]), "no class_zones"),
        (lambda: _hard(class_semantics=["E", "E"]), "class_semantics must name"),
        (lambda: _hard(label_tokens=None), "label_tokens"),
        (lambda: _hard(label_tokens=["E"]), "label_tokens must hold"),
        (lambda: _hard(label_tokens=["A", "A"]), "label_tokens must hold"),
        (lambda: _soft(fp_probes=["only one"]), "fp_hidden shape"),
        (lambda: _hard(label_token_ids=[39]), "label_token_ids"),
        (lambda: _hard(content_hash=None), "content_hash"),
    ],
)
def test_semantic_errors(bundle_fn, match):
    bundle = bundle_fn()
    meta = {k: v for k, v in bundle.meta.items() if v is not None}
    bundle = ClassifierBundle(
        bundle.kind, bundle.prompt, bundle.head_weight, bundle.head_bias, bundle.fp_hidden, meta
    )
    with pytest.raises(RcvFormatError, match=match):
        encode_rcv(bundle)  # the writer refuses ...
    with pytest.raises(RcvFormatError, match=match):
        decode_rcv(rcv._build(bundle))  # ... and so does the reader


def test_reader_rejects_required_key_with_wrong_value_type():
    data = encode_rcv(_soft())
    meta_off, meta_len = struct.unpack_from("<QQ", data, 24)
    meta = data[meta_off : meta_off + meta_len]
    patched = meta.replace(b"\x09threshold\x01", b"\x09threshold\x02")  # threshold: f32 -> i32
    assert patched != meta
    buf = bytearray(data)
    buf[meta_off : meta_off + meta_len] = patched
    with pytest.raises(RcvFormatError, match="threshold"):
        decode_rcv(_refresh_header_crc(bytes(buf)))


def test_kind_and_reserved_keys_rejected_in_metadata():
    with pytest.raises(RcvFormatError, match="header"):
        encode_rcv(_soft(kind="soft"))
    with pytest.raises(RcvFormatError, match="reserved"):
        encode_rcv(_soft(_internal=1))


# -- 6. extension and compatibility -----------------------------------------


def test_newer_minor_is_readable():
    assert decode_rcv(rcv._build(_soft(), minor=7)).version == "v2"


def test_newer_major_is_rejected():
    buf = bytearray(encode_rcv(_soft()))
    struct.pack_into("<H", buf, 4, 2)
    with pytest.raises(RcvFormatError, match="major"):
        decode_rcv(_refresh_header_crc(bytes(buf)))


def test_unknown_kind_is_rejected():
    buf = bytearray(encode_rcv(_soft()))
    buf[56] = 2
    with pytest.raises(RcvFormatError, match="kind"):
        decode_rcv(_refresh_header_crc(bytes(buf)))


def test_header_flags_critical_vs_optional():
    assert decode_rcv(rcv._build(_soft(), header_flags=1 << 20)).kind == "soft"  # optional: ignored
    with pytest.raises(RcvFormatError, match="critical"):
        decode_rcv(rcv._build(_soft(), header_flags=1))


def test_reserved_slot_ignored_unless_critical():
    extra = (rcv.DT_U8, (4,), b"\x01\x02\x03\x04")
    assert decode_rcv(rcv._build(_soft(), extra_slots={5: (*extra, 0)})).kind == "soft"
    assert decode_rcv(rcv._build(_soft(), extra_slots={5: (*extra, 1 << 16)})).kind == "soft"
    with pytest.raises(RcvFormatError, match="slot 5: unknown critical"):
        decode_rcv(rcv._build(_soft(), extra_slots={5: (*extra, 1)}))


def test_more_than_eight_slots_is_readable():
    data = rcv._build(_soft(), n_sections=9, extra_slots={8: (rcv.DT_U8, (3,), b"abc", 0)})
    assert struct.unpack_from("<I", data, 12)[0] == 9
    np.testing.assert_array_equal(decode_rcv(data).head_bias, _soft().head_bias)


def test_unknown_and_private_keys_are_kept():
    back = decode_rcv(encode_rcv(_soft(**{"x-team": "router", "future_key": [1, 2, 3]})))
    assert back.meta["x-team"] == "router" and back.meta["future_key"] == [1, 2, 3]


def test_unknown_value_type_kept_as_bytes():
    meta = rcv._encode_metadata({"x-blob": "ok"})
    patched = meta.replace(b"x-blob\x00", b"x-blob\x63")  # value type 99 (reserved)
    assert rcv._decode_metadata(patched)["x-blob"] == b"ok"


@pytest.mark.unit
def test_nan_and_inf_tensors_are_rejected():
    import numpy as np

    for slot in ("prompt", "head_weight", "head_bias", "fp_hidden"):
        bundle = _soft()
        assert bundle.token_form
        tensor = np.array(getattr(bundle, slot), copy=True)
        tensor.flat[0] = np.nan
        tensor.flat[-1] = np.inf
        bad = ClassifierBundle(
            kind=bundle.kind,
            prompt=tensor if slot == "prompt" else bundle.prompt,
            head_weight=tensor if slot == "head_weight" else bundle.head_weight,
            head_bias=tensor if slot == "head_bias" else bundle.head_bias,
            fp_hidden=tensor if slot == "fp_hidden" else bundle.fp_hidden,
            meta=bundle.meta,
        )
        with pytest.raises(RcvFormatError, match="NaN/Inf"):
            encode_rcv(bad)


@pytest.mark.unit
def test_write_rcv_closes_the_fd_when_chmod_fails(tmp_path, monkeypatch):
    import os

    bundle = _soft()
    target = tmp_path / "qwen35-2b" / "v9.rcv"
    target.parent.mkdir(parents=True)
    captured = {}
    real_mkstemp = tempfile.mkstemp

    def mkstemp(*args, **kwargs):
        fd, tmp = real_mkstemp(*args, **kwargs)
        captured["fd"] = fd
        captured["tmp"] = tmp
        return fd, tmp

    def broken_chmod(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(rcv.os, "chmod", broken_chmod)
    with pytest.raises(OSError, match="permission denied"):
        write_rcv(str(target), bundle)
    assert not Path(captured["tmp"]).exists()  # temp cleaned up
    with pytest.raises(OSError):  # fd was closed, not leaked
        os.fstat(captured["fd"])
