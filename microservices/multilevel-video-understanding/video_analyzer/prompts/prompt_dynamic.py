# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Adapter that wraps four arbitrary prompt strings as a BasePrompt subclass.

Used by the runtime registry so that dynamic video summary tasks plug into the
existing prompt_builder factory / VideoSummarizer call chain without special
cases elsewhere in the codebase.
"""

from video_analyzer.prompts.prompt_base import BasePrompt, escape_unknown_braces


class DynamicPrompt(BasePrompt):
    """Runtime-registered prompt set.

    `{question}` and `{chunk_subtitle}` are optional (their lines/sections are
    stripped when the value is empty). All other `{...}` that are not recognized
    placeholders are escaped at construction time so example JSON / code in a
    user prompt renders literally instead of breaking `str.format`.
    """

    # Placeholders that may be absent at render time (default to empty).
    _OPTIONAL = frozenset({"question", "chunk_subtitle"})

    def __init__(
        self,
        task_name: str,
        global_prompt: str,
        macro_prompt: str,
        local_prompt: str,
        t_minus_prompt: str,
    ):
        self.task_name = task_name
        # Escape unknown braces so arbitrary user content is safe to `.format`.
        self._global = escape_unknown_braces(global_prompt)
        self._macro = escape_unknown_braces(macro_prompt)
        self._local = escape_unknown_braces(local_prompt)
        self._t_minus = escape_unknown_braces(t_minus_prompt)

    # ------------------------------------------------------------------ shared
    @staticmethod
    def _strip_empty_question_line(lines):
        """Drop lines that are just an (empty) user-prompt echo."""
        return [
            ln for ln in lines
            if not ln.strip().startswith("User prompt:")
            and not ln.strip().startswith("用户提问:")
        ]

    @staticmethod
    def _strip_empty_subtitle_section(lines):
        """Drop a '##Subtitles:' header and its (now empty) body."""
        out = []
        skip = 0
        for i, ln in enumerate(lines):
            if skip:
                skip -= 1
                continue
            if ln.strip().startswith("##Subtitles:"):
                skip = 1
                if i + 2 < len(lines) and not lines[i + 2].strip():
                    skip = 2
                continue
            out.append(ln)
        while out and not out[0].strip():
            out.pop(0)
        while out and not out[-1].strip():
            out.pop()
        return out

    def _render_optional(self, template: str, kwargs: dict) -> str:
        """Render with {question} and {chunk_subtitle} treated as optional.

        Empty values default to '' and their surrounding line/section is stripped.
        """
        fields = self._get_template_fields(template)
        optional = self._OPTIONAL & fields
        rendered = self._render_validated(template, kwargs, optional_fields=optional)

        lines = rendered.splitlines()
        if "question" in fields and not str(kwargs.get("question", "")).strip():
            lines = self._strip_empty_question_line(lines)
        if "chunk_subtitle" in fields and not str(kwargs.get("chunk_subtitle", "")).strip():
            lines = self._strip_empty_subtitle_section(lines)
        return "\n".join(lines) + "\n"

    # ----------------------------------------------------------- BasePrompt impl
    def assign_global_prompt(self, **kwargs) -> str:
        return self._render_optional(self._global, kwargs)

    def assign_macro_prompt(self, **kwargs) -> str:
        return self._render_optional(self._macro, kwargs)

    def assign_local_prompt(self, **kwargs) -> str:
        return self._render_optional(self._local, kwargs)

    def assign_t_minus_prompt(self, **kwargs) -> str:
        return self._render_optional(self._t_minus, kwargs)
