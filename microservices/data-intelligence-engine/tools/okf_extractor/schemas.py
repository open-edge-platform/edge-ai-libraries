# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Task metadata and shared-upload file references; bundles are returned by path."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .prompts import DEFAULT_INSTRUCTIONS
from .shared import relative_path


class TaskOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="", max_length=100)
    goal: str = Field(default="", max_length=8000)
    instructions: dict[str, str] = Field(default_factory=dict)

    @field_validator("instructions")
    @classmethod
    def known_instructions(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - DEFAULT_INSTRUCTIONS.keys()
        if unknown:
            raise ValueError(f"Unknown instruction segments: {', '.join(sorted(unknown))}")
        return value


class TaskContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1024)
    content: str | None = None
    file_path: str | None = Field(default=None, min_length=1, max_length=2048)
    media_type: str = ""
    asset_id: str = ""

    @field_validator("path", "file_path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return relative_path(value) if value is not None else None

    @model_validator(mode="after")
    def one_payload(self) -> Self:
        if (self.content is None) == (self.file_path is None):
            raise ValueError("Provide exactly one of content or file_path")
        return self


class TaskMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(
        default_factory=lambda: uuid4().hex,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
    )
    options: TaskOptions = Field(default_factory=TaskOptions)


class ExtractionTask(TaskMetadata):
    items: list[TaskContent] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        paths = [item.path for item in self.items]
        if len(set(paths)) != len(paths):
            raise ValueError("Task source paths must be unique")
        # A source cannot be both a file and a parent directory of another file.
        names = set(paths)
        if any(parent.as_posix() in names for path in paths
               for parent in PurePosixPath(path).parents if parent != PurePosixPath(".")):
            raise ValueError("Task source paths have a file/directory conflict")
        ids = [item.asset_id for item in self.items if item.asset_id]
        if len(set(ids)) != len(ids):
            raise ValueError("Task asset IDs must be unique")
        return self


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    bundle_path: str
    concept_count: int = Field(ge=1)