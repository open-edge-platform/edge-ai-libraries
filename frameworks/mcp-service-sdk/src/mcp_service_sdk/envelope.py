"""Event envelope — the single shape every service emits.

Contract (walkthrough §3, Step 1): type name, timestamp, service/store identity,
payload, and a reference id for correlation and idempotent replay.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class EventEnvelope:
    """A single durable, replayable event.

    ``ref_id`` makes replay idempotent: re-emitting the same ref_id is a no-op
    at the log layer.
    """

    event_type: str
    service: str
    store_id: str
    payload: dict[str, Any]
    ref_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Wall-clock time in epoch milliseconds; ordering is by log sequence, not this.
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    schema_version: int = 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "EventEnvelope":
        data = json.loads(raw)
        return cls(**data)


def new_event(
    event_type: str,
    service: str,
    store_id: str,
    payload: dict[str, Any],
    ref_id: str | None = None,
) -> EventEnvelope:
    """Convenience factory so services never build the envelope by hand."""
    kwargs: dict[str, Any] = {
        "event_type": event_type,
        "service": service,
        "store_id": store_id,
        "payload": payload,
    }
    if ref_id is not None:
        kwargs["ref_id"] = ref_id
    return EventEnvelope(**kwargs)
