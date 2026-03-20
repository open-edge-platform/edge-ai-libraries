# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Common utilities for GenAI application sizing tool.

This package provides modular utilities organized into:
- constants: Magic numbers and configuration constants
- config: Configuration reading and profile management
- metrics: Metrics calculation and reporting
- video: Video file processing and analysis
- perf_tools: Performance monitoring tool management
- utils: Core utility functions and backward-compatible re-exports

For backward compatibility, all functions are also re-exported from utils.
"""

from common.constants import *
from common.config import *
from common.metrics import *
from common.video import *
from common.perf_tools import *
from common.utils import (
    setup_report_permissions,
    safe_parse_string_to_dict,
    get_ip_address,
    delete_existing_docs,
    upload_document_before_conversation,
    setup_document_upload,
    get_response,
)
