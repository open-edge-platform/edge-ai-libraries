# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum


class SummarizationStatus(str, Enum):
    """Enum for the status of a summarization job"""
    COMPLETED = "completed"
    FAILED = "failed"
