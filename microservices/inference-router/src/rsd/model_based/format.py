# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""``.rcv`` (Router Classifier Version) binary format, v1.

One file holds one classifier version. Soft and hard versions share a single
container layout; only the header ``kind`` byte (and the profile it selects)
differs. All integers are little-endian and every offset is absolute from the
start of the file::

    [0, 64)                       Fixed header
    [64, 64 + 48*n)               Section table, n fixed slots (n = 8 in v1)
    [metadata_offset, +len)       Metadata, TLV entries
    zero padding to 64 B
    [payload_offset, len - 4)     Slot data, each slot 64 B aligned
    [len - 4, len)                file_crc32 over everything before it

Slots are aligned by meaning across kinds: 0 = prompt (soft vectors / hard
prompt text), 1 = head_weight, 2 = head_bias, 3 = fp_hidden, 4-7 reserved.

Spec gaps resolved here:

* ``bf16`` slots are returned as raw ``uint16`` arrays (numpy has no bf16);
  v1 profiles only use ``f32`` and ``utf8``.
* JSON-valued keys (``fp_probes``, ``class_semantics``, ``render``,
  ``train_meta``, ``route_metrics``) are serialized on write and parsed on read.
* Matching ``version`` against the file name (``<backbone>/vN.rcv``) is left to
  the registry and the packing tool; the bundled ``default`` of each backbone is
  ``prompts/<backbone>/v1.rcv``.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple, Union

import numpy as np

from src.rsd.model_based.bundle import KIND_HARD, KIND_SOFT, ClassifierBundle

MAGIC = b"RCVF"
MAJOR = 1
MINOR = 0

HEADER_SIZE = 64
ENTRY_SIZE = 48
N_SLOTS = 8
ALIGN = 64
FOOTER_SIZE = 4

_HEADER = struct.Struct("<4sHHIIQQQQQB3sI")  # 64 bytes
_ENTRY = struct.Struct("<HBBI4IQQII")  # 48 bytes
assert _HEADER.size == HEADER_SIZE and _ENTRY.size == ENTRY_SIZE

# Low 16 bits of a flags word are "critical" (unknown => reject), high 16 bits
# are "optional" (unknown => ignore). v1 defines no flags yet.
_CRITICAL_MASK = 0x0000FFFF
_KNOWN_HEADER_FLAGS = 0
_KNOWN_ENTRY_FLAGS = 0

_KIND_CODES = {KIND_SOFT: 0, KIND_HARD: 1}
_KIND_NAMES = {code: name for name, code in _KIND_CODES.items()}

# dtype code -> (numpy dtype, itemsize); 6 = utf8 text.
DT_F32, DT_F16, DT_BF16, DT_I32, DT_I64, DT_U8, DT_UTF8 = range(7)
_DTYPES = {
    DT_F32: (np.float32, 4),
    DT_F16: (np.float16, 2),
    DT_BF16: (np.uint16, 2),
    DT_I32: (np.int32, 4),
    DT_I64: (np.int64, 8),
    DT_U8: (np.uint8, 1),
    DT_UTF8: (None, 1),
}

SLOT_PROMPT, SLOT_HEAD_WEIGHT, SLOT_HEAD_BIAS, SLOT_FP_HIDDEN = range(4)

# Metadata value types.
VT_UTF8, VT_F32, VT_I32, VT_BASE64, VT_I32_ARRAY, VT_F32_ARRAY = range(6)

_JSON_KEYS = {
    "fp_probes",
    "class_semantics",
    "zone_names",
    "label_tokens",
    "render",
    "train_meta",
    "route_metrics",
}
_KEY_TYPES = {
    "model_name": VT_UTF8,
    "version": VT_UTF8,
    "created": VT_UTF8,
    "note": VT_UTF8,
    "hidden": VT_I32,
    "fp_probes": VT_UTF8,
    "fp_ref": VT_UTF8,
    "fp_token_ids": VT_I32_ARRAY,
    "num_classes": VT_I32,
    "class_labels": VT_I32_ARRAY,
    "class_semantics": VT_UTF8,
    "label_tokens": VT_UTF8,
    "label_token_ids": VT_I32_ARRAY,
    "soft_token_ids": VT_I32_ARRAY,
    "class_zones": VT_I32_ARRAY,
    "zone_names": VT_UTF8,
    "threshold": VT_F32,
    "tau_folded": VT_F32,
    "text_max_tokens": VT_I32,
    "truncation_side": VT_UTF8,
    "render": VT_UTF8,
    "content_hash": VT_UTF8,
    "eval_precision": VT_UTF8,
    "train_meta": VT_UTF8,
    "route_metrics": VT_UTF8,
}
_REQUIRED_KEYS = (
    "model_name",
    "version",
    "created",
    "hidden",
    "fp_probes",
    "fp_ref",
    "fp_token_ids",
    "num_classes",
    "class_semantics",
    "threshold",
    "text_max_tokens",
    "truncation_side",
    "render",
)
_REQUIRED_HARD_KEYS = ("label_tokens", "label_token_ids", "content_hash")


class RcvFormatError(ValueError):
    """The bytes are not a valid ``.rcv`` v1 file."""


def _align(n: int) -> int:
    return (n + ALIGN - 1) // ALIGN * ALIGN


def _crc(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Metadata (TLV)
# ---------------------------------------------------------------------------


def _infer_value_type(value: Any) -> int:
    if isinstance(value, str):
        return VT_UTF8
    if isinstance(value, bool):
        raise RcvFormatError("bool metadata values are not supported")
    if isinstance(value, (int, np.integer)):
        return VT_I32
    if isinstance(value, (float, np.floating)):
        return VT_F32
    if isinstance(value, (bytes, bytearray)):
        return VT_BASE64
    if isinstance(value, (list, tuple, np.ndarray)):
        items = list(np.asarray(value).ravel()) if isinstance(value, np.ndarray) else list(value)
        if all(isinstance(x, (int, np.integer)) and not isinstance(x, bool) for x in items):
            return VT_I32_ARRAY
        if all(isinstance(x, (int, float, np.integer, np.floating)) for x in items):
            return VT_F32_ARRAY
    raise RcvFormatError(f"cannot store metadata value of type {type(value).__name__}")


def _encode_value(key: str, value: Any) -> Tuple[int, bytes]:
    if key in _JSON_KEYS and not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    vtype = _KEY_TYPES.get(key)
    if vtype is None:
        vtype = _infer_value_type(value)
    try:
        if vtype == VT_UTF8:
            if not isinstance(value, str):
                raise TypeError
            return vtype, value.encode("utf-8")
        if vtype == VT_F32:
            return vtype, struct.pack("<f", float(value))
        if vtype == VT_I32:
            return vtype, struct.pack("<i", int(value))
        if vtype == VT_BASE64:
            return vtype, base64.b64encode(bytes(value))
        if vtype == VT_I32_ARRAY:
            return vtype, np.asarray(value, dtype="<i4").tobytes()
        if vtype == VT_F32_ARRAY:
            return vtype, np.asarray(value, dtype="<f4").tobytes()
    except (TypeError, ValueError, OverflowError, struct.error) as exc:
        raise RcvFormatError(f"metadata {key!r}: cannot encode {value!r}") from exc
    raise RcvFormatError(f"metadata {key!r}: unsupported value type {vtype}")


def _encode_metadata(meta: Mapping[str, Any]) -> bytes:
    out = bytearray()
    for key, value in meta.items():
        if key == "kind":
            raise RcvFormatError("'kind' lives in the header, not in metadata")
        if key.startswith("_"):
            raise RcvFormatError(f"metadata keys starting with '_' are reserved: {key!r}")
        key_bytes = key.encode("utf-8")
        if not 0 < len(key_bytes) <= 255:
            raise RcvFormatError(f"metadata key length must be 1..255 bytes: {key!r}")
        vtype, payload = _encode_value(key, value)
        out += struct.pack("<B", len(key_bytes)) + key_bytes + struct.pack("<BI", vtype, len(payload)) + payload
    return bytes(out)


def _decode_value(key: str, vtype: int, raw: bytes) -> Any:
    try:
        if vtype == VT_UTF8:
            text = raw.decode("utf-8")
            return json.loads(text) if key in _JSON_KEYS else text
        if vtype in (VT_F32, VT_I32):
            if len(raw) != 4:
                raise RcvFormatError(f"metadata {key!r}: scalar must be 4 bytes, got {len(raw)}")
            return struct.unpack("<f" if vtype == VT_F32 else "<i", raw)[0]
        if vtype == VT_BASE64:
            return base64.b64decode(raw, validate=True)
        if vtype in (VT_I32_ARRAY, VT_F32_ARRAY):
            if len(raw) % 4:
                raise RcvFormatError(f"metadata {key!r}: array length {len(raw)} is not a multiple of 4")
            dtype = "<i4" if vtype == VT_I32_ARRAY else "<f4"
            return np.frombuffer(raw, dtype=dtype).tolist()
    except RcvFormatError:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        raise RcvFormatError(f"metadata {key!r}: malformed value") from exc
    # Unknown (reserved / private) value type: keep the raw bytes, don't interpret.
    return bytes(raw)


def _decode_metadata(data: bytes) -> Dict[str, Any]:
    return _decode_metadata_typed(data)[0]


def _decode_metadata_typed(data: bytes) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Decode the TLV block; also return each key's stored value type."""
    meta: Dict[str, Any] = {}
    vtypes: Dict[str, int] = {}
    pos, end = 0, len(data)
    while pos < end:
        key_len = data[pos]
        pos += 1
        if key_len == 0 or pos + key_len + 5 > end:
            raise RcvFormatError("metadata entry runs past the metadata block")
        try:
            key = data[pos : pos + key_len].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RcvFormatError("metadata key is not valid UTF-8") from exc
        pos += key_len
        vtype, val_len = struct.unpack_from("<BI", data, pos)
        pos += 5
        if pos + val_len > end:
            raise RcvFormatError(f"metadata {key!r}: value runs past the metadata block")
        if key in meta:
            raise RcvFormatError(f"duplicate metadata key {key!r}")
        meta[key] = _decode_value(key, vtype, data[pos : pos + val_len])
        vtypes[key] = vtype
        pos += val_len
    return meta, vtypes


# ---------------------------------------------------------------------------
# Profile / semantic checks (shared by read and write)
# ---------------------------------------------------------------------------

_PY_TYPES = {
    VT_UTF8: str,
    VT_F32: float,
    VT_I32: int,
    VT_I32_ARRAY: list,
    VT_F32_ARRAY: list,
}


def _check_meta_types(kind: str, meta: Mapping[str, Any]) -> None:
    required = _REQUIRED_KEYS + (_REQUIRED_HARD_KEYS if kind == KIND_HARD else ())
    missing = [k for k in required if k not in meta]
    if missing:
        raise RcvFormatError(f"missing required metadata for kind={kind}: {missing}")
    for key, value in meta.items():
        vtype = _KEY_TYPES.get(key)
        if vtype is None:
            continue
        if key in _JSON_KEYS:
            if isinstance(value, bytes):
                raise RcvFormatError(f"metadata {key!r} has the wrong value type")
            continue
        expected = _PY_TYPES[vtype]
        if expected is float and isinstance(value, (int, float)) and not isinstance(value, bool):
            continue
        if not isinstance(value, expected) or isinstance(value, bool):
            raise RcvFormatError(f"metadata {key!r} must be {expected.__name__}")


def _check_semantics(bundle: ClassifierBundle) -> None:
    meta = bundle.meta
    _check_meta_types(bundle.kind, meta)
    hidden, num_classes = int(meta["hidden"]), int(meta["num_classes"])
    if hidden <= 0 or num_classes < 2:
        raise RcvFormatError("hidden must be > 0 and num_classes >= 2")

    if bundle.head_weight.shape != (num_classes, hidden):
        raise RcvFormatError(f"head_weight shape {bundle.head_weight.shape} != {(num_classes, hidden)}")
    if bundle.head_bias.shape != (num_classes,):
        raise RcvFormatError(f"head_bias shape {bundle.head_bias.shape} != {(num_classes,)}")

    probes = meta["fp_probes"]
    if not isinstance(probes, list) or not all(isinstance(p, str) for p in probes) or not probes:
        raise RcvFormatError("fp_probes must be a non-empty JSON array of strings")
    if bundle.fp_hidden.shape != (len(probes), hidden):
        raise RcvFormatError(f"fp_hidden shape {bundle.fp_hidden.shape} != {(len(probes), hidden)}")

    # NaN/Inf would flow straight into the graph and the decision (softmax of
    # NaN is NaN) and route silently wrong: reject the version outright.
    for name, tensor in (
        ("head_weight", bundle.head_weight),
        ("head_bias", bundle.head_bias),
        ("fp_hidden", bundle.fp_hidden),
    ):
        if not np.isfinite(tensor).all():
            raise RcvFormatError(f"{name} holds NaN/Inf values")

    labels = bundle.class_labels
    if len(labels) != num_classes or len(set(labels)) != num_classes:
        raise RcvFormatError("class_labels must hold num_classes distinct entries")
    _check_decision(bundle, num_classes)

    if bundle.kind == KIND_SOFT:
        prompt = bundle.prompt
        if prompt.ndim != 2 or prompt.shape[0] == 0 or prompt.shape[1] != hidden:
            raise RcvFormatError(f"soft prompt shape {prompt.shape} must be [k, {hidden}]")
        if not np.isfinite(prompt).all():
            raise RcvFormatError("the soft prompt holds NaN/Inf values")
        _check_token_form(meta, prompt.shape[0], num_classes)
    else:
        if not bundle.prompt:
            raise RcvFormatError("hard prompt text is empty")
        if "soft_token_ids" in meta:
            raise RcvFormatError("a hard version has no soft tokens: no soft_token_ids")
        if len(meta["label_token_ids"]) != num_classes:
            raise RcvFormatError("label_token_ids must have num_classes entries")
        if not _distinct_names(meta["label_tokens"], num_classes):
            raise RcvFormatError(
                "label_tokens must hold num_classes distinct token strings "
                "(the answer codes the head rows were taken from, e.g. E/H or A/B/C)"
            )
        if "class_zones" in meta:
            raise RcvFormatError("a hard version maps classes to zones one-to-one: no class_zones")


def _distinct_names(value: Any, count: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == count
        and all(isinstance(v, str) and v for v in value)
        and len(set(value)) == count
    )


def _check_token_form(meta: Mapping[str, Any], k: int, num_classes: int) -> None:
    """A soft version names the vocabulary ids of its soft and class rows (token form).

    Shape checks only here (k / num_classes / distinct, non-negative); whether
    the ids sit in the backbone's free rows and follow the canonical layout is
    checked against the backbone (see :func:`.vocab_tokens.check_token_ids`).
    """
    soft_ids, label_ids = meta.get("soft_token_ids"), meta.get("label_token_ids")
    if soft_ids is None or label_ids is None:
        raise RcvFormatError(
            "a soft version needs soft_token_ids and label_token_ids (token form); "
            "re-pack it with tools/pack_rcv.py"
        )
    if len(soft_ids) != k:
        raise RcvFormatError(f"soft_token_ids must have k={k} entries, got {len(soft_ids)}")
    if len(label_ids) != num_classes:
        raise RcvFormatError(
            f"label_token_ids must have num_classes={num_classes} entries, got {len(label_ids)}"
        )
    ids = list(soft_ids) + list(label_ids)
    if any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in ids):
        raise RcvFormatError("soft_token_ids / label_token_ids must be non-negative integers")
    if len(set(ids)) != len(ids):
        raise RcvFormatError("soft_token_ids / label_token_ids must not repeat an id")


def _check_decision(bundle: ClassifierBundle, num_classes: int) -> None:
    """Validate ``threshold`` and how classes merge into routing zones."""
    meta = bundle.meta
    threshold = float(meta["threshold"])
    if not 0.0 <= threshold <= 1.0:
        raise RcvFormatError(f"threshold {threshold} must be within [0, 1]")
    zones = meta.get("class_zones")
    if zones is None:
        if "zone_names" in meta:
            raise RcvFormatError(
                "zone_names needs class_zones; without it the zones are the classes"
            )
        if not _distinct_names(meta["class_semantics"], num_classes):
            raise RcvFormatError(
                "without class_zones, class_semantics must name the num_classes zones (distinct)"
            )
        return
    if len(zones) != num_classes:
        raise RcvFormatError(f"class_zones must have num_classes ({num_classes}) entries")
    n_zones = max(zones) + 1 if zones else 0
    if min(zones) < 0 or n_zones < 2 or set(zones) != set(range(n_zones)):
        raise RcvFormatError(
            f"class_zones {zones} must use zones 0..Z-1 (Z >= 2), each at least once"
        )
    if not _distinct_names(meta.get("zone_names"), n_zones):
        raise RcvFormatError(f"zone_names must name the {n_zones} zones (distinct)")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _slot_payloads(bundle: ClassifierBundle) -> List[Tuple[int, Tuple[int, ...], bytes]]:
    """Return ``(dtype, shape, raw_bytes)`` for slots 0-3."""
    if bundle.kind == KIND_SOFT:
        prompt = (DT_F32, bundle.prompt.shape, bundle.prompt.astype("<f4").tobytes())
    else:
        text = bundle.prompt.encode("utf-8")
        prompt = (DT_UTF8, (len(text),), text)
    tensors = [
        (DT_F32, a.shape, a.astype("<f4").tobytes())
        for a in (bundle.head_weight, bundle.head_bias, bundle.fp_hidden)
    ]
    return [prompt, *tensors]


def encode_rcv(bundle: ClassifierBundle) -> bytes:
    """Serialize ``bundle`` to ``.rcv`` bytes (validates it first)."""
    _check_semantics(bundle)
    return _build(bundle)


def _build(
    bundle: ClassifierBundle,
    *,
    minor: int = MINOR,
    header_flags: int = 0,
    n_sections: int = N_SLOTS,
    extra_slots: Mapping[int, Tuple[int, Tuple[int, ...], bytes, int]] = (),
) -> bytes:
    """Lay out the bytes. The keyword arguments exist so tests can produce files
    that a future minor version could write (reserved slots, optional flags,
    more slots); :func:`encode_rcv` always uses the v1 defaults."""
    extra_slots = dict(extra_slots)
    metadata = _encode_metadata(bundle.meta)
    metadata_offset = HEADER_SIZE + ENTRY_SIZE * n_sections
    payload_offset = _align(metadata_offset + len(metadata))

    payloads = {slot: (dtype, shape, raw, 0) for slot, (dtype, shape, raw) in enumerate(_slot_payloads(bundle))}
    payloads.update(extra_slots)
    entries, chunks = [], []
    cursor = payload_offset
    for slot in range(n_sections):
        if slot in payloads:
            dtype, shape, raw, eflags = payloads[slot]
            cursor = _align(cursor)
            dims = list(shape) + [0] * (4 - len(shape))
            entries.append(_ENTRY.pack(slot, dtype, len(shape), eflags, *dims, cursor, len(raw), _crc(raw), 0))
            chunks.append((cursor, raw))
            cursor += len(raw)
        else:
            entries.append(_ENTRY.pack(slot, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    file_length = cursor + FOOTER_SIZE

    buf = bytearray(file_length)
    header_fields = (
        MAGIC, MAJOR, minor, header_flags, n_sections, HEADER_SIZE, metadata_offset, len(metadata),
        payload_offset, file_length, _KIND_CODES[bundle.kind], b"\x00\x00\x00",
    )
    header_crc = _crc(_HEADER.pack(*header_fields, 0)[:60])
    buf[0:HEADER_SIZE] = _HEADER.pack(*header_fields, header_crc)
    buf[HEADER_SIZE:metadata_offset] = b"".join(entries)
    buf[metadata_offset : metadata_offset + len(metadata)] = metadata
    for offset, raw in chunks:
        buf[offset : offset + len(raw)] = raw
    struct.pack_into("<I", buf, file_length - FOOTER_SIZE, _crc(bytes(buf[: file_length - FOOTER_SIZE])))
    return bytes(buf)


def write_rcv(path: Union[str, Path], bundle: ClassifierBundle) -> Path:
    """Write ``bundle`` to ``path``; refuse to overwrite an existing file.

    ``.rcv`` files are immutable: a changed version is a new file. The bytes are
    written to a temp file in the same directory and then hard-linked into place,
    which fails atomically if ``path`` already exists.
    """
    path = Path(path)
    data = encode_rcv(bundle)
    if path.exists():
        raise FileExistsError(f"{path} already exists; .rcv files are immutable")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            # mkstemp creates the file 0600; versions are read by whoever runs the router.
            os.chmod(tmp, 0o644)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise FileExistsError(f"{path} already exists; .rcv files are immutable") from None
        except OSError:
            # Filesystem without hard links: best-effort check-then-replace.
            if path.exists():
                raise FileExistsError(f"{path} already exists; .rcv files are immutable") from None
            os.replace(tmp, path)
            tmp = ""
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    return path


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def decode_rcv(data: bytes) -> ClassifierBundle:
    """Parse and fully validate ``.rcv`` bytes."""
    data = bytes(data)
    min_len = HEADER_SIZE + ENTRY_SIZE * N_SLOTS + FOOTER_SIZE
    if len(data) < min_len:
        raise RcvFormatError(f"file too short ({len(data)} < {min_len} bytes)")

    # 1. header
    (magic, major, _minor, flags, n_sections, table_offset, metadata_offset, metadata_length,
     payload_offset, file_length, kind_code, _reserved, header_crc) = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise RcvFormatError(f"bad magic {magic!r}")
    if major == 0 or major > MAJOR:
        raise RcvFormatError(f"unsupported format major version {major}")
    if _crc(data[:60]) != header_crc:
        raise RcvFormatError("header CRC mismatch")
    if file_length != len(data):
        raise RcvFormatError(f"file_length {file_length} != actual size {len(data)} (truncated?)")
    if flags & _CRITICAL_MASK & ~_KNOWN_HEADER_FLAGS:
        raise RcvFormatError(f"unknown critical header flags 0x{flags:08x}")
    if kind_code not in _KIND_NAMES:
        raise RcvFormatError(f"unknown kind {kind_code}")
    kind = _KIND_NAMES[kind_code]

    # 2. whole-file CRC
    (file_crc,) = struct.unpack_from("<I", data, len(data) - FOOTER_SIZE)
    if _crc(data[: len(data) - FOOTER_SIZE]) != file_crc:
        raise RcvFormatError("file CRC mismatch")

    # 3. section table
    if n_sections < N_SLOTS:
        raise RcvFormatError(f"n_sections {n_sections} < {N_SLOTS}")
    if table_offset != HEADER_SIZE or metadata_offset != HEADER_SIZE + ENTRY_SIZE * n_sections:
        raise RcvFormatError("section table / metadata offsets do not follow the header")
    metadata_end = metadata_offset + metadata_length
    data_end = len(data) - FOOTER_SIZE
    if metadata_end > data_end or payload_offset % ALIGN or not metadata_end <= payload_offset <= data_end:
        raise RcvFormatError("metadata / payload region out of bounds")

    slots: Dict[int, Tuple[int, Tuple[int, ...], bytes]] = {}
    spans = []
    for slot in range(n_sections):
        (slot_id, dtype, ndim, eflags, d0, d1, d2, d3, offset, length, scrc, _r) = _ENTRY.unpack_from(
            data, HEADER_SIZE + slot * ENTRY_SIZE
        )
        if slot_id != slot:
            raise RcvFormatError(f"section table entry {slot} claims slot {slot_id}")
        if eflags & _CRITICAL_MASK & ~_KNOWN_ENTRY_FLAGS:
            raise RcvFormatError(f"slot {slot}: unknown critical flags 0x{eflags:08x}")
        if length == 0:
            if any((dtype, ndim, d0, d1, d2, d3, offset, scrc)):
                raise RcvFormatError(f"slot {slot}: empty slot has non-zero fields")
            continue
        if ndim > 4 or offset % ALIGN or offset < payload_offset or offset + length > data_end:
            raise RcvFormatError(f"slot {slot}: data out of bounds or misaligned")
        shape = (d0, d1, d2, d3)[:ndim]
        if any((d0, d1, d2, d3)[ndim:]):
            raise RcvFormatError(f"slot {slot}: unused shape dims must be 0")
        raw = data[offset : offset + length]
        if _crc(raw) != scrc:
            raise RcvFormatError(f"slot {slot}: section CRC mismatch")
        if dtype in _DTYPES:
            _np, itemsize = _DTYPES[dtype]
            expected = shape[0] if dtype == DT_UTF8 and ndim == 1 else int(np.prod(shape)) * itemsize
            if dtype == DT_UTF8 and ndim != 1:
                raise RcvFormatError(f"slot {slot}: utf8 data must be 1-D")
            if length != expected:
                raise RcvFormatError(f"slot {slot}: data_length {length} != shape/dtype size {expected}")
        spans.append((offset, offset + length, slot))
        slots[slot] = (dtype, shape, raw)
    spans.sort()
    for (_, end_a, slot_a), (start_b, _, slot_b) in zip(spans, spans[1:]):
        if start_b < end_a:
            raise RcvFormatError(f"slots {slot_a} and {slot_b} overlap")

    # 4. profile: slots 0-3 present with the right dtype; reserved slots are ignored
    def tensor(slot: int, name: str) -> np.ndarray:
        if slot not in slots:
            raise RcvFormatError(f"required slot {slot} ({name}) is empty")
        dtype, shape, raw = slots[slot]
        if dtype != DT_F32:
            raise RcvFormatError(f"slot {slot} ({name}) must be f32, got dtype {dtype}")
        return np.frombuffer(raw, dtype="<f4").reshape(shape).astype(np.float32)

    if SLOT_PROMPT not in slots:
        raise RcvFormatError("required slot 0 (prompt) is empty")
    p_dtype, p_shape, p_raw = slots[SLOT_PROMPT]
    if kind == KIND_SOFT:
        prompt: Union[np.ndarray, str] = tensor(SLOT_PROMPT, "prompt")
    else:
        if p_dtype != DT_UTF8:
            raise RcvFormatError(f"hard prompt (slot 0) must be utf8, got dtype {p_dtype}")
        try:
            prompt = p_raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RcvFormatError("hard prompt is not valid UTF-8") from exc

    meta, vtypes = _decode_metadata_typed(data[metadata_offset:metadata_end])
    for key, vtype in vtypes.items():
        # A known key must carry the value type the spec assigns to it; reading
        # e.g. an f32 as i32 would yield a meaningless number rather than fail.
        if key in _KEY_TYPES and vtype != _KEY_TYPES[key]:
            raise RcvFormatError(f"metadata {key!r} stored as value type {vtype}, expected {_KEY_TYPES[key]}")
    try:
        bundle = ClassifierBundle(
            kind=kind,
            prompt=prompt,
            head_weight=tensor(SLOT_HEAD_WEIGHT, "head_weight"),
            head_bias=tensor(SLOT_HEAD_BIAS, "head_bias"),
            fp_hidden=tensor(SLOT_FP_HIDDEN, "fp_hidden"),
            meta=meta,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, RcvFormatError):
            raise
        raise RcvFormatError(str(exc)) from exc

    # 5. semantic consistency
    _check_semantics(bundle)
    return bundle


def read_rcv(path: Union[str, Path]) -> ClassifierBundle:
    """Read and validate the ``.rcv`` file at ``path``."""
    return decode_rcv(Path(path).read_bytes())
