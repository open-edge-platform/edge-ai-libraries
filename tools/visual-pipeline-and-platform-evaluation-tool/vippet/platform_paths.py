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


def resolve_linux_path(value: str) -> str:
    r"""Map a Linux resource reference to a configured directory on Windows.

    ``value`` is the stored path. Map LINUX_MODELS_PREFIX to MODELS_PATH and
    LINUX_PUBLIC_MODEL_PROC_PREFIX to PUBLIC_MODEL_PROC_PATH.
    Use the first matching root.
    Only on Windows, paths starting with a mapped Linux root plus '/' are mapped.
    On Linux, or when the prefix does not match, return ``value`` unchanged.
    Relative paths are not joined to a destination directory by this function.

    Preserve the relative suffix, allowing one trailing '/'. Raise
    ValueError for empty, '.' or '..' components, backslashes, colons,
    NUL characters, or a resolved target outside the destination root
    (including an existing symlink pointing outside it). Files need not
    exist; this function does not create directories or copy files.

    Examples on Linux (all inputs are unchanged):
        resolve_linux_path('/models/output/model.xml')
        -> /models/output/model.xml
        resolve_linux_path('public/model.xml')
        -> public/model.xml

    Examples on native Windows, with environment variables set before import:
        MODELS_PATH=C:\Vippet\models
        PUBLIC_MODEL_PROC_PATH=C:\DLStreamer\model-proc

        resolve_linux_path('/models/output/public/model.xml')
        -> C:\Vippet\models\public\model.xml
        resolve_linux_path(LINUX_PUBLIC_MODEL_PROC_PREFIX + '/preproc.json')
        -> C:\DLStreamer\model-proc\preproc.json
        resolve_linux_path('public/model.xml')
        -> public/model.xml
        resolve_linux_path(r'C:\custom\model.xml')
        -> C:\custom\model.xml
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
