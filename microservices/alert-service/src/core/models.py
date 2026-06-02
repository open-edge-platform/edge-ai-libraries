"""Internal alert envelope model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class AlertEnvelope:
    """Normalized internal representation of an incoming alert."""

    __slots__ = ("alert_type", "metadata", "timestamp", "payload")

    def __init__(
        self,
        alert_type: str,
        metadata: dict[str, Any],
        timestamp: str,
        payload: dict[str, Any],
    ) -> None:
        self.alert_type = alert_type
        self.metadata = metadata
        self.timestamp = timestamp
        self.payload = payload

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> AlertEnvelope:
        """Create an envelope from a raw incoming alert payload."""
        return cls(
            alert_type=raw.get("alert_type", "UNKNOWN"),
            metadata=raw.get("metadata", {}),
            timestamp=raw.get(
                "timestamp",
                datetime.now(timezone.utc).isoformat(),
            ),
            payload=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a clean dict for delivery (excludes raw payload to avoid duplication)."""
        return {
            "alert_type": self.alert_type,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
