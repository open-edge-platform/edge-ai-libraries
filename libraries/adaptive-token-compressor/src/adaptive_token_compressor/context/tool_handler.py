# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tool message handlers: classification + STATUS / ERROR rule compressions +
web_search strip.

All public symbols are pure functions / read-only constants (no backend
calls). Used by `ContextCompressor.compress` to dispatch tool messages into 4
categories:
  - STATUS      '(no new output)' / 'Command still running' etc. (caller
                elides or drops it, pairing-aware).
  - ERROR       '{"status":"error","tool":"X","error":"msg"}' → 'X failed: msg'
  - WEB_SEARCH  Tavily JSON → plaintext, then compress-server with a digit guard.
  - OTHER       everything else; main compressor decides min_chars + routing.
"""
import json
import re
from enum import Enum


class ToolContentCategory(str, Enum):
    """Result of `classify(content)` — drives ContextCompressor's dispatch."""

    STATUS = "status"           # delete or stub-out (pairing-aware)
    ERROR = "error"             # simplify error JSON to short sentence
    WEB_SEARCH = "web_search"   # web_search_strip + compress-server with digit guard
    OTHER = "other"             # main compressor decides min_chars + routing


def classify(content: str) -> ToolContentCategory:
    """Pick the compression category for a tool message (first match wins):
    STATUS regex → ERROR (JSON status=="error") → WEB_SEARCH (JSON results
    list) → OTHER. Pure / idempotent.
    """
    stripped = content.strip()
    if is_status_message(content):
        return ToolContentCategory.STATUS
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            return ToolContentCategory.OTHER
        if isinstance(data, dict):
            if data.get("status") == "error":
                return ToolContentCategory.ERROR
            if isinstance(data.get("results"), list):
                return ToolContentCategory.WEB_SEARCH
    return ToolContentCategory.OTHER


# STATUS rules

STATUS_PATTERNS: list[re.Pattern] = [
    # OpenClaw 2026.3.24 process poll with nothing new appends the process
    # state: "(no new output)\n\nProcess still running." Only the
    # still-running form is a status; "Process exited with code N." /
    # "... signal X." carry the outcome and stay OTHER.
    re.compile(r"^\(no new output\)(\s*\n\s*Process still running\.)?$"),
    re.compile(r"^Command still running"),
    re.compile(r"^\(no output\)$"),
]


def is_status_message(content: str) -> bool:
    """True iff `content.strip()` matches any STATUS_PATTERNS regex."""
    stripped = content.strip()
    return any(pat.match(stripped) for pat in STATUS_PATTERNS)


# ERROR rule

# Keys simplify_error may drop without losing information.
_ERROR_KEYS = frozenset({"status", "tool", "error"})


def simplify_error(content: str) -> str:
    """Reduce '{"status":"error","tool":"X","error":"msg"}' → 'X failed: msg'.
    Lossless: only applies when the JSON has no keys besides status / tool /
    error and both values are strings; anything else (non-error, non-JSON,
    extra fields) is returned unchanged. Pure / idempotent.
    """
    stripped = content.strip()
    if not stripped.startswith("{"):
        return content
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return content
    if not isinstance(data, dict) or data.get("status") != "error":
        return content
    if not set(data) <= _ERROR_KEYS:
        return content
    tool = data.get("tool", "tool")
    msg = data.get("error", "")
    if not isinstance(tool, str) or not isinstance(msg, str):
        return content
    return f"{tool} failed: {msg}"


# WEB_SEARCH strip (Tavily JSON → plaintext, no backend call)

def web_search_strip(content: str) -> str:
    """Strip Tavily search-result JSON to plaintext:
    "Search: {query}\\n\\n{title}\\n{snippet}\\n\\n..." with each field run
    through `_clean_snippet` (no URLs / metadata / tags). Output feeds the
    digit-guarded backend compress. Pure / idempotent; returns input unchanged
    on JSON parse failure.
    """
    try:
        data = json.loads(content.strip())
    except (json.JSONDecodeError, TypeError):
        return content
    if not isinstance(data, dict):
        return content

    parts: list[str] = []
    for r in data.get("results", []) or []:
        if not isinstance(r, dict):
            continue
        title = _clean_snippet(r.get("title", "") or "")
        snippet = _clean_snippet(r.get("snippet", "") or "")
        if snippet:
            parts.append(f"{title}\n{snippet}" if title else snippet)
        elif title:
            parts.append(title)

    query = data.get("query", "") or ""
    return f"Search: {query}\n\n" + "\n\n".join(parts)


def _clean_snippet(text: str) -> str:
    """Strip per-snippet noise (untrusted tags, Markdown images/links, bare
    URLs, nav boilerplate, whitespace). Pure helper for `web_search_strip`.
    """
    text = _UNTRUSTED_TAG_RE.sub("", text)          # security tags
    text = _SOURCE_HEADER_RE.sub("", text)          # 'Source: Web Search\n---' banner
    text = _MD_IMAGE_RE.sub("", text)               # ![alt](url)
    text = _NAV_MENU_RE.sub("", text)               # nav boilerplate (before link reduction)
    text = _MD_LINK_RE.sub(r"\1", text)             # [text](url) → text
    text = _BARE_URL_RE.sub("", text)               # bare https?://...
    text = _WS_RUN_RE.sub(" ", text)                # collapse whitespace runs
    text = _BLANK_LINES_RE.sub("\n\n", text)        # collapse blank-line runs
    return text.strip()


# Noise regexes for `_clean_snippet` (module-level so they compile once).
# Tavily tags carry an id attr: <<<EXTERNAL_UNTRUSTED_CONTENT id="...">>>.
_UNTRUSTED_TAG_RE = re.compile(r"<<<(?:END_)?EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>")
_SOURCE_HEADER_RE = re.compile(r"Source: Web Search\s*\n-{2,}")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_NAV_MENU_RE = re.compile(r"Skip to main content.*?Cookie Settings\.?", re.DOTALL)
_WS_RUN_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n\s*(?:\n\s*)+")
