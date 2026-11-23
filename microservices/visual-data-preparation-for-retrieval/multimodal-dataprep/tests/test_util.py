# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from src.core.utils.common_utils import sanitize_input


def test_sanitize_input():
    """Test how sanitize_input validator should behave on several inputs."""
    assert sanitize_input("") == None
    assert sanitize_input("  ") == None
    assert sanitize_input("test") == "test"
    assert sanitize_input("  test  ") == "test"
