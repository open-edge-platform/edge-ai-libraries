# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Escaping for GStreamer descriptions, not shell command lines."""

import re


def quote_property(value: object) -> str:
    text = str(value)
    if text and not re.search(r"""[\s\\!"',]""", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unquote_property(value: str) -> str:
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return re.sub(r"""\\([\\"])""", r"\1", value[1:-1])
    return value
