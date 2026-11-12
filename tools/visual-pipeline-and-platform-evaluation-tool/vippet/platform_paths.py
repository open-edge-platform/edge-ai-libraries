# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Windows mapping for known Linux resource roots."""

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
LINUX_MODELS_PREFIX = "/models/output"
LINUX_PUBLIC_MODEL_PROC_PREFIX = (
    "/home/dlstreamer/dlstreamer/samples/gstreamer/model_proc/public"
)
MODELS_PATH: str = os.path.normpath(os.environ.get("MODELS_PATH", "/models/output"))
PUBLIC_MODEL_PROC_PATH: str = os.path.normpath(
    os.environ.get("PUBLIC_MODEL_PROC_PATH", LINUX_PUBLIC_MODEL_PROC_PREFIX)
)
LINUX_PATH_MAPPINGS: dict[str, str] = {
    LINUX_MODELS_PREFIX: MODELS_PATH,
    LINUX_PUBLIC_MODEL_PROC_PREFIX: PUBLIC_MODEL_PROC_PATH,
}


def adapt_linux_path_for_windows(value: str) -> str:
    """Adapt stored Linux model and model-proc paths for native Windows.

    Pipeline descriptions and model definitions can contain absolute Linux paths
    for model, model-proc or extra-model-proc files. On Windows, replace their known Linux
    prefixes with the configured MODELS_PATH or PUBLIC_MODEL_PROC_PATH,
    preserving the relative path within the destination directory.

    MODELS_PATH cannot serve as the source prefix: when configured for Windows,
    it points to a Windows directory, while the stored reference still starts
    with '/models/output'. LINUX_MODELS_PREFIX and LINUX_PUBLIC_MODEL_PROC_PREFIX
    therefore identify source paths independently of the configured destinations.

    On Linux, or for paths without a recognized prefix, return the input unchanged.
    Reject invalid mapped suffixes and targets outside the configured directory.
    """
    if not IS_WINDOWS:
        return value
    for linux_root, directory in LINUX_PATH_MAPPINGS.items():
        prefix = linux_root + "/"
        if not value.startswith(prefix):
            continue
        relative = value[len(prefix) :].removesuffix("/")
        parts = relative.split("/")
        if any(part in {"", ".", ".."} for part in parts) or any(
            char in relative for char in "\\:\0"
        ):
            raise ValueError(f"Invalid relative path under {linux_root}")
        root = Path(directory)
        target = root.joinpath(*parts)
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError(
                f"Resource path escapes configured directory for {linux_root}"
            )
        return str(target)
    return value
