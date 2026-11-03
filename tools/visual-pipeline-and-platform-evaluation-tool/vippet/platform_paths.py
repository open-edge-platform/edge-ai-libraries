# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Windows filesystem defaults and mapping for known Linux resource roots."""

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
LEGACY_MODELS_PATH = "/models/output"
LEGACY_PUBLIC_MODEL_PROC = (
    "/home/dlstreamer/dlstreamer/samples/gstreamer/model_proc/public"
)


def data_path(relative: str, posix_default: str) -> str:
    if not IS_WINDOWS:
        return posix_default
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return str(root / "Vippet" / relative)


def resolve_legacy_path(value: str, legacy_root: str, directory: str) -> str:
    prefix = legacy_root + "/"
    if not IS_WINDOWS or not value.startswith(prefix):
        return value
    relative = value[len(prefix) :]
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts) or any(
        char in relative for char in "\\:\0"
    ):
        raise ValueError(f"Invalid relative path under {legacy_root}")
    root = Path(directory)
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(
            f"Resource path escapes configured directory for {legacy_root}"
        )
    return str(target)
