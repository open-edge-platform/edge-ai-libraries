"""Tests for alert envelope model."""

from __future__ import annotations

import pytest

from src.core.models import AlertEnvelope


class TestAlertEnvelope:
    def test_from_raw_with_all_fields(self, sample_concealment_alert):
        """Creates envelope with all fields from a complete payload."""
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)

        assert envelope.alert_type == "CONCEALMENT"
        assert envelope.metadata["poi_id"] == "person-001"
        assert envelope.metadata["camera_id"] == "cam-north-01"
        assert envelope.timestamp == "2025-01-15T10:30:00Z"
        assert envelope.payload == sample_concealment_alert

    def test_from_raw_missing_alert_type(self):
        """Defaults alert_type to UNKNOWN when not provided."""
        envelope = AlertEnvelope.from_raw({"foo": "bar"})
        assert envelope.alert_type == "UNKNOWN"

    def test_from_raw_missing_metadata(self):
        """Defaults metadata to empty dict when not provided."""
        envelope = AlertEnvelope.from_raw({"alert_type": "TEST"})
        assert envelope.metadata == {}

    def test_from_raw_auto_timestamp(self):
        """Auto-generates a timestamp when none is supplied."""
        envelope = AlertEnvelope.from_raw({"alert_type": "TEST"})
        assert envelope.timestamp is not None
        assert len(envelope.timestamp) > 0

    def test_to_dict(self, sample_concealment_alert):
        """to_dict returns clean envelope without raw payload duplication."""
        envelope = AlertEnvelope.from_raw(sample_concealment_alert)
        result = envelope.to_dict()

        assert result["alert_type"] == "CONCEALMENT"
        assert result["metadata"]["poi_id"] == "person-001"
        assert result["timestamp"] == "2025-01-15T10:30:00Z"
        assert "payload" not in result
