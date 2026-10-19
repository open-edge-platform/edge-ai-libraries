# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the external-media correlation contract.

These guard the fields that let a separately-stored recording be matched back to
an embedding produced here. They are deliberately independent of *which* service
owns the media, so that integrating an external stream manager later does not
require touching the decode or embedding path.
"""

import dataclasses

from src.core.embedding.embedding_helper import FrameMetadata
from src.core.live.models import LiveStream


def _make_stream(**overrides) -> LiveStream:
    params = {
        "stream_url": "******cam.local:554/s1",
        "stream_name": "cam-1",
        "frame_interval": 15,
        "enable_object_detection": False,
        "detection_confidence": 0.85,
    }
    params.update(overrides)
    return LiveStream.new(**params)


class TestSensorIdentity:
    """sensor_id is the portable key an external recorder files media under."""

    def test_defaults_to_stream_id(self):
        stream = _make_stream()

        assert stream.sensor_id == stream.stream_id
        assert stream.effective_sensor_id == stream.stream_id

    def test_caller_supplied_value_is_kept(self):
        stream = _make_stream(sensor_id="cam-07")

        assert stream.effective_sensor_id == "cam-07"
        # The registration handle stays distinct from the source identity.
        assert stream.stream_id != "cam-07"

    def test_survives_a_persistence_round_trip(self):
        stream = _make_stream(sensor_id="cam-07")

        restored = LiveStream.from_row(stream.to_row())

        assert restored.effective_sensor_id == "cam-07"

    def test_registration_persisted_before_the_field_existed_still_loads(self):
        row = _make_stream().to_row()
        del row["sensor_id"]

        restored = LiveStream.from_row(row)

        # Falls back to the stream_id rather than leaving the key unset, so
        # correlation never has to handle a missing value.
        assert restored.effective_sensor_id == restored.stream_id

    def test_exposed_on_the_api_model(self):
        info = _make_stream(sensor_id="cam-07").to_info()

        assert info.sensor_id == "cam-07"

    def test_api_model_never_leaks_credentials(self):
        info = _make_stream(sensor_id="cam-07").to_info()

        assert "secret" not in info.stream_url


class TestFrameCorrelationFields:
    """The per-embedding fields an external lookup is keyed on."""

    def test_contract_fields_exist(self):
        names = {f.name for f in dataclasses.fields(FrameMetadata)}

        assert {"sensor_id", "capture_time", "capture_time_source", "media_owner"} <= names

    def test_absent_for_file_based_ingestion(self):
        meta = FrameMetadata()

        assert meta.sensor_id is None
        assert meta.capture_time is None
        assert meta.media_owner is None
        assert meta.is_live is False

    def test_capture_time_is_distinct_from_ingest_time(self):
        """Capture and ingest are separate fields even when currently equal.

        They are populated from the same clock today, but a consumer must key
        external lookups on capture_time so that sourcing a real capture clock
        later is a value change rather than a schema change.
        """
        names = {f.name for f in dataclasses.fields(FrameMetadata)}

        assert "capture_time" in names and "wall_clock_time" in names

    def test_estimated_capture_time_is_labelled(self):
        meta = FrameMetadata(
            is_live=True,
            capture_time="2026-09-16T09:12:03.400000+00:00",
            capture_time_source="ingest_estimated",
        )

        # Consumers must be able to tell an estimate from a real capture clock,
        # because an estimate carries pipeline latency and needs a tolerance
        # window when matched against externally recorded media.
        assert meta.capture_time_source == "ingest_estimated"

    def test_media_owner_identifies_who_holds_the_clip(self):
        meta = FrameMetadata(is_live=True, media_owner="self")

        assert meta.media_owner == "self"

    def test_fields_survive_serialization(self):
        meta = FrameMetadata(
            is_live=True,
            sensor_id="cam-07",
            capture_time="2026-09-16T09:12:03.400000+00:00",
            capture_time_source="ingest_estimated",
            media_owner="self",
        ).to_dict()

        assert meta["sensor_id"] == "cam-07"
        assert meta["capture_time"] == "2026-09-16T09:12:03.400000+00:00"
        assert meta["capture_time_source"] == "ingest_estimated"
        assert meta["media_owner"] == "self"


class TestWorkerPropagatesSensorId:
    """The pipeline must receive the source identity, not just our handle."""

    def test_metadata_dict_carries_sensor_id(self):
        from src.core.live.worker import LiveStreamWorker

        stream = _make_stream(sensor_id="cam-07")
        worker = LiveStreamWorker.__new__(LiveStreamWorker)
        worker.stream = stream

        live = worker._metadata_dict()["live"]

        assert live["sensor_id"] == "cam-07"
        assert live["stream_id"] == stream.stream_id
        assert "secret" not in live["stream_url"]
