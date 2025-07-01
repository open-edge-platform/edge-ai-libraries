# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from unittest.mock import MagicMock
import pytest

# Mock the vdms module at the test session level
@pytest.fixture(scope="session", autouse=True)
def mock_vdms_module():
    """Mock the vdms module to avoid import errors."""
    mock_vdms = MagicMock()
    sys.modules['vdms'] = mock_vdms
    
    # Mock the langchain_community.vectorstores.vdms module
    mock_vdms_vectorstore = MagicMock()
    mock_vdms_vectorstore.VDMS = MagicMock()
    mock_vdms_vectorstore.VDMS_Client = MagicMock()
    sys.modules['langchain_community.vectorstores.vdms'] = mock_vdms_vectorstore
    
    return mock_vdms