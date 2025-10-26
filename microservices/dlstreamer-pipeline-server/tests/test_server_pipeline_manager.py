#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest import mock
from unittest.mock import patch, MagicMock
from collections import defaultdict, deque
import os
from src.server.pipeline_manager import PipelineManager

@pytest.fixture
def pipeline_manager_for_load_pipelines(mocker):
    pipeline_dir = "user_pipeline"
    max_running_pipelines = 5
    model_manager = MagicMock()
    pipeline_manager_instance = PipelineManager(model_manager, pipeline_dir, max_running_pipelines, ignore_init_errors=True)
    return pipeline_manager_instance

@pytest.fixture
def pipeline_manager(mocker):
    mocker.patch.object(PipelineManager, '_load_pipelines', return_value=True)
    pipeline_dir = "user_pipeline"
    max_running_pipelines = 5
    model_manager = MagicMock()
    pipeline_manager_instance = PipelineManager(model_manager, pipeline_dir, max_running_pipelines, ignore_init_errors=True)
    return pipeline_manager_instance

class TestPipelineManager:
    def test_init_pipeline_manager(self,pipeline_manager):
        assert pipeline_manager.max_running_pipelines == 5
        assert pipeline_manager.model_manager is not None
        assert pipeline_manager.pipeline_dir == "user_pipeline"

    def test_init_failed_load(self,mocker):
        mocker.patch.object(PipelineManager, '_load_pipelines', return_value=False)
        with pytest.raises(Exception, match="Error Initializing Pipelines"):
            pipeline_manager_obj = PipelineManager(MagicMock(),"user_pipeline",5,False)

    def test_import_pipeline_types(self, pipeline_manager, mocker):
        mocker.patch('src.server.gstreamer_pipeline.GStreamerPipeline', return_value=MagicMock())
        pipeline_types = pipeline_manager._import_pipeline_types()
        assert "GStreamer" in pipeline_types
        mocker.patch.dict('sys.modules',{'src.server.gstreamer_pipeline':None})
        pipeline_types = pipeline_manager._import_pipeline_types()
        assert {} == pipeline_types

    def test_load_pipelines(self, pipeline_manager_for_load_pipelines, mocker):
        pipeline_manager_for_load_pipelines.pipeline_dir = "user_pipeline"
        pipeline_manager_for_load_pipelines.pipeline_types = {"GStreamer" : MagicMock()}
        mocker.patch('os.walk', return_value=[('user_pipeline', ['pallet'], []),('pallet', [], ['config.json'])])
        mocker.patch('os.path.abspath', side_effect=lambda x: x)
        mocker.patch('os.path.dirname', side_effect=lambda x: {
            'user_pipeline': "",
            'pallet': "user_pipeline",
            'config.json': "pallet"
        }[x])
        mocker.patch('builtins.open', mocker.mock_open(read_data='{"type": "GStreamer", "description": "Test Pipeline"}'))
        mocker.patch('json.load', return_value={"type": "GStreamer", "description": "Test Pipeline"})
        mocker.patch('src.server.pipeline_manager.PipelineManager._validate_config', return_value=True)
        mocker.patch('src.server.pipeline_manager.PipelineManager._update_defaults_from_env')
        success = pipeline_manager_for_load_pipelines._load_pipelines()
        assert success
        assert pipeline_manager_for_load_pipelines.pipeline_dir in  pipeline_manager_for_load_pipelines.pipelines

    def test_pipeline_exists(self, pipeline_manager, mocker):
        pipeline_manager.pipelines = {'pipeline1': {'v1': {}}}
        assert pipeline_manager.pipeline_exists('pipeline1', 'v1')
        assert not pipeline_manager.pipeline_exists('pipeline2', 'v1')

    def test_get_pipeline_parameters(self, pipeline_manager, mocker):
        mocker.patch('src.server.pipeline_manager.PipelineManager.pipeline_exists', return_value = True)
        pipeline_manager.pipelines = {'pipeline1': {'v1': {'type': 'GStreamer', 'description': 'Test Pipeline', 'parameters' : {'properties':{}}}}}
        params = pipeline_manager.get_pipeline_parameters("pipeline1", 'v1')
        assert params is not None
        assert params["name"] == "pipeline1"
        assert params["version"] == 'v1'
        assert "type" in params
        assert "description" in params
        assert "parameters" in params
        mocker.patch('src.server.pipeline_manager.PipelineManager.pipeline_exists', return_value = False)
        params = pipeline_manager.get_pipeline_parameters("pipeline", 'v1')
        assert params is None

    def test_get_loaded_pipelines(self, pipeline_manager, mocker):
        mock_get_pipeline_params = mocker.patch('src.server.pipeline_manager.PipelineManager.get_pipeline_parameters', return_value = {'name':'pipeline1', 'version': 'v1', "type": "GStreamer"})
        pipeline_manager.pipelines = {'pipeline1': {'v1': {'type': 'GStreamer', 'description': 'Test Pipeline'}}}
        loaded_pipelines = pipeline_manager.get_loaded_pipelines()
        assert len(loaded_pipelines) == 1
        assert loaded_pipelines[0]["name"] == "pipeline1"
        assert loaded_pipelines[0]["version"] == "v1"
        assert loaded_pipelines[0]["type"] == "GStreamer"
        mock_get_pipeline_params.assert_called_once_with('pipeline1','v1')

    def test_instance_exists(self, pipeline_manager, mocker):
        mock_pipeline = MagicMock()
        mock_pipeline.request = {"pipeline": {"name": "pipeline1", "version": "v1"}}
        pipeline_manager.pipeline_instances = {'instance_id': mock_pipeline}
        assert pipeline_manager.instance_exists('instance_id')
        assert not pipeline_manager.instance_exists('invalid_id')
        assert pipeline_manager.instance_exists('instance_id','pipeline1','v1')
        assert not pipeline_manager.instance_exists('instance_id','pipeline_na','v1')

    @pytest.mark.parametrize(
    "instance_exists_value, pipeline_instances, instance_id, expected_summary",
    [
        (True, {'instance_id': MagicMock(params=MagicMock(return_value={'name': 'pipeline1'}))}, 'instance_id', {'name': 'pipeline1'}),
        (False, {}, 'instance_id', None)
    ])
    def test_get_instance_summary(self, pipeline_manager, instance_exists_value, pipeline_instances, instance_id, expected_summary):
        pipeline_manager.instance_exists = MagicMock(return_value=instance_exists_value)
        pipeline_manager.pipeline_instances = pipeline_instances
        summary = pipeline_manager.get_instance_summary(instance_id)
        assert summary == expected_summary
        pipeline_manager.instance_exists.assert_called_once_with(instance_id)

    @pytest.mark.parametrize(
    "instance_exists_value, pipeline_instances, instance_id, expected_status",
    [
        (True, {'instance_id': MagicMock(status=MagicMock(return_value={'status': 'running'}))}, 'instance_id', {'status': 'running'}),
        (False, {}, 'instance_id', None)
    ])
    def test_get_instance_status(self, pipeline_manager, pipeline_instances, instance_id, instance_exists_value,expected_status):
        pipeline_manager.instance_exists = MagicMock(return_value=instance_exists_value)
        pipeline_manager.pipeline_instances = pipeline_instances
        status = pipeline_manager.get_instance_status(instance_id)
        assert status == expected_status
        pipeline_manager.instance_exists.assert_called_once_with(instance_id,None,None)

    def test_get_all_instance_status(self, pipeline_manager):
        pipeline_manager.pipeline_instances = {'instance_id1': MagicMock(status=MagicMock(return_value={'pipeline1': 'running'})),'instance_id2': MagicMock(status=MagicMock(return_value={'pipeline2': 'running'}))}
        status = pipeline_manager.get_all_instance_status()
        assert status == [{'pipeline1': 'running'},{'pipeline2': 'running'}]

    @pytest.mark.parametrize(
    "instance_exists_value, pipeline_instances, instance_id, expected_params",
    [
        (True, {'instance_id': MagicMock(params=MagicMock(return_value={'param1': 'value1'}))}, 'instance_id', {'param1': 'value1'}),
        (False, {}, 'instance_id', None)
    ])
    def test_get_instance_parameters(self, pipeline_manager, pipeline_instances, instance_id, instance_exists_value,expected_params):
        name = "pipeline1"
        version = "v1"
        pipeline_manager.instance_exists = MagicMock(return_value=instance_exists_value)
        pipeline_manager.pipeline_instances = pipeline_instances
        status = pipeline_manager.get_instance_parameters(name,version,instance_id)
        assert status == expected_params
        pipeline_manager.instance_exists.assert_called_once_with(instance_id,name,version)

    def test_stop_instance(self, pipeline_manager):
        pipeline_manager.instance_exists = MagicMock(return_value=True)
        pipeline_manager.pipeline_queue = deque(["instance1", "instance2"])
        pipeline_manager.pipeline_instances = {'instance1': MagicMock(stop=MagicMock(return_value=True)),'instance3': MagicMock(stop=MagicMock(return_value=True))}
        result = pipeline_manager.stop_instance('instance1')
        assert result
        assert pipeline_manager.pipeline_queue == deque(["instance2"])
        pipeline_manager.instance_exists.assert_called_once_with("instance1",None,None)
        result = pipeline_manager.stop_instance('instance3')
        assert result
        pipeline_manager.instance_exists = MagicMock(return_value=False)
        result = pipeline_manager.stop_instance('instance2')
        assert result is None

    @pytest.mark.parametrize(
    "max_running_pipelines, running_pipelines, pipeline_queue, expected_result",
    [
        (5, 3, deque(['pipeline1', 'pipeline2']), 'pipeline1'),
        (5, 5, deque(['pipeline1', 'pipeline2']), None),
        (5, 6, deque(['pipeline1', 'pipeline2']), None),
        (5, 3, deque([]), None),
        (5, 3, "pipeline", None)
    ])
    def test_get_next_pipeline_identifier(self, pipeline_manager, max_running_pipelines, running_pipelines, pipeline_queue, expected_result):
        pipeline_manager.max_running_pipelines = max_running_pipelines
        pipeline_manager.running_pipelines = running_pipelines
        pipeline_manager.pipeline_queue = pipeline_queue
        result = pipeline_manager._get_next_pipeline_identifier()
        assert result == expected_result

    @pytest.mark.parametrize(
    "value, expected_result",
    [
        ('{"name": "pipeline1", "version": "v1"}', {"name": "pipeline1", "version": "v1"}),
        ('dlstreamer pipeline server pipeline', 'dlstreamer pipeline server pipeline')
    ])
    def test_get_typed_value(self, pipeline_manager,value, expected_result):
        result = pipeline_manager._get_typed_value(value)
        assert result == expected_result

    @pytest.mark.parametrize(
        "request_value, pipeline_config, section, expected_result",[
            (
                {"parameters": {"param1": "value1"}},{"parameters": {"type": "object", "properties": {"param1": {"type": "string"}}}},"parameters",True),
            (
                {"parameters": {"param1": 123}},{"parameters": {"type": "object", "properties": {"param1": {"type": "string"}}}},"parameters",False),
            (
                {},{"parameters": {"type": "object", "properties": {"param1": {"type": "string"}}}},"parameters",True)])
    def test_is_input_valid(self, pipeline_manager, request_value, pipeline_config, section, expected_result):
        result = pipeline_manager.is_input_valid(request_value, pipeline_config, section)
        assert result == expected_result

    def test_pipeline_finished(self, pipeline_manager,mocker):
        mocker.patch.object(pipeline_manager,'_start')
        pipeline_manager.running_pipelines = 1
        pipeline_manager._pipeline_finished()
        assert pipeline_manager.running_pipelines == 0
        pipeline_manager._start.assert_called_once()

    def test_start_pipeline_manager(self,pipeline_manager,mocker):
        mocker.patch.object(pipeline_manager,'_get_next_pipeline_identifier',return_value='instance_id')
        mock_instance = MagicMock()
        pipeline_manager.pipeline_instances = {'instance_id': mock_instance}
        pipeline_manager.running_pipelines = 0
        mocker.patch.object(mock_instance,'start')
        pipeline_manager._start()
        assert pipeline_manager.running_pipelines == 1
        pipeline_manager._get_next_pipeline_identifier.assert_called_once()
        mock_instance.start.assert_called_once()

    def test_validate_config(self,pipeline_manager,mocker):
        mock_set_defaults = mocker.patch.object(pipeline_manager,'set_defaults')
        pipeline_manager.model_manager.model_manager = {"models":"model1"}
        mock_pipeline = MagicMock()
        pipeline_manager.pipeline_types = {'GStreamer' : mock_pipeline}
        mocker.patch.object(mock_pipeline,'validate_config')
        pipeline_manager._validate_config({"type":"GStreamer"})
        mock_set_defaults.assert_called_once()
        mock_pipeline.validate_config.assert_called_once()

    @pytest.mark.parametrize(
    "config_return, debug_call",
    [
        ({"key1": "value1","key2":{"default":"{env[default_value]}","type": "string"}},"Setting key2=env_value_set using {env[default_value]}"),
        ({"key1": "value1","key2":{"default":"{env[default_value]}","type": "dict"}},"Setting key2=env_get_value using {env[default_value]}")
    ])
    def test_update_defaults_from_env(self,pipeline_manager,mocker,config_return,debug_call):
        config = {"key_config":"value_config"}
        mock_logger = MagicMock()
        pipeline_manager.logger = mock_logger
        mock_get_config = mocker.patch('src.server.pipeline_manager.Pipeline.get_config_section',return_value = config_return)
        mocker.patch.object(os, 'environ', {"default_value":"env_value_set"})
        mock__get_typed_value = mocker.patch.object(pipeline_manager,'_get_typed_value',return_value = "env_get_value")
        pipeline_manager._update_defaults_from_env(config)
        mock_logger.debug.assert_called_once_with(debug_call)
        mock_get_config.assert_called_once_with(config, ["parameters", "properties"])

    def test_update_defaults_from_env_exception(self,pipeline_manager,mocker):
        config = {"key_config":"value_config"}
        mock_logger = MagicMock()
        pipeline_manager.logger = mock_logger
        config_return = {"key1": "value1","key2":{"default":"{env[default_value]}","type": "dict"}}
        mock_get_config = mocker.patch('src.server.pipeline_manager.Pipeline.get_config_section',return_value = config_return)
        mocker.patch.object(os, 'environ', {"default_value":"env_value_set"})
        mock__get_typed_value = mocker.patch.object(pipeline_manager,'_get_typed_value',side_effect = Exception("exception"))
        pipeline_manager._update_defaults_from_env(config)
        mock_logger.debug.assert_called_once_with("ENV variable exception is not set, element will use its default value for property key2")
        assert "default" not in config_return["key2"]

    def test_update_defaults_from_env__negatives(self,pipeline_manager,mocker):
        config = {"key_config":"value_config"}
        config_return = {"key1": "value1","key2":{"default":{"key3":"value"},"type": "dict"}}
        mock_get_config = mocker.patch('src.server.pipeline_manager.Pipeline.get_config_section',return_value = config_return)
        mocker.patch.object(os, 'environ', {"default_value":"env_value_set"})
        mock__get_typed_value = mocker.patch.object(pipeline_manager,'_get_typed_value',side_effect = Exception("exception"))
        pipeline_manager._update_defaults_from_env(config)
        mock_get_config.assert_called_once_with(config, ["parameters", "properties"])
        assert config_return == {"key1": "value1","key2":{"default":{"key3":"value"},"type": "dict"}}

    def test_set_section_defaults(self,pipeline_manager,mocker):
        config_mock = {"key":"value"}
        request = {"param":"param_value","properties":{"prop":{"key1":"value"}}}
        request_section = ["properties","prop"]
        config_section = ["prop"]
        section = {"key1": "value"}
        config = {"key1":"value1","key2":{"default":"default_value"}}
        mock_get_section_and_config = mocker.patch('src.server.pipeline_manager.Pipeline.get_section_and_config',return_value = (section,config))
        pipeline_manager.set_section_defaults(request,config_mock,request_section,config_section)
        assert section == {"key1": "value","key2":"default_value"}
        mock_get_section_and_config.assert_called_once_with(request,config_mock,request_section,config_section)

    def test_set_defaults(self,pipeline_manager,mocker):
        request = {"prop":"value","destination":{"type":"object"},"source":{"type":"object1"}}
        config = {"model":"model1"}
        mock_schema = mocker.patch('src.server.pipeline_manager.schema')
        mock_schema.destination = {"metadata":{"dest_key1":"dest_value1"},"frame":"frame_value"}
        mock_schema.source = {"application":{"app_key1":"app_value1"},"uri":"uri_value"}
        mock_schema.tags = {"filter":{"filter_key1":"filter_value1"},"type":"object"}
        mock_set_section_defaults = mocker.patch.object(pipeline_manager,'set_section_defaults')
        pipeline_manager.set_defaults(request,config)
        mock_set_section_defaults.assert_any_call(request,config,["parameters"],["parameters", "properties"])
        mock_set_section_defaults.assert_any_call(request,config,["destination", "metadata"],["destination", "metadata","object","properties"])
        mock_set_section_defaults.assert_any_call(request,config,["source"],["source","object1","properties"])
        mock_set_section_defaults.assert_any_call(request,config,["tags"],["tags", "properties"])

    @pytest.mark.parametrize(
    "request_input, is_valid, error_expected, is_input_call,pip_exists",
    [
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [True], "Invalid Pipeline or Version", 0,False),
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [False], "Invalid Parameters", 1,True),
        ({"prop":"value","destination":{"metadata":"value"},"source":{"type":"object1"}}, [True,True], "Invalid Destination", 2,True),
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [True,True,False], "Invalid Source", 3,True),
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [True,True,True,False], "Invalid Tags", 4,True)
    ])
    def test_create_instance_negatives(self,pipeline_manager,mocker,request_input,is_valid,error_expected,is_input_call,pip_exists):
        request_original = request_input
        pipeline_manager.pipelines = {"pipeline1":{"v1":{"type":"GStreamer","prop":"value","destination":{"defauls":"value_default"}}}}
        mock_pipeline_exists = mocker.patch.object(pipeline_manager,'pipeline_exists',return_value = pip_exists)
        mock_is_input_valid = mocker.patch.object(pipeline_manager,'is_input_valid',side_effect = is_valid)
        mock_options = MagicMock()
        result, error = pipeline_manager.create_instance("pipeline1","v1",request_original,mock_options)
        assert result == None
        assert error == error_expected
        assert mock_is_input_valid.call_count == is_input_call
        mock_pipeline_exists.assert_called_once()

    def test_create_instance(self,pipeline_manager,mocker):
        request_original = {"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}
        mock_pipeline_exists = mocker.patch.object(pipeline_manager,'pipeline_exists',return_value = True)
        mock_is_input_valid = mocker.patch.object(pipeline_manager,'is_input_valid',return_value = True)
        mock_set_defaults = mocker.patch.object(pipeline_manager,'set_defaults')
        mock_start = mocker.patch.object(pipeline_manager,'_start')
        pipeline_manager.pipelines = {"pipeline1":{"v1":{"type":"GStreamer","prop":"value","destination":{"defauls":"value_default"}}}}
        mock_uuid = mocker.patch('src.server.pipeline_manager.uuid',return_value = MagicMock())
        mock_uuid.uuid1.return_value.hex = "instance_id1"
        mock_gstreamer = MagicMock()
        pipeline_manager.pipeline_types = {"GStreamer" : mock_gstreamer}
        mock_options = MagicMock()
        result_id, error = pipeline_manager.create_instance("pipeline1","v1",request_original,mock_options)
        assert result_id == "instance_id1"
        assert error is None
        mock_pipeline_exists.assert_called_once_with("pipeline1","v1")
        # mock_set_defaults.assert_any_call({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, {"type":"GStreamer","prop":"value","destination":{"defauls":"value_default"}})
        mock_set_defaults.assert_called_once()

    @pytest.mark.parametrize(
    "request_input, is_valid, error_expected, is_input_call,pip_exists",
    [
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [True], "Invalid Pipeline or Version", 0,False),
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [False], "Invalid Parameters", 1,True),
        ({"prop":"value","destination":{"metadata":"value"},"source":{"type":"object1"}}, [True,True], "Invalid Destination", 2,True),
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [True,True,False], "Invalid Source", 3,True),
        ({"prop":"value","destination":{"metadata":{"type":"object"}},"source":{"type":"object1"}}, [True,True,True,False], "Invalid Tags", 4,True)
    ])
    def test_create_instance_negatives(self,pipeline_manager,mocker,request_input,is_valid,error_expected,is_input_call,pip_exists):
        request_original = request_input
        pipeline_manager.pipelines = {"pipeline1":{"v1":{"type":"GStreamer","prop":"value","destination":{"defauls":"value_default"}}}}
        mock_pipeline_exists = mocker.patch.object(pipeline_manager,'pipeline_exists',return_value = pip_exists)
        mock_is_input_valid = mocker.patch.object(pipeline_manager,'is_input_valid',side_effect = is_valid)
        mock_options = MagicMock()
        result, error = pipeline_manager.create_instance("pipeline1","v1",request_original,mock_options)
        assert result == None
        assert error == error_expected
        assert mock_is_input_valid.call_count == is_input_call
        mock_pipeline_exists.assert_called_once()

    def test_load_pipelines(self, pipeline_manager_for_load_pipelines, mocker):
        mock_import_pipeline_types = mocker.patch.object(pipeline_manager_for_load_pipelines,'_import_pipeline_types',return_value = {"GStreamer" : MagicMock()})
        mock_import_pipeline_types = mocker.patch.object(pipeline_manager_for_load_pipelines,'warn_if_mounted')
        mock_validate_config = mocker.patch.object(pipeline_manager_for_load_pipelines,'_validate_config')
        mock_update_env = mocker.patch.object(pipeline_manager_for_load_pipelines,'_update_defaults_from_env')
        pipeline_manager_for_load_pipelines.pipeline_dir = "user_pipeline"
        mocker.patch('os.walk', return_value=[('user_pipeline', ['pallet'], []),('pipeline2', ['v1'], []),('pallet', [], ['config.json'])])
        mocker.patch('os.path.abspath', side_effect=lambda x: x)
        mocker.patch('os.path.dirname', side_effect=lambda x: {
            'user_pipeline': "",
            'pallet': "user_pipeline",
            'config.json': "pallet"
        }[x])
        mocker.patch('builtins.open', mocker.mock_open(read_data='{"type": "GStreamer", "description": "Test Pipeline"}'))
        mocker.patch('json.load', return_value={"type": "GStreamer", "description": "Test Pipeline","template":["value1","value2"]})
        success = pipeline_manager_for_load_pipelines._load_pipelines()
        assert success
        assert pipeline_manager_for_load_pipelines.pipeline_dir in  pipeline_manager_for_load_pipelines.pipelines
        assert pipeline_manager_for_load_pipelines.pipelines == {"pipeline2":{"v1":{}},"user_pipeline":{"pallet":{"type": "GStreamer", "description": "Test Pipeline","template":"value1value2",'name': 'user_pipeline', 'version': 'pallet'}}}
        mock_import_pipeline_types.assert_called_once()
        mock_validate_config.assert_called_once()
        mock_update_env.assert_called_once()

    def test_load_pipelines_delete(self, pipeline_manager_for_load_pipelines, mocker):
        mock_import_pipeline_types = mocker.patch.object(pipeline_manager_for_load_pipelines,'_import_pipeline_types',return_value = {"GStreamer" : MagicMock()})
        mock_import_pipeline_types = mocker.patch.object(pipeline_manager_for_load_pipelines,'warn_if_mounted')
        mock_validate_config = mocker.patch.object(pipeline_manager_for_load_pipelines,'_validate_config')
        mock_update_env = mocker.patch.object(pipeline_manager_for_load_pipelines,'_update_defaults_from_env',side_effect = Exception("Error in updating env"))
        pipeline_manager_for_load_pipelines.pipeline_dir = "user_pipeline"
        mocker.patch('os.walk', return_value=[('user_pipeline', ['pallet'], []),('pallet', [], ['config.json'])])
        mocker.patch('os.path.abspath', side_effect=lambda x: x)
        mocker.patch('os.path.dirname', side_effect=lambda x: {
            'user_pipeline': "",
            'pallet': "user_pipeline",
            'config.json': "pallet"
        }[x])
        mocker.patch('builtins.open', mocker.mock_open(read_data='{"type": "GStreamer", "description": "Test Pipeline"}'))
        mocker.patch('json.load', return_value={"type": "GStreamer", "description": "Test Pipeline","template":["value1","value2"]})
        success = pipeline_manager_for_load_pipelines._load_pipelines()
        assert success is False
        assert pipeline_manager_for_load_pipelines.pipelines == {}
        mocker.patch.object(pipeline_manager_for_load_pipelines,'_update_defaults_from_env')
        mocker.patch('json.load', return_value={"type": "na", "description": "Test Pipeline","template":["value1","value2"]})
        success = pipeline_manager_for_load_pipelines._load_pipelines()
        assert success is False
        assert pipeline_manager_for_load_pipelines.pipelines == {}
        mocker.patch('json.load', return_value={"type": "GStreamer"})
        success = pipeline_manager_for_load_pipelines._load_pipelines()
        assert success is False
        assert pipeline_manager_for_load_pipelines.pipelines == {}
