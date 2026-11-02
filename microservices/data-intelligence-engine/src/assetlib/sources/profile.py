# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A source's profile: what produced its records, fixed when it was created.

Two sources that differ in model *or* in any parameter that changes a vector
are different sources -- that is the rule the multi-source design rests on, and
the profile is how it is checked and shown. It is resolved once, at creation,
from the source's options plus whatever defaults the engine filled in, and then
stored: a later change of an engine default must not quietly change what an
existing collection's vectors mean.

Nothing here knows which options matter or how defaults resolve. The library
specialization says that (`AssetLibrary.describe_source`); this module only
shapes and hashes the answer.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

#: Keys that never reach the hash: they identify the profile or vary by host
#: without changing what a vector means.
_UNHASHED = frozenset({"profile_hash", "device", "supported_roles"})


def build_profile(
    encoder_kind: Optional[str],
    backend: Optional[str] = None,
    model: Optional[str] = None,
    params: Optional[Mapping[str, Any]] = None,
    **extra: Any,
) -> dict:
    """A profile record, with its hash.

    `params` are the options that change a vector (chunking, frames per clip,
    image tokens, ...). `extra` is descriptive -- device, supported roles -- and
    is shown but not hashed.
    """
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
    """`<library>_<source>_<yyyymmddHHMM>`, safe for Milvus.

    For a caller that creates a new source per model or parameter change and
    should not have to invent a collection name each time. Milvus allows
    letters, digits and underscores, starting with a letter or underscore.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    raw = f"{library_name}_{source_name}_{stamp}"
    name = re.sub(r"[^0-9A-Za-z_]", "_", raw)
    if not re.match(r"[A-Za-z_]", name):
        name = f"_{name}"
    return name[:255]


__all__ = ["build_profile", "default_collection_name", "now", "profile_hash"]
