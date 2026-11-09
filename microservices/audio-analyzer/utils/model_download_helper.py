# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Helper for fetching model snapshots from Hugging Face or ModelScope.

Used by the optional FunASR Paraformer provider (Chinese/English ASR). Hub
clients are imported lazily so this module — and the rest of the service —
imports cleanly even when modelscope/huggingface_hub are not installed (the
default image ships without the optional Chinese-ASR dependencies).
"""
import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional


def get_or_download_model_dir(
    model: str,
    hub: Literal["hf", "ms"] = "ms",
    revision: Optional[str] = None,
    local_dir: Optional[str] = None,
    exist_ok: bool = True,
    **snapshot_kwargs: Any,
) -> str:
    """Ensure a model snapshot is present locally and return its directory.

    Args:
        model: Repo/model id or local path.
        hub: "hf" (Hugging Face) or "ms" (ModelScope).
        revision: Optional revision / branch / commit.
        local_dir: Preferred target directory. If it exists and is non-empty
            and exist_ok=True, it is returned as-is (offline-capable reuse).
        exist_ok: If False, re-download even when local_dir already has files.
        **snapshot_kwargs: Passed through to the underlying snapshot_download.

    Returns:
        Absolute path to the directory containing the model files.
    """
    # Reuse an already-populated target directory without touching the network.
    if local_dir and os.path.isdir(local_dir):
        if exist_ok and any(Path(local_dir).iterdir()):
            return str(Path(local_dir).resolve())

    if hub == "hf":
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is not installed") from exc
    elif hub == "ms":
        try:
            from modelscope.hub.snapshot_download import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "modelscope is not installed. Install optional Chinese-ASR "
                "dependencies with: pip install -r requirements-cjk.txt"
            ) from exc
    else:
        raise ValueError(f"Unsupported hub: {hub}")

    kwargs: Dict[str, Any] = {}
    if revision:
        kwargs["revision"] = revision
    if local_dir:
        kwargs["local_dir"] = local_dir
    kwargs.update(snapshot_kwargs)

    # A local path already on disk (not a hub id) is returned unchanged.
    if os.path.isdir(model) and not kwargs.get("local_dir"):
        return str(Path(model).resolve())

    model_dir = snapshot_download(model, **kwargs)
    return str(Path(model_dir).resolve())
