# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Helpers for validating untrusted local artifact references."""

import tempfile
from pathlib import Path
import re
from typing import Optional, Set

_VIDEO_TMP_DIR = Path(tempfile.gettempdir()) / "videoQnA"
_SAFE_LOCAL_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}
_MANIFEST_EXTENSIONS = {".json"}


def _normalize_allowed_extensions(allowed_extensions: Optional[Set[str]]) -> Set[str]:
    normalized: Set[str] = set()
    for ext in allowed_extensions or set():
        cleaned = ext.strip().lower()
        if not cleaned:
            continue
        normalized.add(cleaned if cleaned.startswith(".") else f".{cleaned}")
    return normalized


def build_safe_temp_path(file_name: str, allowed_root: Path = _VIDEO_TMP_DIR) -> str:
    """Build an internal temp path under the allowed root."""
    resolved_root = allowed_root.expanduser().resolve()
    candidate_path = (resolved_root / Path(file_name).name).resolve(strict=False)
    candidate_path.relative_to(resolved_root)
    return str(candidate_path)


def validate_local_artifact_reference(
    file_reference: str,
    *,
    allowed_extensions: Optional[Set[str]] = None,
    allow_extensionless: bool = False,
) -> str:
    """Validate an untrusted local artifact reference and return normalized filename."""
    if not isinstance(file_reference, str) or not file_reference.strip():
        raise ValueError("file reference must be a non-empty string")

    normalized = file_reference.strip()
    if "\x00" in normalized:
        raise ValueError("Null bytes are not allowed in local artifact references")
    if normalized != Path(normalized).name:
        raise ValueError("Only filename references are allowed for local artifacts")
    if not _SAFE_LOCAL_REFERENCE_PATTERN.fullmatch(normalized):
        raise ValueError("Local artifact reference contains invalid characters")

    normalized_extensions = _normalize_allowed_extensions(allowed_extensions)
    suffix = Path(normalized).suffix.lower()
    if normalized_extensions:
        if not suffix and not allow_extensionless:
            raise ValueError("Local artifact reference must include an allowed extension")
        if suffix and suffix not in normalized_extensions:
            raise ValueError(f"Unsupported local artifact extension: {suffix}")

    return normalized


def resolve_local_artifact_reference(
    file_reference: str,
    *,
    allowed_root: Path = _VIDEO_TMP_DIR,
    allowed_extensions: Optional[Set[str]] = None,
    allow_extensionless: bool = False,
) -> str:
    """Resolve a validated local artifact reference under the allowed root."""
    normalized = validate_local_artifact_reference(
        file_reference,
        allowed_extensions=allowed_extensions,
        allow_extensionless=allow_extensionless,
    )
    return build_safe_temp_path(normalized, allowed_root=allowed_root)


def validate_video_artifact_reference(video_reference: str) -> str:
    """Validate untrusted video local reference."""
    return validate_local_artifact_reference(
        video_reference,
        allowed_extensions=_VIDEO_EXTENSIONS,
        allow_extensionless=True,
    )


def resolve_video_artifact_reference(
    video_reference: str, *, allowed_root: Path = _VIDEO_TMP_DIR
) -> str:
    """Resolve validated video local reference under the allowed root."""
    return resolve_local_artifact_reference(
        video_reference,
        allowed_root=allowed_root,
        allowed_extensions=_VIDEO_EXTENSIONS,
        allow_extensionless=True,
    )


def validate_manifest_artifact_reference(manifest_reference: str) -> str:
    """Validate untrusted manifest local reference."""
    return validate_local_artifact_reference(
        manifest_reference,
        allowed_extensions=_MANIFEST_EXTENSIONS,
        allow_extensionless=False,
    )


def resolve_manifest_artifact_reference(
    manifest_reference: str, *, allowed_root: Path = _VIDEO_TMP_DIR
) -> str:
    """Resolve validated manifest local reference under the allowed root."""
    return resolve_local_artifact_reference(
        manifest_reference,
        allowed_root=allowed_root,
        allowed_extensions=_MANIFEST_EXTENSIONS,
        allow_extensionless=False,
    )
