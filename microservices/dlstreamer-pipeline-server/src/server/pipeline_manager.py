#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os
import json
import string
import traceback
from threading import Lock
from collections import deque
from collections import defaultdict
import uuid
import jsonschema
from src.server.common.utils import logging
from src.server.pipeline import Pipeline
from src.server import schema

class PipelineManager:

    def __init__(self, model_manager, pipeline_dir, max_running_pipelines,
                 ignore_init_errors=False):
        self.max_running_pipelines = max_running_pipelines
        self.model_manager = model_manager
        self.running_pipelines = 0
        self.pipeline_types = {}
        self.pipeline_instances = {}
        self.pipeline_state = {}
        self.pipelines = {}
        self.pipeline_queue = deque()
        self.pipeline_dir = pipeline_dir
        self.logger = logging.get_logger('PipelineManager', is_static=True)
        self._run_counter_lock = Lock()
        success = self._load_pipelines()
        if (not ignore_init_errors) and (not success):
            raise Exception("Error Initializing Pipelines")


    def _import_pipeline_types(self):
        pipeline_types = {}
        try:
            from src.server.gstreamer_pipeline import GStreamerPipeline  # pylint: disable=import-error
            pipeline_types['GStreamer'] = GStreamerPipeline
        except Exception as error:
            pipeline_types['GStreamer'] = None
            self.logger.info(
                "GStreamer Pipelines Not Enabled: %s\n", error)

        pipeline_types = {key: value for key,
                          value in pipeline_types.items() if value}

        return pipeline_types

    def _validate_config(self, config):
        # Create a request with Default values
        default_request = {}
        self.set_defaults(default_request, config)
        # Setup models and auto_source with default values for validation
        default_request["models"] = self.model_manager.models
        default_request["auto_source"] = "fakesrc"
        self.pipeline_types[config['type']].validate_config(config, default_request)

    def _load_pipelines(self):
        # TODO: refactor
        # pylint: disable=too-many-branches,too-many-nested-blocks,too-many-statements
        self.log_banner("Loading Pipelines")
        error_occurred = False
        self.pipeline_types = self._import_pipeline_types()
        self.logger.info("Loading Pipelines from Config Path {path}".format(
            path=self.pipeline_dir))
        self.warn_if_mounted()
        pipelines = defaultdict(dict)
        for root, subdirs, files in os.walk(self.pipeline_dir):
            if os.path.abspath(root) == os.path.abspath(self.pipeline_dir):
                for subdir in subdirs:
                    pipelines[subdir] = {}
            else:
                if len(files) == 0:
                    pipeline = os.path.basename(root)
                    pipelines[pipeline] = {}
                    for subdir in subdirs:
                        pipelines[pipeline][subdir] = {}
                else:
                    pipeline = os.path.basename(os.path.dirname(root))
                    version = os.path.basename(root)
                    for file in files:
                        path = os.path.join(root, file)
                        if path.endswith(".json"):
                            try:
                                with open(path, 'r') as jsonfile:
                                    config = json.load(jsonfile)
                                    if ('type' not in config) or ('description' not in config):
                                        del pipelines[pipeline][version]
                                        self.logger.error(
                                            "Pipeline %s"
                                            " is missing type or description", pipeline)
                                        error_occurred = True
                                        continue
                                    if "template" in config:
                                        if isinstance(config["template"], list):
                                            config["template"] = "".join(
                                                config["template"])
                                    if config['type'] in self.pipeline_types:
                                        pipelines[pipeline][version] = config
                                        config['name'] = pipeline
                                        config['version'] = version
                                        # validate_config will throw warning of
                                        # missing elements but continue execution
                                        self._validate_config(config)
                                        self.logger.info("Loading Pipeline: {} version: "
                                                         "{} type: {} from {}".format(
                                                             pipeline,
                                                             version,
                                                             config['type'],
                                                             path))
                                        self._update_defaults_from_env(pipelines[pipeline][version])
                                    else:
                                        del pipelines[pipeline][version]
                                        self.logger.error("Pipeline %s with type %s not supported",
                                                          pipeline, config['type'])
                                        error_occurred = True

                            except Exception as error:
                                if (pipeline in pipelines) and (version in pipelines[pipeline]):
                                    del pipelines[pipeline][version]
                                self.logger.error(
                                    "Failed to Load Pipeline from: {}".format(path))
                                self.logger.error(
                                    "Exception: {}".format(error))
                                self.logger.error(traceback.format_exc())
                                error_occurred = True

        # Remove pipelines with no valid versions
        pipelines = {pipeline: versions for pipeline,
                     versions in pipelines.items() if len(versions) > 0}
        self.pipelines = pipelines
        self.log_banner("Completed Loading Pipelines")
        return not error_occurred

    def _update_defaults_from_env(self, config):
        config = Pipeline.get_config_section(
            config, ["parameters", "properties"])
        for key in config:
            if "default" in config[key]:
                default_value = config[key]["default"]
                if not isinstance(default_value, str):
                    continue
                try:
                    env_value = string.Formatter().vformat(
                        default_value, [], {'env': os.environ})
                    if config[key]["type"] != "string":
                        env_value = self._get_typed_value(env_value)
                    config[key]["default"] = env_value
                    self.logger.debug(
                        "Setting {}={} using {}".format(key, env_value, default_value))
                except Exception as env_key:
                    self.logger.debug(
                        "ENV variable {} is not set, "
                        "element will use its default value for property {}".format(env_key, key))
                    del config[key]["default"]

    def _get_typed_value(self, value):
        try:
            return json.loads(value)
        except ValueError:
            return value

    def warn_if_mounted(self):
        if os.path.islink(self.pipeline_dir):
            self.logger.warning(
                "Pipelines directory is symbolic link")
        if os.path.ismount(self.pipeline_dir):
            self.logger.warning(
                "Pipelines directory is mount point")

    def log_banner(self, heading):
        banner = "="*len(heading)
        self.logger.info(banner)
        self.logger.info(heading)
        self.logger.info(banner)

    def get_loaded_pipelines(self):
        results = []
        for pipeline in self.pipelines:
            for version in self.pipelines[pipeline]:
                result = self.get_pipeline_parameters(
                    pipeline, version)
                if result:
                    results.append(result)
        return results

    def get_pipeline_parameters(self, name, version):
        if not self.pipeline_exists(name, version):
            return None
        params_obj = {
            "name": name,
            "version": version
        }
        if "type" in self.pipelines[name][version]:
            params_obj["type"] = self.pipelines[name][version]["type"]
        if "description" in self.pipelines[name][version]:
            params_obj["description"] = self.pipelines[name][version]["description"]
        if "parameters" in self.pipelines[name][version]:
            params_obj["parameters"] = self.pipelines[name][version]["parameters"]
        return params_obj

    def is_input_valid(self, request, pipeline_config, section):
        config = pipeline_config.get(section, {})
        try:
            if (section in request):
                input_validator = jsonschema.Draft4Validator(
                    schema=config, format_checker=jsonschema.draft4_format_checker)
                input_validator.validate(request.get(section, {}))
                self.logger.debug(
                    "{} Validation successful".format(section))
            return True
        except Exception as error:
            self.logger.debug(
                "Validation error in request section {}, error: {}".format(section, error))
            return False

    def set_section_defaults(self, request, config, request_section, config_section):
        section, config = Pipeline.get_section_and_config(
            request, config, request_section, config_section)
        for key in config:
            if key not in section and "default" in config[key]:
                section[key] = config[key]["default"]

        if (len(section) != 0):
            result = request
            for key in request_section[0:-1]:
                result = result.setdefault(key, {})
            result[request_section[-1]] = section

    def set_defaults(self, request, config):

        if ("destination" not in config):
            config["destination"] = schema.destination
        if ("source" not in config):
            config["source"] = schema.source
        if ("tags" not in config):
            config["tags"] = schema.tags

        self.set_section_defaults(request, config, ["parameters"],
                                  ["parameters", "properties"])
        if "destination" in request:
            if "type" in request["destination"]:
                metadata = {"metadata": request["destination"]}
                request["destination"] = metadata

            for dest_type in request["destination"]:
                if "type" in request["destination"][dest_type]:
                    self.set_section_defaults(request, config, ["destination", dest_type],
                                              ["destination", dest_type,
                                               request["destination"][dest_type]["type"],
                                               "properties"])

        if ("source" in request) and ("type" in request["source"]):
            self.set_section_defaults(request, config, ["source"],
                                      ["source",
                                       request["source"]["type"],
                                       "properties"])

        self.set_section_defaults(request, config, ["tags"],
                                  ["tags", "properties"])

    def create_instance(self, name, version, request_original, options):
        self.logger.info(
            "Creating Instance of Pipeline {name}/{v}".format(name=name, v=version))
        if not self.pipeline_exists(name, version):
            return None, "Invalid Pipeline or Version"

        pipeline_type = self.pipelines[name][str(version)]['type']
        pipeline_config = self.pipelines[name][str(version)]

        request = request_original.copy()

        self.set_defaults(request, pipeline_config)

        if not self.is_input_valid(request, pipeline_config, "parameters"):
            return None, "Invalid Parameters"
        if "destination" in request:
            destination_section = request.get("destination")
            destination_config = pipeline_config.get("destination", {})
            for destination in destination_section:
                if not self.is_input_valid(destination_section, destination_config, destination) or \
                        not isinstance(destination_section[destination], dict):
                    return None, "Invalid Destination"
        if not self.is_input_valid(request, pipeline_config, "source"):
            return None, "Invalid Source"
        if not self.is_input_valid(request, pipeline_config, "tags"):
            return None, "Invalid Tags"

        instance_id = uuid.uuid1().hex
        request["pipeline"] = {
            "name": name,
            "version": version
        }
        self.pipeline_instances[instance_id] = self.pipeline_types[pipeline_type](
            instance_id,
            pipeline_config,
            self.model_manager,
            request,
            self._pipeline_finished,
            options)
        self.pipeline_queue.append(instance_id)
        self._start()
        return instance_id, None

    def _get_next_pipeline_identifier(self):
        if (self.max_running_pipelines > 0):
            if (self.running_pipelines >= self.max_running_pipelines):
                return None

        try:
            if (self.pipeline_queue):
                return self.pipeline_queue.popleft()
        except Exception:
            pass

        return None

    def _start(self):
        pipeline_identifier = self._get_next_pipeline_identifier()
        if (pipeline_identifier):
            pipeline_to_start = self.pipeline_instances[pipeline_identifier]
            with self._run_counter_lock:
                self.running_pipelines += 1
            pipeline_to_start.start()

    def _pipeline_finished(self):
        with self._run_counter_lock:
            self.running_pipelines -= 1
        self._start()

    def get_instance_summary(self, instance_id):
        if self.instance_exists(instance_id):
            return self.pipeline_instances[instance_id].params()
        return None

    def get_instance_parameters(self, name, version, instance_id):
        if self.instance_exists(instance_id, name, version):
            return self.pipeline_instances[instance_id].params()
        return None

    def get_all_instance_status(self):
        results = []
        for pipeline_instance in self.pipeline_instances.values():
            results.append(pipeline_instance.status())
        return results

    def get_instance_status(self, instance_id, name=None, version=None):
        if self.instance_exists(instance_id, name, version):
            status = self.pipeline_instances[instance_id].status()
            return status
        return None

    def stop_instance(self, instance_id, name=None, version=None):
        if self.instance_exists(instance_id, name, version):
            try:
                self.pipeline_queue.remove(instance_id)
            except Exception:
                pass
            return self.pipeline_instances[instance_id].stop()
        return None

    def instance_exists(self, instance_id, name=None, version=None):
        if instance_id in self.pipeline_instances:
            if name and version:
                pipeline = self.pipeline_instances[instance_id].request["pipeline"]
                if name == pipeline["name"] and version == pipeline["version"]:
                    return True
            else:
                return True
        self.logger.warning("Invalid Instance ID")
        return False

    def pipeline_exists(self, name, version):
        if name in self.pipelines and str(version) in self.pipelines[name]:
            return True
        self.logger.warning("Invalid pipeline or version")
        return False
