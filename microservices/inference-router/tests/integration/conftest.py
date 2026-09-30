# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test collected from this directory as integration."""
    integration_root = Path(__file__).resolve().parent
    for item in items:
        try:
            item_path = Path(str(item.path)).resolve()
        except Exception:
            continue
        if integration_root in item_path.parents or item_path == integration_root:
            item.add_marker(pytest.mark.integration)