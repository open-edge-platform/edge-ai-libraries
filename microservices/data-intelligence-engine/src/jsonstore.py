# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Atomic JSON files in the workspace.

Two things persist here -- the asset libraries (`core/repository.py`) and the
database connections (`databasehub/repository.py`) -- and both need the same
guarantee: each file is rewritten *whole* from the live set, so a crash or a
full disk must leave the previous file intact rather than a half-written one.
The records go to a temporary file in the same directory, are flushed to disk,
and only then replace the live file.

It lives at the engine root rather than in `core/` because `databasehub` uses it
and must not import `core` -- the dependency runs the other way.

Callers serialize their own writes; nothing here takes a lock.
"""

import json
import os
import tempfile
from typing import Any, List


def _fsync_directory(directory: str) -> None:
    """Persist the rename itself, where the platform supports it."""
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_json(path: str, records: Any, what: str = "records") -> bool:
    """Replace `path` with `records`, atomically. False if it could not be done.

    A read-only workspace costs persistence, not the request in flight -- and
    whatever was saved last is still whole -- so this reports rather than raises.
    """
    directory = os.path.dirname(path) or "."
    temporary_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp"
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(records, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory(directory)
    except OSError as error:
        print(f"Could not persist {what} to {path}: {error}")
        return False
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
    return True


def read_json(path: str, what: str = "records") -> List[dict]:
    """The dict records in `path`; an empty list if it is absent or unreadable.

    An unreadable file is reported and skipped rather than raised: one corrupt
    file should cost the records it holds, not the service starting at all.
    """
    try:
        with open(path, "r", encoding="utf-8") as file:
            records = json.load(file)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as error:
        print(f"Ignoring unreadable {what} file {path}: {error}")
        return []
    if not isinstance(records, list):
        print(f"Ignoring {what} file {path}: expected a list of records")
        return []
    return [record for record in records if isinstance(record, dict)]
