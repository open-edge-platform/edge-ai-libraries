# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Field extraction — turn a response body into ``{name: value}`` pairs.

The field *name* comes from the response, not from config. A single regex can
therefore discover many fields at once (one per matching line), and each distinct
name becomes its own series downstream. What to parse is data in ``config.yaml``,
not a subclass.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from src.providers.probes.spec import ExtractRule


logger = logging.getLogger(__name__)

# Characters that would break a dotted metadata path (routing reads probe values
# as e.g. ``performance.<name>``) or collide with Prometheus label syntax;
# stripped/replaced when a parsed name becomes a field name.
_LABEL_BLOCK = re.compile(r"\{[^}]*\}")
_UNSAFE_CHARS = re.compile(r"[.:\s]")

# One extracted sample: (name as captured, published field name, value).
Match = Tuple[str, str, float]


def normalize_field_name(name: str) -> str:
    """Make a parsed name safe as a dotted-path segment.

    Drops Prometheus ``{label="..."}`` blocks and replaces ``.``/``:``/space
    so a raw metric name never fractures the path or shadows a nested key.
    Idempotent. Applied once at extraction, so every sink — metadata and file —
    publishes the same name.
    """
    cleaned = _LABEL_BLOCK.sub("", name)
    cleaned = _UNSAFE_CHARS.sub("_", cleaned).strip("_")
    return cleaned or "value"


class FieldExtractor:
    """Apply one :class:`ExtractRule` to a response, yielding ``{name: value}``.

    Regex rules follow the "last group = value, preceding group = name"
    convention so one pattern can name and read many fields. JSON rules read a
    single numeric leaf named by the last path segment. Names are normalized
    with :func:`normalize_field_name`.
    """

    def __init__(self, rule: ExtractRule):
        self.rule = rule
        self._pattern = re.compile(rule.regex) if rule.regex else None

    def apply(self, response_text: str) -> Dict[str, float]:
        """Extract ``{name: value}`` from the raw response body.

        A non-numeric captured value is skipped (a parse error, not fatal). No
        matches simply yields an empty dict — the caller records that as a miss.
        Several matches with the same name → the last one wins.
        """
        return {name: value for _, name, value in self.matches(response_text)}

    def matches(self, response_text: str) -> List[Match]:
        """Every sample in response order, before same-name matches collapse.

        Lets the caller see when several matches publish under one name (only
        the last survives in :meth:`apply`) and warn about it.
        """
        if self._pattern is not None:
            return self._match_regex(response_text)
        return self._match_json(response_text)

    def _match_regex(self, text: str) -> List[Match]:
        found: List[Match] = []
        for match in self._pattern.finditer(text):
            groups = match.groups()
            if len(groups) < 2:
                # A pattern must capture at least (name, value).
                continue
            name, raw_value = groups[-2], groups[-1]
            if name is None or raw_value is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                # Non-numeric value on this line — skip it, keep scanning.
                continue
            found.append((str(name), normalize_field_name(str(name)), value))
        return found

    def _match_json(self, text: str) -> List[Match]:
        try:
            body = json.loads(text)
        except (ValueError, TypeError):
            logger.debug("probe JSON extract: response was not valid JSON")
            return []

        node: Any = body
        parts = self.rule.json_path.split(".")
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return []

        try:
            value = float(node)
        except (TypeError, ValueError):
            return []
        return [(parts[-1], normalize_field_name(parts[-1]), value)]
