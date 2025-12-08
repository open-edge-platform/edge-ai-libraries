#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import copy
import json
import os
import string
import time
from threading import Lock, Thread
from collections import namedtuple

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
# pylint: disable=wrong-import-position
from gi.repository import GLib, Gst, GstApp
from src.server.app_destination import AppDestination
from src.server.app_source import AppSource
from src.server.common.utils import logging
from src.server.pipeline import Pipeline
from src.server.rtsp.gstreamer_rtsp_destination import GStreamerRtspDestination
from src.server.rtsp.gstreamer_rtsp_server import GStreamerRtspServer
from src.server.webrtc.gstreamer_webrtc_destination import GStreamerWebRTCDestination
from src.server.webrtc.gstreamer_webrtc_manager import GStreamerWebRTCManager
# pylint: enable=wrong-import-position

class GStreamerPipeline(Pipeline):
    Gst.init(None)
    GVA_INFERENCE_ELEMENT_TYPES = ["GstGvaDetect",
                                   "GstGvaClassify",
                                   "GstGvaInference",
                                   "GstGvaActionRecognitionBin",
                                   "GvaAudioDetect",
                                   "GvaDetectBin",
                                   "GvaClassifyBin",
                                   "GvaInferenceBin",
                                   "GvaActionRecognitionBin"]
    GVA_ELEMENT_ENUM_TYPES = ["GstGVAMetaPublishFileFormat",
                              "InferenceRegionType",
                              "GstGVAMetaconvertFormatType",
                              "GstGVAMetaPublishMethod",
                              "GstGVAActionRecognitionBinBackend",
                              "GvaInferenceBinRegion",
                              "GvaVideoToTensorBackend"]
    G_PARAM_WRITABLE_FLAG = 2

    SOURCE_ALIAS = "auto_source"
    GST_ELEMENTS_WITH_SOURCE_SETUP = ("GstURISourceBin")
    GST_ELEMENTS_THAT_EMIT_SOURCE = ("GstGvaMetaConvert")

    _inference_element_cache = {}
    _mainloop = None
    _mainloop_thread = None
    _rtsp_server = None
    _webrtc_manager = None
    CachedElement = namedtuple("CachedElement", ["element", "pipelines"])

    @staticmethod
    def gobject_mainloop():
        GStreamerPipeline._mainloop = GLib.MainLoop.new(None, False)
        try:
            GStreamerPipeline._mainloop.run()
        except (KeyboardInterrupt, SystemExit):
            pass

    def __init__(self, identifier, config, model_manager, request, finished_callback, options):
        # TODO: refactor as abstract interface
        # pylint: disable=super-init-not-called
        self.config = config
        self.identifier = identifier
        self.pipeline = None
        self.template = config['template']
        self.model_manager = model_manager
        self.request = request
        self._auto_source = None
        self._unset_properties = []
        self.state = Pipeline.State.QUEUED
        self.frame_count = 0
        self.start_time = None
        self.stop_time = None
        self._avg_fps = 0
        self._gst_launch_string = None
        self.latency_times = dict()
        self.sum_pipeline_latency = 0
        self.count_pipeline_latency = 0
        self._real_base = None
        self._stream_base = None
        self._year_base = None
        self._month_base = None
        self._day_base = None
        self._dir_name = None
        self._bus_connection_id = None
        self._create_delete_lock = Lock()
        self._finished_callback = finished_callback
        self._bus_messages = False
        self.appsrc_element = None
        self._app_source = None
        self.appsink_element = None
        self._app_destinations = []
        self._cached_element_keys = []
        self._logger = logging.get_logger('GSTPipeline', is_static=True)
        self.rtsp_path = None
        self._debug_message = ""
        self._options = options
        self._connection_retries = 0
        self._current_retry_delay = 1000  # 1000ms initial delay


        if (not GStreamerPipeline._mainloop):
            GStreamerPipeline._mainloop_thread = Thread(
                target=GStreamerPipeline.gobject_mainloop)
            GStreamerPipeline._mainloop_thread.daemon = True
            GStreamerPipeline._mainloop_thread.start()
        if options:
            if (options.enable_rtsp and not GStreamerPipeline._rtsp_server):
                GStreamerPipeline._rtsp_server = GStreamerRtspServer(options.rtsp_port)
                GStreamerPipeline._rtsp_server.start()
            if (options.enable_webrtc and not GStreamerPipeline._webrtc_manager):
                GStreamerPipeline._webrtc_manager = GStreamerWebRTCManager(options.webrtc_signaling_server)
        self.rtsp_server = GStreamerPipeline._rtsp_server
        self.webrtc_manager = GStreamerPipeline._webrtc_manager

    @staticmethod
    def mainloop_quit():
        if (GStreamerPipeline._rtsp_server):
            GStreamerPipeline._rtsp_server.stop()
            # Explicit delete frees GstreamerRtspServer resources.
            # Avoids hang or segmentation fault on pipeline_server.stop()
            del GStreamerPipeline._rtsp_server
            GStreamerPipeline._rtsp_server = None
        if (GStreamerPipeline._webrtc_manager):
            GStreamerPipeline._webrtc_manager.stop()
            GStreamerPipeline._webrtc_manager = None
        if (GStreamerPipeline._mainloop):
            GStreamerPipeline._mainloop.quit()
            GStreamerPipeline._mainloop = None
        if (GStreamerPipeline._mainloop_thread):
            GStreamerPipeline._mainloop_thread = None

    def _verify_and_set_frame_destinations(self):
        destination = self.request.get("destination", {})
        frame_destination_dict = {}
        frame_destination = destination.get("frame", {})
        if isinstance(frame_destination, list):
            for type in frame_destination:
                if type["type"] == "rtsp":
                    frame_destination_dict["rtsp"] = type
                if type["type"] == "webrtc":
                    frame_destination_dict["webrtc"] = type
        if isinstance(frame_destination, dict) and frame_destination != {}:
            frame_destination_dict[frame_destination["type"]] = frame_destination
        if "rtsp" in frame_destination_dict:
            rtsp_destination = frame_destination_dict["rtsp"]
            if (not self.appsink_element) or (not self.rtsp_server):
                raise Exception("Unsupported Frame Destination: RTSP Server isn't enabled")
            self.rtsp_path = rtsp_destination["path"]
            if not self.rtsp_path.startswith('/'):
                self.rtsp_path = "/" + self.rtsp_path
            self.rtsp_server.check_if_path_exists(self.rtsp_path)
            rtsp_destination["class"] = GStreamerRtspDestination.__name__
            rtsp_app_destination = AppDestination.create_app_destination(rtsp_destination, self, "frame")
            if not rtsp_app_destination:
                raise Exception("Unsupported Frame Destination: {}".format(
                    rtsp_destination["class"]))
            self._app_destinations.append(rtsp_app_destination)
        if "webrtc" in frame_destination_dict:
            webrtc_destination = frame_destination_dict["webrtc"]
            self._logger.info("Request assigned webrtc frame destination {dest}".format(
                dest=json.dumps(webrtc_destination)))
            if (not self.appsink_element):
                raise Exception("Pipeline does not support Frame Destination")
            webrtc_destination["class"] = GStreamerWebRTCDestination.__name__
            webrtc_app_destination = AppDestination.create_app_destination(webrtc_destination, self, "frame")
            if not webrtc_app_destination:
                raise Exception("Unsupported Frame Destination: {}".format(webrtc_destination["class"]))
            self._app_destinations.append(webrtc_app_destination)

    def _delete_pipeline(self, new_state):
        self._cal_avg_fps()
        self.state = new_state
        self.stop_time = time.time()
        self._logger.debug("Setting Pipeline {id}"
                           " State to {next_state}".format(id=self.identifier,
                                                           next_state=new_state.name))
        if self.pipeline:
            bus = self.pipeline.get_bus()
            if self._bus_connection_id:
                bus.remove_signal_watch()
                bus.disconnect(self._bus_connection_id)
                self._bus_connection_id = None
            self.pipeline.set_state(Gst.State.NULL)
            del self.pipeline
            self.pipeline = None

        if self._app_source:
            self._app_source.finish()
            del self._app_source
            self._app_source = None

        for destination in self._app_destinations:
            destination.finish()

        if self.appsrc_element:
            del self.appsrc_element
            self.appsrc_element = None

        if self.appsink_element:
            del self.appsink_element
            self.appsink_element = None

        self._app_destinations.clear()

        if (new_state == Pipeline.State.ERROR):
            for key in self._cached_element_keys:
                for pipeline in GStreamerPipeline._inference_element_cache[key].pipelines:
                    if (self != pipeline):
                        pipeline.stop()
                del GStreamerPipeline._inference_element_cache[key]

        self._finished_callback()

    def _delete_pipeline_with_lock(self, new_state):
        with(self._create_delete_lock):
            self._delete_pipeline(new_state)

    def stop(self):
        with(self._create_delete_lock):
            if not self.state.stopped():
                if (self.pipeline):
                    structure = Gst.Structure.new_empty(self.state.name)
                    message = Gst.Message.new_custom(
                        Gst.MessageType.APPLICATION, None, structure)
                    self.pipeline.get_bus().post(message)
                else:
                    self.state = Pipeline.State.ABORTED
        return self.status()

    def params(self):
        request = copy.deepcopy(self.request)
        if "models" in request:
            del request["models"]
        if not self._options.emit_source_and_destination:
            self._logger.debug("Not emitting source or destination."\
                "Launch server with --emit-source-and-destination if desired.")
            if "source" in request:
                del request["source"]
            if "destination" in request:
                del request["destination"]
        params_obj = {
            "id": self.identifier,
            "request": request,
            "type": self.config["type"],
            "launch_command": self._gst_launch_string
        }

        return params_obj

    def status(self):
        self._logger.debug("Called Status")
        if self.start_time is not None:
            if self.stop_time is not None:
                elapsed_time = max(0, self.stop_time - self.start_time)
            else:
                elapsed_time = max(0, time.time() - self.start_time)
        else:
            elapsed_time = None

        message = ""
        messages = self._debug_message.splitlines()
        if len(messages):
            messages.pop(0)
            message = ''.join(messages)
        status_obj = {
            "id": self.identifier,
            "state": self.state,
            "avg_fps": self.get_avg_fps(),
            "start_time": self.start_time,
            "elapsed_time": elapsed_time,
            "message": message
        }
        if self.count_pipeline_latency != 0:
            status_obj["avg_pipeline_latency"] = self.sum_pipeline_latency / \
                self.count_pipeline_latency

        return status_obj

    def get_avg_fps(self):
        self._cal_avg_fps()
        return self._avg_fps

    def _cal_avg_fps(self):
        if not self.state.stopped() and self.start_time is not None:
            self._avg_fps = self.frame_count / (time.time() - self.start_time)

    def _get_element_property(self, element, key):
        if isinstance(element, str):
            return (element, key, None)
        if isinstance(element, dict):
            return (element["name"], element.get("property", None), element.get("format", None))
        return None

    def _set_bus_messages_flag(self):
        request_parameters, config_parameters = Pipeline.get_section_and_config(
            self.request, self.config, ["parameters"],
            ["parameters", "properties"])
        bus_msgs = "bus-messages"
        if bus_msgs in config_parameters and bus_msgs in request_parameters and \
           isinstance(request_parameters[bus_msgs], bool):
            self._bus_messages = request_parameters[bus_msgs]

    def _set_section_properties(self, request_section, config_section):
        # TODO: refactor
        # pylint: disable=too-many-nested-blocks
        request, config = Pipeline.get_section_and_config(
            self.request, self.config, request_section, config_section)

        for key in config:
            if isinstance(config[key], dict) and "element" in config[key]:
                if key in request:
                    if isinstance(config[key]["element"], list):
                        element_properties = [self._get_element_property(
                            x, key) for x in config[key]["element"]]
                    else:
                        element_properties = [self._get_element_property(
                            config[key]["element"], key)]
                    for element_name, property_name, format_type in element_properties:
                        element = self.pipeline.get_by_name(element_name)
                        if not element:
                            self._logger.debug("Parameter {} given for element {} but no element found".format(
                                property_name, element_name))
                            continue

                        if format_type == "element-properties":
                            for property_name, property_value in request[key].items():
                                self._set_element_property(
                                    element, property_name, property_value, format_type)
                        else:
                            self._set_element_property(
                                element, property_name, request[key], format_type)

    def _set_element_property(self, element, property_name, property_value, format_type=None):
        if (property_name in [x.name for x in element.list_properties()]):
            if property_name == "source" and element.__gtype__.name in self.GST_ELEMENTS_THAT_EMIT_SOURCE:
                if not self._options.emit_source_and_destination:
                    self._logger.debug(
                        "Not emitting source or destination. "\
                        "Launch server with --emit-source-and-destination if desired.")
                    return
            if (format_type == "json"):
                element.set_property(
                    property_name, json.dumps(property_value))
            else:
                element.set_property(
                    property_name, property_value)
            self._logger.debug("Setting element: {}, property: {}, value: {}".format(
                element.__gtype__.name,
                property_name,
                element.get_property(property_name)))
        else:
            self._logger.debug("Parameter {} given for element {}"
                                 " but no property found".format(
                                     property_name, element.__gtype__.name))
            self._unset_properties.append([element.__gtype__.name, property_name, property_value])

    def _cache_inference_elements(self):
        model_instance_id = "model-instance-id"
        gva_elements = [(element, element.__gtype__.name + '_'
                         + element.get_property(model_instance_id))
                        for element in self.pipeline.iterate_elements()
                        if (element.__gtype__.name in self.GVA_INFERENCE_ELEMENT_TYPES
                            and model_instance_id in [x.name for x in element.list_properties()]
                            and element.get_property(model_instance_id))]
        for element, key in gva_elements:
            if key not in GStreamerPipeline._inference_element_cache:
                GStreamerPipeline._inference_element_cache[key] = GStreamerPipeline.CachedElement(
                    element, [])
            self._cached_element_keys.append(key)
            GStreamerPipeline._inference_element_cache[key].pipelines.append(self)

    def _set_default_models(self):
        model_device_pairing = [("model", "device"),
                                ("enc-model", "enc-device"),
                                ("dec-model", "dec-device")]

        for model_name, device_name in model_device_pairing:
            gva_elements = [element for element in self.pipeline.iterate_elements() if (
                element.__gtype__.name in self.GVA_INFERENCE_ELEMENT_TYPES and
                element.find_property(model_name) and
                "VA_DEVICE_DEFAULT" in element.get_property(model_name))]

            for element in gva_elements:
                network = self.model_manager.get_default_network_for_device(
                    element.get_property(device_name), element.get_property(model_name))
                self._logger.debug("Setting {} to {} for element {}".format(
                    model_name, network, element.get_name()))
                element.set_property(model_name, network)

    @staticmethod
    def _get_elements_by_type(pipeline, type_strings):
        return [element for element in pipeline.iterate_elements()
                if element.__gtype__.name in type_strings]

    def _set_model_property(self, property_name):
        gva_elements = [element for element in self.pipeline.iterate_elements() if (
            element.__gtype__.name in self.GVA_INFERENCE_ELEMENT_TYPES)]
        for element in gva_elements:
            if element.find_property(property_name) and not element.get_property(property_name):
                if element.get_property("model") in self.model_manager.model_properties[property_name]:
                    property_value = self.model_manager.model_properties[property_name][element.get_property("model")]
                    if property_value is None:
                        continue
                    self._logger.debug("Setting {} to {} for element {}".format(
                        property_name, property_value, element.get_name()))
                    element.set_property(property_name, property_value)

    @staticmethod
    def validate_config(config, request):
        # Create a copy of the config to be used for default values
        # Subsititute the values inside config with default_request
        template = string.Formatter().vformat(                  \
                                            config["template"], \
                                            [],                 \
                                            request             \
                                            )
        field_names = [fname for _, fname, _, _ in string.Formatter().parse(template)]
        if GStreamerPipeline.SOURCE_ALIAS in field_names:
            template = template.replace("{"+ GStreamerPipeline.SOURCE_ALIAS +"}", "fakesrc")
        pipeline = Gst.parse_launch(template)
        logger = logging.get_logger('GSTPipeline', is_static=True)
        logger.info("Validating pipeline elements of type {} and {}".format(GstApp.AppSrc.__gtype__.name,
                                                                            GstApp.AppSink.__gtype__.name))
        appsink_elements = GStreamerPipeline._get_elements_by_type(pipeline, [GstApp.AppSink.__gtype__.name])
        metaconvert = pipeline.get_by_name("metaconvert")
        metapublish = pipeline.get_by_name("destination")
        appsrc_elements = GStreamerPipeline._get_elements_by_type(pipeline, [GstApp.AppSrc.__gtype__.name])
        if (len(appsrc_elements) > 1):
            logger.warning("Multiple appsrc elements found")
        if len(appsink_elements) != 1:
            logger.warning("Missing or multiple appsink elements")
        if metaconvert is None:
            logger.warning("Missing metaconvert element")
        if metapublish is None:
            logger.warning("Missing metapublish element")

    def calculate_times(self, sample):
        buffer = sample.get_buffer()
        segment = sample.get_segment()
        times = {}
        times['segment.time'] = segment.time
        times['stream_time'] = segment.to_stream_time(
            Gst.Format.TIME, buffer.pts)
        return times

    def format_location_callback(self,
                                 unused_element,
                                 unused_fragement_id,
                                 sample,
                                 unused_data=None):

        times = self.calculate_times(sample)

        if (self._real_base is None):
            clock = Gst.SystemClock(clock_type=Gst.ClockType.REALTIME)
            self._real_base = clock.get_time()
            self._stream_base = times["segment.time"]
            metaconvert = self.pipeline.get_by_name("metaconvert")

            if metaconvert:
                if ("tags" not in self.request):
                    self.request["tags"] = {}
                self.request["tags"]["real_base"] = self._real_base
                metaconvert.set_property(
                    "tags", json.dumps(self.request["tags"]))

        adjusted_time = self._real_base + \
            (times["stream_time"] - self._stream_base)
        self._year_base = time.strftime(
            "%Y", time.localtime(adjusted_time / 1000000000))
        self._month_base = time.strftime(
            "%m", time.localtime(adjusted_time / 1000000000))
        self._day_base = time.strftime(
            "%d", time.localtime(adjusted_time / 1000000000))
        template = "{prefix}/{yearbase}/{monthbase}/{daybase}"
        self._dir_name = template.format(prefix=self.request["parameters"]["recording_prefix"],
                                         yearbase=self._year_base,
                                         monthbase=self._month_base, daybase=self._day_base)

        try:
            os.makedirs(self._dir_name)
        except FileExistsError:
            self._logger.debug("Directory already exists")

        template = "{dirname}/{adjustedtime}_{time}.mp4"
        return template.format(dirname=self._dir_name,
                               adjustedtime=adjusted_time,
                               time=times["stream_time"] - self._stream_base)

    def _set_properties(self):
        self._set_section_properties(["parameters"],
                                     ["parameters", "properties"])
        self._set_section_properties(["destination", "metadata"],
                                     ["destination", "properties"])
        if "destination" in self.request and \
                "metadata" in self.request["destination"] and \
                    "type" in self.request["destination"]["metadata"]:
            self._set_section_properties(["destination", "metadata"],
                                         ["destination", "metadata",
                                          self.request["destination"]["metadata"]["type"],
                                          "properties"])
        self._set_section_properties(["source"],
                                     ["source", "properties"])

        if "source" in self.request and "type" in self.request["source"]:
            self._set_section_properties(["source"],
                                         ["source", self.request["source"]["type"], "properties"])
        self._set_section_properties([], [])

    def _set_auto_source(self):
        element = self.request["source"].get("element")
        capsfilter = self.request["source"].get("capsfilter", None)
        postproc = self.request["source"].get("postproc", None)

        source = "{} name=source".format(element)
        if capsfilter:
            source = "{} ! capsfilter caps={}".format(source, capsfilter)
        if postproc:
            source = "{} ! {}".format(source, postproc)

        self._auto_source = source

    def _get_any_source(self):
        src = self.pipeline.get_by_name("source")
        if (not src):
            for src in self.pipeline.iterate_sources():
                break
        return src

    def _set_model_instance_id(self):
        model_instance_id = "model-instance-id"
        gva_elements = [element for element in self.pipeline.iterate_elements()
                        if (element.__gtype__.name in self.GVA_INFERENCE_ELEMENT_TYPES)
                        and model_instance_id in [x.name for x in element.list_properties()]
                        and not element.get_property(model_instance_id)]
        for element in gva_elements:
            name = element.get_property("name")
            instance_id = name + "_" + str(self.identifier)
            element.set_property(model_instance_id, instance_id)

    def _set_source_and_sink(self):
        src = self._get_any_source()
        if self._auto_source and src.__gtype__.name in self.GST_ELEMENTS_WITH_SOURCE_SETUP:
            src.connect("source_setup", self.source_setup_callback, src)
        sink = self.pipeline.get_by_name("appsink")
        if (not sink):
            sink = self.pipeline.get_by_name("sink")
        if src and sink:
            src_pad = src.get_static_pad("src")
            if (src_pad):
                src_pad.add_probe(Gst.PadProbeType.BUFFER,
                                    GStreamerPipeline.source_probe_callback, self)
            else:
                src.connect(
                    "pad-added", GStreamerPipeline.source_pad_added_callback, self)
            sink_pad = sink.get_static_pad("sink")
            sink_pad.add_probe(Gst.PadProbeType.BUFFER,
                                GStreamerPipeline.appsink_probe_callback, self)

    def start(self):
        if self.model_manager:
            self.request["models"] = self.model_manager.models
        field_names = [fname for _, fname, _, _ in string.Formatter().parse(self.template)]
        if self.SOURCE_ALIAS in field_names:
            self._set_auto_source()
            self.request[self.SOURCE_ALIAS] = self._auto_source
        self._gst_launch_string = string.Formatter().vformat(
            self.template, [], self.request)

        with(self._create_delete_lock):
            if (self.start_time is not None):
                return

            self._logger.debug("Starting Pipeline {id}".format(id=self.identifier))
            self._logger.debug("Pipeline template (excludes request parameters): {template}".
                format(template=self._gst_launch_string))

            try:
                self.pipeline = Gst.parse_launch(self._gst_launch_string)
                self._set_properties()
                self._set_bus_messages_flag()
                self._set_default_models()
                self._set_model_property("model-proc")
                self._set_model_property("labels")
                self._set_model_property("labels-file")
                self._cache_inference_elements()
                self._set_model_instance_id()
                self._set_source_and_sink()

                bus = self.pipeline.get_bus()
                bus.add_signal_watch()
                self._bus_connection_id = bus.connect("message", self.bus_call)
                splitmuxsink = self.pipeline.get_by_name("splitmuxsink")
                self._real_base = None

                if (not splitmuxsink is None):
                    splitmuxsink.connect("format-location-full",
                                         self.format_location_callback,
                                         None)

                self._set_application_source()
                self._set_application_destination()
                self._log_launch_string()

                if "prepare-pads" in self.config:
                    self.config["prepare-pads"](self.pipeline)

                self.pipeline.set_state(Gst.State.PLAYING)
                self.start_time = time.time()
            except Exception as error:
                self._logger.error("Error on Pipeline {id}: {err}".format(
                    id=self.identifier, err=error))
                # Context is already within _create_delete_lock
                self._delete_pipeline(Pipeline.State.ERROR)

    def _log_launch_string(self):
        if not self._gst_launch_string or not logging.is_debug_level(self._logger):
            return
        try:
            elements = [value.strip()
                        for value in self._gst_launch_string.split("!")]
            for idx, element_str in enumerate(elements):
                element_name = element_str.split(" ")[0]
                properties_str = self._get_element_properties_string(
                    element_name)
                if properties_str:
                    elements[idx] = "{} {}".format(
                        element_name, properties_str)

            self._logger.debug(
                "Gst launch string is only for debugging purposes, may not be accurate")
            self._logger.debug(
                "gst-launch-1.0 {}".format(" ! ".join(elements)))
        except Exception as error:
            self._logger.debug("Unable to log Gst launch string {id}: {err}".format(
                id=self.identifier, err=error))

    def _get_element_properties_string(self, element_name, add_defaults=False):
        properties_str = ""
        for element in self.pipeline.iterate_elements():
            if element_name in element.__gtype__.name.lower():
                for paramspec in element.list_properties():
                    # Skipping adding of caps and params that aren't writable and not readable
                    if paramspec.name in ['caps', 'parent', 'name'] or paramspec.flags == 225 \
                        or paramspec.flags == GStreamerPipeline.G_PARAM_WRITABLE_FLAG:
                        continue
                    if add_defaults or paramspec.default_value != element.get_property(paramspec.name):
                        property_value = element.get_property(
                            paramspec.name)
                        if element.find_property(paramspec.name).value_type.name \
                                in self.GVA_ELEMENT_ENUM_TYPES:
                            property_value = property_value.value_nick
                        properties_str = "{} {}={}".format(
                            properties_str, paramspec.name, property_value)
                break

        return properties_str

    def _set_application_destination(self):
        self.appsink_element = None

        app_sink_elements = GStreamerPipeline._get_elements_by_type(self.pipeline, [GstApp.AppSink.__gtype__.name])
        if (app_sink_elements):
            self.appsink_element = app_sink_elements[0]

        self._verify_and_set_frame_destinations()

        destination = self.request.get("destination", None)
        if destination and "metadata" in destination and destination["metadata"]["type"] == "application":
            app_destination = AppDestination.create_app_destination(
                self.request, self, "metadata")
            if ((not app_destination) or (not self.appsink_element)
                    or (not self.appsink_element.name == "destination")):
                raise Exception("Unsupported Metadata application Destination: {}".format(
                    destination["metadata"]["class"]))
            self._app_destinations.append(app_destination)

        if self.appsink_element is not None:
            self.appsink_element.set_property("emit-signals", True)

            if not self._app_destinations:
                self.appsink_element.connect("new-sample", self.on_sample)
            else:
                self.appsink_element.connect("new-sample", self.on_sample_app_destination)


    def on_need_data_app_source(self, src, _):
        try:
            self._app_source.start_frames()
        except Exception as error:
            self._logger.error("Error on Pipeline {id}: Error in App Source: {err}".format(
                id=self.identifier, err=error))
            src.post_message(Gst.Message.new_error(src, GLib.GError(),
                                                   "AppSource: {}".format(str(error))))

    def on_enough_data_app_source(self, src):
        try:
            self._app_source.pause_frames()
        except Exception as error:
            self._logger.error("Error on Pipeline {id}: Error in App Source: {err}".format(
                id=self.identifier, err=error))
            src.post_message(Gst.Message.new_error(src, GLib.GError(),
                                                   "AppSource: {}".format(str(error))))

    def _set_application_source(self):
        self._app_source = None
        self.appsrc_element = None

        if self.request["source"]["type"] == "application":

            appsrc_element = self.pipeline.get_by_name("source")

            if (appsrc_element) and (appsrc_element.__gtype__.name == GstApp.AppSrc.__gtype__.name):
                self.appsrc_element = appsrc_element

            self._app_source = AppSource.create_app_source(self.request, self)

            if (not self._app_source) or (not self.appsrc_element):
                raise Exception("Unsupported Application Source: {}".format(
                    self.request["source"]["class"]))

            self.appsrc_element.set_property("format", Gst.Format.TIME)
            self.appsrc_element.set_property("block", True)
            self.appsrc_element.set_property("do-timestamp", True)
            self.appsrc_element.set_property("is-live", True)
            self.appsrc_element.set_property("emit-signals", True)
            self.appsrc_element.connect('need-data', self.on_need_data_app_source)
            self.appsrc_element.connect('enough-data', self.on_enough_data_app_source)

    @staticmethod
    def source_pad_added_callback(unused_element, pad, self):
        pad.add_probe(Gst.PadProbeType.BUFFER,
                      GStreamerPipeline.source_probe_callback, self)
        return Gst.FlowReturn.OK

    @staticmethod
    def source_probe_callback(unused_pad, info, self):
        buffer = info.get_buffer()
        pts = buffer.pts
        self.latency_times[pts] = time.time()
        return Gst.PadProbeReturn.OK

    def source_setup_callback(self, unused_bin, src_element, unused_udata):
        for (element_name, property_name, property_value) in self._unset_properties:
            if element_name in self.GST_ELEMENTS_WITH_SOURCE_SETUP:
                self._set_element_property(src_element, property_name, property_value, None)

    @staticmethod
    def appsink_probe_callback(unused_pad, info, self):
        buffer = info.get_buffer()
        pts = buffer.pts
        source_time = self.latency_times.pop(pts, -1)
        if source_time != -1:
            self.sum_pipeline_latency += time.time() - source_time
            self.count_pipeline_latency += 1
        return Gst.PadProbeReturn.OK

    def on_sample_app_destination(self, sink):
        self._logger.debug("Received Sample from Pipeline {id}".format(
            id=self.identifier))
        sample = sink.emit("pull-sample")

        try:
            for destination in self._app_destinations:
                destination.process_frame(sample)
        except Exception as error:
            self._logger.error("Error on Pipeline {id}: Error in App Destination: {err}".format(
                id=self.identifier, err=error))
            return Gst.FlowReturn.ERROR

        self.frame_count += 1
        return Gst.FlowReturn.OK

    def on_sample(self, sink):
        _ = sink.emit("pull-sample")

        self.frame_count += 1
        return Gst.FlowReturn.OK

    def bus_call(self, unused_bus, message, unused_data=None):
        message_type = message.type
        if message_type == Gst.MessageType.APPLICATION:
            self._logger.info("Pipeline {id} Aborted".format(id=self.identifier))
            self._delete_pipeline_with_lock(Pipeline.State.ABORTED)
        if message_type == Gst.MessageType.EOS:
            self._logger.info("Pipeline {id} Ended".format(id=self.identifier))
            self._delete_pipeline_with_lock(Pipeline.State.COMPLETED)
        elif message_type == Gst.MessageType.ERROR:
            error_message, self._debug_message = message.parse_error()
            # Skip error handling if already in recovery state
            if self.state in (Pipeline.State.RECONNECTING, Pipeline.State.BACKOFF_WAIT):
                self._logger.warning(
                    "Error on Pipeline {id} (during recovery): {err}".format(
                        id=self.identifier,
                        err=error_message))
                return True
            self._logger.error(
                "Error on Pipeline {id}: {err}: {debug}".format(id=self.identifier,
                                                                err=error_message,
                                                                debug=self._debug_message))
            # Attempt to recover from connection errors
            if self._handle_source_error(error_message, self._debug_message):
                return True  # Recovery initiated, don't terminate yet
            self._delete_pipeline_with_lock(Pipeline.State.ERROR)
        elif message_type == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, unused_pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                if old_state == Gst.State.PAUSED and new_state == Gst.State.PLAYING:
                    if self.state is Pipeline.State.ABORTED:
                        self._delete_pipeline_with_lock(Pipeline.State.ABORTED)
                    if self.state is Pipeline.State.QUEUED:
                        self._logger.info(
                            "Setting Pipeline {id} State to RUNNING".format(id=self.identifier))
                        self.state = Pipeline.State.RUNNING
                        self.start_time = time.time()
        else:
            if self._bus_messages:
                structure = Gst.Message.get_structure(message)
                if structure:
                    self._logger.info("Message header: {name} , Message: {message}".format(
                        name=Gst.Structure.get_name(structure),
                        message=Gst.Structure.to_string(structure)))
        return True

    def _handle_source_error(self, error_message, debug_message):
        # Handle RTSP source connection errors with automatic recovery
        error_str = str(error_message).lower()
        debug_str = str(debug_message).lower() if debug_message else ""

        recoverable_keywords = ["connection", "rtsp", "timeout", "connect", "failed to connect"]
        is_source_error = any(kw in error_str for kw in recoverable_keywords) or \
                          any(kw in debug_str for kw in recoverable_keywords)

        if not is_source_error:
            return False

        max_retries = 5
        if self._connection_retries >= max_retries:
            self._logger.error(f"Pipeline {self.identifier}: Max retries ({max_retries}) exhausted")
            return False

        # Attempt recovery
        self._connection_retries += 1
        self._logger.warning(
            f"Pipeline {self.identifier}: Connection error (recoverable). "
            f"Retry {self._connection_retries}/{max_retries} after {self._current_retry_delay}ms"
        )


        self.state = Pipeline.State.RECONNECTING

        GLib.timeout_add(self._current_retry_delay, self._scheduled_reconnection_attempt, max_retries, 1000, 1.2, 60000)

        return True  # Recovery attempted, will be handled asynchronously

    def _scheduled_reconnection_attempt(self, max_retries, initial_delay_ms, backoff_multiplier, max_delay_ms):
        """Scheduled reconnection callback - runs in main loop, not in bus handler."""
        try:
            self._logger.info(
                f"Pipeline {self.identifier}: Attempting reconnection "
                f"({self._connection_retries}/{max_retries})..."
            )

            self.state = Pipeline.State.BACKOFF_WAIT

            with self._create_delete_lock:
                # Destroy current pipeline
                if self.pipeline:
                    bus = self.pipeline.get_bus()
                    if self._bus_connection_id:
                        bus.remove_signal_watch()
                        bus.disconnect(self._bus_connection_id)
                        self._bus_connection_id = None
                    self.pipeline.set_state(Gst.State.NULL)
                    del self.pipeline
                    self.pipeline = None

                self.frame_count = 0
                self.latency_times.clear()
                self.sum_pipeline_latency = 0
                self.count_pipeline_latency = 0

                # Rebuild the pipeline from scratch (reusing start() logic)
                gst_launch_string = string.Formatter().vformat(
                    self.template, [], self.request)

                # Create new pipeline
                self.pipeline = Gst.parse_launch(gst_launch_string)
                self._set_properties()
                self._set_bus_messages_flag()
                self._set_default_models()
                self._set_model_property("model-proc")
                self._set_model_property("labels")
                self._set_model_property("labels-file")
                self._cache_inference_elements()
                self._set_model_instance_id()
                self._set_source_and_sink()

                splitmuxsink = self.pipeline.get_by_name("splitmuxsink")
                self._real_base = None
                if splitmuxsink is not None:
                    splitmuxsink.connect("format-location-full",
                                       self.format_location_callback,
                                       None)

                self._set_application_source()
                self._set_application_destination()

                if "prepare-pads" in self.config:
                    self.config["prepare-pads"](self.pipeline)

                # Reconnect bus
                bus = self.pipeline.get_bus()
                bus.add_signal_watch()
                self._bus_connection_id = bus.connect("message", self.bus_call)

                # Set to playing state
                self.pipeline.set_state(Gst.State.PLAYING)
                self.start_time = time.time()  # Reset start time for FPS calculations

            # Reconnection successful
            self.state = Pipeline.State.RUNNING
            self._connection_retries = 0  # Reset retry counter on success
            self._current_retry_delay = 1000
            self._logger.info(f"Pipeline {self.identifier}: Reconnection successful")
            return False  # Don't reschedule

        except Exception as e:
            self._logger.error(f"Pipeline {self.identifier}: Reconnection attempt failed - {e}")

            if self._connection_retries < max_retries:
                # Calculate next delay with exponential backoff
                current_delay = min(
                    int(self._current_retry_delay * backoff_multiplier),
                    max_delay_ms
                )
                self._current_retry_delay = current_delay
                self._logger.info(
                    f"Pipeline {self.identifier}: Scheduling next retry in {current_delay}ms"
                )
                # Reschedule for next attempt
                GLib.timeout_add(current_delay, self._scheduled_reconnection_attempt, max_retries, initial_delay_ms, backoff_multiplier, max_delay_ms)
                return False  # Don't reschedule this call
            else:
                # All retries exhausted
                self._logger.error(
                    f"Pipeline {self.identifier}: All reconnection attempts exhausted ({max_retries})"
                )
                self._delete_pipeline_with_lock(Pipeline.State.ERROR)
                return False
