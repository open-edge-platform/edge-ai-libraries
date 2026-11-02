# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Pytest configuration and shared fixtures for dlsps2 tests."""

import sys
import os
from pathlib import Path

# Add src directory to path so we can import dlsps2 modules
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
