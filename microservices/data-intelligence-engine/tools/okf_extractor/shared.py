# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared upload paths, independent of engine imports and container mount names."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

TASK_DIRECTORY = "okf-extractor"


def upload_directory() -> Path:
    """Use the same upload setting/default as the engine, without importing it."""
    workspace = Path(os.getenv(
        "ENGINE_WORKSPACE", str(Path(__file__).resolve().parents[2] / "workspace"),
    ))
    return Path(os.getenv("ENGINE_UPLOAD_DIR", str(workspace / "uploads"))).resolve()


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not path.parts or path.is_absolute() or path.as_posix() != value
        or any(part in (".", "..") or part.startswith(".") for part in path.parts)
        or any(len(part.encode("utf-8")) > 255 or part == "__files__" for part in path.parts)
        or "\\" in value or ":" in value or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("path must be a safe, non-hidden relative POSIX path")
    return value


def shared_path(root: Path, relative: str) -> Path:
    """Resolve `relative` under the trusted `root`, rejecting traversal and symlinked components."""
    root = root.resolve()
    path = root
    for part in PurePosixPath(relative_path(relative)).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symlinks are not allowed in shared upload paths: {relative!r}")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Path is outside the shared upload directory")
    return path