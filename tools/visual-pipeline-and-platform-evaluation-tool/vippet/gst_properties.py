# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Escaping for GStreamer descriptions, not shell command lines."""

import re


def quote_property(value: object) -> str:
    text = str(value)
    if text and not re.search(r"""[\s\\!"']""", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unquote_property(value: str) -> str:
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return re.sub(r"""\\([\\"])""", r"\1", value[1:-1])
    return value


def split_pipeline(description: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote = ""
    escaped = False
    for index, char in enumerate(description):
        if escaped:
            escaped = False
        elif quote and char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif (
            char == "\\"
            and index + 1 < len(description)
            and description[index + 1] in "\"'!"
        ):
            escaped = True
        elif char in "\"'":
            quote = char
        elif char == "!":
            parts.append(description[start:index])
            start = index + 1
    if quote:
        raise ValueError("Unterminated quoted GStreamer property")
    parts.append(description[start:])
    return parts
