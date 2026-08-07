# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Intelligent classifier vendored from the intelligent-router tool.

Only the classifier core is kept here (protocol, OpenVINO backend, and a small
config/builder); the standalone HTTP server, CLI, and router wrapper are not
vendored. Consumed by :class:`src.rsd.rule.IntelligentRule`.
"""

from src.rsd.tools.base import ClassifyResult, QueryClassifier
from src.rsd.tools.config import (
    ClassifierConfig,
    build_classifier,
    default_classifier_config,
)

__all__ = [
    "ClassifyResult",
    "QueryClassifier",
    "ClassifierConfig",
    "build_classifier",
    "default_classifier_config",
]
