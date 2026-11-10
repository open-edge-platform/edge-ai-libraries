# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Escaping for GStreamer descriptions, not shell command lines."""

import re


def quote_property(value: object) -> str:
    """Serialize a value for use in a GStreamer pipeline property.

    Convert the value to text and add double quotes when it is empty or
    contains whitespace, backslashes, quotes, exclamation marks, or commas.
    Within quoted values, escape backslashes and double quotes.
    This does not provide shell escaping.
    """
    text = str(value)
    if text and not re.search(r"""[\s\\!"',]""", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unquote_property(value: str) -> str:
    """Remove matching outer quotes from a serialized GStreamer property.

    For values enclosed in single or double quotes, remove the outer quotes
    and unescape backslashes that precede a backslash or double quote.
    Return values without matching outer quotes unchanged.
    """
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return re.sub(r"""\\([\\"])""", r"\1", value[1:-1])
    return value
