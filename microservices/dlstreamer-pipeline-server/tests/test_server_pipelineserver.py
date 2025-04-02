#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, patch
from src.server.pipeline_server import __PipelineServer
from collections import namedtuple, defaultdict
import time

@pytest.fixture
def mock_model_manager(mocker):
    return mocker.patch('src.server.pipeline_server.ModelManager', return_value = MagicMock())
@pytest.fixture
def pipeline_server():
    return __PipelineServer()

@pytest.fixture
def mock_pipeline_manager(mocker):
    return mocker.patch('src.server.pipeline_server.PipelineManager', return_value = MagicMock())

@pytest.fixture
def mock_pipeline_server():
    return MagicMock()

@pytest.fixture
def model_proxy(mock_pipeline_server, mock_logger):
    model = {
        "name": "model",
        "version": "v1",
        "networks": {"default": "network_details"}
    }
    return __PipelineServer.ModelProxy(mock_pipeline_server, model, mock_logger)

@pytest.fixture
def mock_logger():
    return MagicMock()

@pytest.fixture
def pipeline_proxy(mock_pipeline_server, mock_logger):
    pipeline = {
        "name": "pipeline1",
        "version": "v1"
    }
    return __PipelineServer.PipelineProxy(mock_pipeline_server, pipeline, mock_logger, instance="instance_id")

class TestPipelineServer:

    def test_init_pipeline_server(self,pipeline_server):
        assert pipeline_server.options is None
        assert pipeline_server.model_manager is None
        assert pipeline_server.pipeline_manager is None
        assert pipeline_server._stopped is True

    def test_start(self, pipeline_server,mocker,mock_model_manager,mock_pipeline_manager):
        pipeline_server._stopped = True
        options = MagicMock()
        options.log_level = "INFO"
        options.config_path = "/path/to/config"
        options.model_dir = "models"
        options.pipeline_dir = "pipelines"
        options.max_running_pipelines = 5
        options.ignore_init_errors = False
        options.network_preference - "network"
        mock_parse = mocker.patch('src.server.pipeline_server.parse_options', return_value = options)
        pipeline_server.start(options)
        mock_model_manager.assert_called_once_with("/path/to/config/models",pipeline_server.options.network_preference,pipeline_server.options.ignore_init_errors)
        mock_pipeline_manager.assert_called_once_with(pipeline_server.model_manager,"/path/to/config/pipelines",max_running_pipelines=pipeline_server.options.max_running_pipelines,ignore_init_errors=pipeline_server.options.ignore_init_errors)
        mock_parse.assert_called_once()
        assert not pipeline_server._stopped

    def test_pipeline_instances(self, pipeline_server,mocker):
        instances = pipeline_server.pipeline_instances()
        assert instances == []
        mock_instance = MagicMock()
        pipeline_server.pipeline_manager = MagicMock()
        pipeline_server.pipeline_manager.pipeline_instances = {'instance_id': mock_instance}
        mock_pipeline_proxy = mocker.patch('src.server.pipeline_server.__PipelineServer.PipelineProxy', return_value = MagicMock())
        instances = pipeline_server.pipeline_instances()
        assert len(instances) == 1
        mock_pipeline_proxy.assert_called_once()

    def test_stop(self, pipeline_server, mocker):
        pipeline_server._stopped = False
        mock_instance = MagicMock()
        mock_instance.status.return_value.state.stopped.return_value = False
        mock_instance.stop.side_effect = lambda: setattr(mock_instance.status.return_value.state, 'stopped', lambda: True)
        mock_pipeline_instances = mocker.patch('src.server.pipeline_server.__PipelineServer.pipeline_instances', return_value=[mock_instance])
        pipeline_server.pipeline_manager = MagicMock()
        pipeline_server.pipeline_manager.pipeline_instances = {'instance_id': mock_instance}
        pipeline_server.options = MagicMock()
        pipeline_server.options.framework = "gstreamer"
        mock_gstreamer_pipeline = mocker.patch('src.server.gstreamer_pipeline.GStreamerPipeline.mainloop_quit')
        pipeline_server.stop()
        mock_instance.stop.assert_called_once()
        mock_gstreamer_pipeline.assert_called_once()
        assert pipeline_server._stopped
    
    # def test_stop_sleep(self,pipeline_server,mocker):
    #     pipeline_server._stopped = False
    #     mock_instance = MagicMock()
    #     mock_pipeline_instances = mocker.patch('src.server.pipeline_server.__PipelineServer.pipeline_instances', return_value=[mock_instance])
    #     mock_status = MagicMock()
    #     mock_instance.status.return_value = mock_status
    #     mock_status.state.stopped.side_effect = [False,False,True,True]
    #     mocker.patch.object(mock_instance,'stop')
    #     mock_time_sleep = mocker.patch('time.sleep', return_value=None)
    #     pipeline_server.options = None
    #     pipeline_server.stop()
    #     mock_time_sleep.assert_called_once()

    def test_stop_gstreamer_exception(self, pipeline_server, mocker):
        pipeline_server._stopped = False
        mock_instance = MagicMock()
        mock_instance.status.return_value.state.stopped.return_value = False
        mock_instance.stop.side_effect = lambda: setattr(mock_instance.status.return_value.state, 'stopped', lambda: True)
        mock_pipeline_instances = mocker.patch('src.server.pipeline_server.__PipelineServer.pipeline_instances', return_value=[mock_instance])
        pipeline_server.pipeline_manager = MagicMock()
        pipeline_server.pipeline_manager.pipeline_instances = {'instance_id': mock_instance}
        pipeline_server.options = MagicMock()
        pipeline_server.options.framework = "gstreamer"
        exception = Exception("GStreamer error")
        mock_gstreamer_pipeline = mocker.patch('src.server.gstreamer_pipeline.GStreamerPipeline.mainloop_quit', side_effect=exception)
        mock_logger = mocker.patch.object(pipeline_server, '_logger')
        pipeline_server.stop()
        mock_instance.stop.assert_called_once()
        mock_gstreamer_pipeline.assert_called_once()
        mock_logger.warning.assert_called_once_with("Failed in quitting GStreamer main loop: %s", exception)
        assert pipeline_server._stopped
    
    def test_wait(self, pipeline_server,mocker):
        mock_instance1 = MagicMock()
        mock_pipeline_instances = mocker.patch.object(pipeline_server,'pipeline_instances', return_value=[mock_instance1])
        mock_status = MagicMock()
        mock_instance1.status.return_value = mock_status
        mock_status.state.stopped.side_effect = [False, True]
        pipeline_server.wait()
        assert mock_status.state.stopped.call_count == 2
        assert mock_instance1.status.call_count == 2

    def test_pipelines(self, pipeline_server, mocker):
        mock_pipeline_manager = MagicMock()
        pipeline_server.pipeline_manager = mock_pipeline_manager
        mock_pipeline_manager.get_loaded_pipelines.return_value = ["Pipeline1"]
        mock_pipeline_proxy = mocker.patch('src.server.pipeline_server.__PipelineServer.PipelineProxy', return_value = MagicMock())
        pipelines = pipeline_server.pipelines()
        assert len(pipelines) == 1
        mock_pipeline_proxy.assert_called_with(pipeline_server,"Pipeline1",pipeline_server._logger)

    def test_pipeline(self, pipeline_server, mocker):
        pipeline_server.pipeline_manager = MagicMock()
        pipeline_server.pipeline_manager.get_pipeline_parameters.return_value = {'name': 'pipeline'}
        mock_pipeline_proxy = mocker.patch('src.server.pipeline_server.__PipelineServer.PipelineProxy', return_value=MagicMock())

        pipeline = pipeline_server.pipeline("pipeline1", "v1")

        pipeline_server.pipeline_manager.get_pipeline_parameters.assert_called_once_with("pipeline1", "v1")
        mock_pipeline_proxy.assert_called_with(pipeline_server, {'name': 'pipeline'}, pipeline_server._logger)
        assert pipeline == mock_pipeline_proxy.return_value
        pipeline = pipeline_server.pipeline("pipeline1", 1)
        pipeline_server.pipeline_manager.get_pipeline_parameters.assert_called_with("pipeline1", '1')
        mock_pipeline_proxy.assert_called_with(pipeline_server, {'name': 'pipeline'}, pipeline_server._logger)
        assert pipeline == mock_pipeline_proxy.return_value

    def test_models(self, pipeline_server, mocker):
        pipeline_server.model_manager = MagicMock()
        pipeline_server.model_manager.get_loaded_models.return_value = ["pallet_defect"]
        mock_model_proxy = mocker.patch('src.server.pipeline_server.__PipelineServer.ModelProxy', return_value = MagicMock())
        models = pipeline_server.models()
        assert len(models) == 1
        mock_model_proxy.assert_called_once()
        models == mock_model_proxy.return_value

    def test_pipeline_instance(self, pipeline_server, mocker):
        pipeline_server._stopped = False
        pipeline_server.pipeline_manager = MagicMock()
        pipeline_server.pipeline_manager.create_instance.return_value = ("instance_id", None)
        instance, err = pipeline_server.pipeline_instance("pipeline1", "v1", {})
        assert instance == "instance_id"
        assert err is None

    def test_pipeline_instance_negative(self, pipeline_server, mocker):
        pipeline_server._stopped = True
        instance, err = pipeline_server.pipeline_instance("pipeline1", "v1", {})
        assert instance is None
        assert err == "Pipeline Server Stopped"

class TestModelProxy:
    def test_init_model_proxy(self,mock_pipeline_server,model_proxy,mock_logger):
        assert model_proxy._model == {
        "name": "model",
        "version": "v1",
        "networks": {"default": "network_details"}}
        assert model_proxy._pipeline_server == mock_pipeline_server
        assert model_proxy._logger == mock_logger

    def test_name(self, model_proxy):
        assert model_proxy.name() == "model"

    def test_version(self, model_proxy):
        assert model_proxy.version() == "v1"

    def test_networks(self, model_proxy):
        assert model_proxy.networks() == {"default": "network_details"}

class TestPipelineProxy:
    def test_name(self, pipeline_proxy):
        assert pipeline_proxy.name() == "pipeline1"

    def test_version(self, pipeline_proxy):
        assert pipeline_proxy.version() == "v1"

    def test_stop(self, pipeline_proxy, mock_pipeline_server):
        mock_pipeline_server.pipeline_manager.stop_instance.return_value = True
        assert pipeline_proxy.stop()
        mock_pipeline_server.pipeline_manager.stop_instance.assert_called_once_with("instance_id")

    @pytest.mark.parametrize(
    "initial_request, section_name, section, expected_request",
    [
        ({}, "parameters", {"key1": "value1"}, {"parameters": {"key1": "value1"}}),
        ({"parameters": {"key1": "value1"}}, "parameters", {"key1": "value2"}, {"parameters": {"key1": "value2"}}),
        ({}, "parameters", None, {"parameters": {}}),
        ({"parameters": {"key1": "value1"}}, "parameters", None, {"parameters": {"key1": "value1"}}),
    ])
    def test_set_or_update(self,pipeline_proxy, initial_request, section_name, section, expected_request):
        pipeline_proxy._set_or_update(initial_request, section_name, section)
        assert initial_request == expected_request

    @pytest.mark.parametrize(
    "instance_exists, status_result",
    [
        (True, {"state": MagicMock(stopped=MagicMock(return_value=True)), "avg_pipeline_latency": 100}),
        (True, {"state": MagicMock(stopped=MagicMock(return_value=True))}),
        (False, None)
    ])
    def test_status(self,pipeline_proxy, mock_pipeline_server, instance_exists, status_result):
        if instance_exists:
            mock_pipeline_server.pipeline_manager.get_instance_status.return_value = status_result
        else:
            pipeline_proxy._instance = None
        status = pipeline_proxy.status()
        if instance_exists:
            if 'avg_pipeline_latency' not in status_result:
                status_result['avg_pipeline_latency'] = None
            expected_named_tuple = namedtuple("PipelineStatus", sorted(status_result))
            expected_status_named_tuple = expected_named_tuple(**status_result)
            mock_pipeline_server.pipeline_manager.get_instance_status.assert_called_once_with("instance_id")
            assert status == expected_status_named_tuple
        else:
            assert status is None
    
    def test_wait_without_timeout(self,pipeline_proxy, mocker):
        mock_status = MagicMock()
        mock_status.state.stopped.side_effect = [False, False, True]
        mocker.patch.object(pipeline_proxy, 'status', return_value=mock_status)
        mock_time_sleep = mocker.patch('time.sleep', return_value=None)
        status = pipeline_proxy.wait(timeout=None)
        assert pipeline_proxy.status.call_count == 3
        assert mock_status.state.stopped.call_count == 3
        assert status == mock_status
        assert mock_time_sleep.call_count == 2

    def test_wait_with_timeout(self,pipeline_proxy, mocker):
        mock_status = MagicMock()
        mock_status.state.stopped.return_value = False
        mocker.patch.object(pipeline_proxy, 'status', return_value=mock_status)
        mock_time_sleep = mocker.patch('time.sleep', return_value=None)
        start_time = time.time()
        status = pipeline_proxy.wait(timeout=2)
        end_time = time.time()
        assert  end_time - start_time >= 2
        assert  end_time - start_time <= 3
        pipeline_proxy.status.assert_called()
        mock_status.state.stopped.assert_called()
        mock_time_sleep.assert_called()
    
    def test_start_pipeline_proxy(self,pipeline_proxy,mock_pipeline_server,mocker):
        if pipeline_proxy._instance:
            result = pipeline_proxy.start()
            assert result == pipeline_proxy._instance
        pipeline_proxy._instance = None
        mocker.patch.object(pipeline_proxy,'_set_or_update')
        mocker.patch.object(pipeline_proxy,'name', return_value = "pipeline1")
        mocker.patch.object(pipeline_proxy,'version',return_value = 'v1')
        mock_pipeline_server.pipeline_instance.return_value = ("instance_id1", None)
        result = pipeline_proxy.start(defaultdict(dict),{},{},{},{})
        assert pipeline_proxy._instance == "instance_id1"
        pipeline_proxy._set_or_update.call_count == 4

    def test_start_pipeline_proxy_failed(self,pipeline_proxy,mock_logger,mock_pipeline_server,mocker):
        pipeline_proxy._instance = None
        mocker.patch.object(pipeline_proxy,'_set_or_update')
        mocker.patch.object(pipeline_proxy,'name', return_value = "pipeline1")
        mocker.patch.object(pipeline_proxy,'version',return_value = 'v1')
        mock_pipeline_server.pipeline_instance.return_value = (None,"Error")
        mocker.patch.object(mock_logger,'error')
        pipeline_proxy.start(defaultdict(dict),{},{},{},{})
        mock_logger.error.assert_called_once_with("Error Starting Pipeline: Error")
