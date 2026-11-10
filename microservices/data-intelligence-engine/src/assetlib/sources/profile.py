# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

#: Keys excluded from the hash: they do not change what a vector means.
_UNHASHED = frozenset({"profile_hash", "device", "supported_roles"})


# Legacy backend name -> (backend, runtime).
_LEGACY_BACKENDS = {
    "llamaindex_openvino": ("local_openvino", "ov_llamaindex"),
    "openvino": ("local_openvino", "ov_llamaindex"),
    "openvino_genai": ("local_openvino", "ov_genai"),
    "native_openvino_gme": ("local_openvino", "ov_gme"),
    "gme": ("local_openvino", "ov_gme"),
    "openai_compatible": ("remote_openai_compatible", ""),
    "openai": ("remote_openai_compatible", ""),
}


def upgrade_legacy_backends(
    profile: Mapping[str, Any], configuration: Mapping[str, Any]
) -> tuple:
    """A stored source's profile and options with legacy backend names renamed; hashes untouched."""
    profile = dict(profile)
    configuration = dict(configuration)
    legacy = _LEGACY_BACKENDS.get(str(profile.get("backend") or "").lower())
    if legacy:
        profile["backend"] = legacy[0]
        if profile.get("encoder_kind") == "text":
            profile.setdefault("runtime", legacy[1])
            profile.setdefault("fused", legacy[1] == "ov_gme")
    option = _LEGACY_BACKENDS.get(str(configuration.get("embedding_backend") or "").lower())
    if option:
        configuration["embedding_backend"] = option[0]
    return profile, configuration


def build_profile(
    encoder_kind: Optional[str],
    backend: Optional[str] = None,
    model: Optional[str] = None,
    params: Optional[Mapping[str, Any]] = None,
    **extra: Any,
) -> dict:
    """A profile record with its hash; `params` change vectors, `extra` is descriptive only."""
    profile = {
        "encoder_kind": encoder_kind,
        "backend": backend,
        "model": model,
        "params": dict(sorted((params or {}).items())),
        **extra,
    }
    profile["profile_hash"] = profile_hash(profile)
    return profile


def profile_hash(profile: Mapping[str, Any]) -> str:
    """Twelve hex characters over the parts of a profile that change vectors."""
    hashed = {key: value for key, value in profile.items() if key not in _UNHASHED}
    canonical = json.dumps(hashed, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_collection_name(library_name: str, source_name: str) -> str:
    """`<library>_<source>_<yyyymmddHHMM>`, sanitized for Milvus naming rules."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    raw = f"{library_name}_{source_name}_{stamp}"
    name = re.sub(r"[^0-9A-Za-z_]", "_", raw)
    if not re.match(r"[A-Za-z_]", name):
        name = f"_{name}"
    return name[:255]


__all__ = [
    "build_profile", "default_collection_name", "now", "profile_hash", "upgrade_legacy_backends",
]
