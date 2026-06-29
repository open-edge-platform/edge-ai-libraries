# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared logging utilities for gateway and provider
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


# Keys that are handled by the router and should not be passed through to backends
_EXCLUDE_KEYS = frozenset({"messages", "model", "stream"})


def build_call_params(request_params: dict) -> dict:
    """Extract backend-passthrough parameters from request params.

    Filters out router-specific keys (messages, model, stream) and keys with
    None values.
    """
    return {k: v for k, v in request_params.items()
            if k not in _EXCLUDE_KEYS and v is not None}


def sanitize_for_log(value) -> str:
    """Strip CR/LF from a user-controlled value before logging.

    Removing newline characters prevents an attacker from forging additional
    log lines via embedded ``\\r``/``\\n`` sequences (CWE-117).
    """
    if value is None:
        return ""
    return str(value).replace("\r\n", "").replace("\n", "").replace("\r", "")


def is_verbose_enabled(verbose_flag: bool = False) -> bool:
    """Check whether verbose response logging is enabled."""
    return (
        verbose_flag
        or os.getenv("GATEWAY_VERBOSE", "").lower() in {"1", "true", "yes", "on"}
        or os.getenv("GATEWAY_VERBOSE_FULL", "").lower() in {"1", "true", "yes", "on"}
    )


def is_verbose_full_enabled(verbose_full_flag: bool = False) -> bool:
    """Check whether full verbose logging is enabled."""
    return verbose_full_flag or os.getenv("GATEWAY_VERBOSE_FULL", "").lower() in {"1", "true", "yes", "on"}


def log_to_gateway_file(message: str, log_dir: Optional[Path] = None):
    """Write message to the central gateway.log file."""
    if log_dir:
        gateway_log = log_dir / "gateway.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(gateway_log, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")


def log_verbose_response(label: str, payload, request_id: str = None, log_dir: Optional[Path] = None, verbose_flag: bool = False):
    """Print and optionally save raw backend responses when verbose mode is enabled.

    Behavior:
    - If verbose enabled: always print to terminal
    - If verbose AND log_dir provided: print to terminal AND save to files
    """
    if not is_verbose_enabled(verbose_flag):
        return

    import json

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    header = f"🔎 {label}"
    if request_id:
        header += f" [request_id={request_id}]"

    try:
        formatted = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        formatted = str(payload)

    # Always print to terminal when verbose is enabled
    print(f"\n{'='*80}")
    print(f"[{timestamp}] {header}")
    print(f"{'='*80}")
    print(formatted)
    print()

    # Additionally save to files if log_dir is configured
    if log_dir:
        # Save to per-request log file if request_id is provided
        if request_id:
            log_file = log_dir / f"{request_id}.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp}] {label}\n")
                f.write(f"{'='*80}\n")
                f.write(formatted)
                f.write("\n")

        # Also save to central gateway.log
        gateway_log = log_dir / "gateway.log"
        with open(gateway_log, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[{timestamp}] {header}\n")
            f.write(f"{'='*80}\n")
            f.write(formatted)
            f.write("\n")
