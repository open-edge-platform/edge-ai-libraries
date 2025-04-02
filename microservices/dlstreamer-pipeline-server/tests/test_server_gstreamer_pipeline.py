#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, patch
from src.server.gstreamer_pipeline import GStreamerPipeline
import time
import json
from gi.repository import Gst, GLib
from collections import namedtuple
import os

@pytest.fixture
def mock_model_manager():
    return MagicMock()

@pytest.fixture
def mock_finished_callback():
    return MagicMock()

@pytest.fixture
def Gst(mocker):
    return mocker.patch('src.server.gstreamer_pipeline.Gst')

@pytest.fixture
def mock_options():
    return MagicMock()

@pytest.fixture
def gstreamer_pipeline(mock_model_manager, mock_finished_callback, mock_options):
    config = {
        "template": "{auto_source} name=source",
        "type": "GStreamer"
    }
    request = {
        "source": {"type": "uri"},
        "destination": {"metadata": {"type": "file"}}
    }
    return GStreamerPipeline("test_id", config, mock_model_manager, request, mock_finished_callback, mock_options)

class TestGStreamerPipeline:

    def test_init(self, gstreamer_pipeline):
        assert gstreamer_pipeline.identifier == "test_id"
        assert gstreamer_pipeline.config["template"] == "{auto_source} name=source"
        assert gstreamer_pipeline.model_manager is not None
        assert gstreamer_pipeline.request["source"]["type"] == "uri"
        assert gstreamer_pipeline._finished_callback is not None
        assert gstreamer_pipeline._options is not None

    def test_set_application_source(self,gstreamer_pipeline,mocker):
        gstreamer_pipeline.request["source"]["type"] = "application"
        gstreamer_pipeline.pipeline = MagicMock()
        mock_appsrc_element = MagicMock()
        gstreamer_pipeline.pipeline.get_by_name.return_value = mock_appsrc_element
        mock_gtype = MagicMock()
        mock_appsrc_element.__gtype__ = mock_gtype
        mock_gst_app = mocker.patch('src.server.gstreamer_pipeline.GstApp.AppSrc')
        mock_gst_app.__gtype__ = mock_gtype
        mock_appsource = mocker.patch("src.server.app_source.AppSource.create_app_source")
        mock_appsource.return_value = MagicMock()
        gstreamer_pipeline._set_application_source()
        gstreamer_pipeline.pipeline.get_by_name.assert_called_once_with("source")
        mock_appsource.assert_called_once_with(gstreamer_pipeline.request,gstreamer_pipeline)
        assert gstreamer_pipeline.appsrc_element.set_property.call_count == 5
        assert gstreamer_pipeline.appsrc_element.connect.call_count == 2
        assert gstreamer_pipeline.appsrc_element == mock_appsrc_element

    def test_set_application_source_negative(self,gstreamer_pipeline,mocker):
        gstreamer_pipeline.request["source"]["type"] = "application"
        gstreamer_pipeline.request["source"]["class"] = "class1"
        mock_appsource = mocker.patch("src.server.app_source.AppSource.create_app_source",return_value = None)
        gstreamer_pipeline.pipeline = MagicMock()
        gstreamer_pipeline.pipeline.get_by_name.return_value = None
        with pytest.raises(Exception) as expinfo:
            gstreamer_pipeline._set_application_source()
        assert str(expinfo.value) == "Unsupported Application Source: class1"

    def test_on_enough_data_app_source(self, mocker, gstreamer_pipeline):
        mock_app_source = MagicMock()
        gstreamer_pipeline._app_source = mock_app_source
        mock_src = MagicMock()
        gstreamer_pipeline.on_enough_data_app_source(mock_src)
        mock_app_source.pause_frames.assert_called_once()

    def test_on_enough_data_app_source_exception(self, mocker, gstreamer_pipeline,Gst):
        mock_app_source = MagicMock()
        mock_app_source.pause_frames.side_effect = Exception("Test exception")
        gstreamer_pipeline._app_source = mock_app_source
        mock_src = MagicMock()
        gstreamer_pipeline.on_enough_data_app_source(mock_src)
        mock_app_source.pause_frames.assert_called_once()
        mock_src.post_message.assert_called_once()
        Gst.Message.new_error.assert_called_once()

    def test_on_need_data_app_source(self, mocker, gstreamer_pipeline):
        mock_app_source = MagicMock()
        gstreamer_pipeline._app_source = mock_app_source
        mock_src = MagicMock()
        gstreamer_pipeline.on_need_data_app_source(mock_src,"temp")
        mock_app_source.start_frames.assert_called_once()

    def test_on_need_data_app_source_exception(self, mocker, gstreamer_pipeline):
        mock_app_source = MagicMock()
        mock_app_source.start_frames.side_effect = Exception("Test exception")
        gstreamer_pipeline._app_source = mock_app_source
        mock_src = MagicMock()
        mock_gst_error = mocker.patch('src.server.gstreamer_pipeline.Gst.Message.new_error')
        gstreamer_pipeline.on_need_data_app_source(mock_src,"temp")
        mock_app_source.start_frames.assert_called_once()
        mock_src.post_message.assert_called_once()
        mock_gst_error.assert_called_once()

    @pytest.mark.parametrize(
    "request_source, expected_result",
    [
        ({"element": "test_src","capsfilter": "test_caps","postproc": "test_proc"}, "test_src name=source ! capsfilter caps=test_caps ! test_proc"),
        ({"element": "test_src","postproc": "test_proc"}, "test_src name=source ! test_proc"),
        ({"element": "test_src","capsfilter": "test_caps"}, "test_src name=source ! capsfilter caps=test_caps"),
        ({}, "None name=source")
    ])
    def test_set_auto_source(self, gstreamer_pipeline,request_source,expected_result):
        gstreamer_pipeline.request["source"] = request_source
        gstreamer_pipeline._set_auto_source()
        assert gstreamer_pipeline._auto_source == expected_result

    def test_calculate_times(self, gstreamer_pipeline,Gst):
        mock_sample = MagicMock()
        mock_buffer = MagicMock()
        mock_sample.get_buffer.return_value = mock_buffer
        mock_segment = MagicMock()
        mock_segment.time = 10
        mock_sample.get_segment.return_value = mock_segment
        mock_segment.to_stream_time.return_value = 20
        times = gstreamer_pipeline.calculate_times(mock_sample)
        expected_times = {'segment.time': 10,'stream_time': 20}
        mock_sample.get_buffer.assert_called_once()
        mock_sample.get_segment.assert_called_once()
        mock_segment.to_stream_time.assert_called_once_with(Gst.Format.TIME,mock_buffer.pts)
        assert times == expected_times

    @pytest.mark.parametrize(
    "stopped, expected_fps, start_time",
        [(False, 10, 10),
        (True, 0, 10),
        (False, 0, None)])
    def test_cal_avg_fps(self, gstreamer_pipeline, mocker,stopped,expected_fps,start_time):
        gstreamer_pipeline.state = MagicMock()
        gstreamer_pipeline.state.stopped.return_value = stopped
        mocker.patch.object(time,'time',return_value = 20)
        gstreamer_pipeline.start_time = start_time
        gstreamer_pipeline.frame_count = 100
        gstreamer_pipeline._cal_avg_fps()
        assert gstreamer_pipeline._avg_fps == expected_fps
    
    def test_get_avg_fps(self,gstreamer_pipeline,mocker):
        mocker.patch.object(gstreamer_pipeline,'_cal_avg_fps')
        avg_fps = gstreamer_pipeline.get_avg_fps()
        gstreamer_pipeline._cal_avg_fps.assert_called_once()
        assert avg_fps == 0

    def test_stop_running_pipeline(self, mocker, gstreamer_pipeline,Gst):
        gstreamer_pipeline.state = MagicMock()
        gstreamer_pipeline.state.name = "RUNNING"
        gstreamer_pipeline.state.stopped.return_value = False
        mock_status = MagicMock()
        mocker.patch.object(gstreamer_pipeline,'status',return_value = mock_status)
        mock_pipeline = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        Gst.Structure.new_empty.return_value = "Structure"
        Gst.Message.new_custom.return_value = "message"
        status = gstreamer_pipeline.stop()
        assert gstreamer_pipeline.state.stopped.call_count == 1
        Gst.Structure.new_empty.assert_called_once_with(gstreamer_pipeline.state.name)
        Gst.Message.new_custom.assert_called_once_with(Gst.MessageType.APPLICATION,None,"Structure")
        gstreamer_pipeline.pipeline.get_bus().post.assert_called_once_with("message")
        assert status == mock_status

    def test_stop_pipeline_not_running(self, gstreamer_pipeline,mocker,Gst):
        gstreamer_pipeline.state = MagicMock()
        gstreamer_pipeline.state.stopped.return_value = False
        mock_state = mocker.patch("src.server.gstreamer_pipeline.Pipeline",return_value = MagicMock())
        mock_status = MagicMock()
        mock_state.State.ABORTED = "ABORT"
        mocker.patch.object(gstreamer_pipeline,'status',return_value = mock_status)
        status = gstreamer_pipeline.stop()
        assert status == mock_status
        assert gstreamer_pipeline.state == "ABORT"
        Gst.Structure.new_empty.call_count == 0
        Gst.Message.new_custom.call_count == 0

    def test_stop_pipeline_not_running_stop(self, gstreamer_pipeline,mocker,Gst):
        gstreamer_pipeline.state = MagicMock()
        gstreamer_pipeline.state.stopped.return_value = True
        mock_status = MagicMock()
        mocker.patch.object(gstreamer_pipeline,'status',return_value = mock_status)
        status = gstreamer_pipeline.stop()
        assert status == mock_status

    @pytest.mark.parametrize(
        "input_value, expected_output",
        [
            ("name_value", ("name_value", "property", None)),
            ({"name": "name_value", "property": "property_value", "format": "json"}, ("name_value", "property_value", "json")),
            ({"name": "name_value"}, ("name_value", None, None)),
            (None, None),
        ])
    def test_get_element_property(self, gstreamer_pipeline, input_value, expected_output):
        result = gstreamer_pipeline._get_element_property(input_value, "property")
        assert result == expected_output

    @pytest.mark.parametrize(
        "mock_pipeline_return, expected_bus_messages",
        [
            (({"bus-messages": True},{"bus-messages": True}), True),
            (({"bus-messages": False},{"bus-messages": True}), False),
            (({"bus-messages": "True"},{"bus-messages": True}), False),
            (({},{"bus-messages": True}), False),
            (({},{}), False)
        ])
    def test_set_bus_messages_flag(self,gstreamer_pipeline,mocker,mock_pipeline_return,expected_bus_messages):
        mock_pipeline = mocker.patch("src.server.gstreamer_pipeline.Pipeline",return_value = MagicMock())
        mock_pipeline.get_section_and_config.return_value = mock_pipeline_return
        gstreamer_pipeline._set_bus_messages_flag()
        mock_pipeline.get_section_and_config.assert_called_once_with(gstreamer_pipeline.request,gstreamer_pipeline.config,["parameters"],["parameters", "properties"])
        assert gstreamer_pipeline._bus_messages == expected_bus_messages
    
    def test_get_elements_by_type(self, mocker, gstreamer_pipeline):
        mock_element1 = MagicMock()
        mock_element1.__gtype__ = MagicMock()
        mock_element1.__gtype__.name = 'GstElementType1'
        mock_element2 = MagicMock()
        mock_element2.__gtype__ = MagicMock()
        mock_element2.__gtype__.name = 'GstElementType2'
        mock_element3 = MagicMock()
        mock_element3.__gtype__ = MagicMock()
        mock_element3.__gtype__.name = 'GstElementType1'
        mock_pipeline = MagicMock()
        mock_pipeline.iterate_elements.return_value = [mock_element1, mock_element2, mock_element3]
        gstreamer_pipeline.pipeline = mock_pipeline
        elements = gstreamer_pipeline._get_elements_by_type(gstreamer_pipeline.pipeline, ["GstElementType1"])
        assert elements == [mock_element1,mock_element3]
        elements = gstreamer_pipeline._get_elements_by_type(gstreamer_pipeline.pipeline, ['GstElementType2'])
        assert elements == [mock_element2]
        elements = gstreamer_pipeline._get_elements_by_type(gstreamer_pipeline.pipeline, ['NA'])
        assert elements == []
        assert mock_pipeline.iterate_elements.call_count == 3

    def test_on_sample(self, mocker, gstreamer_pipeline,Gst):
        mock_sink = MagicMock()
        initial_frame = gstreamer_pipeline.frame_count
        result = gstreamer_pipeline.on_sample(mock_sink)
        mock_sink.emit.assert_called_once_with("pull-sample")
        assert gstreamer_pipeline.frame_count == initial_frame + 1
        assert result == Gst.FlowReturn.OK
    
    def test_on_sample_app_destination(self, mocker, gstreamer_pipeline, Gst):
        mock_sink = MagicMock()
        mock_sample = MagicMock()
        mock_sink.emit.return_value = mock_sample
        mock_app_destination1 = MagicMock()
        mock_app_destination2 = MagicMock()
        gstreamer_pipeline._app_destinations = [mock_app_destination1, mock_app_destination2]
        initial_frame = gstreamer_pipeline.frame_count
        result = gstreamer_pipeline.on_sample_app_destination(mock_sink)
        mock_app_destination1.process_frame.assert_called_once_with(mock_sample)
        mock_app_destination2.process_frame.assert_called_once_with(mock_sample)
        mock_sink.emit.assert_called_once_with("pull-sample")
        assert gstreamer_pipeline.frame_count == initial_frame + 1
        assert result == Gst.FlowReturn.OK

    def test_on_sample_app_destination_exception(self, mocker, gstreamer_pipeline,Gst):
        mock_sink = MagicMock()
        mock_sample = MagicMock()
        mock_sink.emit.return_value = mock_sample
        mock_app_destination = MagicMock()
        mock_app_destination.process_frame.side_effect = Exception("Test exception")
        gstreamer_pipeline._app_destinations = [mock_app_destination]
        initial_frame = gstreamer_pipeline.frame_count
        result = gstreamer_pipeline.on_sample_app_destination(mock_sink)
        mock_app_destination.process_frame.assert_called_once_with(mock_sample)
        assert gstreamer_pipeline.frame_count == initial_frame
        assert result == Gst.FlowReturn.ERROR

    @pytest.mark.parametrize(
        "pts, sum_latency, count_latency",
        [
            (1234, 20, 1),
            (123, 0, 0)
        ])
    def test_appsink_probe_callback(self, mocker,Gst,gstreamer_pipeline,pts,sum_latency,count_latency):
        mocker.patch.object(time,'time',return_value = 30)
        mock_info = MagicMock()
        mock_buffer = MagicMock()
        mock_buffer.pts = pts
        mock_info.get_buffer.return_value = mock_buffer
        gstreamer_pipeline.latency_times = {1234: 10}
        result = gstreamer_pipeline.appsink_probe_callback(None, mock_info, gstreamer_pipeline)
        mock_info.get_buffer.assert_called_once()
        assert gstreamer_pipeline.sum_pipeline_latency == sum_latency
        assert gstreamer_pipeline.count_pipeline_latency == count_latency
        assert result == Gst.PadProbeReturn.OK

    def test_source_setup_callback(self, mocker, gstreamer_pipeline):
        mock_src_element = MagicMock()
        gstreamer_pipeline._unset_properties = [
            ('GstURISourceBin', 'property1', 'value1'),
            ('GstURISourceBin', 'property2', 'value2'),
            ('Element', 'property3', 'value3')
        ]
        mock_set_element_property = mocker.patch.object(gstreamer_pipeline, '_set_element_property')
        gstreamer_pipeline.source_setup_callback(None, mock_src_element, None)
        mock_set_element_property.assert_any_call(mock_src_element, 'property1', 'value1', None)
        mock_set_element_property.assert_any_call(mock_src_element, 'property2', 'value2', None)
        assert mock_set_element_property.call_count == 2
    
    def test_source_probe_callback(self, mocker, gstreamer_pipeline,Gst):
        mock_info = MagicMock()
        mock_buffer = MagicMock()
        mock_buffer.pts = 10
        mock_info.get_buffer.return_value = mock_buffer
        mocker.patch.object(time,'time',return_value = 50)
        result = gstreamer_pipeline.source_probe_callback(None, mock_info, gstreamer_pipeline)
        assert 10 in gstreamer_pipeline.latency_times
        assert gstreamer_pipeline.latency_times[10] == 50
        assert result == Gst.PadProbeReturn.OK

    def test_source_pad_added_callback(self, mocker, gstreamer_pipeline,Gst):
        mock_pad = MagicMock()
        mock_add_probe = mocker.patch.object(mock_pad, 'add_probe')
        result = gstreamer_pipeline.source_pad_added_callback(None, mock_pad, gstreamer_pipeline)
        mock_add_probe.assert_called_once_with(Gst.PadProbeType.BUFFER, GStreamerPipeline.source_probe_callback, gstreamer_pipeline)
        assert result == Gst.FlowReturn.OK

    def test_set_source_and_sink(self, mocker, gstreamer_pipeline,Gst):
        mock_source = MagicMock()
        mock_sink = MagicMock()
        mock_source_pad = MagicMock()
        mock_sink_pad = MagicMock()
        mock_sink.get_static_pad.return_value = mock_sink_pad
        mocker.patch.object(gstreamer_pipeline,"_get_any_source",return_value = mock_source)
        gstreamer_pipeline.pipeline = MagicMock()
        gstreamer_pipeline.pipeline.get_by_name.return_value = mock_sink
        mock_source.get_static_pad.return_value = mock_source_pad
        gstreamer_pipeline._set_source_and_sink()
        gstreamer_pipeline._get_any_source.assert_called_once()
        gstreamer_pipeline.pipeline.get_by_name.assert_any_call("appsink")
        mock_source.get_static_pad.assert_any_call("src")
        mock_source_pad.add_probe.assert_any_call(Gst.PadProbeType.BUFFER,gstreamer_pipeline.source_probe_callback,gstreamer_pipeline)
        mock_sink.get_static_pad.assert_called_with("sink")
        mock_sink_pad.add_probe.assert_called_with(Gst.PadProbeType.BUFFER,gstreamer_pipeline.appsink_probe_callback,gstreamer_pipeline)

    def test_set_source_and_sink_with_src_pad_none(self, mocker, gstreamer_pipeline, Gst):
        mock_source = MagicMock()
        mock_sink = MagicMock()
        mock_sink_pad = MagicMock()
        mock_sink.get_static_pad.return_value = mock_sink_pad
        mocker.patch.object(gstreamer_pipeline, "_get_any_source", return_value=mock_source)
        gstreamer_pipeline.pipeline = MagicMock()
        gstreamer_pipeline.pipeline.get_by_name.return_value = mock_sink
        mock_source.get_static_pad.return_value = None
        gstreamer_pipeline._set_source_and_sink()
        gstreamer_pipeline._get_any_source.assert_called_once()
        gstreamer_pipeline.pipeline.get_by_name.assert_any_call("appsink")
        mock_source.get_static_pad.assert_any_call("src")
        mock_source.connect.assert_called_with("pad-added", gstreamer_pipeline.source_pad_added_callback, gstreamer_pipeline)
        mock_sink.get_static_pad.assert_called_with("sink")
        mock_sink_pad.add_probe.assert_called_with(Gst.PadProbeType.BUFFER,gstreamer_pipeline.appsink_probe_callback,gstreamer_pipeline)

    def test_set_source_and_sink_with_sink_name_sink(self, mocker, gstreamer_pipeline, Gst):
        mock_source = MagicMock()
        mock_sink = MagicMock()
        mock_sink_pad = MagicMock()
        mocker.patch.object(gstreamer_pipeline, "_get_any_source", return_value=mock_source)
        gstreamer_pipeline.pipeline = MagicMock()
        gstreamer_pipeline.pipeline.get_by_name.side_effect = lambda name: mock_sink if name == "sink" else None
        mock_source.get_static_pad.return_value = mock_sink_pad
        gstreamer_pipeline._set_source_and_sink()
        gstreamer_pipeline._get_any_source.assert_called_once()
        gstreamer_pipeline.pipeline.get_by_name.assert_any_call("sink")
        mock_source.get_static_pad.assert_any_call("src")
        mock_sink_pad.add_probe.assert_any_call(Gst.PadProbeType.BUFFER, gstreamer_pipeline.source_probe_callback, gstreamer_pipeline)

    def test_set_source_and_sink_with_auto_source_exits(self, mocker, gstreamer_pipeline, Gst):
        mock_source = MagicMock()
        mock_source.__gtype__ = MagicMock()
        mock_source.__gtype__.name = 'GstURISourceBin'
        gstreamer_pipeline._auto_source = "source"
        mocker.patch.object(gstreamer_pipeline, "_get_any_source", return_value=mock_source)
        gstreamer_pipeline.pipeline = MagicMock()
        gstreamer_pipeline.pipeline.get_by_name.return_value = None
        gstreamer_pipeline._set_source_and_sink()
        gstreamer_pipeline._get_any_source.assert_called_once()
        mock_source.connect.assert_called_with("source_setup", gstreamer_pipeline.source_setup_callback, mock_source)

    def test_set_model_instance_id(self, mocker, gstreamer_pipeline):
        mock_element1 = MagicMock()
        mock_element1.__gtype__ = MagicMock()
        mock_prop1 = MagicMock()
        mock_prop1.name = "model-instance-id"
        mock_element1.__gtype__.name = 'GstGvaDetect'
        mock_element1.list_properties.return_value = [mock_prop1]
        mock_element1.get_property.side_effect = lambda x: "model1" if x== "name" else None
        mock_element2 = MagicMock()
        mock_element2.__gtype__ = MagicMock()
        mock_prop2 = MagicMock()
        mock_prop2.name = "model-instance-id"
        mock_element2.__gtype__.name = 'GstGvaClassify'
        mock_element2.list_properties.return_value = [mock_prop2]
        mock_element2.get_property.side_effect = lambda x: "model2" if x== "name" else None
        mock_element3 = MagicMock()
        mock_element3.__gtype__ = MagicMock()
        mock_element3.__gtype__.name = 'Error'
        mock_pipeline = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.iterate_elements.return_value = [mock_element1,mock_element2,mock_element3]
        gstreamer_pipeline._set_model_instance_id()
        mock_element1.set_property.assert_any_call("model-instance-id","model1_test_id")
        mock_element2.set_property.assert_any_call("model-instance-id","model2_test_id")

    def test_get_any_source_with_src(self, gstreamer_pipeline):
        mock_source = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.get_by_name.return_value = mock_source
        gstreamer_pipeline.pipeline = mock_pipeline
        result = gstreamer_pipeline._get_any_source()
        assert result == mock_source
        mock_pipeline.get_by_name.assert_called_once_with("source")

    def test_get_any_source_with_src_none(self, gstreamer_pipeline):
        mock_source1 = MagicMock()
        mock_source2 = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.get_by_name.return_value = None
        mock_pipeline.iterate_sources.return_value = [mock_source1, mock_source2]
        gstreamer_pipeline.pipeline = mock_pipeline
        result = gstreamer_pipeline._get_any_source()
        assert result == mock_source1
        mock_pipeline.get_by_name.assert_called_once_with("source")
        mock_pipeline.iterate_sources.return_value = []
        result2 = gstreamer_pipeline._get_any_source()
        assert result2 == None

    def test_param(self, gstreamer_pipeline):
        gstreamer_pipeline.request["models"] = "model1"
        gstreamer_pipeline._gst_launch_string = "gst-launch-1.0"
        result = gstreamer_pipeline.params()
        expected_result = {
            "id": gstreamer_pipeline.identifier,
            "request": {
                "source": {"type": "uri"},
                "destination": {"metadata": {"type": "file"}}},
            "type": gstreamer_pipeline.config["type"],
            "launch_command": gstreamer_pipeline._gst_launch_string}
        assert result == expected_result

    def test_param_without_source_or_destination(self, gstreamer_pipeline):
        gstreamer_pipeline.request["models"] = "model1"
        gstreamer_pipeline._gst_launch_string = "gst-launch-1.0"
        gstreamer_pipeline._options.emit_source_and_destination = False
        result = gstreamer_pipeline.params()
        expected_result = {
            "id": gstreamer_pipeline.identifier,
            "request": {},
            "type": gstreamer_pipeline.config["type"],
            "launch_command": gstreamer_pipeline._gst_launch_string}
        assert result == expected_result

    @pytest.mark.parametrize(
    "starttime, stoptime, elapsedtime",
        [(10, None, 20),
         (10,15,5),
         (None,10,None)])
    def test_status_running_pipeline(self, mocker, gstreamer_pipeline,starttime,stoptime,elapsedtime):
        mocker.patch.object(time,'time',return_value = 30)
        gstreamer_pipeline.start_time = starttime
        gstreamer_pipeline.stop_time = stoptime
        gstreamer_pipeline._debug_message = "Debug message\nDebug"
        mock_state = MagicMock()
        gstreamer_pipeline.state = mock_state
        mocker.patch.object(gstreamer_pipeline,'get_avg_fps',return_value = 10)
        expected_status = {
            "id": "test_id",
            "state": mock_state,
            "avg_fps": 10,
            "start_time": starttime,
            "elapsed_time": elapsedtime,
            "message": "Debug"}
        result = gstreamer_pipeline.status()
        assert result == expected_status

    def test_status_with_pipeline_latency(self, mocker, gstreamer_pipeline):
        mocker.patch.object(time,'time',return_value = 30)
        gstreamer_pipeline.start_time = 15
        gstreamer_pipeline.stop_time = 10
        gstreamer_pipeline._debug_message = "Debug message\nDebug"
        mock_state = MagicMock()
        gstreamer_pipeline.state = mock_state
        mocker.patch.object(gstreamer_pipeline,'get_avg_fps',return_value = 10)
        gstreamer_pipeline.count_pipeline_latency = 2
        gstreamer_pipeline.sum_pipeline_latency = 50
        expected_status = {
            "id": "test_id",
            "state": mock_state,
            "avg_fps": 10,
            "start_time": 15,
            "elapsed_time": 0,
            "message": "Debug",
            "avg_pipeline_latency": 25}
        result = gstreamer_pipeline.status()
        assert result == expected_status

    def test_delete_pipeline_with_lock(self,gstreamer_pipeline,mocker):
        mock_state = MagicMock()
        mock_delete_pipeline = mocker.patch.object(gstreamer_pipeline,'_delete_pipeline')
        gstreamer_pipeline._delete_pipeline_with_lock(mock_state)
        mock_delete_pipeline.assert_called_with(mock_state)

    def test_log_launch_string(self, mocker, gstreamer_pipeline):
        gstreamer_pipeline._gst_launch_string = "testsrc ! sink"
        mock_logging = mocker.patch('src.server.gstreamer_pipeline.logging')
        mock_logger = MagicMock()
        gstreamer_pipeline._logger = mock_logger
        mock_get_element_prop_str = mocker.patch.object(gstreamer_pipeline,'_get_element_properties_string')
        mock_get_element_prop_str.return_value = "property_value"
        gstreamer_pipeline._log_launch_string()
        mock_get_element_prop_str.assert_called()
        mock_logger.debug.assert_any_call("Gst launch string is only for debugging purposes, may not be accurate")
        mock_logger.debug.assert_any_call("gst-launch-1.0 testsrc property_value ! sink property_value")
        mock_logging.is_debug_level.assert_called_once_with(mock_logger)

    def test_log_launch_string_exception(self, mocker, gstreamer_pipeline):
        gstreamer_pipeline._gst_launch_string = "testsrc ! sink"
        mock_logging = mocker.patch('src.server.gstreamer_pipeline.logging')
        mock_logger = MagicMock()
        gstreamer_pipeline._logger = mock_logger
        mock_get_element_prop_str = mocker.patch.object(gstreamer_pipeline,'_get_element_properties_string')
        mock_get_element_prop_str.side_effect = Exception("test no prop")
        gstreamer_pipeline._log_launch_string()
        mock_logger.debug.assert_called_once_with("Unable to log Gst launch string test_id: test no prop")
        mock_logging.is_debug_level.assert_called_once_with(mock_logger)

    def test_log_launch_string_with_none(self,gstreamer_pipeline,mocker):
        mock_logging = mocker.patch('src.server.gstreamer_pipeline.logging')
        mock_logger = MagicMock()
        gstreamer_pipeline._logger = mock_logger
        gstreamer_pipeline._log_launch_string()
        mock_logger.debug.assert_not_called()
        gstreamer_pipeline._gst_launch_string = "testsrc ! sink"
        mocker.patch.object(mock_logging,'is_debug_level',return_value = False)
        gstreamer_pipeline._log_launch_string()
        mock_logger.debug.assert_not_called()

    def test_delete_pipeline(self, mocker, gstreamer_pipeline,Gst):
        gstreamer_pipeline._cal_avg_fps = MagicMock()
        mock_state = MagicMock()
        mocker.patch.object(time,'time',return_value = 30)
        mock_pipeline = MagicMock()
        mock_bus = MagicMock()
        mock_app_destination = MagicMock()
        mock_app_source = MagicMock()
        mock_pipeline.get_bus.return_value = mock_bus
        gstreamer_pipeline.pipeline = mock_pipeline
        gstreamer_pipeline._bus_connection_id = 1
        gstreamer_pipeline._app_source = mock_app_source
        gstreamer_pipeline._app_destinations = [mock_app_destination]
        gstreamer_pipeline.appsink_element = "appsink"
        gstreamer_pipeline.appsrc_element = "appsink"
        gstreamer_pipeline._delete_pipeline(mock_state)
        gstreamer_pipeline._cal_avg_fps.assert_called_once()
        mock_pipeline.get_bus.assert_called_once()
        mock_bus.remove_signal_watch.assert_called_once()
        mock_bus.disconnect.assert_called_once_with(1)
        mock_pipeline.set_state.assert_called_once_with(Gst.State.NULL)
        mock_app_source.finish.assert_called_once()
        mock_app_destination.finish.assert_called_once()
        gstreamer_pipeline._finished_callback.assert_called_once()
        assert gstreamer_pipeline.pipeline is None
        assert gstreamer_pipeline._app_source is None
        assert gstreamer_pipeline.appsrc_element is None
        assert gstreamer_pipeline.appsink_element is None
        assert gstreamer_pipeline._bus_connection_id is None
        assert gstreamer_pipeline._app_destinations == []

    def test_delete_pipeline_with_error_state(self, mocker, gstreamer_pipeline):
        gstreamer_pipeline._cal_avg_fps = MagicMock()
        mock_pipeline = MagicMock()
        mock_stop_pipeline = MagicMock()
        mock_state = mocker.patch('src.server.gstreamer_pipeline.Pipeline.State',return_value = MagicMock())
        gstreamer_pipeline._cached_element_keys = ['key1']
        GStreamerPipeline._inference_element_cache = {'key1':mock_pipeline}
        mock_pipeline.pipelines = [mock_stop_pipeline]
        gstreamer_pipeline._delete_pipeline(mock_state.ERROR)
        gstreamer_pipeline._cal_avg_fps.assert_called_once()
        mock_stop_pipeline.stop.assert_called_once()
        assert gstreamer_pipeline.pipeline is None
        assert gstreamer_pipeline._app_source is None
        assert gstreamer_pipeline.appsrc_element is None
        assert gstreamer_pipeline.appsink_element is None
        assert gstreamer_pipeline._bus_connection_id is None
        assert gstreamer_pipeline._app_destinations == []
        gstreamer_pipeline._finished_callback.assert_called_once()

    def test_verify_and_set_frame_destinations_rtsp(self, mocker, gstreamer_pipeline):
        gstreamer_pipeline.request["destination"]["frame"] = {"type":"rtsp","path":"rtsppath"}
        mock_app_sink_element = MagicMock()
        gstreamer_pipeline.appsink_element = mock_app_sink_element
        gstreamer_pipeline.rtsp_server = MagicMock()
        mock_rtsp_dest_class = mocker.patch('src.server.gstreamer_pipeline.GStreamerRtspDestination')
        mock_rtsp_dest_class.__name__ = MagicMock(return_value = "Class_rtsp")
        mock_rtsp_destination = MagicMock()
        mock_create_app_destination = mocker.patch('src.server.gstreamer_pipeline.AppDestination.create_app_destination', return_value=mock_rtsp_destination)
        gstreamer_pipeline._verify_and_set_frame_destinations()
        gstreamer_pipeline.rtsp_server.check_if_path_exists.assert_called_once_with("/rtsppath")
        mock_create_app_destination.assert_called_once_with({"type":"rtsp","path":"rtsppath", 'class':mock_rtsp_dest_class.__name__},gstreamer_pipeline,"frame")
        assert gstreamer_pipeline._app_destinations == [mock_rtsp_destination]

    def test_verify_and_set_frame_destinations_webrtc(self, mocker, gstreamer_pipeline):
        mock_app_sink_element = MagicMock()
        gstreamer_pipeline.appsink_element = mock_app_sink_element
        gstreamer_pipeline.request["destination"]["frame"] = {"type":"webrtc","path":"webrtcpath"}
        mock_webrtc_dest_class = mocker.patch('src.server.gstreamer_pipeline.GStreamerWebRTCDestination')
        mock_webrtc_dest_class.__name__ = MagicMock(return_value = "Class_webrtc")
        mock_webrtc_destination = MagicMock()
        mock_create_app_destination = mocker.patch('src.server.gstreamer_pipeline.AppDestination.create_app_destination', return_value=mock_webrtc_destination)
        gstreamer_pipeline._verify_and_set_frame_destinations()
        mock_create_app_destination.assert_called_once_with({"type":"webrtc","path":"webrtcpath", 'class':mock_webrtc_dest_class.__name__},gstreamer_pipeline,"frame")
        assert gstreamer_pipeline._app_destinations == [mock_webrtc_destination]

    def test_verify_and_set_frame_destinations_webrtc_exception(self,gstreamer_pipeline,mocker):
        gstreamer_pipeline._verify_and_set_frame_destinations()
        assert gstreamer_pipeline._app_destinations == []
        gstreamer_pipeline.appsink_element = None
        gstreamer_pipeline.request["destination"]["frame"] = {"type":"webrtc","path":"webrtcpath"}
        with pytest.raises(Exception, match="Pipeline does not support Frame Destination"):
            gstreamer_pipeline._verify_and_set_frame_destinations()
        mock_app_sink_element = MagicMock()
        gstreamer_pipeline.appsink_element = mock_app_sink_element
        mock_webrtc_dest_class = mocker.patch('src.server.gstreamer_pipeline.GStreamerWebRTCDestination',return_value = MagicMock())
        mock_webrtc_dest_class.__name__ = "Class_webrtc"
        mock_create_app_destination = mocker.patch('src.server.gstreamer_pipeline.AppDestination.create_app_destination', return_value=None)
        with pytest.raises(Exception, match="Unsupported Frame Destination: Class_webrtc"):
            gstreamer_pipeline._verify_and_set_frame_destinations()
        mock_create_app_destination.assert_called_once_with({"type":"webrtc","path":"webrtcpath", "class": "Class_webrtc"},gstreamer_pipeline,"frame")
    def test_verify_and_set_frame_destinations_rtsp_exception(self, mocker, gstreamer_pipeline):
        gstreamer_pipeline.request["destination"]["frame"] = {"type":"rtsp","path":"rtsppath"}
        with pytest.raises(Exception, match="Unsupported Frame Destination: RTSP Server isn't enabled"):
            gstreamer_pipeline._verify_and_set_frame_destinations()
        mock_app_sink_element = MagicMock()
        gstreamer_pipeline.appsink_element = mock_app_sink_element
        gstreamer_pipeline.rtsp_server = None
        with pytest.raises(Exception, match="Unsupported Frame Destination: RTSP Server isn't enabled"):
            gstreamer_pipeline._verify_and_set_frame_destinations()
        gstreamer_pipeline.rtsp_server = MagicMock()
        mock_rtsp_dest_class = mocker.patch('src.server.gstreamer_pipeline.GStreamerRtspDestination',return_value = MagicMock())
        mock_rtsp_dest_class.__name__ = "Class_rtsp"
        mock_create_app_destination = mocker.patch('src.server.gstreamer_pipeline.AppDestination.create_app_destination', return_value=None)
        with pytest.raises(Exception, match="Unsupported Frame Destination: Class_rtsp"):
            gstreamer_pipeline._verify_and_set_frame_destinations()
        mock_create_app_destination.assert_called_once_with({"type":"rtsp","path":"rtsppath", "class": "Class_rtsp"},gstreamer_pipeline,"frame")

    def test_cache_inference_elements(self, mocker, gstreamer_pipeline):
        mock_prop1 = MagicMock()
        mock_prop1.name = "model-instance-id"
        mock_element1 = MagicMock()
        mock_element1.__gtype__ = MagicMock()
        mock_element1.__gtype__.name = 'GstGvaDetect'
        mock_element1.list_properties.return_value = [mock_prop1]
        mock_element1.get_property.return_value = "model1"
        mock_element2 = MagicMock()
        mock_element2.__gtype__ = MagicMock()
        mock_prop2 = MagicMock()
        mock_prop2.name = "model-instance-id"
        mock_element2.__gtype__.name = 'GstGvaClassify'
        mock_element2.list_properties.return_value = [mock_prop2]
        mock_element2.get_property.return_value = "model2"
        mock_element3 = MagicMock()
        mock_element3.__gtype__ = MagicMock()
        mock_element3.__gtype__.name = 'Error'
        mock_pipeline = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.iterate_elements.return_value = [mock_element1,mock_element2,mock_element3]
        Cache = namedtuple("CachedElement", ["element", "pipelines"])
        mocker.patch.object(GStreamerPipeline,'CachedElement',side_effect= Cache)
        gstreamer_pipeline._cache_inference_elements()
        assert gstreamer_pipeline._inference_element_cache == {'GstGvaDetect_model1':Cache(mock_element1,[gstreamer_pipeline]),'GstGvaClassify_model2': Cache(mock_element2,[gstreamer_pipeline])}
        assert gstreamer_pipeline._cached_element_keys == ['GstGvaDetect_model1','GstGvaClassify_model2']

    def test_bus_call(self, mocker, gstreamer_pipeline,Gst):
        # Testcase for Gst.MessageType.APPLICATION, Gst.MessageType.EOS and Gst.MessageType.ERROR
        mock_bus = MagicMock()
        mock_message = MagicMock()
        mock_message.type = Gst.MessageType.APPLICATION
        mock_delete_pipeline_with_lock = mocker.patch.object(gstreamer_pipeline, '_delete_pipeline_with_lock')
        mock_state = mocker.patch('src.server.gstreamer_pipeline.Pipeline.State',return_value = MagicMock())
        gstreamer_pipeline.bus_call(mock_bus, mock_message)
        mock_delete_pipeline_with_lock.assert_called_once_with(mock_state.ABORTED)
        mock_message.type = Gst.MessageType.EOS
        gstreamer_pipeline.bus_call(mock_bus, mock_message)
        mock_delete_pipeline_with_lock.assert_any_call(mock_state.COMPLETED)
        mock_message.type = Gst.MessageType.ERROR
        mock_message.parse_error.return_value = ("ERROR","Debug")
        gstreamer_pipeline.bus_call(mock_bus, mock_message)
        mock_delete_pipeline_with_lock.assert_any_call(mock_state.ERROR)
        mock_message.parse_error.assert_called_once()

    def test_bus_call_state_changed(self, mocker, gstreamer_pipeline,Gst):
        mock_bus = MagicMock()
        mock_message = MagicMock()
        mock_state = mocker.patch('src.server.gstreamer_pipeline.Pipeline.State',return_value = MagicMock())
        mock_message.type = Gst.MessageType.STATE_CHANGED
        gstreamer_pipeline.pipeline = mock_message.src
        mock_message.parse_state_changed.return_value = (Gst.State.PAUSED,Gst.State.PLAYING,MagicMock())
        gstreamer_pipeline.state = mock_state.ABORTED
        mock_delete_pipeline_with_lock = mocker.patch.object(gstreamer_pipeline, '_delete_pipeline_with_lock')
        result = gstreamer_pipeline.bus_call(mock_bus, mock_message)
        assert result is True
        gstreamer_pipeline._delete_pipeline_with_lock.assert_any_call(mock_state.ABORTED)
        gstreamer_pipeline.state = mock_state.QUEUED
        mocker.patch.object(time,'time',return_value = 10)
        result = gstreamer_pipeline.bus_call(mock_bus, mock_message)
        assert result is True
        assert gstreamer_pipeline.state == mock_state.RUNNING
        assert gstreamer_pipeline.start_time == 10

    def test_bus_call_message_type_none(self, mocker, gstreamer_pipeline,Gst):
        gstreamer_pipeline._bus_messages = True
        mock_bus = MagicMock()
        mock_message = MagicMock()
        mock_logger = MagicMock()
        mock_structure = MagicMock()
        gstreamer_pipeline._logger = mock_logger
        Gst.Message.get_structure.return_value = mock_structure
        Gst.Structure.get_name.return_value = "Bus_name"
        Gst.Structure.to_string.return_value = "Message"
        result = gstreamer_pipeline.bus_call(mock_bus, mock_message)
        assert result is True
        Gst.Message.get_structure.assert_called_once_with(mock_message)
        Gst.Structure.get_name.assert_called_once_with(mock_structure)
        Gst.Structure.to_string.assert_called_once_with(mock_structure)
        mock_logger.info.assert_called_once_with("Message header: Bus_name , Message: Message")
    
    def test_start(self, mocker, gstreamer_pipeline,Gst):
        gstreamer_pipeline.config["prepare-pads"] = MagicMock()
        gstreamer_pipeline.model_manager.models = {"model1":"details"}
        mock_auto_source = mocker.patch.object(gstreamer_pipeline,'_set_auto_source',side_effect=lambda: setattr(gstreamer_pipeline, '_auto_source', "filesrc"))
        mock_pipeline = MagicMock()
        mock_bus = MagicMock()
        mock_splitmuxsink = MagicMock()
        Gst.parse_launch.return_value = mock_pipeline
        mock_pipeline.get_bus.return_value = mock_bus
        mock_set_properties = mocker.patch.object(gstreamer_pipeline, '_set_properties')
        mock_set_bus_messages_flag = mocker.patch.object(gstreamer_pipeline, '_set_bus_messages_flag')
        mock_set_default_models = mocker.patch.object(gstreamer_pipeline, '_set_default_models')
        mock_set_model_property = mocker.patch.object(gstreamer_pipeline, '_set_model_property')
        mock_cache_inference_elements = mocker.patch.object(gstreamer_pipeline, '_cache_inference_elements')
        mock_set_model_instance_id = mocker.patch.object(gstreamer_pipeline, '_set_model_instance_id')
        mock_set_source_and_sink = mocker.patch.object(gstreamer_pipeline, '_set_source_and_sink')
        mock_set_application_source = mocker.patch.object(gstreamer_pipeline, '_set_application_source')
        mock_set_application_destination = mocker.patch.object(gstreamer_pipeline, '_set_application_destination')
        mock_log_launch_string = mocker.patch.object(gstreamer_pipeline, '_log_launch_string')
        mock_bus_call = mocker.patch.object(gstreamer_pipeline, 'bus_call')
        mock_format_location = mocker.patch.object(gstreamer_pipeline, 'format_location_callback')
        mock_pipeline.get_by_name.return_value = mock_splitmuxsink
        gstreamer_pipeline.start()
        assert gstreamer_pipeline.request["models"] == {"model1":"details"}
        assert gstreamer_pipeline.request[gstreamer_pipeline.SOURCE_ALIAS] == "filesrc"
        assert gstreamer_pipeline._gst_launch_string == "filesrc name=source"
        assert gstreamer_pipeline.start_time is not None
        Gst.parse_launch.asser_called_once_with(gstreamer_pipeline._gst_launch_string)
        mock_set_properties.assert_called_once()
        mock_set_bus_messages_flag.assert_called_once()
        mock_set_default_models.assert_called_once()
        mock_cache_inference_elements.assert_called_once()
        mock_set_model_property.assert_any_call("model-proc")
        mock_set_model_property.assert_any_call("labels")
        mock_set_model_property.assert_any_call("labels-file")
        mock_set_model_instance_id.assert_called_once()
        mock_set_source_and_sink.assert_called_once()
        mock_pipeline.get_bus.assert_called_once()
        mock_bus.add_signal_watch.assert_called_once_with()
        mock_auto_source.assert_called_once()
        mock_bus.connect.assert_called_once_with("message",mock_bus_call)
        mock_pipeline.get_by_name.assert_called_once_with("splitmuxsink")
        mock_splitmuxsink.connect.assert_called_once_with("format-location-full",mock_format_location,None)
        mock_set_application_source.assert_called_once()
        mock_set_application_destination.assert_called_once()
        mock_log_launch_string.assert_called_once()
        mock_pipeline.set_state.assert_called_once_with(Gst.State.PLAYING)
        gstreamer_pipeline.config["prepare-pads"].assert_called_once_with(gstreamer_pipeline.pipeline)

    def test_start_exception(self, mocker, gstreamer_pipeline,Gst):
        gstreamer_pipeline.start_time = 10
        gstreamer_pipeline.model_manager.models = {"model1":"details"}
        mock_auto_source = mocker.patch.object(gstreamer_pipeline,'_set_auto_source',side_effect=lambda: setattr(gstreamer_pipeline, '_auto_source', "filesrc"))
        result = gstreamer_pipeline.start()
        result is None
        gstreamer_pipeline.start_time = None
        mock_state = mocker.patch('src.server.gstreamer_pipeline.Pipeline.State',return_value = MagicMock())
        mock_gst_parse_launch = mocker.patch.object(Gst,'parse_launch',side_effect = Exception("Error in parsing"))
        mock_delete_pipeline = mocker.patch.object(gstreamer_pipeline, '_delete_pipeline')
        gstreamer_pipeline.start()
        mock_gst_parse_launch.assert_called_once()
        mock_delete_pipeline.assert_called_once_with(mock_state.ERROR)

    def test_set_application_destination(self,gstreamer_pipeline,mocker):
        mock_appsink_element = MagicMock()
        mock_app_destination = MagicMock()
        mock_appsink_element.name = "destination"
        mock_get_ele_type = mocker.patch('src.server.gstreamer_pipeline.GStreamerPipeline._get_elements_by_type',return_value = [mock_appsink_element])
        mock_create_app_dest = mocker.patch('src.server.gstreamer_pipeline.AppDestination.create_app_destination',return_value = mock_app_destination)
        mock_verify = mocker.patch.object(gstreamer_pipeline,'_verify_and_set_frame_destinations')
        gstreamer_pipeline.request["destination"]["metadata"]["type"] = "application"
        gstreamer_pipeline._set_application_destination()
        mock_get_ele_type.assert_called_once()
        mock_verify.assert_called_once()
        mock_create_app_dest.assert_called_once_with(gstreamer_pipeline.request,gstreamer_pipeline,"metadata")
        mock_appsink_element.set_property.assert_any_call("emit-signals", True)
        mock_appsink_element.set_property.assert_any_call("sync", False)
        mock_appsink_element.connect.assert_called_once_with("new-sample",gstreamer_pipeline.on_sample_app_destination)
        gstreamer_pipeline.request["destination"]["metadata"]["class"] = "app_class"
        mock_appsink_element.name = ""
        gstreamer_pipeline.appsink_element = None
        with pytest.raises(Exception, match="Unsupported Metadata application Destination: app_class"):
            gstreamer_pipeline._set_application_destination()

    def test_set_application_destination_no_destination(self,gstreamer_pipeline,mocker):
        mock_appsink_element = MagicMock()
        mock_get_ele_type = mocker.patch('src.server.gstreamer_pipeline.GStreamerPipeline._get_elements_by_type',return_value = [mock_appsink_element])
        mock_verify = mocker.patch.object(gstreamer_pipeline,'_verify_and_set_frame_destinations')
        gstreamer_pipeline._set_application_destination()
        mock_appsink_element.set_property.assert_any_call("emit-signals", True)
        mock_appsink_element.set_property.assert_any_call("sync", False)
        mock_appsink_element.connect.assert_any_call("new-sample",gstreamer_pipeline.on_sample)
        mock_verify.assert_called_once()
        mock_get_ele_type.assert_called_once()

    def test_set_default_models(self,gstreamer_pipeline,mocker):
        mock_element1 = MagicMock()
        mock_element1.__gtype__ = MagicMock()
        mock_element1.__gtype__.name = 'GstGvaDetect'
        mock_element1.find_property.return_value = False
        mock_element1.get_property.side_effect = lambda x: ["VA_DEVICE_DEFAULT"] if x=="model" or x =="device" else None
        mock_element2 = MagicMock()
        mock_element2.__gtype__ = MagicMock()
        mock_element2.__gtype__.name = 'GstGvaClassify'
        mock_element2.find_property.return_value = True
        mock_element2.get_property.side_effect = lambda x: ["VA_DEVICE_DEFAULT"] if x=="model" or x =="device" else []
        mock_element3 = MagicMock()
        mock_element3.__gtype__ = MagicMock()
        mock_element3.__gtype__.name = 'Error'
        mock_pipeline = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.iterate_elements.return_value = [mock_element1,mock_element2,mock_element3]
        mock_network = MagicMock()
        mock_get_default_network = mocker.patch.object(gstreamer_pipeline.model_manager,'get_default_network_for_device',return_value = mock_network)
        gstreamer_pipeline._set_default_models()
        assert mock_pipeline.iterate_elements.call_count == 3
        assert mock_element1.find_property.call_count == 3
        assert mock_element2.find_property.call_count == 3
        assert mock_element3.find_property.call_count == 0
        assert mock_element1.get_property.call_count == 0
        assert mock_element2.get_property.call_count == 5
        assert mock_element3.get_property.call_count == 0
        mock_get_default_network.assert_called_once_with(mock_element2.get_property("model"),mock_element2.get_property("device"))
        mock_element2.set_property.assert_called_once_with("model",mock_network)

    def test_set_model_property(self,gstreamer_pipeline,mocker):
        mock_element1 = MagicMock()
        mock_element1.__gtype__ = MagicMock()
        mock_element1.__gtype__.name = 'GstGvaDetect'
        mock_element1.find_property.return_value = True
        mock_element1.get_property.side_effect = lambda  x: "property" if x=="model" else None
        mock_element2 = MagicMock()
        mock_element2.__gtype__ = MagicMock()
        mock_element2.__gtype__.name = 'GstGvaClassify'
        mock_element2.find_property.return_value = True
        mock_element2.get_property.side_effect = lambda  x: "property" if x=="model" else None
        mock_element3 = MagicMock()
        mock_element3.__gtype__ = MagicMock()
        mock_element3.__gtype__.name = 'Error'
        mock_pipeline = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.iterate_elements.return_value = [mock_element1,mock_element2,mock_element3]
        gstreamer_pipeline.model_manager.model_properties = {"model-proc": {"property":None}}
        gstreamer_pipeline._set_model_property("model-proc")
        mock_pipeline.iterate_elements.assert_called_once()
        mock_element1.set_property.assert_not_called()
        gstreamer_pipeline.model_manager.model_properties = {"model-proc": {"property":"prop_value"}}
        gstreamer_pipeline._set_model_property("model-proc")
        mock_element1.set_property.assert_called_once()
        mock_element2.set_property.assert_called_once()

    def test_validate_config(self, gstreamer_pipeline, Gst,mocker):
        config = {"template": "{auto_source} name=source"}
        request = {
        "source": {"type": "uri"},
        "destination": {"metadata": {"type": "file"}},
        "auto_source": "filesrc"}
        mock_pipeline = MagicMock()
        mock_pipeline.get_by_name.return_value = None
        Gst.parse_launch.return_value = mock_pipeline
        mock_logging = mocker.patch('src.server.gstreamer_pipeline.logging')
        mock_logger = mock_logging.get_logger.return_value
        mock_get_element_type = mocker.patch.object(GStreamerPipeline,'_get_elements_by_type',return_value = [MagicMock(),MagicMock()])
        GStreamerPipeline.validate_config(config,request)
        assert mock_get_element_type.call_count == 2
        Gst.parse_launch.assert_called_once_with("filesrc name=source")
        mock_logger.warning.assert_any_call("Multiple appsrc elements found")
        mock_logger.warning.assert_any_call("Missing or multiple appsink elements")
        mock_logger.warning.assert_any_call("Missing metapublish element")
        mock_logger.warning.assert_any_call("Missing metaconvert element")
        mock_pipeline.get_by_name.assert_any_call("metaconvert")
        mock_pipeline.get_by_name.assert_any_call("destination")

    def test_format_location_callback(self, gstreamer_pipeline,mocker,Gst):
        mock_sample = MagicMock()
        gstreamer_pipeline.request['parameters'] = {'recording_prefix':"file"}
        mock_time = mocker.patch.object(time,'strftime',return_value = 2)
        mock_calculate_times = mocker.patch.object(gstreamer_pipeline,'calculate_times',return_value = {"segment.time": 10, "stream_time": 20})
        mock_pipeline = MagicMock()
        mock_clock = MagicMock()
        Gst.SystemClock.return_value = mock_clock
        mock_clock.get_time.return_value = 15
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_meta_convert = MagicMock()
        mock_pipeline.get_by_name.return_value = mock_meta_convert
        mocker.patch.object(mock_meta_convert,'set_property')
        mockmkdir = mocker.patch.object(os,'makedirs')
        result = gstreamer_pipeline.format_location_callback(MagicMock(),2,mock_sample)
        mock_clock.get_time.assert_called_once()
        mock_calculate_times.assert_called_once()
        mock_pipeline.get_by_name.assert_called_once_with("metaconvert")
        mockmkdir.assert_called_once_with("file/2/2/2")
        assert mock_time.call_count == 3
        assert result == "file/2/2/2/25_10.mp4"
        assert gstreamer_pipeline._dir_name == "file/2/2/2"
        mockmkdir.side_effect = FileExistsError()
        mock_logger = MagicMock()
        gstreamer_pipeline._logger = mock_logger
        result = gstreamer_pipeline.format_location_callback(MagicMock(),2,mock_sample)
        mock_logger.debug.assert_called_once_with("Directory already exists")

    def test_get_element_properties_string(self,gstreamer_pipeline,mocker):
        mock_element1 = MagicMock()
        mock_element1.__gtype__ = MagicMock()
        mock_element1.__gtype__.name = 'GstClassify'
        mock_element1.get_property.return_value = "param_default"
        mock_element1.list_properties.return_value = [MagicMock(name="caps", flags=225, default = "param_default")]
        mock_element2 = MagicMock()
        mock_element2.__gtype__ = MagicMock()
        mock_prop_value = MagicMock()
        mock_prop_value.value_nick = "prop_value"
        mock_element2.__gtype__.name = 'GstGvaDetect'
        mock_element2.get_property.return_value = mock_prop_value
        mock_paramspec = MagicMock()
        mock_paramspec.name = "param_name"
        mock_element2.find_property.return_value.value_type.name = "GstGVAMetaPublishFileFormat"
        mock_element2.list_properties.return_value = [mock_paramspec]
        mock_element3 = MagicMock()
        mock_element3.__gtype__ = MagicMock()
        mock_element3.__gtype__.name = 'Error'
        mock_element1.list_properties.return_value = [MagicMock()]
        mock_pipeline = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.iterate_elements.return_value = [mock_element1,mock_element2,mock_element3]
        result = gstreamer_pipeline._get_element_properties_string("gstgvadetect")
        assert result == " param_name=prop_value"

    def test_get_element_properties_string_with_caps(self,gstreamer_pipeline,mocker):
        mock_element1 = MagicMock()
        mock_element1.__gtype__ = MagicMock()
        mock_element1.__gtype__.name = 'GstClassify'
        mock_element1.get_property.return_value = "param_default"
        mock_element1.list_properties.return_value = [MagicMock(name="caps", flags=225, default = "param_default")]
        mock_element2 = MagicMock()
        mock_element2.__gtype__ = MagicMock()
        mock_prop_value = MagicMock()
        mock_prop_value.value_nick = "prop_value"
        mock_element2.__gtype__.name = 'GstGvaDetect'
        mock_element2.get_property.return_value = mock_prop_value
        mock_paramspec = MagicMock()
        mock_paramspec.name = "caps"
        mock_element2.find_property.return_value.value_type.name = "GstGVAMetaPublishFileFormat"
        mock_element2.list_properties.return_value = [mock_paramspec]
        mock_element3 = MagicMock()
        mock_element3.__gtype__ = MagicMock()
        mock_element3.__gtype__.name = 'Error'
        mock_element1.list_properties.return_value = [MagicMock()]
        mock_pipeline = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.iterate_elements.return_value = [mock_element1,mock_element2,mock_element3]
        result = gstreamer_pipeline._get_element_properties_string("gstgvadetect")
        assert result == ""
    
    def test_set_properties(self, gstreamer_pipeline,mocker):
        mock_set_section_prop = mocker.patch.object(gstreamer_pipeline,'_set_section_properties')
        gstreamer_pipeline._set_properties()
        mock_set_section_prop.assert_any_call(["parameters"],["parameters", "properties"])
        mock_set_section_prop.assert_any_call(["destination", "metadata"],["destination", "properties"])
        mock_set_section_prop.assert_any_call(["destination", "metadata"],["destination", "metadata","file","properties"])
        mock_set_section_prop.assert_any_call(["source"],["source", "properties"])
        mock_set_section_prop.assert_any_call(["source"],["source", "uri", "properties"])
        mock_set_section_prop.assert_any_call([],[])
        assert mock_set_section_prop.call_count == 6

    def test_set_element_property(self,gstreamer_pipeline,mocker):
        mock_prop1 = MagicMock()
        mock_prop1.name = "source"
        mock_prop2 = MagicMock()
        mock_prop2.name = "mock_src"
        mock_element = MagicMock()
        mock_element.__gtype__ = MagicMock()
        mock_element.__gtype__.name = "GstGvaMetaConvert"
        mock_element.list_properties.return_value = [mock_prop1,mock_prop2]
        mock_element.get_property.return_value = "mock_property"
        mock_logger = MagicMock()
        gstreamer_pipeline._logger = mock_logger
        result = gstreamer_pipeline._set_element_property(mock_element,"mock_src",'testsrc')
        mock_element.set_property.assert_called_once_with("mock_src",'testsrc')
        mock_logger.debug.assert_called_once_with("Setting element: GstGvaMetaConvert, property: mock_src, value: mock_property")
        gstreamer_pipeline._set_element_property(mock_element,"mock_src",'testsrc',"json")
        mock_element.set_property.assert_any_call("mock_src",json.dumps("testsrc"))
        gstreamer_pipeline._options.emit_source_and_destination = None
        gstreamer_pipeline._set_element_property(mock_element,"source",'testsrc')
        mock_logger.debug.assert_any_call("Not emitting source or destination. Launch server with --emit-source-and-destination if desired.")
        gstreamer_pipeline._set_element_property(mock_element,"na",'testsrc')
        mock_logger.debug.assert_any_call("Parameter na given for element GstGvaMetaConvert but no property found")
        assert gstreamer_pipeline._unset_properties == [["GstGvaMetaConvert","na","testsrc"]]

    def test_set_section_properties(self,gstreamer_pipeline,mocker):
        mock_config = {"template": "{auto_source} name=source","type": "GStreamer","properties": {"element": "element1"}}
        mock_request = {"source": {"type": "uri"},"destination": {"metadata": {"type": "file"}},"properties": {"element": "first"}}
        mock_get_section_config = mocker.patch('src.server.gstreamer_pipeline.Pipeline.get_section_and_config',return_value = (mock_request,mock_config))
        mock_get_property = mocker.patch.object(gstreamer_pipeline,'_get_element_property',return_value = ("element_name1","property_name1","element-properties"))
        mock_set_property = mocker.patch.object(gstreamer_pipeline,'_set_element_property')
        mock_pipeline = MagicMock()
        mock_element = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.get_by_name.return_value = mock_element
        result = gstreamer_pipeline._set_section_properties(["req"],["config"])
        mock_get_section_config.assert_called_once_with(gstreamer_pipeline.request,gstreamer_pipeline.config,["req"],["config"])
        mock_get_property.assert_any_call("element1","properties")
        mock_pipeline.get_by_name.assert_any_call("element_name1")
        mock_set_property.assert_any_call(mock_element,'element','first','element-properties')
    
    def test_set_section_properties_negatives(self,gstreamer_pipeline,mocker):
        mock_config = {"template": "{auto_source} name=source","type": "GStreamer","properties": {"element": ["element1","element2"]}}
        mock_request = {"source": {"type": "uri"},"destination": {"metadata": {"type": "file"}},"properties": {"element": "first"}}
        mock_get_section_config = mocker.patch('src.server.gstreamer_pipeline.Pipeline.get_section_and_config',return_value = (mock_request,mock_config))
        mock_get_property = mocker.patch.object(gstreamer_pipeline,'_get_element_property',side_effect = [("element_name1","property_name1","format1"),("element_name2","property_name2","element-properties")])
        mock_set_property = mocker.patch.object(gstreamer_pipeline,'_set_element_property')
        mock_logger = MagicMock()
        gstreamer_pipeline._logger = mock_logger
        mock_pipeline = MagicMock()
        mock_element1 = MagicMock()
        gstreamer_pipeline.pipeline = mock_pipeline
        mock_pipeline.get_by_name.side_effect = [mock_element1,None]
        result = gstreamer_pipeline._set_section_properties(["req"],["config"])
        mock_get_section_config.assert_called_once_with(gstreamer_pipeline.request,gstreamer_pipeline.config,["req"],["config"])
        mock_get_property.assert_any_call("element1","properties")
        mock_get_property.assert_any_call("element2","properties")
        mock_pipeline.get_by_name.assert_any_call('element_name1')
        mock_set_property.assert_any_call(mock_element1,'property_name1',{"element": "first"},"format1")
        mock_pipeline.get_by_name.assert_any_call('element_name2')
        mock_logger.debug.assert_called_once_with("Parameter property_name2 given for element element_name2 but no element found")