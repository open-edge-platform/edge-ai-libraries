# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: tests/conftest.py
Configuration for pytest - adds src to path for imports.
"""

import sys
from pathlib import Path

# Add project/workspace paths required by cross-package integration tests.
project_root = Path(__file__).resolve().parent.parent
workspace_root = project_root.parent
candidate_paths = [
    project_root / "src",
    workspace_root / "image" / "src",
    workspace_root / "core" / "python",
]
for path in candidate_paths:
    if path.exists():
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

