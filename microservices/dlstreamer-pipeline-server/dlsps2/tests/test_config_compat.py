# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for config.compat module (destination fan-out logic)."""

import pytest
import sys
from unittest.mock import patch, MagicMock
from typing import Optional

# Mock gi/GStreamer so the module can be imported without a real GStreamer install
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gst'] = MagicMock()

from api.schema import (
    SourceConfig, DestinationConfig, MetadataDestinationConfig,
    FrameDestinationConfig, StartNamedPipelineRequest
)
from config.compat import (
    apply_destination, apply_source, _rtsp_chain, _webrtc_chain,
    _replace_appsink_with_chains, _as_list
)


class TestSourceConfig:
    """Test source configuration schema."""
    
    def test_source_config_with_uri(self):
        """Test creating a SourceConfig with URI type."""
        cfg = SourceConfig(uri="file:///home/test.mp4", type="uri")
        assert cfg.uri == "file:///home/test.mp4"
        assert cfg.type == "uri"
    
    def test_source_config_empty(self):
        """Test creating an empty SourceConfig (all optional)."""
        cfg = SourceConfig()
        assert cfg.uri is None
        assert cfg.type is None
    
    def test_source_config_extra_fields(self):
        """Test SourceConfig accepts extra fields via model_config."""
        cfg = SourceConfig(uri="rtsp://example.com", custom_field="value")
        assert cfg.uri == "rtsp://example.com"


class TestDestinationConfig:
    """Test destination configuration schema."""
    
    def test_metadata_destination_mqtt(self):
        """Test MQTT metadata destination."""
        meta = MetadataDestinationConfig(
            type="mqtt", topic="test_topic", publish_frame=True
        )
        assert meta.type == "mqtt"
        assert meta.topic == "test_topic"
        assert meta.publish_frame is True
    
    def test_frame_destination_webrtc_single(self):
        """Test single WebRTC frame destination."""
        frame = FrameDestinationConfig(
            type="webrtc", peer_id="peer1", bitrate=2048
        )
        assert frame.type == "webrtc"
        assert frame.peer_id == "peer1"
        assert frame.bitrate == 2048
        assert frame.overlay is True  # default
    
    def test_frame_destination_s3(self):
        """Test S3 frame destination."""
        frame = FrameDestinationConfig(type="s3_write", path="mybucket")
        assert frame.type == "s3_write"
        assert frame.path == "mybucket"
    
    def test_frame_destination_list(self):
        """Test DestinationConfig with frame as a list."""
        frame_list = [
            FrameDestinationConfig(type="webrtc", peer_id="p1"),
            FrameDestinationConfig(type="s3_write", path="bucket1")
        ]
        dest = DestinationConfig(frame=frame_list)
        assert isinstance(dest.frame, list)
        assert len(dest.frame) == 2
        assert dest.frame[0].type == "webrtc"
        assert dest.frame[1].type == "s3_write"
    
    def test_frame_destination_single_object(self):
        """Test DestinationConfig with frame as a single object."""
        frame = FrameDestinationConfig(type="rtsp", path="stream")
        dest = DestinationConfig(frame=frame)
        assert dest.frame == frame
        assert dest.frame.type == "rtsp"
    
    def test_destination_mqtt_plus_multiple_frames(self):
        """Test combined MQTT metadata + list of frame destinations."""
        meta = MetadataDestinationConfig(type="mqtt", topic="results")
        frames = [
            FrameDestinationConfig(type="webrtc", peer_id="demo"),
            FrameDestinationConfig(type="s3_write", path="ecgdemo")
        ]
        dest = DestinationConfig(metadata=meta, frame=frames)
        assert dest.metadata.type == "mqtt"
        assert len(dest.frame) == 2


class TestChainBuilders:
    """Test individual chain-building functions."""
    
    def test_rtsp_chain(self):
        """Test RTSP chain construction."""
        chain = _rtsp_chain("mystream")
        assert "videoconvert" in chain
        assert "openh264enc" in chain
        assert "rtspclientsink" in chain
        assert "mystream" in chain
    
    def test_webrtc_chain_with_overlay(self):
        """Test WebRTC chain with overlay enabled."""
        chain = _webrtc_chain("peer1", overlay=True, bitrate=1024)
        assert "videoconvert" in chain
        assert "gvawatermark" in chain  # overlay enabled
        assert "openh264enc" in chain
        assert "whipclientsink" in chain
        assert "peer1" in chain
        assert "bitrate=1024" not in chain  # bitrate not in webrtc chain builder
    
    def test_webrtc_chain_without_overlay(self):
        """Test WebRTC chain with overlay disabled."""
        chain = _webrtc_chain("peer2", overlay=False)
        assert "videoconvert" in chain
        assert "gvawatermark" not in chain
        assert "whipclientsink" in chain


class TestReplaceAppSinkWithChains:
    """Test _replace_appsink_with_chains function."""
    
    def test_no_chains(self):
        """Test with no chains (no-op)."""
        pipeline = "videotestsrc ! appsink name=appsink"
        result = _replace_appsink_with_chains(pipeline, [])
        assert result == pipeline
    
    def test_single_chain_in_place(self):
        """Test single chain replaces appsink in-place, no tee."""
        pipeline = "videotestsrc ! appsink name=appsink"
        chain = "fakesink"
        result = _replace_appsink_with_chains(pipeline, [chain])
        assert "fakesink" in result
        assert "tee" not in result
        assert "appsink" not in result
    
    def test_single_chain_preserves_properties(self):
        """Test that appsink properties are replaced correctly."""
        pipeline = "videotestsrc ! appsink name=appsink sync=false"
        chain = "fakesink"
        result = _replace_appsink_with_chains(pipeline, [chain])
        assert "fakesink" in result
        assert "appsink" not in result
        assert "sync=" not in result
    
    def test_two_chains_creates_tee(self):
        """Test two chains create a tee fan-out."""
        pipeline = "videotestsrc ! appsink name=appsink"
        chains = ["fakesink1", "fakesink2"]
        result = _replace_appsink_with_chains(pipeline, chains)
        assert "tee name=dest_tee" in result
        assert "queue" in result
        assert "fakesink1" in result
        assert "fakesink2" in result
        assert "appsink" not in result
    
    def test_three_chains_tee_structure(self):
        """Test three chains create proper tee structure."""
        pipeline = "videotestsrc ! appsink name=appsink"
        chains = ["sink1", "sink2", "sink3"]
        result = _replace_appsink_with_chains(pipeline, chains)
        assert "tee name=dest_tee ! queue ! sink1" in result
        assert "dest_tee. ! queue ! sink2" in result
        assert "dest_tee. ! queue ! sink3" in result
    
    def test_no_appsink_found(self):
        """Test when appsink is not found in pipeline."""
        pipeline = "videotestsrc ! fakesink"
        chains = ["mqtt_sink"]
        result = _replace_appsink_with_chains(pipeline, chains)
        assert result == pipeline  # unchanged
    
    def test_complex_pipeline_with_properties(self):
        """Test complex pipeline with multiple elements before appsink."""
        pipeline = (
            "urisourcebin uri=rtsp://example.com ! "
            "decodebin ! videoconvert ! "
            "gvametaconvert name=meta ! "
            "queue ! appsink name=destination"
        )
        chains = ["mqtt_sink", "s3_sink"]
        result = _replace_appsink_with_chains(pipeline, chains)
        assert "tee name=dest_tee" in result
        assert "mqtt_sink" in result
        assert "s3_sink" in result


class TestApplyDestination:
    """Test apply_destination function."""
    
    def test_no_destination(self):
        """Test with None destination (no-op)."""
        pipeline = "videotestsrc ! appsink name=appsink"
        result = apply_destination(pipeline, None)
        assert result == pipeline
    
    def test_metadata_mqtt_only(self):
        """Test MQTT metadata destination only (no frame dest)."""
        pipeline = "videotestsrc ! appsink name=appsink"
        meta = MetadataDestinationConfig(type="mqtt", topic="results")
        dest = DestinationConfig(metadata=meta)
        result = apply_destination(pipeline, dest)
        assert "mqttsinkpy" in result
        assert "topic=results" in result
        assert "tee" not in result  # single destination, no tee
    
    def test_frame_webrtc_only(self):
        """Test WebRTC frame destination only."""
        pipeline = "videotestsrc ! appsink name=appsink"
        frame = FrameDestinationConfig(type="webrtc", peer_id="demo")
        dest = DestinationConfig(frame=frame)
        result = apply_destination(pipeline, dest)
        assert "whipclientsink" in result
        assert "demo" in result
        assert "tee" not in result
    
    def test_mqtt_metadata_plus_webrtc_frame_tee(self):
        """Test MQTT metadata + WebRTC frame creates tee fan-out."""
        pipeline = "videotestsrc ! appsink name=appsink"
        meta = MetadataDestinationConfig(type="mqtt", topic="t1")
        frame = FrameDestinationConfig(type="webrtc", peer_id="p1")
        dest = DestinationConfig(metadata=meta, frame=frame)
        result = apply_destination(pipeline, dest)
        assert "tee name=dest_tee" in result
        assert "mqttsinkpy" in result
        assert "whipclientsink" in result
    
    def test_frame_list_webrtc_and_s3_tee(self):
        """Test list of frame destinations (webrtc + s3) creates tee."""
        pipeline = "videotestsrc ! appsink name=appsink"
        frames = [
            FrameDestinationConfig(type="webrtc", peer_id="p1"),
            FrameDestinationConfig(type="s3_write", path="bucket1")
        ]
        dest = DestinationConfig(frame=frames)
        result = apply_destination(pipeline, dest)
        assert "tee name=dest_tee" in result
        assert "whipclientsink" in result
        assert "s3sinkpy bucket=bucket1" in result
    
    def test_three_way_mqtt_webrtc_s3_tee(self):
        """Test MQTT + WebRTC + S3 creates 3-way tee."""
        pipeline = "videotestsrc ! appsink name=appsink"
        meta = MetadataDestinationConfig(type="mqtt", topic="results")
        frames = [
            FrameDestinationConfig(type="webrtc", peer_id="stream1"),
            FrameDestinationConfig(type="s3_write", path="mybucket")
        ]
        dest = DestinationConfig(metadata=meta, frame=frames)
        result = apply_destination(pipeline, dest)
        assert "tee name=dest_tee" in result
        assert result.count("queue") >= 3  # at least 3 queues for 3-way tee
        assert "mqttsinkpy" in result
        assert "whipclientsink" in result
        assert "s3sinkpy" in result
    
    def test_rtsp_destination(self):
        """Test RTSP frame destination."""
        pipeline = "videotestsrc ! appsink name=appsink"
        frame = FrameDestinationConfig(type="rtsp", path="stream")
        dest = DestinationConfig(frame=frame)
        result = apply_destination(pipeline, dest)
        assert "rtspclientsink" in result
        assert "stream" in result
    
    def test_opcua_metadata_destination(self):
        """Test OPC-UA metadata destination."""
        pipeline = "videotestsrc ! appsink name=appsink"
        meta = MetadataDestinationConfig(type="opcua", path="ns=2;s=Var1")
        dest = DestinationConfig(metadata=meta)
        result = apply_destination(pipeline, dest)
        assert "opcuasinkpy" in result
        assert "ns=2;s=Var1" in result
    
    def test_influx_metadata_destination(self):
        """Test InfluxDB metadata destination."""
        pipeline = "videotestsrc ! appsink name=appsink"
        meta = MetadataDestinationConfig(
            type="influx_write", path="mybucket", format="dlstreamer"
        )
        dest = DestinationConfig(metadata=meta)
        result = apply_destination(pipeline, dest)
        assert "influxsinkpy" in result
        assert "bucket=mybucket" in result
        assert "measurement=dlstreamer" in result


class TestApplySource:
    """Test apply_source function."""
    
    def test_no_source_with_auto_source_raises(self):
        """Test that {auto_source} without source raises ValueError."""
        pipeline = "{auto_source} ! appsink"
        with pytest.raises(ValueError, match="contains {auto_source}"):
            apply_source(pipeline, None)
    
    def test_file_uri_source(self):
        """Test file URI source replacement."""
        pipeline = "{auto_source} ! appsink"
        source = SourceConfig(uri="file:///home/test.mp4", type="uri")
        result = apply_source(pipeline, source)
        assert "file:///home/test.mp4" in result
        assert "urisourcebin" in result
        assert "{auto_source}" not in result
    
    def test_rtsp_uri_source(self):
        """Test RTSP URI source replacement."""
        pipeline = "{auto_source} ! appsink"
        source = SourceConfig(uri="rtsp://example.com/stream", type="uri")
        result = apply_source(pipeline, source)
        assert "rtsp://example.com/stream" in result
        assert "urisourcebin" in result
    
    def test_no_auto_source_placeholder(self):
        """Test when {auto_source} is not in pipeline."""
        pipeline = "videotestsrc ! appsink"
        source = SourceConfig(uri="file:///test.mp4", type="uri")
        result = apply_source(pipeline, source)
        assert result == pipeline  # unchanged


class TestAsListHelper:
    """Test the _as_list helper function."""
    
    def test_none_returns_empty_list(self):
        """Test None returns empty list."""
        assert _as_list(None) == []
    
    def test_single_item_returns_list(self):
        """Test single item returns list with one element."""
        assert _as_list("item") == ["item"]
    
    def test_list_returns_unchanged(self):
        """Test list returns unchanged."""
        items = ["a", "b", "c"]
        assert _as_list(items) == items


class TestStartNamedPipelineRequest:
    """Test StartNamedPipelineRequest schema."""
    
    def test_minimal_request(self):
        """Test minimal request with just source."""
        req = StartNamedPipelineRequest(
            source=SourceConfig(uri="file:///test.mp4")
        )
        assert req.source.uri == "file:///test.mp4"
        assert req.destination is None
        assert req.parameters is None
    
    def test_full_request_with_destinations(self):
        """Test full request with source, destination, and parameters."""
        req = StartNamedPipelineRequest(
            source=SourceConfig(uri="rtsp://example.com"),
            destination=DestinationConfig(
                metadata=MetadataDestinationConfig(type="mqtt", topic="t1"),
                frame=[
                    FrameDestinationConfig(type="webrtc", peer_id="p1"),
                    FrameDestinationConfig(type="s3_write", path="bucket")
                ]
            ),
            parameters={"model": "/path/to/model.xml", "device": "CPU"},
            tags={"app": "vision", "version": "2.0"}
        )
        assert req.source.uri == "rtsp://example.com"
        assert req.destination.metadata.type == "mqtt"
        assert len(req.destination.frame) == 2
        assert req.parameters["device"] == "CPU"
        assert req.tags["app"] == "vision"
