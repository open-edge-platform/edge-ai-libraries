# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Requests and results shared by asset-library sources."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config

@dataclass
class VectorIngestRequest:
    documents: List[Any] = field(default_factory=list)
    nodes: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class VectorRetrieveRequest:
    query: str
    top_k: int = config.RETRIEVE_TOP_K
    filters: Any = None


@dataclass
class GraphIngestRequest:
    vertices: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class GraphRetrieveRequest:
    statement: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceResult:
    source_id: str
    record_id: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None