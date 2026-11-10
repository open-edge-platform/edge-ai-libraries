# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class VectorCollection:
    name: str
    dimension: int = 0


@dataclass(frozen=True)
class SqlCollection:
    table: str
    schema: str = "public"
    database: str = ""


@dataclass(frozen=True)
class GraphCollection:
    space: str


@dataclass(frozen=True)
class ObjectCollection:
    bucket: str
    prefix: str = ""


CollectionLocator = Union[
    VectorCollection,
    SqlCollection,
    GraphCollection,
    ObjectCollection,
]