#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import json
import os
from typing import List, Dict, Any

from src.common.log import get_logger


class PublisherConfig:  # TODO: can create a base class for both pub and sub config
    def __init__(self, pub) -> None:
        self._pub_cfg = pub
    
    def get_pub_cfg(self):     
        return self._pub_cfg
    
    def get_topics(self):
        if "topic" in self._pub_cfg:            
            return self._pub_cfg["topic"]
        elif "Topics" in self._pub_cfg:
            return self._pub_cfg["Topics"]
        else:
            raise KeyError("topic/Topics key not found in publisher config")
    
    def get_endpoint(self):
        if "endpoint" in self._pub_cfg:
            return self._pub_cfg["endpoint"]
        elif "EndPoint" in self._pub_cfg:
            return self._pub_cfg["EndPoint"]
        else:
            raise KeyError("endpoint/EndPoint key not found in publisher config")
    
    def get_interface_value(self, key):
        return self._pub_cfg.get(key)
        
class SubscriberConfig:
    def __init__(self,sub) -> None:
        self._sub_cfg = sub
    
    def get_sub_cfg(self):
        return self._sub_cfg

    def get_topics(self):
        if "topic" in self._sub_cfg:            
            return self._sub_cfg["topic"]
        elif "Topics" in self._sub_cfg:
            return self._sub_cfg["Topics"]
        else:
            raise KeyError("topic/Topics key not found in subscriber config")
    
    def get_endpoint(self):
        if "endpoint" in self._sub_cfg:
            return self._sub_cfg["endpoint"]
        elif "EndPoint" in self._sub_cfg:
            return self._sub_cfg["EndPoint"]
        else:
            raise KeyError("endpoint/EndPoint key not found in subscriber config")
    
    def get_interface_value(self, key):
        return self._sub_cfg.get(key)

class PipelineServerConfig:
    """DL Streamer Pipeline Server configuration class. 
    Abstracts config sources whether its from a config file"""

    class _ConfigHandler:
        def __init__(self, watch_cb=None, watch_file_cbfunc=None) -> None:
            self.log = get_logger(__name__)
            try:
                with open("config.json", "r") as f:
                    _cfg = json.load(f)
                    self._app_cfg = _cfg["config"] # read from file
                    self._app_interface = _cfg.get("interfaces",{})
            except FileNotFoundError:
                self.log.exception("could not find config.json")
                raise
            
        def get_app_cfg(self):
            return self._app_cfg
                
        def get_app_interface(self):
            return self._app_interface
        
        def get_mqtt_publisher(self):
            """Return list of mqtt publishers"""
            return self._app_cfg.get("mqtt_publisher")

        def get_mqtt_subscriber(self):
            """Return list of mqtt subscribers"""
            raise NotImplementedError

    def __init__(self, watch_cb=None, watch_file_cbfunc=None) -> None:
        self.log = get_logger(__name__)
        self._cfg_handler = self._ConfigHandler(watch_cb, watch_file_cbfunc)

    def get_app_config(self):
        return self._cfg_handler.get_app_cfg()
    
    def get_app_interface(self):
        return self._cfg_handler.get_app_interface()

    def get_publishers(self)-> List[PublisherConfig]:
        """Return list of publishers."""
        publishers = []
        self.log.info("Fetching publishers")
        mqtt_publishers = self._cfg_handler.get_mqtt_publisher()
        for p in self._cfg_handler.get_mqtt_publisher():
            publishers.append(PublisherConfig(p))  # simply add config dict
        self.log.info(f"Publishers: {publishers}")
        self.log.info("="*100)
        return publishers
    
    def get_subscribers(self)-> List[SubscriberConfig]:
        subscribers = []
        self.log.info("Fetching subscribers")
        # TODO: get mqtt subscriber for each pipeline
        subscribers.append(SubscriberConfig(s))  # simply add config dict
        return subscribers
    
    def get_pipelines_config(self) -> List[Dict[str,Any]]:
        app_cfg = self.get_app_config()
        return app_cfg['pipelines']

    def set_app_config(self, new_config: Dict[str, Any]) -> None:
        """Set the application configuration with a new configuration.

        Args:
            new_config (Dict[str, Any]): The new configuration to set.
        """
        self._cfg_handler._app_cfg = new_config

    def update_pipeline_config(self, model_path_dict: Dict) -> None:
        """Update the configuration of pipelines with new model paths.

        Args:
            model_path_dict (Dict): Dictionary mapping pipeline element names to model paths.
        """
        app_cfg = self.get_app_config()
        pipelines = app_cfg.get('pipelines', [])
        for pipeline_index, pipeline in enumerate(pipelines):
            for pipeline_element_name, model_path in model_path_dict.items():
                elements = pipeline["pipeline"].split('!')
                for i, element in enumerate(elements):
                    if pipeline_element_name in element:
                        if 'udfloader' in element:
                            deployment_dir = model_path.split('/deployment', 1)[0] + '/deployment'
                            app_cfg["pipelines"][pipeline_index]["udfs"]["udfloader"][0]["deployment"] = deployment_dir
                        elif 'model=' in element:
                            # Update the model path if it already exists
                            elements[i] = f"{element.split('model=')[0]}model={model_path} "
                        else:
                            # Add the model path if it does not already exist
                            elements[i] = f"{element.rstrip()} model={model_path} "
                        break
                app_cfg['pipelines'][pipeline_index]["pipeline"] = elements[0] + ''.join(f'!{e}' for e in elements[1:-1]) + '!' + elements[-1]                
                self.log.debug("Pipeline '%s' updated with model %s for '%s'.", pipeline, model_path, pipeline_element_name)

        self.set_app_config(app_cfg)
        self.log.info("Updated pipeline configuration with model paths. New configuration is %s.", json.dumps(app_cfg, indent=4))