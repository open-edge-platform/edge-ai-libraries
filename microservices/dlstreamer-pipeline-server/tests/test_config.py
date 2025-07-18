#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import json
import os
from src import config

class TestPublisherConfig:
    
    def test_mqtt(self):
        pub_cfg = {
            "mqtt_publisher": {
                "host": "localhost",
                "port": 1883,
                "topic": "test",
                "publish_frame": False,
                "endpoint": "mqtt_endpoint"
            }
        }
        pub_obj = config.PublisherConfig(pub_cfg["mqtt_publisher"])
        assert pub_obj.get_pub_cfg() == pub_cfg["mqtt_publisher"]
        assert pub_obj.get_topics() == "test"
        assert pub_obj.get_endpoint() == "mqtt_endpoint"

    def test_mqtt_with_Topics(self):
        pub_cfg = {
            "mqtt_publisher": {
                "host": "localhost",
                "port": 1883,
                "Topics": "test",
                "publish_frame": False,
                "endpoint": "mqtt_endpoint"
            }
        }
        pub_obj = config.PublisherConfig(pub_cfg["mqtt_publisher"])
        assert pub_obj.get_pub_cfg() == pub_cfg["mqtt_publisher"]
        assert pub_obj.get_topics() == "test"
        assert pub_obj.get_endpoint() == "mqtt_endpoint"

    def test_mqtt_with_EndPoint(self):
        pub_cfg = {
            "mqtt_publisher": {
                "host": "localhost",
                "port": 1883,
                "topic": "test",
                "publish_frame": False,
                "EndPoint": "mqtt_EndPoint"
            }
        }
        pub_obj = config.PublisherConfig(pub_cfg["mqtt_publisher"])
        assert pub_obj.get_pub_cfg() == pub_cfg["mqtt_publisher"]
        assert pub_obj.get_topics() == "test"
        assert pub_obj.get_endpoint() == "mqtt_EndPoint"

    def test_missing_topic_key(self):
        pub_cfg = {
            "mqtt_publisher": {
                "host": "localhost",
                "port": 1883,
                "publish_frame": False,
                "endpoint": "mqtt_endpoint"
            }
        }
        pub_obj = config.PublisherConfig(pub_cfg["mqtt_publisher"])
        with pytest.raises(KeyError, match="topic/Topics key not found in publisher config"):
            pub_obj.get_topics()

    def test_missing_endpoint_key(self):
        pub_cfg = {
            "mqtt_publisher": {
                "host": "localhost",
                "port": 1883,
                "topic": "test",
                "publish_frame": False
            }
        }
        pub_obj = config.PublisherConfig(pub_cfg["mqtt_publisher"])
        with pytest.raises(KeyError, match="endpoint/EndPoint key not found in publisher config"):
            pub_obj.get_endpoint()


class TestSubscriberConfig:
    
    def test_mqtt(self):
        sub_cfg = {
            "mqtt_subscriber": {
                "host": "localhost",
                "port": 1883,
                "topic": "test",
                "subscribe_frame": False,
                "endpoint": "mqtt_endpoint"
            }
        }
        sub_obj = config.SubscriberConfig(sub_cfg["mqtt_subscriber"])
        assert sub_obj.get_sub_cfg() == sub_cfg["mqtt_subscriber"]
        assert sub_obj.get_topics() == "test"
        assert sub_obj.get_endpoint() == "mqtt_endpoint"

    def test_mqtt_with_Topics(self):
        sub_cfg = {
            "mqtt_subscriber": {
                "host": "localhost",
                "port": 1883,
                "Topics": "test",
                "subscribe_frame": False,
                "endpoint": "mqtt_endpoint"
            }
        }
        sub_obj = config.SubscriberConfig(sub_cfg["mqtt_subscriber"])
        assert sub_obj.get_sub_cfg() == sub_cfg["mqtt_subscriber"]
        assert sub_obj.get_topics() == "test"
        assert sub_obj.get_endpoint() == "mqtt_endpoint"

    def test_mqtt_with_EndPoint(self):
        sub_cfg = {
            "mqtt_subscriber": {
                "host": "localhost",
                "port": 1883,
                "topic": "test",
                "EndPoint": "localhost:1883",
                "subscribe_frame": False
            }
        }
        sub_obj = config.SubscriberConfig(sub_cfg["mqtt_subscriber"])
        assert sub_obj.get_sub_cfg() == sub_cfg["mqtt_subscriber"]
        assert sub_obj.get_topics() == "test"
        assert sub_obj.get_endpoint() == "localhost:1883"

    def test_missing_topic_key(self):
        sub_cfg = {
            "mqtt_subscriber": {
                "host": "localhost",
                "port": 1883,
                "EndPoint": "localhost:1883",
                "subscribe_frame": False
            }
        }
        with pytest.raises(KeyError, match="topic/Topics key not found in subscriber config"):
            sub_obj = config.SubscriberConfig(sub_cfg["mqtt_subscriber"])
            sub_obj.get_topics()

    def test_missing_endpoint_key(self):
        sub_cfg = {
            "mqtt_subscriber": {
                "host": "localhost",
                "topic": "test",
                "port": 1883,
                "subscribe_frame": False
            }
        }
        with pytest.raises(KeyError, match="endpoint/EndPoint key not found in subscriber config"):
            sub_obj = config.SubscriberConfig(sub_cfg["mqtt_subscriber"])
            sub_obj.get_endpoint()

class TestConfigHandler:
    def test_config_handler(self, mocker):
        mocker.patch(
        "builtins.open",
        mocker.mock_open(
            read_data=json.dumps({
                "config": "test_data"
            })))
        ch = config.PipelineServerConfig._ConfigHandler()
        ch.log = mocker.MagicMock()
        
        assert ch._app_cfg == "test_data"
    
    @pytest.fixture
    def mock_open_file(mocker):
        data = {
            "config": {"key": "value"},
            "interfaces": {"interface_key": "interface_value"}
        }
        return mocker.mock_open(read_data=json.dumps(data))
    
    def test_config_handler_non_eii_mode_file_not_found(self, mocker):
        mocker.patch("builtins.open", side_effect=FileNotFoundError)
        with pytest.raises(FileNotFoundError):
            config.PipelineServerConfig._ConfigHandler()

    def side_effect_get_interface(self,i):
        data = {0:"cfg1", 1:"cfg2"}
        return data[i]
    
class TestPipelineServerConfig:

    @pytest.fixture
    def test_pipeline_server_config(self, mocker):
        mocker.patch("src.config.PipelineServerConfig._ConfigHandler")
        pipeline_server = config.PipelineServerConfig()
        pipeline_server._cfg_handler.get_app_cfg.return_value = {"test_data": "test", "pipelines": "test_pipeline", "model_registry": "test_model_registry"}    
        return pipeline_server
    
    def test_get_app_cfg(self, test_pipeline_server_config):
        assert test_pipeline_server_config.get_app_config() == {"test_data": "test", "pipelines": "test_pipeline", "model_registry": "test_model_registry"}

    def test_get_pipelines_config(self, test_pipeline_server_config):
        assert test_pipeline_server_config.get_pipelines_config() == "test_pipeline"

    def test_get_app_interface(self, test_pipeline_server_config):
        test_pipeline_server_config._cfg_handler.get_app_interface.return_value = "mocked_interface"
        result = test_pipeline_server_config.get_app_interface()
        assert result == "mocked_interface"

    def test_get_publishers(self, test_pipeline_server_config):
        test_publisher = [{"host": "localhost", "port": 1883, "topic": "test", "publish_frame": False}]
        test_pipeline_server_config._cfg_handler.get_mqtt_publisher.return_value = test_publisher
        result = test_pipeline_server_config.get_publishers()        
        assert len(result) == 1
        assert isinstance(result[0], config.PublisherConfig)

    @pytest.mark.parametrize("new_config", [
        ({"test_data": "new_test", "pipelines": "new_pipeline", "model_registry": "new_model_registry"})
    ])
    def test_set_app_config(self, test_pipeline_server_config, new_config):    
        test_pipeline_server_config.set_app_config(new_config)
        assert test_pipeline_server_config._cfg_handler._app_cfg == new_config
    
    @pytest.mark.parametrize("new_config, model_path_dict, expected_pipeline, expected_udfloader", [
        (
            {"test_data": "test", "pipelines": [{"pipeline": "element1 ! element2 name=element2 ! element3 name=element3"}], "model_registry": "test_model_registry"},
            {
                "element2": "/fake/dir/model1/model1.xml",
                "element3": "/fake/dir/model2/model2.xml"
            },
            "element1 ! element2 name=element2 model=/fake/dir/model1/model1.xml ! element3 name=element3 model=/fake/dir/model2/model2.xml ",
            None
        ),
        (
            {"test_data": "test", "pipelines": [{"pipeline": "element1 ! element2 name=element2 ! udfloader name=udfloader", "udfs": {"udfloader": [{"name": "python.geti_udf.geti_udf"}]}}], "model_registry": "test_model_registry"},
            {
                "element2": "/fake/dir/model1/model1.xml",
                "udfloader": "/fake/dir/model/deployment"
            },
            "element1 ! element2 name=element2 model=/fake/dir/model1/model1.xml ! udfloader name=udfloader",
            "/fake/dir/model/deployment"
        ),
        (
            {"test_data": "test", "pipelines": [{"pipeline": "element1 ! udfloader name=udfloader", "udfs": {"udfloader": [{"name": "python.geti_udf.geti_udf"}]}}], "model_registry": "test_model_registry"},
            {
                "udfloader": "/fake/dir/model/deployment"
            },
            "element1 ! udfloader name=udfloader",
            "/fake/dir/model/deployment"
        ),
    ])
    def test_update_pipeline_config(self, mocker, new_config, model_path_dict, expected_pipeline, expected_udfloader):
        mocker.patch("src.config.PipelineServerConfig._ConfigHandler")
        mock_config = config.PipelineServerConfig()
        mock_config._cfg_handler.get_app_cfg.return_value = new_config
        mock_config.update_pipeline_config(model_path_dict)
        updated_config = mock_config.get_app_config()
        assert updated_config["pipelines"][0]["pipeline"] == expected_pipeline
        if expected_udfloader:
            assert updated_config["pipelines"][0]["udfs"]["udfloader"][0]["deployment"] == expected_udfloader
