# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for config.models module (Pydantic models)."""

import pytest
from typing import Any

from config.models import (
    MqttPublisherConfig, OpcuaPublisherConfig, InfluxWriteConfig, S3WriteConfig,
    PipelineParameterElement, PipelineParameterProperty, PipelineParameters,
    PipelineConfig, AppConfig, LegacyConfig
)


class TestPublisherConfigs:
    """Test publisher configuration models."""
    
    def test_mqtt_publisher_defaults(self):
        """Test MQTT publisher with defaults."""
        cfg = MqttPublisherConfig(topic="test")
        assert cfg.topic == "test"
        assert cfg.publish_frame is False
        assert cfg.qos == 0
    
    def test_mqtt_publisher_all_fields(self):
        """Test MQTT publisher with all fields set."""
        cfg = MqttPublisherConfig(topic="custom", publish_frame=True, qos=1)
        assert cfg.topic == "custom"
        assert cfg.publish_frame is True
        assert cfg.qos == 1
    
    def test_mqtt_publisher_extra_fields(self):
        """Test MQTT publisher accepts extra fields."""
        cfg = MqttPublisherConfig(topic="test", custom_field="value")
        assert cfg.topic == "test"
    
    def test_opcua_publisher_config(self):
        """Test OPC-UA publisher configuration."""
        cfg = OpcuaPublisherConfig(variable="ns=2;s=Var1", publish_frame=True)
        assert cfg.variable == "ns=2;s=Var1"
        assert cfg.publish_frame is True
    
    def test_influx_write_config(self):
        """Test InfluxDB write configuration."""
        cfg = InfluxWriteConfig(bucket="my_bucket", org="my_org", measurement="custom")
        assert cfg.bucket == "my_bucket"
        assert cfg.org == "my_org"
        assert cfg.measurement == "custom"
    
    def test_influx_write_defaults(self):
        """Test InfluxDB write with default measurement."""
        cfg = InfluxWriteConfig(bucket="data", org="main")
        assert cfg.measurement == "dlsps"
    
    def test_s3_write_config(self):
        """Test S3 write configuration."""
        cfg = S3WriteConfig(bucket="mybucket", folder_prefix="results", block=True)
        assert cfg.bucket == "mybucket"
        assert cfg.folder_prefix == "results"
        assert cfg.block is True
    
    def test_s3_write_defaults(self):
        """Test S3 write with defaults."""
        cfg = S3WriteConfig(bucket="data", folder_prefix="output")
        assert cfg.block is False


class TestPipelineParameters:
    """Test pipeline parameter schema."""
    
    def test_parameter_element_defaults(self):
        """Test PipelineParameterElement default format."""
        elem = PipelineParameterElement(name="my_element")
        assert elem.name == "my_element"
        assert elem.format == "element-properties"
    
    def test_parameter_element_custom_format(self):
        """Test PipelineParameterElement with custom format."""
        elem = PipelineParameterElement(name="elem", format="custom")
        assert elem.format == "custom"

    def test_parameter_element_property_remap_defaults_to_none(self):
        """DLSPS 1.0 compat: property remap defaults to None (falls back to param name)."""
        elem = PipelineParameterElement(name="destination")
        assert elem.property is None

    def test_parameter_element_property_remap(self):
        """DLSPS 1.0 compat: the property remap field can differ from the element name."""
        elem = PipelineParameterElement(name="destination", property="file-path")
        assert elem.name == "destination"
        assert elem.property == "file-path"

    def test_parameter_property_with_element(self):
        """Test PipelineParameterProperty wrapping a single element."""
        elem = PipelineParameterElement(name="target")
        prop = PipelineParameterProperty(element=elem)
        assert prop.element.name == "target"
    
    def test_parameter_property_none(self):
        """Test PipelineParameterProperty with no element."""
        prop = PipelineParameterProperty()
        assert prop.element is None

    def test_parameter_property_element_as_list(self):
        """DLSPS 1.0 compat: element may be a list, fanning out to multiple elements."""
        prop = PipelineParameterProperty(
            element=[
                PipelineParameterElement(name="source", property="device"),
                PipelineParameterElement(name="metaconvert", property="source"),
            ]
        )
        assert isinstance(prop.element, list)
        assert len(prop.element) == 2
        assert prop.element[0].name == "source"
        assert prop.element[1].property == "source"
    
    def test_pipeline_parameters_empty(self):
        """Test empty PipelineParameters."""
        params = PipelineParameters()
        assert params.type == "object"
        assert params.properties == {}
    
    def test_pipeline_parameters_with_properties(self):
        """Test PipelineParameters with properties."""
        elem = PipelineParameterElement(name="detector")
        prop = PipelineParameterProperty(element=elem)
        params = PipelineParameters(properties={
            "model": prop,
            "device": PipelineParameterProperty(element=PipelineParameterElement(name="detector"))
        })
        assert len(params.properties) == 2
        assert "model" in params.properties


class TestPipelineConfig:
    """Test individual pipeline configuration."""
    
    def test_minimal_pipeline_config(self):
        """Test minimal PipelineConfig."""
        cfg = PipelineConfig(name="test_pipeline", pipeline="videotestsrc ! fakesink")
        assert cfg.name == "test_pipeline"
        assert cfg.pipeline == "videotestsrc ! fakesink"
        assert cfg.source == "gstreamer"
        assert cfg.queue_maxsize == 50
        assert cfg.auto_start is False
    
    def test_pipeline_config_with_publishers(self):
        """Test PipelineConfig with multiple publishers."""
        cfg = PipelineConfig(
            name="multi_pub",
            pipeline="videotestsrc ! fakesink",
            mqtt_publisher=MqttPublisherConfig(topic="results"),
            s3_write=S3WriteConfig(bucket="data", folder_prefix="frames")
        )
        assert cfg.mqtt_publisher is not None
        assert cfg.s3_write is not None
        assert cfg.opcua_publisher is None
    
    def test_pipeline_config_publishers_property(self):
        """Test PipelineConfig.publishers property."""
        cfg = PipelineConfig(
            name="test",
            pipeline="videotestsrc ! fakesink",
            mqtt_publisher=MqttPublisherConfig(topic="t1"),
            influx_write=InfluxWriteConfig(bucket="b1", org="o1")
        )
        pubs = cfg.publishers
        assert "mqtt" in pubs
        assert "influx" in pubs
        assert "opcua" not in pubs
        assert len(pubs) == 2
    
    def test_pipeline_config_empty_publishers(self):
        """Test PipelineConfig with no publishers."""
        cfg = PipelineConfig(name="no_pub", pipeline="videotestsrc ! fakesink")
        assert cfg.publishers == {}
    
    def test_pipeline_config_with_parameters(self):
        """Test PipelineConfig with parameter schema."""
        params = PipelineParameters(
            properties={
                "model": PipelineParameterProperty(
                    element=PipelineParameterElement(name="detector")
                )
            }
        )
        cfg = PipelineConfig(
            name="param_test",
            pipeline="videotestsrc ! gvadetect name=detector ! fakesink",
            parameters=params
        )
        assert cfg.parameters is not None
        assert "model" in cfg.parameters.properties
    
    def test_pipeline_config_custom_source(self):
        """Test PipelineConfig with custom source type."""
        cfg = PipelineConfig(
            name="image_ingestor_test",
            pipeline="appsrc ! fakesink",
            source="image_ingestor"
        )
        assert cfg.source == "image_ingestor"
    
    def test_pipeline_config_auto_start(self):
        """Test PipelineConfig with auto_start enabled."""
        cfg = PipelineConfig(
            name="autostart",
            pipeline="videotestsrc ! fakesink",
            auto_start=True
        )
        assert cfg.auto_start is True


class TestAppConfig:
    """Test application-level configuration."""
    
    def test_app_config_empty(self):
        """Test empty AppConfig."""
        cfg = AppConfig()
        assert cfg.pipelines == []
        assert cfg.mqtt_publisher is None
    
    def test_app_config_with_pipelines(self):
        """Test AppConfig with multiple pipelines."""
        pipelines = [
            PipelineConfig(name="p1", pipeline="videotestsrc ! fakesink"),
            PipelineConfig(name="p2", pipeline="videotestsrc ! fakesink")
        ]
        cfg = AppConfig(pipelines=pipelines)
        assert len(cfg.pipelines) == 2
    
    def test_app_config_with_mqtt_publishers(self):
        """Test AppConfig with global MQTT publishers."""
        mqtt_pubs = [
            MqttPublisherConfig(topic="global1"),
            MqttPublisherConfig(topic="global2")
        ]
        cfg = AppConfig(mqtt_publisher=mqtt_pubs)
        assert len(cfg.mqtt_publisher) == 2


class TestLegacyConfig:
    """Test root configuration model."""
    
    def test_legacy_config_minimal(self):
        """Test minimal LegacyConfig."""
        cfg = LegacyConfig(
            config=AppConfig(
                pipelines=[
                    PipelineConfig(name="p1", pipeline="videotestsrc ! fakesink")
                ]
            )
        )
        assert len(cfg.pipelines) == 1
        assert cfg.pipelines[0].name == "p1"
    
    def test_legacy_config_with_interfaces(self):
        """Test LegacyConfig with interfaces."""
        cfg = LegacyConfig(
            config=AppConfig(),
            interfaces={"interface1": {"key": "value"}}
        )
        assert "interface1" in cfg.interfaces
    
    def test_legacy_config_pipelines_property(self):
        """Test LegacyConfig.pipelines property delegates to config."""
        pipelines = [
            PipelineConfig(name="p1", pipeline="videotestsrc ! fakesink"),
            PipelineConfig(name="p2", pipeline="videotestsrc ! fakesink")
        ]
        cfg = LegacyConfig(config=AppConfig(pipelines=pipelines))
        assert cfg.pipelines == pipelines
        assert len(cfg.pipelines) == 2
    
    def test_legacy_config_get_pipeline_found(self):
        """Test get_pipeline when pipeline exists."""
        pipelines = [
            PipelineConfig(name="detector", pipeline="videotestsrc ! fakesink"),
            PipelineConfig(name="classifier", pipeline="videotestsrc ! fakesink")
        ]
        cfg = LegacyConfig(config=AppConfig(pipelines=pipelines))
        found = cfg.get_pipeline("detector")
        assert found is not None
        assert found.name == "detector"
    
    def test_legacy_config_get_pipeline_not_found(self):
        """Test get_pipeline when pipeline doesn't exist."""
        cfg = LegacyConfig(config=AppConfig())
        found = cfg.get_pipeline("nonexistent")
        assert found is None
    
    def test_legacy_config_from_dict(self):
        """Test LegacyConfig construction from dictionary."""
        data = {
            "config": {
                "pipelines": [
                    {"name": "test", "pipeline": "videotestsrc ! fakesink"}
                ]
            },
            "interfaces": {}
        }
        cfg = LegacyConfig.model_validate(data)
        assert len(cfg.pipelines) == 1
        assert cfg.pipelines[0].name == "test"
    
    def test_legacy_config_full_example(self):
        """Test LegacyConfig with complex realistic structure."""
        data = {
            "config": {
                "pipelines": [
                    {
                        "name": "inference_pipeline",
                        "pipeline": "urisourcebin uri={auto_source} ! queue ! gvadetect name=detector ! appsink name=appsink",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "model": {
                                    "element": {"name": "detector", "format": "element-properties"}
                                },
                                "device": {
                                    "element": {"name": "detector", "format": "element-properties"}
                                }
                            }
                        },
                        "mqtt_publisher": {
                            "topic": "results",
                            "publish_frame": False
                        },
                        "s3_write": {
                            "bucket": "frames",
                            "folder_prefix": "output"
                        }
                    }
                ]
            },
            "interfaces": {
                "rest": {"port": 8080}
            }
        }
        cfg = LegacyConfig.model_validate(data)
        assert len(cfg.pipelines) == 1
        p = cfg.pipelines[0]
        assert p.name == "inference_pipeline"
        assert p.mqtt_publisher is not None
        assert p.s3_write is not None
        assert "model" in p.parameters.properties
        assert len(cfg.interfaces) == 1
