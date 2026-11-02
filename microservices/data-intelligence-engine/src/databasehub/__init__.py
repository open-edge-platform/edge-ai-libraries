# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Connection-owning adapters and low-level database operations."""

from databasehub.models import (
	GraphCollection,
	ObjectCollection,
	SqlCollection,
	VectorCollection,
)

__all__ = [
	"GraphCollection",
	"ObjectCollection",
	"SqlCollection",
	"VectorCollection",
	"database_manager",
]


def __getattr__(name: str):
	if name == "database_manager":
		from databasehub.manager import database_manager

		return database_manager
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")