# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Import helper for the execd reader scripts under scripts/.

The readers are standalone scripts, not a package. At import they attach a
FileHandler (default /app/<name>_trace.log) to the *root* logger, which would
fail outside the container and clobber logging for the rest of the test session.
``load_reader`` points the log at a temp file and restores the root logger
afterwards.
"""

import importlib.util
import logging
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def load_reader(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Callable[..., ModuleType]]:
    """Return ``load(script_stem, log_env)`` that imports scripts/<script_stem>.py."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    loaded: list[str] = []
    monkeypatch.syspath_prepend(str(SCRIPTS_DIR))

    def load(script_stem: str, log_env: str) -> ModuleType:
        monkeypatch.setenv(log_env, str(tmp_path / f"{script_stem}.log"))
        name = f"_reader_under_test_{script_stem}"
        spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{script_stem}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        loaded.append(name)
        spec.loader.exec_module(module)
        return module

    yield load

    for handler in root.handlers:
        if handler not in saved_handlers:
            handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    for name in loaded:
        sys.modules.pop(name, None)
