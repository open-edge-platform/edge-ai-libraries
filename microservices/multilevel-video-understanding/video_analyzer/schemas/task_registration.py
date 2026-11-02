# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Request/response schemas for the dynamic prompt task registry (/v1/tasks).

The `content` field of RegisterTaskRequest holds a single Python-module-style
string with four named anchor sections (GLOBAL_PROMPT / MACRO_CHUNK_PROMPT /
LOCAL_PROMPT / T_MINUS_1_PROMPT). The service parses those anchors, applies
smart auto-fill for missing placeholders, validates rendering, then persists.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


class PromptContent(BaseModel):
    """A prompt content payload — inline text, or an HTTPS URL to fetch.

    Exactly one of `text` / `url` must be provided.
    """
    text: Optional[str] = Field(
        default=None,
        description=(
            "Inline full prompt text containing all four anchors "
            "(GLOBAL_PROMPT / MACRO_CHUNK_PROMPT / LOCAL_PROMPT / T_MINUS_1_PROMPT)."
        ),
    )
    url: Optional[HttpUrl] = Field(
        default=None,
        description="HTTPS URL fetched by the service; Content-Length must be <= 256 KB.",
    )

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.text is None) == (self.url is None):
            raise ValueError("PromptContent requires exactly one of 'text' or 'url'")
        return self


class RegisterTaskRequest(BaseModel):
    """POST /v1/tasks body."""
    task_name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]{1,63}$",
        description="Lowercase ascii, 2-64 chars, underscores allowed. Must not collide with a built-in TASKNAME.",
    )
    mode: Literal["autogen", "full"] = Field(
        ...,
        description=(
            "`autogen` asks the service's own LLM to draft all four sections from `description`; "
            "`full` accepts a user-supplied `content` string with the four anchors."
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description="Required when mode=autogen. Short natural-language description of the use case.",
    )
    content: Optional[PromptContent] = Field(
        default=None,
        description="Required when mode=full. See PromptContent.",
    )

    @model_validator(mode="after")
    def _check_mode_payload(self):
        if self.mode == "autogen":
            if not (self.description and self.description.strip()):
                raise ValueError("mode=autogen requires a non-empty 'description'")
            if self.content is not None:
                raise ValueError("mode=autogen does not accept 'content' (description-only)")
        else:  # full
            if self.content is None:
                raise ValueError("mode=full requires 'content'")
        return self


class PatchTaskRequest(BaseModel):
    """PATCH /v1/tasks/{name} body — every field optional; at least one must be set."""
    new_task_name: Optional[str] = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{1,63}$",
        description="Rename the task. Same charset rules as on register.",
    )
    mode: Optional[Literal["autogen", "full"]] = Field(
        default=None,
        description="If provided, regenerate all four sections from description/content.",
    )
    description: Optional[str] = None
    content: Optional[PromptContent] = None

    @model_validator(mode="after")
    def _non_empty(self):
        if all(v is None for v in (self.new_task_name, self.mode, self.description, self.content)):
            raise ValueError("PATCH body must set at least one of new_task_name/mode/description/content")
        if self.mode == "autogen" and not (self.description and self.description.strip()):
            raise ValueError("mode=autogen requires 'description'")
        if self.mode == "full" and self.content is None:
            raise ValueError("mode=full requires 'content'")
        return self


class TaskInfo(BaseModel):
    """Row returned by GET /v1/tasks."""
    name: str
    source: Literal["builtin", "dynamic"]
    description: Optional[str] = None


class TaskListResponse(BaseModel):
    tasks: List[TaskInfo]


class TaskDetailResponse(BaseModel):
    """Row returned by GET /v1/tasks/{name} and by POST/PATCH on success."""
    name: str
    source: Literal["builtin", "dynamic"]
    description: Optional[str] = None
    content: str = Field(
        ...,
        description=(
            "The full prompt as a single anchor-style text block containing "
            "GLOBAL_PROMPT / MACRO_CHUNK_PROMPT / LOCAL_PROMPT / T_MINUS_1_PROMPT "
            "sections. Ready to copy and re-submit as `content.text` on a future "
            "POST/PATCH (round-trip safe)."
        ),
    )
