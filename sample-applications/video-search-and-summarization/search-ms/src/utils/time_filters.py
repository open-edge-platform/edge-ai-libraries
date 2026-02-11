# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Utilities to extract time ranges from natural language queries."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

import dateparser
from dateparser import search as date_search
from tzlocal import get_localzone
from word2number import w2n

# VDMS stores frame metadata with an ISO 8601 "created_at" string (local tz).
# We parse user text into an aware datetime range and return ISO strings
# suitable for VDMS constraints.


def _normalized_now(now: Optional[datetime] = None) -> datetime:
    """Return a timezone-aware now aligned with DataPrep's local-time storage."""
    if now is None:
        # Align with DataPrep which stores local-timezone timestamps
        return datetime.now(get_localzone())
    return now


def _parse_number(value: str) -> Optional[int]:
    """Convert digits or number words (incl. multi-word) to int; None if invalid."""
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        try:
            return w2n.word_to_num(value)
        except Exception:
            return None


def _range_from_relative(match: re.Match, now: datetime) -> Optional[Tuple[datetime, datetime]]:
    """Build (start, end) for phrases like 'last 6 hours' or 'past twenty four minutes'."""
    number_raw = match.group("value")
    number = _parse_number(number_raw)
    if number is None:
        return None
    unit = match.group("unit")

    if unit.startswith("sec"):
        delta = timedelta(seconds=number)
    elif unit.startswith("min"):
        delta = timedelta(minutes=number)
    elif unit.startswith("hour"):
        delta = timedelta(hours=number)
    elif unit.startswith("day"):
        delta = timedelta(days=number)
    elif unit.startswith("week"):
        delta = timedelta(weeks=number)
    else:
        return None

    start = now - delta
    end = now
    return start, end


def _range_for_today(now: datetime) -> Tuple[datetime, datetime]:
    """Return today's range from midnight to now."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _range_for_yesterday(now: datetime) -> Tuple[datetime, datetime]:
    """Return yesterday's full-day range (local tz)."""
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def parse_time_range(text: str, now: Optional[datetime] = None) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Parse common natural-language time ranges.

    Returns (start_dt, end_dt) as timezone-aware datetimes when possible.
    """
    if not text:
        return None, None

    current = _normalized_now(now)
    lowered = text.lower()

    # Explicit relative ranges like "last 6 hours", "past thirty minutes", "past 45 seconds"
    # Regex captures:
    #  - group 1: 'last' or 'past'
    #  - value: digits or one-or-more word tokens (allows multi-word numbers: twenty four)
    #  - unit: seconds|minutes|hours|days|weeks (singular/plural)
    rel_match = re.search(
        r"(last|past)\s+(?P<value>(\d+|[a-z-]+(?:\s+[a-z-]+)*))\s+(?P<unit>seconds?|minutes?|hours?|days?|weeks?)",
        lowered,
    )
    if rel_match:
        parsed = _range_from_relative(rel_match, current)
        if parsed:
            return parsed

    # Today / yesterday shortcuts
    if "today" in lowered:
        return _range_for_today(current)
    if "yesterday" in lowered:
        return _range_for_yesterday(current)

    # Specific day phrases (e.g., "last Sunday")
    settings = {
        "RELATIVE_BASE": current,
        "PREFER_DATES_FROM": "past",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "STRICT_PARSING": True,
    }

    search_results = date_search.search_dates(text, settings=settings)
    if search_results:
        # Pick the first match; treat it as a day span
        _, dt = search_results[0]
        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    # Fallback: best-effort single parse
    dt = dateparser.parse(text, settings=settings)
    if dt:
        # If the original text hints at a relative period but our regex missed it (e.g., misspelling),
        # treat the parsed datetime as the start and use now as the end.
        if any(marker in lowered for marker in ("last", "past")):
            return dt, current

        # If a time component is present, keep a tight window of one hour from that time.
        if dt.hour or dt.minute or dt.second or dt.microsecond:
            return dt, dt + timedelta(hours=1)

        # Otherwise treat it as a date-only span.
        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    return None, None


def build_vdms_time_filter(text: str, property_name: str = "created_at", now: Optional[datetime] = None) -> Optional[dict]:
    """Return a VDMS constraints dict for the given text-derived time range."""
    start, end = parse_time_range(text, now=now)
    if not (start and end):
        return None

    # Convert to ISO with timezone to keep lexical ordering reliable
    start_iso = start.isoformat()
    end_iso = end.isoformat()
    return {property_name: [">=", start_iso, "<=", end_iso]}
