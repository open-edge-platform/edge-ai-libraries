# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Standard 5-field cron expressions: ``minute hour day-of-month month day-of-week``."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import FrozenSet, Optional, Tuple

_FIELDS: Tuple[Tuple[str, int, int], ...] = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day of month", 1, 31),
    ("month", 1, 12),
    ("day of week", 0, 7),
)


def _field(text: str, name: str, low: int, high: int) -> FrozenSet[int]:
    values = set()
    for part in text.split(","):
        body, _, step_text = part.partition("/")
        try:
            step = int(step_text) if step_text else 1
            if body == "*":
                start, end = low, high
            elif "-" in body:
                start, end = (int(bound) for bound in body.split("-", 1))
            else:
                start = int(body)
                end = high if step_text else start
        except ValueError:
            raise ValueError(f"Invalid cron {name} field: {text!r}") from None
        if step < 1 or not low <= start <= end <= high:
            raise ValueError(f"Cron {name} field {text!r} is outside {low}-{high}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class Cron:
    expression: str
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]          # 0 = Sunday
    any_day: bool
    any_weekday: bool

    def _day_matches(self, moment: datetime) -> bool:
        if moment.month not in self.months:
            return False
        day = moment.day in self.days
        weekday = (moment.isoweekday() % 7) in self.weekdays
        if self.any_day or self.any_weekday:
            return day and weekday
        return day or weekday

    def matches(self, moment: datetime) -> bool:
        """Whether `moment`'s minute is one this expression fires on."""
        return (
            moment.minute in self.minutes and moment.hour in self.hours
            and self._day_matches(moment)
        )

    def next_after(self, moment: datetime) -> Optional[datetime]:
        """First firing minute strictly after `moment`; None if none within ~4 years."""
        start = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        day = start.replace(hour=0, minute=0)
        for offset in range(366 * 4 + 1):
            candidate_day = day + timedelta(days=offset)
            if not self._day_matches(candidate_day):
                continue
            for hour in sorted(self.hours):
                for minute in sorted(self.minutes):
                    candidate = candidate_day.replace(hour=hour, minute=minute)
                    if candidate >= start:
                        return candidate
        return None


def parse(expression: str) -> Cron:
    """A parsed cron expression; ValueError naming the bad field otherwise."""
    parts = str(expression or "").split()
    if len(parts) != 5:
        raise ValueError(
            f"A cron expression has 5 fields (minute hour day month weekday), got {expression!r}"
        )
    minutes, hours, days, months, weekdays = (
        _field(text, name, low, high) for text, (name, low, high) in zip(parts, _FIELDS)
    )
    return Cron(
        expression=" ".join(parts),
        minutes=minutes, hours=hours, days=days, months=months,
        weekdays=frozenset(day % 7 for day in weekdays),
        any_day=parts[2] == "*", any_weekday=parts[4] == "*",
    )
