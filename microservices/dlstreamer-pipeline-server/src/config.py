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
    def __init__(self, pub, eii_mode=False) -> None:
        self._pub_cfg = pub
        self.eii_mode = eii_mode

    def is_emb_publisher(self):
        return self.eii_mode
    
    def get_pub_cfg(self):
        if self.eii_mode:   
            return self._pub_cfg.get_eis_servers()        
        return self._pub_cfg
    
    def get_topics(self):
        if self.eii_mode:
            # return self._pub_cfg.get_topics()
            return self._pub_cfg.get_interface_value("topics")
        if "topic" in self._pub_cfg:            
            return self._pub_cfg["topic"]
        elif "Topics" in self._pub_cfg:
            return self._pub_cfg["Topics"]
        else:
            raise KeyError("topic/Topics key not found in publisher config")
    
    def get_endpoint(self):
        if self.eii_mode:
            return self._pub_cfg.get_endpoint()
        if "endpoint" in self._pub_cfg:
            return self._pub_cfg["endpoint"]
        elif "EndPoint" in self._pub_cfg:
            return self._pub_cfg["EndPoint"]
        else:
            raise KeyError("endpoint/EndPoint key not found in publisher config")
    
    def get_interface_value(self, key):
        if self.eii_mode:
            return self._pub_cfg.get_interface_value(key)
        return self._pub_cfg.get(key)
        


class SubscriberConfig:
    def __init__(self,sub, eii_mode=False) -> None:
        self._sub_cfg = sub
        self.eii_mode = eii_mode

    def is_emb_subscriber(self):
        return self.eii_mode
    
    def get_sub_cfg(self):
        if self.eii_mode:   
            return self._sub_cfg.get_eis_clients()
        return self._sub_cfg

    def get_topics(self):
        if self.eii_mode:
            # return self._sub_cfg.get_topics()
            return self._sub_cfg.get_interface_value("topics")
        if "topic" in self._sub_cfg:            
            return self._sub_cfg["topic"]
        elif "Topics" in self._sub_cfg:
            return self._sub_cfg["Topics"]
        else:
            raise KeyError("topic/Topics key not found in subscriber config")
    
    def get_endpoint(self):
        if self.eii_mode:
            return self._sub_cfg.get_endpoint()
        if "endpoint" in self._sub_cfg:
            return self._sub_cfg["endpoint"]
        elif "EndPoint" in self._sub_cfg:
            return self._sub_cfg["EndPoint"]
        else:
            raise KeyError("endpoint/EndPoint key not found in subscriber config")
    
    def get_interface_value(self, key):
        if self.eii_mode:
            return self._sub_cfg.get_interface_value(key)
        return self._sub_cfg.get(key)

def get_eis_cfg():
    import cfgmgr.config_manager as cfg    
    return cfg

class PipelineServerConfig:
    """DL Streamer Pipeline Server configuration class. 
    Abstracts config sources whether its from a config file or from EII ETCD."""

    class _ConfigHandler:
        def __init__(self, eii_mode=False, watch_cb=None, watch_file_cbfunc=None) -> None:
            self.eii_mode = eii_mode
            self.log = get_logger(__name__)
            if not self.eii_mode:
                try:
                    with open("config.json", "r") as f:
                        _cfg = json.load(f)
                        self._app_cfg = _cfg["config"] # read from file
                        self._app_interface = _cfg.get("interfaces",{})
                except FileNotFoundError:
                    self.log.exception("could not find config.json")
                    raise
            else:
                try:
                    # import cfgmgr.config_manager as cfg
                    cfg = get_eis_cfg()
                except ImportError:
                    self.log.exception("Error: Unable to import config manager")
                    raise
                if watch_cb is None:
                    raise ValueError("Callback for watch config is missing")
                self._cfg_mgr = cfg.ConfigMgr()
                watch_cfg = self._cfg_mgr.get_watch_obj()
                self._read_config_from_file = os.getenv("READ_CONFIG_FROM_FILE_ENV", "false")
                if self._read_config_from_file.lower() == "true":
                    self.log.info("Watching on config.json file")
                    # watch_file_cbfunc will be called on any change in config.json file
                    watch_cfg.watch_config_file(watch_file_cbfunc)
                else:
                    # Watch on key /<AppName>
                    key_to_watch = '/' + os.environ['AppName'] + '/'
                    watch_cfg.watch_prefix(key_to_watch, watch_cb)
                self._app_cfg = self._cfg_mgr.get_app_config().get_dict()
            
        def get_app_cfg(self):
            return self._app_cfg
                
        def get_app_interface(self):
            return self._app_interface

        def get_emb_subscribers(self):
            """Return list of emb subscribers"""
            subs=[]
            if self.eii_mode:
                for i in range(self._cfg_mgr.get_num_subscribers()):
                    subs.append(self._cfg_mgr.get_subscriber_by_index(i))
            return subs
        
        def get_emb_publishers(self):
            """Return list of emb publishers""" # TODO: add support for other fetches such as by_name, etc
            pubs=[]
            if self.eii_mode:
                for i in range(self._cfg_mgr.get_num_publishers()):
                    pubs.append(self._cfg_mgr.get_publisher_by_index(i))
            return pubs

        def get_eis_servers(self):
            """Return list of eis servers"""
            servers =[]
            if self.eii_mode:
                for i in range(self._cfg_mgr.get_num_servers()):
                    servers.append(self._cfg_mgr.get_server_by_index(i))
            return servers
                
        def get_eis_clients(self):
            """Return list of eis clients"""
            clients =[]
            if self.eii_mode:
                for i in range(self._cfg_mgr.get_num_clients()):
                    clients.append(self._cfg_mgr.get_client_by_index(i))
            return clients
        
        def get_mqtt_publisher(self):
            """Return list of mqtt publishers"""
            return self._app_cfg.get("mqtt_publisher")

        def get_mqtt_subscriber(self):
            """Return list of mqtt subscribers"""
            raise NotImplementedError
        
        def get_grpc_clients(self):
            """Return list of grpc clients"""
            return self._app_interface.get("Clients",[])
        
        def get_grpc_servers(self):
            """Return list of grpc servers"""
            raise NotImplementedError

    def __init__(self, mode, watch_cb=None, watch_file_cbfunc=None) -> None:
        self.log = get_logger(__name__)
        self._cfg_handler = self._ConfigHandler(mode, watch_cb, watch_file_cbfunc)
        self.is_eii_mode = self._cfg_handler.eii_mode

    def get_app_config(self):
        return self._cfg_handler.get_app_cfg()
    
    def get_app_interface(self):
        return self._cfg_handler.get_app_interface()

    def get_publishers(self)-> List[PublisherConfig]:
        """Return list of publishers. Each publisher can be identified whether
        it is an emb publisher by its attribute eii_mode"""
        publishers = []
        if self._cfg_handler.eii_mode:
            self.log.info("Fetching edge gRPC publishers/clients")
            for p in self._cfg_handler.get_eis_clients():
                publishers.append(PublisherConfig(p, eii_mode=True))   # add msg bus config instance
        else:
            self.log.info("Fetching publishers")
            mqtt_publishers = self._cfg_handler.get_mqtt_publisher()
            grpc_clients = self._cfg_handler.get_grpc_clients()
            if mqtt_publishers:
                for p in self._cfg_handler.get_mqtt_publisher():
                    publishers.append(PublisherConfig(p, eii_mode=False))  # simply add config dict
            if grpc_clients:
                for p in self._cfg_handler.get_grpc_clients():
                    publishers.append(PublisherConfig(p, eii_mode=False))
        self.log.info(f"Publishers: {publishers}")
        self.log.info("="*100)
        return publishers
    
    def get_subscribers(self)-> List[SubscriberConfig]:
        subscribers = []
        if self._cfg_handler.eii_mode:
            self.log.info("Fetching edge gRPC subscribers/servers")
            for s in self._cfg_handler.get_eis_servers():
                subscribers.append(SubscriberConfig(s, eii_mode=True))   # add msg bus config instance
        else:
            self.log.info("Fetching subscribers")
            # TODO: get mqtt subscriber for each pipeline
            subscribers.append(SubscriberConfig(s, eii_mode=False))  # simply add config dict
        return subscribers
    
    def get_pipelines_config(self) -> List[Dict[str,Any]]:
        app_cfg = self.get_app_config()
        return app_cfg['pipelines']

    def get_model_registry_config(self) -> Dict[str,Any]:
        """Get the properties related to the model registry microservice in 
        the config.json file. 

        Returns:
            Dict[str,Any]: The properties for establishing a 
            connection to a model registry microservice and storing the 
            model artifacts locally.
        """
        model_registry_cfg = {
            "url": os.getenv("MR_URL"),
            "saved_models_dir": os.getenv("MR_SAVED_MODELS_DIR"),
            "request_timeout": int(os.getenv("MR_REQUEST_TIMEOUT"))
        }
        return model_registry_cfg

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