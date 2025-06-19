#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import base64
import copy
import json
import os
import queue
import time
import re

from collections import defaultdict
from distutils.util import strtobool
from typing import Dict, Any, Tuple, List, Union, Optional
from src.server.gstreamer_app_source import GvaFrameData
from src.server.pipeline_server import PipelineServer
from src.server.pipeline import Pipeline as PipelineServer_Pipeline # avoid shadowing

from src.publisher.publisher import Publisher
from src.subscriber.cam_ingestor import XirisCamIngestor
from src.subscriber.image_ingestor import ImageIngestor
from src.publisher.image_publisher import ImagePublisher
from src.config import PipelineServerConfig
from src.common.log import get_logger, LOG_LEVEL


class PipelineInstance:
    _SUPPORTED_PUBLISHERS = ["S3_write"]
    def __init__(self, 
                 name:str, 
                 version:str, 
                 config: Dict[str, Any], 
                 publisher_config:List[Any], 
                 subscriber_config: Dict[str, Any], 
                 subscriber_topic: str, 
                 publish_frame: bool, 
                 request:Optional[Dict[str,Any]]) -> None:
        """Initializes a new pipeline instance

        Args:
            name (str): name of the pipeline
            version (str): version of the pipeline
            config (Dict[str, Any]): pipeline config
            publisher_config (List[Any]): list of EdgeGrpcPublisher config
            subscriber_config (Dict[str, Any]): subscriber config
            subscriber_topic (str): subscriber topic
            publish_frame (bool): whether to publish frame
            request (Dict[str,Any], optional): start pipeline request typically via REST call. Defaults to None.
        """
        self.log = get_logger(__name__)
        self.name = name
        self.version = version
        self.config = config
        self.pub_cfg = publisher_config
        self.sub_cfg = subscriber_config
        self.sub_topic = subscriber_topic
        self.publish_frame = publish_frame
        self.source_type = config.get("source")
        self._request = request
        self.is_async = True if self._request is None else not(request.get("sync", False))
        self._source = None
        self._destination = None
        self._parameters = None
        self.tag = None
        self.instance_id = None
        self.is_running = False
        self.subscriber = None
        self.ingestor = None

    def _mutable_deepcopy(self, obj):
        """creates a deepcopy of mutable objects"""
        if obj is None:
            return None
        return copy.deepcopy(obj)
    
    @property
    def source(self):
        return self._mutable_deepcopy(self._source)
    
    @property
    def destination(self):
        return self._mutable_deepcopy(self._destination)
    
    @property
    def parameters(self):
        return self._mutable_deepcopy(self._parameters)
    
    @property
    def request(self):
        return self._mutable_deepcopy(self._request)

    def to_dict(self):
        """Return a dict of instance parameters"""
        return {
            'name': self.name,
            'version': self.version,
            'instance_id': self.instance_id,
            'source_type': self.source_type,
            'source': self.source,
            'destination': self.destination,
            'parameters': self.parameters,
            'tags': self.tag,
            'request': self.request
        }
    
    def start(self):
        """Prepares and starts ingestor, publisher, pipeline threads and starts the pipeline instance."""
        queue_maxsize = self.config.get("queue_maxsize",0)
        self.output_queue = queue.Queue(maxsize=queue_maxsize)
        
       
        if self.source_type == "ingestor":
            self.input_queue = queue.Queue()
            self.ingestor = XirisCamIngestor(self.input_queue, self.config)
            self.ingestor.start()

        elif self.source_type == "image_ingestor":
            self.input_queue = queue.Queue()    # maxsize =1 ?
            self.ingestor = ImageIngestor(self.input_queue, self.config)
            self.ingestor.start()   # start thread and wait for inbound image request
        
        elif self.source_type != "gstreamer":
            raise RuntimeError(f'Unsupported source: {self.source_type}')
        
        request_cpy = copy.deepcopy(self.request)   # keep a copy of request to update instance summary
        self.publisher = Publisher(self.config, self.pub_cfg, self.output_queue,request=self._request)

        # add imagepublisher for source= "image_ingestor"
        if self.source_type == "image_ingestor":
            image_publisher = ImagePublisher()
            self.publisher.image_publisher = image_publisher    # to track image publisher
            self.publisher.publishers.append(image_publisher)   # add to list of publishers, if exists

        self.log.info("Starting client threads")
        for client in self.publisher.publishers:
            if client.initialized:
                client.start()
        self.publisher.start()


        # prepare and start pipeline request
        self.log.debug("preparing pipeline request")
        
        # identify source
        if self.source_type == "ingestor" or self.source_type == "image_ingestor":
            src = {
                "type": "application",
                "class": "GStreamerAppSource",
                "input": self.input_queue,
            }
        else:
            # when src is from REST API request
            if self.request is not None and "source" in self.request:
                src = self.request["source"]     #TODO: validate with udfs elements if not gst type source
                if self.request["source"]["type"] == "application":
                    src["input"] = self.input_queue
            else:
                # hardcoded source from pipeline config
                src = {
                    "type": "gst",
                    "element": self.config['pipeline'].split()[0]
                }
        
        # identify destination
        self.is_appdest = False
        dest = {}
        if self.request is not None and "destination" in self.request :
            # for pipeline restart where request is picked from a prior run and had appsink set as destination
            if "metadata" in self.request["destination"] and self.request["destination"]["metadata"]["type"] == "application":   # there could be request with only frame and no metadata
                dest = self.request["destination"]
                dest["metadata"]["output"] = self.output_queue
                self.is_appdest = True
            if "frame" in self.request["destination"]:
                dest["frame"] = self.request["destination"]["frame"]
        if self.publisher.publishers != [] and ("destination" not in self.request or "metadata" not in self.request["destination"]):
            pipeline_config = self.config["pipeline"]
            appsink_name=""
            appsink_pattern = r"appsink\s+name\s*=\s*(\w+)"
            match = re.search(appsink_pattern, pipeline_config)
            if match:
                appsink_name = match.group(1)
            self.log.debug(f'Appsink name found as - {appsink_name}')
            
            if appsink_name =="destination":
                dest['metadata'] = {
                        'type': 'application',
                        'class': 'GStreamerAppDestination',
                        'output': self.output_queue,
                        'mode':
                            'frames'  # TODO: Should this be something else? options?
                    }
                self.is_appdest = True
            else:
                dest = {}
                self.is_appdest = False  

        # identify model parameters, add udfs params if present
        model_params = {}
        
        if 'udfs' in self.config:
            self.log.info(f'Config specified UDFs')
            model_params = {"udfloader": {"udfs": self.config['udfs']['udfloader']}}
        if 'model_parameters' in self.config:
            model_params.update(self.config['model_parameters'])
        
        # when udfloader is from REST API request
        if self.request is not None and 'parameters' in self.request and "udfloader" in self.request['parameters']:
            model_params["udfloader"] = self.request['parameters']['udfloader']

        if self.request is not None and 'tags' in self.request:
            self.tags = self.request["tags"]
        else:
            self.tags = self.config.get("tags")

        self.log.info(
            f'Creating Pipeline Server pipeline {self.name}/{self.version}')
        self.pipeline = PipelineServer.pipeline(self.name, self.version)
        if self.pipeline is None:
            raise RuntimeError('Failed to initialize Pipeline Server pipeline')

        self.log.info('Starting Pipeline Server pipeline {} {} {}'.format(
            src, dest,model_params))
        self.instance_id = self.pipeline.start(request=copy.deepcopy(self.request),
                                               source=src,
                                               destination=dest,
                                               parameters=model_params,
                                               tags=self.tags)
        if self.instance_id is None:
            raise RuntimeError('Failed to start pipeline')
        self.is_running = True
        
        # remove input and output queue objects from source and destination for serialization
        if src["type"] == "application":
            src["input"] = "REDACTED_INPUT_QUEUE_OBJECT"
        self._source = src
        
        if "metadata" in dest:
            if dest["metadata"]["type"] == "application":
                dest["metadata"]["output"] = "REDACTED_OUTPUT_QUEUE_OBJECT"
        self._destination = dest
        self._parameters = model_params
        self._request = request_cpy

        self.log.info("Pipeline instance started: {}".format(self.instance_id))
        self.publisher.set_pipeline_info(self.name, self.version,
                                         self.instance_id, self.get_status)

    def execute_request(self,
                        instance_id: str,
                        request: Dict[str, Any],
                        REQUEST_PUT_TIMEOUT=5):
        """execute a request on a queued pipeline. Used by image ingestor where 
        pipeline is running and user would like to call inference on demand for 
        user supplied image path.

        Args:
            instance_id (str): pipeline instance id
            request (Dict[str, Any]): request carrying image path to execute pipeline on
        """
        MSG_PREFIX = "[{}]:".format(instance_id)
        if not self.source_type == "image_ingestor":
            raise ValueError("Request execution is supported only for image_ingestor pipelines")
        if instance_id != self.instance_id:
            raise ValueError("Invalid instance id- {}".format(instance_id))
        
        DATA=None
        ERR=None
        if not self.is_async and not self.is_appdest:
            return None, "Pipeline destination must be appsink for synchronous request"

        try:
            # clear response queue to remove any stale data
            while not self.publisher.image_publisher.response_queue.empty():
                self.log.info("{} Clearing stale data from response queue".format(MSG_PREFIX))
                try:
                    self.publisher.image_publisher.response_queue.get_nowait()
                except queue.Empty:
                    break

            self.ingestor.request_queue.put(request, timeout=REQUEST_PUT_TIMEOUT)
            self.log.info("{} Request submitted: {}".format(MSG_PREFIX, request))
            DATA="Request submitted. Check destination for response."
            ERR = None
        except queue.Full:
            ERR = "Could not execute requeust due to timeout."
            self.log.error(MSG_PREFIX, ERR)
            return DATA, ERR
        
        if not self.is_async:
        # wait for response
            if not isinstance(self.publisher.image_publisher,ImagePublisher):
                ERR = "Invalid publisher type for image ingestor"
                DATA=None
                self.log.error(MSG_PREFIX, ERR)
            else:
                try:
                    RESPONSE_TIMEOUT = 5
                    timeout = request.get("timeout", RESPONSE_TIMEOUT)
                    response = self.publisher.image_publisher.response_queue.get(timeout=timeout)    # only one publisher for image_ingestor
                    # self.log.info("Request executed. Response: {}".format(response))
                    frame, metadata = response     # frame-bytes, metadata

                    publish_frame = request.get("publish_frame", False)
                    if not publish_frame:
                        enc_frame = ""
                    else:
                        enc_frame = base64.b64encode(frame).decode("utf-8")

                    resp_data = {"metadata":metadata, "blob":enc_frame} 
                    DATA= json.dumps(resp_data) 
                    ERR= None
                except queue.Empty:
                    DATA= None
                    ERR= "Request execution timed out"
                    self.log.error(MSG_PREFIX, ERR)
        return DATA, ERR

    def get_status(self):
        """Return status dict of pipeline instance"""
        if self.instance_id is not None:
            return self.pipeline.status()

    def stop(self):
        """Stop the Pipeline instance and its thread."""
        self.publisher.stop()
        if self.publisher.publishers:
            for p in self.publisher.publishers:
                p.stop()
        if self.ingestor is not None:
            self.ingestor.stop()
        if self.subscriber is not None:
            self.subscriber.stop()
        self.is_running = False
        self.pipeline = None
        self.log.info("Pipeline instance stopped: {}".format(self.instance_id))


class Pipeline:
    """Manages a single pipeline in the pipeline server. Handles spawns a new 
    pipeline instance as well as stopping it. 
    In pipeline-server teminiology, it corresponds to pipeline 'version'.
    """
    _INSTANCES = defaultdict(dict)     # bookkeeper for all active instances
    def __init__(self, 
                 root_dir:str,
                 pipeline_name: str, 
                 pipeline_config: Dict[str,Any], 
                 publisher_config: List[Any], 
                 subscriber_config: Dict[str, Any], 
                 subscriber_topic:str, 
                 publish_frame:bool=False):
        """Intializes a pipeline.

        Args:
            root_dir (str): path to all the pipelines
            pipeline_name (str): name of pipeline
            pipeline_config (Dict[str,Any]): pipeline configuration dict
            publisher_config (List[Any]): list of publishers configuration
            subscriber_config (Dict[str, Any]): subscriber configuration
            subscriber_topic (str): subscriber topic
            publish_frame (bool, optional): whether to publish frame. Defaults to False.

        """
        self.log = get_logger(__name__)
        self.root = root_dir
        self.pipeline_name = pipeline_name
        self.pipeline_config = pipeline_config
        self.pipeline_version = pipeline_config["name"]
        self.pub_cfg = publisher_config # list of publishers
        self.sub_cfg = subscriber_config
        self.sub_topic = subscriber_topic
        self.publish_frame = publish_frame
        self.instance_refcount = 0

        self.auto_start = pipeline_config.get("auto_start", False)
        self.pipeline_dir = os.path.join(root_dir, self.pipeline_name, self.pipeline_version)   
        self.pipeline_json_path = os.path.join(self.pipeline_dir, "pipeline.json")

        self.log.info("Initializing pipeline for {}".format(self.pipeline_version))

        if 'pipeline' not in self.pipeline_config:
            raise ValueError("Missing 'pipeline' key in pipeline configuration")
        
        self.log.info("Gstreamer Pipeline: {}".format(self.pipeline_config['pipeline']))
        parameters = self.pipeline_config.get('parameters', {})
        pipeline_template = {
            "type": "GStreamer",
            "template": [self.pipeline_config['pipeline']],
            "description": "DL Streamer Pipeline Server pipeline",
            "parameters": parameters
        }
        os.makedirs(self.pipeline_dir, exist_ok=True)
        with open(self.pipeline_json_path, "w") as f:
            f.write(json.dumps(pipeline_template, sort_keys=False,
                                indent=4))
        self.log.debug("pipeline template generated: {}".format(self.pipeline_json_path))        
        self.log.info("Pipeline initialized")

    def start(self, 
              request=None)->str:
        """Start a new pipeline instance

        Args:
            request (Dict, optional): request via REST API. Defaults to None.

        Returns:
            str: instance id
        """
        pinstance = PipelineInstance(self.pipeline_name, 
                                     self.pipeline_version, 
                                     self.pipeline_config, 
                                     self.pub_cfg, 
                                     self.sub_cfg, 
                                     self.sub_topic, 
                                     self.publish_frame, 
                                     request)
        pinstance.start()
        self.instance_refcount += 1
        self._INSTANCES[pinstance.instance_id].update({"obj":pinstance, "params":pinstance.to_dict()})
        self.log.debug("Pipeline instance started: {}".format(pinstance.instance_id))
        self.log.debug("Pipeline instance params: {}".format(json.dumps(self._INSTANCES[pinstance.instance_id]["params"], indent=4)))
        return pinstance.instance_id
    
    def stop(self, 
             instance_id)->None:
        """Stop a pipeline instance

        Args:
            instance_id (str): id of the new pipeline instance
        """
        if instance_id in self._INSTANCES:
            pinstance = self._INSTANCES[instance_id]["obj"]
            pinstance.stop()
            self.instance_refcount -= 1
            self._INSTANCES.pop(instance_id)
            self.log.info("Pipeline instance stopped: {}".format(instance_id))
        else:
            self.log.error("Pipeline instance not found")


class PipelineServerManager:
    """Manager class for Pipeline Server."""
    _PIPELINES = {}
    _GVAELEMENT_MODEL_INSTANCE_ID = {
        "gvadetect":defaultdict(dict),
        "gvaclassify":defaultdict(dict),
        "gvainference":defaultdict(dict)
        }   # bookkeeper to keep track of model-instance-id for gva elements in pipeline and their status
    def __init__(self, 
                 config:PipelineServerConfig, 
                 pipeline_root: str="/home/pipeline-server") -> None:
        """Initialize PipelineServerManager

        Args:
            config (PipelineServerConfig): DL Streamer Pipeline Server configuration instance
            pipeline_root (str, optional): root dir where pipeline templates are generated or looked up. Defaults to "/home/pipeline-server".
        """
        self.log = get_logger(__name__)
        self.pipeline_root = pipeline_root
        self.pipeline_name = "user_defined_pipelines"
        self.config = config
        self.app_config = self.config.get_app_config()
        self.server_running = False
        self.pipeline_path = os.path.join(self.pipeline_root, self.pipeline_name)
        self.gencam_serial_availability = dict()   # anytime, allow only 1 gencam serial to be used

        if not os.path.isdir(self.pipeline_path):
            os.makedirs(self.pipeline_path)
        self.log.info("PipelineServerManager initialized")


    def _initialize_pipelines(self)->None:
        """Initialize pipelines from app config"""
        pipeline_configs = self.app_config['pipelines']
        publishers = self.config.get_publishers()
                
        for i, pipeline_cfg in enumerate(pipeline_configs):
            #TODO: add camera serial check
            pipeline_version = pipeline_cfg['name']
            sub_cfg = None
            pub_cfg = None
            sub_topic = None

            if pipeline_cfg['source'] == "grpc":
                subscribers = self.config.get_subscribers()
                if len(subscribers)!=1:
                    raise ValueError("Only single subscriber is supported.")
                if not subscribers[0].is_emb_subscriber():
                    raise ValueError("Subsciber must be an edge grpc subscriber")
                            
                sub_cfg = subscribers[0]    # TODO  enable multi-subscriber ?
                sub_topic = sub_cfg.get_topics()[i]

            publish_frame = pipeline_cfg.get('publish_frame', False)

            if publishers:  # only in EIS deployment, for standard, publisher info is inside pipeline cfg
                pub_cfg = publishers
                    
            # initialize pipeline
            pipeline = Pipeline(self.pipeline_root, self.pipeline_name, pipeline_cfg, pub_cfg, sub_cfg, sub_topic, publish_frame)
            self._PIPELINES[pipeline_version] = pipeline
            self.log.info("Initialized pipeline: {} with publishers: {}".format(pipeline_version, pub_cfg))

    def start(self)->None:
        """Start Pipeline Server and autostart enabled pipelines """
        if 'pipelines' not in self.app_config:
            raise RuntimeError("No pipelines found in config")
        try:
            self._initialize_pipelines()            
            self.log.info("Pipelines initialization complete.")
        except Exception as e:
            self.log.exception("One or more pipelines could not be initialized. {}".format(e))
            raise

        try:
            self.log.info('Starting Pipeline Server')
            self.pserv = PipelineServer
            self.pserv.start({          # TODO: check behavior with 0 pipelines
                'log_level': LOG_LEVEL,
                'ignore_init_errors': True,
                'pipeline_dir': self.pipeline_path,
                'model_dir': "/home/pipeline-server/models"
            })
        except Exception as e:
            self.log.exception("Pipeline Server failed to start. {}".format(e))
            raise

        # start pipelines with autostart enabled
        for ver, pipeline in self._PIPELINES.items():
            if pipeline.auto_start:
                # try to start pipeline instance with default request
                request = pipeline.pipeline_config.get("payload")
        
                instance_id = pipeline.start(request=request)
                self.log.info("Autostarted pipeline: {} ID: {}".format(ver, instance_id))                
    
    def _get_pinstance_data(self, 
                            instance_id: str)->Tuple[PipelineInstance, Dict[str,Any]]:
        """get pipeline instance object & params from pipeline instance_id

        Args:
            instance_id (str): pipeline instance id

        Returns:
            Tuple: A tuple of pipeline instance and its parameter dict
        """
        for p in self._PIPELINES.values():
            inst_book = p._INSTANCES[instance_id]
            return inst_book["obj"], inst_book["params"]

    def get_loaded_pipelines(self)->List[Dict[str,Any]]:
        """GET /pipelines"""
        return self.pserv.pipeline_manager.get_loaded_pipelines()
        
    def get_pipeline_instance_summary(self, 
                                      instance_id: str)->Tuple[Union[Dict, None], Union[None, str]]:
        """GET /pipelines/{instance_id}"""
        psummary = self.pserv.pipeline_manager.get_instance_summary(instance_id)
        try:
            _, pparams = self._get_pinstance_data(instance_id)
            psummary["params"] = pparams
            pserv_p_instances = self.get_all_instance_status()
            for pserv_p_instance in pserv_p_instances:
                if pserv_p_instance.get("id") == psummary.get("id"):
                    psummary["state"] = pserv_p_instance['state'].name
                    break
            return psummary, None
        except KeyError:
            errmsg= "Pipeline instance not found"
            self.log.error(errmsg)
            return None, errmsg

    def get_all_instance_status(self)-> List[Dict]:
        """GET /pipelines/status"""
        return self.pserv.pipeline_manager.get_all_instance_status()

    def get_instance_status(self, instance_id: str) -> List[Dict]:
        """GET /pipelines/{instance_id}/status"""
        return self.pserv.pipeline_manager.get_instance_status(instance_id)

    def stop_instance(self, 
                      instance_id: str)->str:
        """DELETE /pipelines/{instance_id}"""
        try:
            pinstance, _ = self._get_pinstance_data(instance_id)
            pinstance.stop()
        except KeyError:
            self.log.error("Pipeline instance not found")
        except Exception as e:
            self.log.exception("Failed to stop pipeline instance. {}".format(e))
        return self.pserv.pipeline_manager.stop_instance(instance_id)
    
    def start_instance(self, 
                       name:str, 
                       version: str, 
                       request:Dict[str, Any]=None)->Tuple[Union[str, None], Union[None, str]]:
        """POST /pipelines/{name}/{version}"""
        try:
            self.log.info(self._PIPELINES)
            pipeline = self._PIPELINES[version]
        except KeyError:
            errmsg = "Pipeline not found"
            self.log.error(errmsg)
            return None, errmsg

        launch_str = pipeline.pipeline_config.get("pipeline")
        
        MODEL_IDS_TO_SET={"gvadetect":[],"gvaclassify":[],"gvainference":[]}    # update instance_id once pipeline is started
        
        for elem in launch_str.split('!'):
            if "gvadetect" in elem:
                gvaelement = "gvadetect"
            elif "gvaclassify" in elem:
                gvaelement = "gvaclassify"
            elif "gvainference" in elem:
                gvaelement = "gvainference"
            else:
                continue
            
            model_inst_data = self._GVAELEMENT_MODEL_INSTANCE_ID[gvaelement]
            match = re.search(r"\s*model-instance-id\s*=\s*(\w+)\s*", elem)
            minst_id = match.group(1) if match else None
            if minst_id is not None:    # check if model instance id is errored out
                if minst_id in model_inst_data:
                    if model_inst_data[minst_id].get('id') is not None:
                        state = self.pserv.pipeline_manager.get_instance_status(model_inst_data[minst_id]['id'])['state']
                        if state == PipelineServer_Pipeline.State.ERROR:
                            return None, "Cannot start pipeline. {} element uses model-instance-id: {} that errored out on a prior run due to incorrect parameters. Review parameters and relaunch DL Streamer Pipeline Server.".format(gvaelement, minst_id)
                else:
                    model_inst_data[minst_id]['id'] = None  # to be set once pipeline is started
                    MODEL_IDS_TO_SET[gvaelement].append(minst_id)
            
        #TODO if model-instance-id comes from a REST request/payload
        
        instance_id = pipeline.start(request)
        self.log.info("Pipeline instance_id: {}".format(instance_id))
        
        # set model-instance-id for gvaelements if present
        for gvaelem,model_ids in MODEL_IDS_TO_SET.items():
            for model_id in model_ids:
                self._GVAELEMENT_MODEL_INSTANCE_ID[gvaelem][model_id]['id'] = instance_id
                
        return instance_id,  None

    def execute_request_on_instance(self, 
                                    name:str, 
                                    version:str, 
                                    instance_id:str, 
                                    request:Dict[str,Any])->Tuple[Union[str, None], Union[None, str]]:
        """POST /pipelines/{name}/{version}/{instance_id}"""
        try:
            pinstance, _ = self._get_pinstance_data(instance_id)
            # TODO: validate for name and version            
        except KeyError:
            return None, "Pipeline instance not found"
        
        try:
            data, err = pinstance.execute_request(instance_id, request,
                                                  REQUEST_PUT_TIMEOUT=5)
            return data, err
        except Exception as e:
            self.log.exception("Failed to execute request.{} {}".format(instance_id, e))
            return None, "Failed to execute request"

    def stop_pipelines(self)-> None:
        """Stop any running pipeline instances"""
        self.log.info('Stopping Pipelines ...')        
        for p in self._PIPELINES.values():
            for _id, pdata in p._INSTANCES.items():
                pinst = pdata["obj"]
                if pinst.is_running:
                    self.stop_instance(_id)
                    self.log.info('Pipeline instance stopped: {}'.format(_id))
        self.log.info('All pipelines stopped')

    def stop(self):
        """Stop pipleines and pipeline server """
        self.log.info('Stopping services ...')
        self.stop_pipelines()
        self.pserv.stop()
