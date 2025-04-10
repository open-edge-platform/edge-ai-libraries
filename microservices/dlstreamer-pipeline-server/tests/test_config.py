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
    @pytest.fixture
    def setup_eii(self):
        pub_cfg = {
            "eis_servers": {
                "topics": ["test"],
                "endpoint": "eii_endpoint"
            }
        }
        return pub_cfg

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
        assert pub_obj.is_emb_publisher() == False

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
        assert pub_obj.is_emb_publisher() == False

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
        assert pub_obj.is_emb_publisher() == False
    
    def test_eii(self, setup_eii):
        class MockPubCfg:
            def get_eis_servers(self):
                return setup_eii["eis_servers"]
            def get_interface_value(self, key):
                return setup_eii["eis_servers"][key]
            def get_endpoint(self):
                return setup_eii["eis_servers"]["endpoint"]
        pub_obj = config.PublisherConfig(MockPubCfg(), eii_mode=True)
        assert pub_obj.get_pub_cfg() == setup_eii["eis_servers"]
        assert pub_obj.get_topics() == ["test"]
        assert pub_obj.get_endpoint() == "eii_endpoint"
        assert pub_obj.is_emb_publisher() == True

    def test_get_interface_value(self, setup_eii):
        class MockPubCfg:
            def get_eis_servers(self):
                return setup_eii["eis_servers"]
            
            def get_interface_value(self, key):
                return setup_eii["eis_servers"][key]
            
            def get_endpoint(self):
                return setup_eii["eis_servers"]["endpoint"]

        pub_obj = config.PublisherConfig(MockPubCfg(), eii_mode=True)
        assert pub_obj.get_interface_value("topics") == ["test"]
        assert pub_obj.get_interface_value("endpoint") == "eii_endpoint"

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
        assert pub_obj.get_interface_value("host") == "localhost"
        assert pub_obj.get_interface_value("port") == 1883

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
    @pytest.fixture
    def setup_eii(self):
        sub_cfg = {
            "eis_clients": {
                "topics": ["test"],
                "endpoint": "eii_endpoint"
            }
        }
        return sub_cfg

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
        assert sub_obj.is_emb_subscriber() == False

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
        assert sub_obj.is_emb_subscriber() == False

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
        assert sub_obj.is_emb_subscriber() == False

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

    def test_eii(self, setup_eii):
        class MockSubCfg:
            def get_eis_clients(self):
                return setup_eii["eis_clients"]
            
            def get_interface_value(self, key):
                return setup_eii["eis_clients"][key]
            
            def get_endpoint(self):
                return setup_eii["eis_clients"]["endpoint"]

        sub_obj = config.SubscriberConfig(MockSubCfg(), eii_mode=True)
        assert sub_obj.get_sub_cfg() == setup_eii["eis_clients"]
        assert sub_obj.get_topics() == ["test"]
        assert sub_obj.get_endpoint() == "eii_endpoint"
        assert sub_obj.is_emb_subscriber() == True

    def test_get_interface_value(self, setup_eii):
        class MockSubCfg:
            def get_eis_clients(self):
                return setup_eii["eis_clients"]
            
            def get_interface_value(self, key):
                return setup_eii["eis_clients"][key]
            
            def get_endpoint(self):
                return setup_eii["eis_clients"]["endpoint"]

        sub_obj = config.SubscriberConfig(MockSubCfg(), eii_mode=True)
        assert sub_obj.get_interface_value("topics") == ["test"]
        assert sub_obj.get_interface_value("endpoint") == "eii_endpoint"

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
        assert sub_obj.get_interface_value("host") == "localhost"
        assert sub_obj.get_interface_value("port") == 1883
        

class TestConfigHandler:
    def test_config_handler(self, mocker):
        mocker.patch(
        "builtins.open",
        mocker.mock_open(
            read_data=json.dumps({
                "config": "test_data"
            })))
        ch = config.EvamConfig._ConfigHandler()
        ch.log = mocker.MagicMock()
        
        assert ch.eii_mode == False
        assert ch._app_cfg == "test_data"

    @pytest.fixture
    def config_handler_eis(self, mocker, monkeypatch):
        monkeypatch.setenv("READ_CONFIG_FROM_FILE_ENV", "True")
        monkeypatch.setenv("AppName", "TestEVAM")
        mck_cfg = mocker.patch("src.config.get_eis_cfg")
        mck_cfgmgr = mck_cfg.config_manager.ConfigMgr.return_value = mocker.MagicMock()
        mocker.patch("src.config.get_logger")
        ch = config.EvamConfig._ConfigHandler(eii_mode=True, watch_cb=mocker.MagicMock(), watch_file_cbfunc=mocker.MagicMock())                
        assert ch.eii_mode == True
        return ch
    
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
            config.EvamConfig._ConfigHandler(eii_mode=False)

    # def test_config_handler_eii_raises_exception(self, mocker):
    #     with pytest.raises(ValueError):
    #         ch = config.EvamConfig._ConfigHandler(eii_mode=True)

    def test_get_app_cfg(self, config_handler_eis):        
        config_handler_eis._app_cfg = "test_data"
        assert config_handler_eis.get_app_cfg() == "test_data"

    def side_effect_get_interface(self,i):
        data = {0:"cfg1", 1:"cfg2"}
        return data[i]
    
    def test_get_emb_subscriber(self, config_handler_eis):
        config_handler_eis._cfg_mgr.get_num_of_subscribers.return_value = 1
        config_handler_eis._cfg_mgr.get_subscriber_by_index.side_effect=self.side_effect_get_interface        
        
        assert config_handler_eis.eii_mode == True
        assert config_handler_eis.get_emb_subscribers() == ["cfg1"]

    def test_get_emb_publisher(self, config_handler_eis):
        config_handler_eis._cfg_mgr.get_num_of_publishers.return_value = 1
        config_handler_eis._cfg_mgr.get_publisher_by_index.side_effect=self.side_effect_get_interface        
        
        assert config_handler_eis.eii_mode == True
        assert config_handler_eis.get_emb_publishers() == ["cfg1"]

    def test_get_eis_servers(self, config_handler_eis):
        config_handler_eis._cfg_mgr.get_num_of_servers.return_value = 1
        config_handler_eis._cfg_mgr.get_server_by_index.side_effect=self.side_effect_get_interface        
        
        assert config_handler_eis.eii_mode == True
        assert config_handler_eis.get_eis_servers() == ["cfg1"]

    def test_get_eis_clients(self, config_handler_eis):
        config_handler_eis._cfg_mgr.get_num_of_clients.return_value = 1
        config_handler_eis._cfg_mgr.get_client_by_index.side_effect=self.side_effect_get_interface        
        
        assert config_handler_eis.eii_mode == True
        assert config_handler_eis.get_eis_clients() == ["cfg1"]


class TestEvamConfig:

    @pytest.fixture
    def test_evam_config(self, mocker):
        mocker.patch("src.config.EvamConfig._ConfigHandler")
        evam = config.EvamConfig(mode=False)
        evam._cfg_handler.get_app_cfg.return_value = {"test_data": "test", "pipelines": "test_pipeline", "model_registry": "test_model_registry"}    
        return evam
    
    def test_get_app_cfg(self, test_evam_config):
        assert test_evam_config.get_app_config() == {"test_data": "test", "pipelines": "test_pipeline", "model_registry": "test_model_registry"}

    def test_get_pipelines_config(self, test_evam_config):
        assert test_evam_config.get_pipelines_config() == "test_pipeline"

    def test_get_model_registry_config(self, test_evam_config):
        assert test_evam_config.get_model_registry_config() == "test_model_registry"

    def test_get_app_interface(self, test_evam_config):
        test_evam_config._cfg_handler.get_app_interface.return_value = "mocked_interface"
        result = test_evam_config.get_app_interface()
        assert result == "mocked_interface"

    def test_get_publishers(self, test_evam_config):
        test_publisher = [{"host": "localhost", "port": 1883, "topic": "test", "publish_frame": False}]
        test_evam_config._cfg_handler.eii_mode = False
        test_evam_config._cfg_handler.get_mqtt_publisher.return_value = test_publisher
        result = test_evam_config.get_publishers()        
        assert len(result) == 1
        assert isinstance(result[0], config.PublisherConfig)

    def test_get_publishers_eii_mode(self,test_evam_config, mocker):
        evam = test_evam_config
        evam._cfg_handler.eii_mode = True
        eis_clients = [{"host": "localhost", "port": 50051, "service": "test_service"}]
        evam._cfg_handler.get_eis_clients.return_value = eis_clients
        publishers = evam.get_publishers()
        assert len(publishers) == 1
        assert publishers[0].is_emb_publisher() == True
        
    def test_get_subscribers(self, test_evam_config):
        test_subscriber = ["sub_cfg"]
        test_evam_config._cfg_handler.eii_mode = True
        test_evam_config._cfg_handler.get_eis_servers.return_value = test_subscriber
        result = test_evam_config.get_subscribers()        
        assert len(result) == 1
        assert isinstance(result[0], config.SubscriberConfig)

    @pytest.mark.parametrize("new_config", [
        ({"test_data": "new_test", "pipelines": "new_pipeline", "model_registry": "new_model_registry"})
    ])
    def test_set_app_config(self, test_evam_config, new_config):    
        test_evam_config.set_app_config(new_config)
        assert test_evam_config._cfg_handler._app_cfg == new_config
    
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
        mocker.patch("src.config.EvamConfig._ConfigHandler")
        mock_config = config.EvamConfig(mode=False)
        mock_config._cfg_handler.get_app_cfg.return_value = new_config
        mock_config.update_pipeline_config(model_path_dict)
        updated_config = mock_config.get_app_config()
        assert updated_config["pipelines"][0]["pipeline"] == expected_pipeline
        if expected_udfloader:
            assert updated_config["pipelines"][0]["udfs"]["udfloader"][0]["deployment"] == expected_udfloader
