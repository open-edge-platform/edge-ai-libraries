# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for config.loader module (config file loading)."""

import json
import os
import tempfile
from pathlib import Path
import pytest

from config.loader import load_legacy_config
from config.models import LegacyConfig


class TestLoadLegacyConfig:
    """Test load_legacy_config function."""
    
    def test_load_minimal_config(self):
        """Test loading minimal valid config file."""
        config_data = {
            "config": {
                "pipelines": []
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            assert isinstance(cfg, LegacyConfig)
            assert len(cfg.pipelines) == 0
        finally:
            os.unlink(temp_path)
    
    def test_load_config_with_single_pipeline(self):
        """Test loading config with single pipeline."""
        config_data = {
            "config": {
                "pipelines": [
                    {
                        "name": "detector",
                        "pipeline": "videotestsrc ! gvadetect name=detector ! appsink"
                    }
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            assert len(cfg.pipelines) == 1
            assert cfg.pipelines[0].name == "detector"
        finally:
            os.unlink(temp_path)
    
    def test_load_config_with_multiple_pipelines(self):
        """Test loading config with multiple pipelines."""
        config_data = {
            "config": {
                "pipelines": [
                    {"name": "p1", "pipeline": "videotestsrc ! fakesink"},
                    {"name": "p2", "pipeline": "videotestsrc ! fakesink"},
                    {"name": "p3", "pipeline": "videotestsrc ! fakesink"}
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            assert len(cfg.pipelines) == 3
            names = [p.name for p in cfg.pipelines]
            assert names == ["p1", "p2", "p3"]
        finally:
            os.unlink(temp_path)
    
    def test_load_config_with_interfaces(self):
        """Test loading config with interfaces section."""
        config_data = {
            "config": {"pipelines": []},
            "interfaces": {
                "rest": {"port": 8080},
                "other": {"key": "value"}
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            assert "rest" in cfg.interfaces
            assert "other" in cfg.interfaces
        finally:
            os.unlink(temp_path)
    
    def test_load_config_with_publishers(self):
        """Test loading config with publisher configurations."""
        config_data = {
            "config": {
                "pipelines": [
                    {
                        "name": "with_mqtt",
                        "pipeline": "videotestsrc ! fakesink",
                        "mqtt_publisher": {
                            "topic": "results",
                            "publish_frame": True,
                            "qos": 1
                        }
                    }
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            p = cfg.pipelines[0]
            assert p.mqtt_publisher is not None
            assert p.mqtt_publisher.topic == "results"
            assert p.mqtt_publisher.publish_frame is True
        finally:
            os.unlink(temp_path)
    
    def test_load_config_with_parameters(self):
        """Test loading config with parameter schema."""
        config_data = {
            "config": {
                "pipelines": [
                    {
                        "name": "param_test",
                        "pipeline": "videotestsrc ! gvadetect name=detector ! fakesink",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "model": {
                                    "element": {"name": "detector"}
                                },
                                "device": {
                                    "element": {"name": "detector"}
                                }
                            }
                        }
                    }
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            p = cfg.pipelines[0]
            assert p.parameters is not None
            assert "model" in p.parameters.properties
            assert "device" in p.parameters.properties
        finally:
            os.unlink(temp_path)
    
    def test_load_file_not_found(self):
        """Test that FileNotFoundError raised when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_legacy_config("/nonexistent/path/config.json")
    
    def test_load_invalid_json(self):
        """Test that ValueError raised for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json")
            temp_path = f.name
        
        try:
            with pytest.raises(Exception):  # json.JSONDecodeError or ValueError
                load_legacy_config(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_load_invalid_schema(self):
        """Test that ValueError raised for invalid schema."""
        # Missing required "config" key
        config_data = {"interfaces": {}}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            with pytest.raises(Exception):  # Pydantic ValidationError
                load_legacy_config(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_load_with_path_object(self):
        """Test loading with Path object instead of string."""
        config_data = {
            "config": {"pipelines": []}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = Path(f.name)
        
        try:
            cfg = load_legacy_config(temp_path)
            assert isinstance(cfg, LegacyConfig)
        finally:
            temp_path.unlink()
    
    def test_load_with_utf8_content(self):
        """Test loading config with UTF-8 content."""
        config_data = {
            "config": {
                "pipelines": [
                    {
                        "name": "unicode_test",
                        "pipeline": "videotestsrc ! fakesink",
                        "custom_field": "Test with émojis 🎬"
                    }
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            assert len(cfg.pipelines) == 1
        finally:
            os.unlink(temp_path)
    
    def test_load_complex_realistic_config(self):
        """Test loading complex realistic config file."""
        config_data = {
            "config": {
                "pipelines": [
                    {
                        "name": "inference_pipeline",
                        "source": "gstreamer",
                        "queue_maxsize": 100,
                        "pipeline": (
                            "urisourcebin uri={auto_source} ! "
                            "queue ! decodebin ! videoconvert ! "
                            "gvadetect name=detector model-properties::model=/models/detector.xml ! "
                            "gvadetect name=classifier ! "
                            "appsink name=appsink"
                        ),
                        "auto_start": False,
                        "mqtt_publisher": {
                            "topic": "inference/results",
                            "publish_frame": True
                        },
                        "s3_write": {
                            "bucket": "video-frames",
                            "folder_prefix": "detections"
                        },
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "detector_model": {
                                    "element": {"name": "detector"}
                                },
                                "classifier_model": {
                                    "element": {"name": "classifier"}
                                }
                            }
                        }
                    }
                ]
            },
            "interfaces": {
                "rest": {
                    "port": 8080,
                    "host": "0.0.0.0"
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            assert len(cfg.pipelines) == 1
            p = cfg.pipelines[0]
            assert p.name == "inference_pipeline"
            assert p.queue_maxsize == 100
            assert p.mqtt_publisher is not None
            assert p.s3_write is not None
            assert p.parameters is not None
            assert "rest" in cfg.interfaces
        finally:
            os.unlink(temp_path)
    
    def test_load_returns_validated_config(self):
        """Test that returned config is a validated LegacyConfig instance."""
        config_data = {
            "config": {
                "pipelines": [
                    {"name": "test", "pipeline": "videotestsrc ! fakesink"}
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            cfg = load_legacy_config(temp_path)
            # Verify it's actually a LegacyConfig instance with validated models
            assert isinstance(cfg, LegacyConfig)
            assert isinstance(cfg.config.pipelines[0], type(cfg.pipelines[0]))
        finally:
            os.unlink(temp_path)
