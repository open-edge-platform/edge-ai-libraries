# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Text normalizer: hide session-specific tokens for cache stability."""
from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable


RestoreContext = Any


@runtime_checkable
class TextNormalizer(Protocol):
    def normalize(self, text: str) -> tuple[str, RestoreContext]: ...

    def restore(self, text: str, ctx: RestoreContext) -> str: ...

    def sweep_residual(self, final: str, source: str) -> str:
        # Whole-text safety net for placeholders that leaked past restore.
        # Single-value normalizers override; multi-value can't pick globally.
        return final

    def placeholders(self) -> list[str]:
        # Strings the compressor passes as backend force_tokens so the BERT
        # tokenizer keeps each placeholder atomic (otherwise restore can't
        # find it back).
        return []


class WorkspaceNormalizer:
    def __init__(
        self,
        *,
        pattern: str,
        placeholder: str = "__AGENT_WORKSPACE__",
    ) -> None:
        self._pattern = re.compile(pattern)
        self._placeholder = placeholder

    def normalize(self, text: str) -> tuple[str, RestoreContext]:
        match = self._pattern.search(text)
        if match is None:
            return text, {"original": None}
        original = match.group(0)
        normalized = self._pattern.sub(self._placeholder, text)
        return normalized, {"original": original}

    def restore(self, text: str, ctx: RestoreContext) -> str:
        original = ctx.get("original") if ctx else None
        if original is None:
            return text
        return text.replace(self._placeholder, original)

    def sweep_residual(self, final: str, source: str) -> str:
        if self._placeholder not in final:
            return final
        match = self._pattern.search(source)
        if match is None:
            return final
        return final.replace(self._placeholder, match.group(0))

    def placeholders(self) -> list[str]:
        return [self._placeholder]


class NullNormalizer:
    def normalize(self, text: str) -> tuple[str, RestoreContext]:
        return text, None

    def restore(self, text: str, ctx: RestoreContext) -> str:
        return text

    def sweep_residual(self, final: str, source: str) -> str:
        return final

    def placeholders(self) -> list[str]:
        return []


class CompositeNormalizer:
    """Chain normalizers: forward in order, restore in reverse."""

    def __init__(self, normalizers: list[TextNormalizer]) -> None:
        self._normalizers = list(normalizers)

    def normalize(self, text: str) -> tuple[str, RestoreContext]:
        ctxs: list[RestoreContext] = []
        current = text
        for n in self._normalizers:
            current, ctx = n.normalize(current)
            ctxs.append(ctx)
        return current, ctxs

    def restore(self, text: str, ctx: RestoreContext) -> str:
        current = text
        for n, c in zip(reversed(self._normalizers), reversed(ctx)):
            current = n.restore(current, c)
        return current

    def sweep_residual(self, final: str, source: str) -> str:
        current = final
        for n in self._normalizers:
            current = n.sweep_residual(current, source)
        return current

    def placeholders(self) -> list[str]:
        out: list[str] = []
        for n in self._normalizers:
            fn = getattr(n, "placeholders", None)
            if fn is not None:
                out.extend(fn())
        return out
