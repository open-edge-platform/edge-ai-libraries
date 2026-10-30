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
from typing import Any, Dict

from src.providers.probes.spec import ExtractRule


logger = logging.getLogger(__name__)


class FieldExtractor:
    """Apply one :class:`ExtractRule` to a response, yielding ``{name: value}``.

    Regex rules follow the "last group = value, preceding group = name"
    convention so one pattern can name and read many fields. JSON rules read a
    single numeric leaf named by the last path segment.
    """

    def __init__(self, rule: ExtractRule):
        self.rule = rule
        self._pattern = re.compile(rule.regex) if rule.regex else None

    def apply(self, response_text: str) -> Dict[str, float]:
        """Extract ``{name: value}`` from the raw response body.

        A non-numeric captured value is skipped (a parse error, not fatal). No
        matches simply yields an empty dict — the caller records that as a miss.
        """
        if self._pattern is not None:
            return self._apply_regex(response_text)
        return self._apply_json(response_text)

    def _apply_regex(self, text: str) -> Dict[str, float]:
        fields: Dict[str, float] = {}
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
            # Same name on several lines → last match wins (documented). Include
            # a distinguishing label in the captured name to keep series apart.
            fields[str(name)] = value
        return fields

    def _apply_json(self, text: str) -> Dict[str, float]:
        try:
            body = json.loads(text)
        except (ValueError, TypeError):
            logger.debug("probe JSON extract: response was not valid JSON")
            return {}

        node: Any = body
        parts = self.rule.json_path.split(".")
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return {}

        try:
            value = float(node)
        except (TypeError, ValueError):
            return {}
        return {parts[-1]: value}
