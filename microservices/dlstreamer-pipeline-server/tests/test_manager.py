#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import copy
import base64
import queue
from unittest.mock import MagicMock
import sys
import src.common.log
import json
import os

# Mocked modules - cfgmgr
mocked_cfgmgr = MagicMock()
sys.modules['cfgmgr.config_manager'] = mocked_cfgmgr

from src.manager import PipelineServerManager
from src.manager import Pipeline
from src.manager import PipelineInstance


class TestPipelineInstance:
    def test_init(self, mocker):
        test_pipeline_name = "test_pipeline_name"
        test_pipeline_version = "1.0"
        test_config = {"source":"test_source", 
                                "name": "test_pipeline", 
                                "pipeline": "test ! gstreamer ! pipeline",
                                "parameters": {"param1":"test_param1"}}
        test_publisher_config = ["test_publisher_cfg"]
        test_request= {"mock_request_key": "mock_request_value"}
        test_subscriber_config = "test_subscriber_cfg"
        test_subscriber_topic = "test_subscriber_topic"
        test_publish_frame = False

        pipeline_obj = PipelineInstance(test_pipeline_name, test_pipeline_version, test_config, test_publisher_config, test_subscriber_config, test_subscriber_topic, test_publish_frame, test_request) 
        
        assert pipeline_obj.pub_cfg == test_publisher_config
        assert pipeline_obj.sub_cfg == test_subscriber_config
        assert pipeline_obj.sub_topic == test_subscriber_topic
        assert pipeline_obj.config == test_config
        assert pipeline_obj.publish_frame == False
       
    @pytest.fixture(scope="class")
    def pipeline_instance(self):
        name = "mock_pipeline"
        version = "mock_version"
        config = {
            "name": "mock_version",
            "source": "ingestor",
            "parameters": {"param1": "value1"}
        }
        publisher_config = ["mock_publisher"]
        subscriber_config = {"mock_subscriber_key": "mock_subscriber_value"}
        subscriber_topic = "mock_topic"
        publish_frame = True
        request = {"mock_request_key": "mock_request_value"}

        return PipelineInstance(name, version, config, publisher_config, subscriber_config, subscriber_topic, publish_frame, request)

    def test_mutable_deepcopy_none(self, pipeline_instance):
        result = pipeline_instance._mutable_deepcopy(None)
        assert result is None

    def test_mutable_deepcopy_nested(self, pipeline_instance):
        original = {"key1": [1]}
        copy_result = pipeline_instance._mutable_deepcopy(original)
        assert copy_result == original
        
    def test_to_dict(self, pipeline_instance):
        pipeline_instance.instance_id = "mock_instance_id"
        pipeline_instance.source_type = "mock_source_type"
        pipeline_instance._source = {"type": "mock_source"}
        pipeline_instance._destination = {"type": "mock_destination"}
        pipeline_instance._parameters = {"param1": "value1"}
        pipeline_instance.tag = "mock_tag"
        pipeline_instance._request = {"mock_request_key": "mock_request_value"}
        result = pipeline_instance.to_dict()
        expected_dict = {
            'name': "mock_pipeline",
            'version': "mock_version",
            'instance_id': "mock_instance_id",
            'source_type': "mock_source_type",
            'source': {"type": "mock_source"},
            'destination': {"type": "mock_destination"},
            'parameters': {"param1": "value1"},
            'tags': "mock_tag",
            'request': {"mock_request_key": "mock_request_value"}
        }
        assert result == expected_dict

    def test_start_unsupported_source_type(self, mocker, pipeline_instance):
        pipeline_instance.source_type = "source_type"
        mock_image_ingestor = mocker.patch("src.subscriber.image_ingestor.ImageIngestor")
        mock_xiris_cam_ingestor = mocker.patch("src.subscriber.cam_ingestor.XirisCamIngestor")
        mock_publisher = mocker.patch("src.publisher.publisher.Publisher")
        mock_pipeline_server = mocker.patch("src.manager.PipelineServer")
        mock_pipeline_server.pipeline.return_value = MagicMock()
        mock_pipeline_server.pipeline.return_value.start.return_value = "mock_instance_id"
        mock_publisher.return_value.publishers = [MagicMock()]
        with pytest.raises(RuntimeError, match="Unsupported source:"):
            pipeline_instance.start()

    


    def test_execute_request_invalid_source_type(self, pipeline_instance):
        pipeline_instance.source_type = "invalid_source_type"
        pipeline_instance.instance_id = "valid_instance_id"
        request = {"image_path": "mock_path"}
        valid_instance_id = "valid_instance_id"
        with pytest.raises(ValueError, match="Request execution is supported only for image_ingestor pipelines"):
            pipeline_instance.execute_request(valid_instance_id, request)

    def test_execute_request_invalid_instance_id(self, pipeline_instance):
        pipeline_instance.source_type = "image_ingestor"
        pipeline_instance.instance_id = "valid_instance_id"
        request = {"image_path": "mock_path"}
        invalid_instance_id = "invalid_instance_id"
        with pytest.raises(ValueError, match="Invalid instance id"):
            pipeline_instance.execute_request(invalid_instance_id, request)
    
    def test_execute_request_clear_response_queue(self, pipeline_instance, mocker):
        pipeline_instance.source_type = "image_ingestor"
        pipeline_instance.instance_id = "valid_instance_id"
        pipeline_instance.is_async = False
        pipeline_instance.is_appdest = True
        pipeline_instance.publisher = MagicMock()
        pipeline_instance.publisher.image_publisher = MagicMock()
        pipeline_instance.publisher.image_publisher.response_queue = MagicMock()
        pipeline_instance.publisher.image_publisher.response_queue.empty.side_effect = [False, False, True]
        pipeline_instance.publisher.image_publisher.response_queue.get_nowait.side_effect = [None, queue.Empty]
        pipeline_instance.ingestor = MagicMock()
        pipeline_instance.ingestor.request_queue = MagicMock()
        request = {"timeout": 5, "publish_frame": True}
        data, err = pipeline_instance.execute_request("valid_instance_id", request)
        assert pipeline_instance.publisher.image_publisher.response_queue.get_nowait.call_count == 2

    def test_execute_request_queue_full(self, pipeline_instance, mocker):
        pipeline_instance.source_type = "image_ingestor"
        pipeline_instance.instance_id = "valid_instance_id"
        pipeline_instance.is_async = False
        pipeline_instance.is_appdest = True
        pipeline_instance.publisher = MagicMock()
        pipeline_instance.publisher.image_publisher = MagicMock()
        pipeline_instance.publisher.image_publisher.response_queue = MagicMock()
        pipeline_instance.ingestor = MagicMock()
        pipeline_instance.ingestor.request_queue = MagicMock()
        pipeline_instance.ingestor.request_queue.put.side_effect = queue.Full
        request = {"timeout": 5, "publish_frame": True}
        data, err = pipeline_instance.execute_request("valid_instance_id", request)
        assert data is None
        assert err == "Could not execute requeust due to timeout."

    def test_stop(self, pipeline_instance):
        mock_publisher = MagicMock()
        mock_publisher.publishers = [MagicMock(), MagicMock()]
        pipeline_instance.publisher = mock_publisher
        pipeline_instance.ingestor = MagicMock()
        pipeline_instance.subscriber = MagicMock()
        pipeline_instance.instance_id = "mock_instance_id"
        pipeline_instance.stop()
        for p in mock_publisher.publishers:
            p.stop.assert_called_once()
        mock_publisher.stop.assert_called_once()
        pipeline_instance.ingestor.stop.assert_called_once()
        pipeline_instance.subscriber.stop.assert_called_once()
        assert pipeline_instance.is_running is False
        assert pipeline_instance.pipeline is None
    
    def test_get_status(self, mocker, pipeline_instance):
        mock_pipeline = mocker.patch.object(pipeline_instance, 'pipeline', MagicMock())
        mock_pipeline.status.return_value = {"status": "running"}
        pipeline_instance.instance_id = "mock_instance_id"
        status = pipeline_instance.get_status()
        assert status == {"status": "running"}



class TestPipeline:
    
    @pytest.fixture
    def pipeline_config(self):
        return {
            "name": "test_pipeline",
            "pipeline": "test_pipeline_string",
            "parameters": {},
            "auto_start": False
        }

    @pytest.fixture
    def publisher_config(self):
        return []

    @pytest.fixture
    def subscriber_config(self):
        return {}

    @pytest.fixture
    def setup_pipeline_obj(self, mocker, tmp_path, pipeline_config, publisher_config, subscriber_config):
        test_root_dir = tmp_path
        test_pipeline_name = "test_pipeline_name"
        test_subscriber_topic = "test_subscriber_topic"        
        pipeline_obj = Pipeline(test_root_dir, test_pipeline_name, pipeline_config, publisher_config, subscriber_config, test_subscriber_topic)
        return pipeline_obj

    def test_pipeline_initialization(self, setup_pipeline_obj, tmp_path, pipeline_config):
        pipeline_obj = setup_pipeline_obj
        assert pipeline_obj.root == tmp_path
        assert pipeline_obj.pipeline_name == "test_pipeline_name"
        assert pipeline_obj.pub_cfg == []
        assert pipeline_obj.sub_cfg == {}
        assert pipeline_obj.sub_topic == "test_subscriber_topic"
        assert pipeline_obj.pipeline_config == pipeline_config
        assert pipeline_obj.publish_frame == False
        assert pipeline_obj.auto_start == False
        expected_pipeline_dir = os.path.join(tmp_path, "test_pipeline_name", "test_pipeline")
        expected_pipeline_json_path = os.path.join(expected_pipeline_dir, "pipeline.json")
        assert pipeline_obj.pipeline_dir == expected_pipeline_dir
        assert pipeline_obj.pipeline_json_path == expected_pipeline_json_path
        assert os.path.exists(expected_pipeline_json_path)
        with open(expected_pipeline_json_path, "r") as f:
            pipeline_json_content = json.load(f)
            expected_pipeline_json_content = {
                "type": "GStreamer",
                "template": ["test_pipeline_string"],
                "description": "EVAM pipeline",
                "parameters": {}
            }
            assert pipeline_json_content == expected_pipeline_json_content

    def test_pipeline_start(self, setup_pipeline_obj, mocker):
        pipeline_obj = setup_pipeline_obj        
        mock_pipeline_instance = mocker.patch('src.manager.PipelineInstance')
        mock_instance = mock_pipeline_instance.return_value
        mock_instance.instance_id = "instance_1"
        mock_instance.to_dict.return_value = {"key": "value"}
        instance_id = pipeline_obj.start()
        mock_pipeline_instance.assert_called_once_with(
            pipeline_obj.pipeline_name,
            pipeline_obj.pipeline_version,
            pipeline_obj.pipeline_config,
            pipeline_obj.pub_cfg,
            pipeline_obj.sub_cfg,
            pipeline_obj.sub_topic,
            pipeline_obj.publish_frame,
            None
        )
        mock_instance.start.assert_called_once()
        assert instance_id == "instance_1"
        assert pipeline_obj.instance_refcount == 1
        assert pipeline_obj._INSTANCES["instance_1"] == {"obj": mock_instance, "params": {"key": "value"}}

    def test_pipeline_stop(self, setup_pipeline_obj, mocker):
        pipeline_obj = setup_pipeline_obj
        
        # Mock the PipelineInstance class
        mock_instance = MagicMock()
        mock_instance.instance_id = "instance_1"
        pipeline_obj._INSTANCES["instance_1"] = {"obj": mock_instance, "params": {"key": "value"}}
        pipeline_obj.instance_refcount = 1
        
        pipeline_obj.stop("instance_1")
        
        assert pipeline_obj.instance_refcount == 0
        assert "instance_1" not in pipeline_obj._INSTANCES
        mock_instance.stop.assert_called_once()
    
    def test_pipeline_stop_nonexistent_instance(self, setup_pipeline_obj, mocker):
        pipeline_obj = setup_pipeline_obj
        pipeline_obj.stop("nonexistent_instance")
        


class TestPipelineServerManager:
    @pytest.fixture(scope="class")
    def pipeline_server_manager(self):
        config = MagicMock()
        config.get_app_config.return_value = {
            'pipelines': [
                {'name': 'pipeline1', 'source': 'grpc', 'publish_frame': False},
                {'name': 'pipeline2', 'source': 'grpc', 'publish_frame': True}
            ]
        }
        config.get_publishers.return_value = [MagicMock(), MagicMock()]
        config.get_subscribers.return_value = [MagicMock()]
        config.is_eii_mode = True
        return PipelineServerManager(config)

    def test_initialize_pipelines(self, mocker, pipeline_server_manager):
        mocker.patch("src.manager.Pipeline", return_value=MagicMock())
        pipeline_server_manager._initialize_pipelines()
        assert len(pipeline_server_manager._PIPELINES) == 2

    def test_initialize_pipelines_multiple_subscribers(self, pipeline_server_manager):
        pipeline_server_manager.app_config = {
            'pipelines': [
                {'name': 'pipeline1', 'source': 'grpc', 'publish_frame': False}
            ]
        }
        mock_subscriber1 = MagicMock()
        mock_subscriber2 = MagicMock()
        pipeline_server_manager.config.get_subscribers = MagicMock(return_value=[mock_subscriber1, mock_subscriber2])
        with pytest.raises(ValueError, match="Only single subscriber is supported."):
            pipeline_server_manager._initialize_pipelines()

    def test_initialize_pipelines_invalid_subscriber(self, pipeline_server_manager):
        pipeline_server_manager.app_config = {
            'pipelines': [
                {'name': 'pipeline1', 'source': 'grpc', 'publish_frame': False}
            ]
        }
        mock_subscriber = MagicMock()
        mock_subscriber.is_emb_subscriber.return_value = False
        pipeline_server_manager.config.get_subscribers = MagicMock(return_value=[mock_subscriber])
        with pytest.raises(ValueError, match="Subsciber must be an edge grpc subscriber"):
            pipeline_server_manager._initialize_pipelines()

    def test_get_loaded_pipelines(self, pipeline_server_manager):
        mock_loaded_pipelines = [
            {"name": "pipeline1", "source": "grpc", "publish_frame": False},
            {"name": "pipeline2", "source": "grpc", "publish_frame": True}
        ]
        pipeline_server_manager.pserv = MagicMock()
        pipeline_server_manager.pserv.pipeline_manager.get_loaded_pipelines = MagicMock(return_value=mock_loaded_pipelines)
        result = pipeline_server_manager.get_loaded_pipelines()
        assert result == mock_loaded_pipelines
        pipeline_server_manager.pserv.pipeline_manager.get_loaded_pipelines.assert_called_once()


    def test_get_pipeline_instance_summary_success(self, pipeline_server_manager):
        instance_id = "instance1"
        psummary = {"id": instance_id, "summary": "test_summary"}
     
        pipeline_server_manager.pserv = MagicMock()
        pipeline_server_manager.pserv.pipeline_manager.get_instance_summary.return_value = psummary
        pipeline_server_manager.get_pipeline_instance_summary(instance_id)

    def test_get_pipeline_instance_summary_key_error(self, pipeline_server_manager):
        mock_psummary = {"id": "instance_123", "name": "test_pipeline"}
        pipeline_server_manager.pserv = MagicMock()
        pipeline_server_manager.pserv.pipeline_manager.get_instance_summary = MagicMock(return_value=mock_psummary)
        pipeline_server_manager._get_pinstance_data = MagicMock(side_effect=KeyError)
        pipeline_server_manager.log = MagicMock()
        result, error = pipeline_server_manager.get_pipeline_instance_summary("instance_123")
        assert result is None
        assert error == "Pipeline instance not found"
        pipeline_server_manager.log.error.assert_called_once_with("Pipeline instance not found")


    def test_get_all_instance_status(self, pipeline_server_manager):
        status = [
            {"id": "instance1", "status": "running"},
            {"id": "instance2", "status": "stopped"}
        ]
        pipeline_server_manager.pserv = MagicMock()
        pipeline_server_manager.pserv.pipeline_manager.get_all_instance_status.return_value = status
        result = pipeline_server_manager.get_all_instance_status()
        pipeline_server_manager.pserv.pipeline_manager.get_all_instance_status.assert_called_once()
        assert result == status

    def test_stop_instance(self, mocker, pipeline_server_manager):
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.instance_id = "mock_instance_id"
        mocker.patch.object(pipeline_server_manager, '_get_pinstance_data', return_value=(mock_pipeline_instance, {}))
        mocker.patch.object(pipeline_server_manager.pserv.pipeline_manager, 'stop_instance', return_value="mock_instance_id")
        pipeline_server_manager.log = MagicMock()
        instance_id = pipeline_server_manager.stop_instance("mock_instance_id")
        assert instance_id == "mock_instance_id"
        mock_pipeline_instance.stop.assert_called_once()
        pipeline_server_manager.log.error.assert_not_called()
        pipeline_server_manager.log.exception.assert_not_called()
    
    def test_stop_instance_not_found(self, mocker, pipeline_server_manager):
        mocker.patch.object(pipeline_server_manager, '_get_pinstance_data', side_effect=KeyError)
        mocker.patch.object(pipeline_server_manager.pserv.pipeline_manager, 'stop_instance', return_value="mock_instance_id")
        pipeline_server_manager.log = MagicMock()
        instance_id = pipeline_server_manager.stop_instance("mock_instance_id")
        assert instance_id == "mock_instance_id"
        pipeline_server_manager.log.error.assert_called_once_with("Pipeline instance not found")
        pipeline_server_manager.log.exception.assert_not_called()

    def test_stop_instance_exception(self, mocker, pipeline_server_manager):
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.instance_id = "mock_instance_id"
        mocker.patch.object(pipeline_server_manager, '_get_pinstance_data', return_value=(mock_pipeline_instance, {}))
        mock_pipeline_instance.stop.side_effect = Exception("Mock exception")
        mocker.patch.object(pipeline_server_manager.pserv.pipeline_manager, 'stop_instance', return_value="mock_instance_id")
        pipeline_server_manager.log = MagicMock()
        instance_id = pipeline_server_manager.stop_instance("mock_instance_id")
        assert instance_id == "mock_instance_id"
        mock_pipeline_instance.stop.assert_called_once()
        pipeline_server_manager.log.error.assert_not_called()
        pipeline_server_manager.log.exception.assert_called_once_with("Failed to stop pipeline instance. Mock exception")

    def test_start_no_pipelines_in_config(self, pipeline_server_manager):
        pipeline_server_manager.app_config = {}
        pipeline_server_manager.log = MagicMock()
        with pytest.raises(RuntimeError, match="No pipelines found in config"):
            pipeline_server_manager.start()

    def test_start_initialize_pipelines_exception(self, pipeline_server_manager):
        pipeline_server_manager.app_config = {'pipelines': []}
        pipeline_server_manager._initialize_pipelines = MagicMock(side_effect=Exception("Initialization error"))
        pipeline_server_manager.log = MagicMock()
        with pytest.raises(Exception, match="Initialization error"):
            pipeline_server_manager.start()
        pipeline_server_manager.log.exception.assert_called_once_with("One or more pipelines could not be initialized. Initialization error")

    def test_start(self, mocker, pipeline_server_manager):
        mocker.patch.object(pipeline_server_manager, '_initialize_pipelines', return_value=None) 
        mocker.patch("src.manager.PipelineServer.start", return_value=None) 
        mocker.patch("src.manager.Pipeline.start", return_value="mock_instance_id")
        pipeline_server_manager.start()
                    
   
    def test_start_instance_pipeline_not_found(self, pipeline_server_manager):
        pipeline_server_manager.log = MagicMock()
        instance_id, errmsg = pipeline_server_manager.start_instance("pipeline1", "non_existent_version")
        assert instance_id is None
        assert errmsg == "Pipeline not found"
        pipeline_server_manager.log.error.assert_called_once_with("Pipeline not found")

    def test_start_instance(self,pipeline_server_manager, mocker):
        pipeline_server_manager._PIPELINES = {
            "mock_version": MagicMock()
        }
        pipeline_server_manager._PIPELINES["mock_version"].pipeline_config = {
            "pipeline": "gvadetect ! gvaclassify ! gvainference"
        }
        pipeline_server_manager._GVAELEMENT_MODEL_INSTANCE_ID = {
            "gvadetect": {},
            "gvaclassify": {},
            "gvainference": {}
        }
        mock_pipeline = pipeline_server_manager._PIPELINES["mock_version"]
        mock_pipeline.start.return_value = "instance_id"

        instance_id, err = pipeline_server_manager.start_instance("mock_name", "mock_version")

        assert instance_id == "instance_id"
        assert err is None
        mock_pipeline.start.assert_called_once()

    def test_execute_request_on_instance(self, pipeline_server_manager):
        pipeline_instance = MagicMock()
        pipeline_server_manager._PIPELINES = {
            'pipeline1': MagicMock(_INSTANCES={'instance1': {'obj': pipeline_instance}})
        }
        request = {"key": "value"}
        result, errmsg = pipeline_server_manager.execute_request_on_instance("pipeline1", "pipeline1", "instance1", request)
        assert errmsg == 'Pipeline instance not found'

    def test_start_instance_model_instance_id_set(self, pipeline_server_manager, mocker):
        pipeline_server_manager._PIPELINES = {
            "mock_version": MagicMock()
        }
        pipeline_server_manager._PIPELINES["mock_version"].pipeline_config = {
            "pipeline": "gvadetect model-instance-id=mock_id ! gvaclassify ! gvainference"
        }
        pipeline_server_manager._GVAELEMENT_MODEL_INSTANCE_ID = {
            "gvadetect": {"mock_id": {}},
            "gvaclassify": {},
            "gvainference": {}
        }
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_instance_status.return_value = {'state': 'RUNNING'}
        pipeline_server_manager.pserv = MagicMock()
        pipeline_server_manager.pserv.pipeline_manager = mock_pipeline_manager
        mock_pipeline = pipeline_server_manager._PIPELINES["mock_version"]
        mock_pipeline.start.return_value = "instance_id"
        instance_id, err = pipeline_server_manager.start_instance("mock_name", "mock_version")
        assert instance_id == "instance_id"
        assert err is None
        mock_pipeline.start.assert_called_once()
        
    def test_execute_request_on_instance_exception(self, pipeline_server_manager):
        mock_pinstance = MagicMock()
        pipeline_server_manager._get_pinstance_data = MagicMock(return_value=(mock_pinstance, None))
        mock_pinstance.execute_request = MagicMock(side_effect=Exception("Execution error"))
        pipeline_server_manager.log = MagicMock()
        result, error = pipeline_server_manager.execute_request_on_instance("test_name", "1.0", "instance_123", {"key": "value"})
        assert result is None
        assert error == "Failed to execute request"
        pipeline_server_manager.log.exception.assert_called_once_with("Failed to execute request.instance_123 Execution error")

    def test_stop_pipelines(self, mocker, pipeline_server_manager):
        pipeline_instance = MagicMock(is_running=True)
        pipeline_server_manager._PIPELINES = {
            'pipeline1': MagicMock(_INSTANCES={'instance1': {'obj': pipeline_instance}})
        }
        mocker.patch.object(pipeline_server_manager, 'stop_instance', return_value=None) 
        pipeline_server_manager.stop_pipelines()

    def test_stop(self, mocker,pipeline_server_manager):
        pipeline_server_manager.pserv = MagicMock()
        mocker.patch.object(pipeline_server_manager, 'stop_pipelines', return_value=None)
        pipeline_server_manager.stop()
        pipeline_server_manager.pserv.stop.assert_called_once()
            
    