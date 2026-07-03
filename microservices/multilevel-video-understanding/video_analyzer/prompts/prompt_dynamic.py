# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Adapter that wraps four arbitrary prompt strings as a BasePrompt subclass.

Used by the runtime registry so that dynamic video summary tasks plug into the
existing prompt_builder factory / VideoSummarizer call chain without special
cases elsewhere in the codebase.
"""

from video_analyzer.prompts.prompt_base import BasePrompt


class DynamicPrompt(BasePrompt):
    """Runtime-registered prompt set.

    Each section string may contain `{question}` as an optional placeholder
    (stripped when the question is empty). The T-minus-1 section has stricter
    required fields — see _render_validated calls below.
    """

    def __init__(
        self,
        task_name: str,
        global_prompt: str,
        macro_prompt: str,
        local_prompt: str,
        t_minus_prompt: str,
    ):
        self.task_name = task_name
        self._global = global_prompt
        self._macro = macro_prompt
        self._local = local_prompt
        self._t_minus = t_minus_prompt

    # ------------------------------------------------------------------ shared
    @staticmethod
    def _strip_empty_question_line(rendered: str) -> str:
        """Drop lines starting with '用户提问:' when the question is empty."""
        lines = rendered.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("用户提问:")]
        return "\n".join(lines) + "\n"

    def _render_optional_question(self, template: str, kwargs: dict) -> str:
        """Render with {question} treated as optional (empty -> strip line)."""
        question = kwargs.get("question", "")
        fields = self._get_template_fields(template)
        optional = {"question"} & fields
        rendered = self._render_validated(template, kwargs, optional_fields=optional)
        if not str(question).strip() and "question" in fields:
            return self._strip_empty_question_line(rendered)
        return rendered

    # ----------------------------------------------------------- BasePrompt impl
    def assign_global_prompt(self, **kwargs) -> str:
        return self._render_optional_question(self._global, kwargs)

    def assign_macro_prompt(self, **kwargs) -> str:
        return self._render_optional_question(self._macro, kwargs)

    def assign_local_prompt(self, **kwargs) -> str:
        return self._render_optional_question(self._local, kwargs)

    def assign_t_minus_prompt(self, **kwargs) -> str:
        # T-1 context has no optional fields by convention.
        return self._render_validated(self._t_minus, kwargs, optional_fields=set())
