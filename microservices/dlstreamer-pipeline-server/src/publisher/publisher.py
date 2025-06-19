#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""EII Pipeline Server results publisher.
"""
import gi

gi.require_version('Gst', '1.0')
# pylint: disable=wrong-import-position
import os
import json
import queue
import string
import random
import re
import copy
import cv2
import threading as th
import numpy as np
import datetime
from time import time_ns
from gi.repository import Gst
from distutils.util import strtobool
from gstgva.util import gst_buffer_data
from typing import Dict, List

from src.server.gstreamer_app_source import GvaFrameData
from src.common.log import get_logger

from utils import publisher_utils as utils
from src.publisher.mqtt.mqtt_publisher import MQTTPublisher
from src.publisher.opcua.opcua_publisher import OPCUAPublisher
from src.publisher.s3.s3_writer import S3Writer


class Publisher:
    """EII Pipeline Server publisher thread.
    """

    def __init__(self, app_cfg, 
                 pub_cfg, 
                 queue,
                 request:str=None,
                 add_timestamp:bool=True, 
                 append_pipeline_name_to_topic=strtobool(os.getenv("APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC","false"))):
        """Constructor

        .. note:: This method immediately starts the publishing thread.

        :param json app_cfg: Pipeline configuration
        :param cfg.Publisher pub_config: ConfigManager publisher configuration
        :param queue.Queue queue: Python queue of data to publish
        """
        self.app_cfg = app_cfg
        self.pub_cfg = pub_cfg
        self.add_timestamp = add_timestamp
        self.append_pipeline_name_to_topic = append_pipeline_name_to_topic
        self.queue = queue
        self.request=request
        self.stop_ev = th.Event()
        self.done = False
        self.log = get_logger(__name__)

        self.convert_metadata_to_dcaas_format = self.app_cfg.get('convert_metadata_to_dcaas_format', False)

        self.img_handle_length = self.app_cfg.get('img_handle_length', 10)
        if self.img_handle_length <= 0:
            msg = "Invalid string length"
            self.log.error(msg)
            self.error_handler(msg)

        try:
            self.encoding, self.encoding_type, self.encoding_level = self._enable_encoding()
        except Exception as e:
            self.log.error(e)
            self.error_handler(e)

        self.frame_id = 0

        self.overlayed_frame = None
        self.send_overlayed_frame = False
        self.publish_raw_frame = self.app_cfg.get('publish_raw_frame', False)
        self.tags = self.app_cfg.get('tags', None)
        self.publishers = self._get_publishers()
        self.image_publisher = None # specific to image_ingestor. need to track

        self.tracking = self._is_tracking_enabled()

    def start(self):
        """Start the publisher.
        """
        self.log.debug('Starting publisher thread')
        self.th = th.Thread(target=self._run)
        self.th.start()

    def stop(self):
        """Stop the publisher.
        """
        if self.stop_ev.is_set():
            return
        self.stop_ev.set()
        self.th.join()
        self.th = None
        if os.getenv('RUN_MODE') == "EII":  #todo: check if this is needed
            for p in self.publishers:
                if isinstance(p, EdgeGrpcPublisher):
                    #Close eis publisher on thread exit.
                    p.close()
        self.log.info("Stopped publisher thread")

    def error_handler(self, msg):
        self.log.error('Error in publisher thread: {}'.format(msg))
        self.done = True

    def set_pipeline_info(self, name, version, instance_id, get_pipeline_status):
        self.pipeline_name = name
        self.pipeline_version = version
        self.pipeline_instance_id = instance_id
        self.get_pipeline_status = get_pipeline_status

    def _get_meta_publisher_config(self,meta_destination):
        """Get config for meta publishers
        :param meta_destination: Frame destination
        """
        if isinstance(meta_destination, dict):
            if "type" in meta_destination and meta_destination["type"] == "mqtt":
                self.mqtt_config = meta_destination
                self.request["destination"].pop("metadata") # Remove metadata from destination if no more metadata publishers
            elif "type" in meta_destination and meta_destination["type"] == "opcua":
                self.opcua_config = meta_destination
                self.request["destination"].pop("metadata") # Remove metadata from destination if no more metadata publishers
        elif isinstance(meta_destination, list):
            for dest in meta_destination:
                if "type" in dest and dest["type"] == "mqtt":
                    self.mqtt_config = dest
                elif "type" in dest and dest["type"] == "opcua":
                    self.opcua_config = dest
                self.request["destination"]["metadata"].remove(dest)
            if len(self.request["destination"]["metadata"]) == 0: # Remove the metadata from destination if list is empty
                self.request["destination"].pop("metadata")

        # if no mqtt config in REST request, check if mqtt config is in app_cfg
        if not self.mqtt_config and self.app_cfg.get("mqtt_publisher"):
            self.mqtt_config = self.app_cfg.get("mqtt_publisher")
        if not self.opcua_config and self.app_cfg.get("opcua_publisher"):
            self.opcua_config = self.app_cfg.get("opcua_publisher")

    def _get_frame_publisher_config(self,frame_destination):
        """Get config for frame publishers
        :param frame_destination: Frame destination
        """
        if isinstance(frame_destination, dict):
            if "type" in frame_destination and frame_destination["type"] == "s3_write":
                self.s3_config = frame_destination
                self.request["destination"].pop("frame") # Remove frame from destination if no more frame publishers

        elif isinstance(frame_destination, list):
            for dest in frame_destination:
                if "type" in dest and dest["type"] == "s3_write":
                    self.s3_config = dest
                    self.request["destination"]["frame"].remove(dest)
            if len(self.request["destination"]["frame"]) == 0: # Remove the frame from destination if list is empty
                self.request["destination"].pop("frame")

        # if no s3 config in REST request, check if s3 config is in app_cfg
        if not self.s3_config and self.app_cfg.get("S3_write"):
            self.s3_config = self.app_cfg["S3_write"]
        
    def _get_publishers(self):
        """Get publishers based on config.

        :return: Return list of publisher types
        :rtype: List
        """
        publishers = []
        self.mqtt_publish_frame = False
        self.opcua_publish_frame = False
        self.grpc_publish = False
        self.s3_config = None
        self.mqtt_config = None
        self.opcua_config = None

        try:
            launch_string = self.app_cfg.get("pipeline")
            pattern = r'appsink[^!]*name=destination'
            if re.search(pattern, launch_string):
                self.log.info("appsink destination found. Publisher will be initialized")
                # identify DLStreamer pipeline server publishers and pop them from the request
                if self.request is not None and "destination" in self.request:
                    frame_destination = copy.deepcopy(self.request.get("destination").get("frame", None))
                    meta_destination = copy.deepcopy(self.request.get("destination").get("metadata", None))
                    self._get_frame_publisher_config(frame_destination)
                    self._get_meta_publisher_config(meta_destination)
                    if not self.request["destination"]:
                        self.request.pop("destination")
                                
                # NOTE: always add S3_write first in the list of publishers, essential for blocking case
                if self.s3_config:
                    publishers.append(S3Writer(self.s3_config))
                if self.mqtt_config:
                    mqtt_pub = MQTTPublisher(self.mqtt_config)
                    self.mqtt_publish_frame = mqtt_pub.publish_frame
                    publishers.append(mqtt_pub)
                if self.opcua_config:
                    opcua_pub = OPCUAPublisher(self.opcua_config)
                    self.opcua_publish_frame = opcua_pub.publish_frame
                    publishers.append(opcua_pub)            
                        
            if os.getenv('RUN_MODE') == "EII":
                dev_mode = os.getenv("DEV_MODE", "False")
            else:
                dev_mode = "True"   # for grpc clients in standalone mode
            if self.pub_cfg:
                for pub in self.pub_cfg:
                    pub_topic = pub.get_topics()[0]
                    if self.append_pipeline_name_to_topic:
                        pub_topic += "_"+self.app_cfg.get('name')
                    publishers.append(EdgeGrpcPublisher(pub, pub_topic, dev_mode))
                    self.grpc_publish = True
                    self.log.info("Edge gRPC publisher initialized")
        except Exception as e:
            self.log.exception(f'Error in initializing publisher')
            self.error_handler(e)

        for p in publishers:
            if hasattr(p, 'overlay_annotation'):    # enable overalayed frame generation only if at least one publisher requires it
                if p.overlay_annotation:
                    self.send_overlayed_frame = p.overlay_annotation
                    self.log.info("Publisher {} requires overlayed frame. overlayed frames will be generated".format(p))
                    break
        self.log.info("overlayed frame generation is set to : {}".format(self.send_overlayed_frame))
        return publishers

    def _generate_image_handle(self, n):
        """Helper method to generate random alpha-numeric string

        :param n: random string length
        :type: int
        :return: Return random string
        :rtype: str
        """
        res = ''.join(
            random.choices(string.ascii_uppercase + string.digits, k=n))
        return res

    def _enable_encoding(self):
        """Method to check if encoding is enabled

        :return: Return whether encoding is enabled
        :rtype: bool
        """
        if 'encoding' in self.app_cfg.keys():
            encode_level = self.app_cfg['encoding']['level']
            encode_type = self.app_cfg['encoding']['type'].lower()
            if encode_type == "jpeg":
                if not (encode_level >= 0 and encode_level <= 100):
                    msg = "Invalid jpeg compression level"
                    self.log.error(msg)
                    self.error_handler(msg)
            elif encode_type == "png":
                if not (encode_level >= 0 and encode_level <= 9):
                    msg = "Invalid png compression level"
                    self.log.error(msg)
                    self.error_handler(msg)
            else:
                msg = "Invalid encoding type"
                self.log.error(msg)
                self.error_handler(msg)
            return True, encode_type, encode_level
        return False, None, None

    def _get_pipeline_encoding_properties(self):
        """Helper method to get properties of encoding element
        :return: Return encoding type and level
        :rtype: tuple where first item is encoding type and second item is encoding level
        """
        pipeline = self.app_cfg['pipeline']
        elements = pipeline.split('!')
        enc_type = None
        enc_level = None
        for element in elements:
            if "jpegenc" in element:
                match = re.search(r"\s*quality\s*=\s*(\w+)\s*", element)
                enc_type = "jpeg"
                enc_level = int(match.group(1)) if match else int(85)
            if "pngenc" in element:
                match = re.search(r"\s*compression-level\s*=\s*(\w+)\s*",
                                  element)
                enc_type = "png"
                enc_level = match.group(1) if match else "6"
        return enc_type, enc_level

    def _get_gst_buffer_info(self, results):
        """Helper method to get gst buffer data

        :param results: Video frame and additional metadata
        :type: Gst.Sample
        :return: Return frame
        :rtype: bytes
        :return: Return Meta data of the frame
        :rtype: Dict
        """
        # Get buffer data
        with gst_buffer_data(results.get_buffer(), Gst.MapFlags.READ) as data:
            frame = bytes(data)
            # Discarding gst buffer data
            del data

        caps = results.get_caps()
        # Get buffer width & height
        gst_struct = caps.get_structure(0)

        success, width = gst_struct.get_int('width')
        if not success:
            msg = "Failed to get buffer width"
            self.log.error(msg)
            self.error_handler(msg)
        success, height = gst_struct.get_int('height')
        if not success:
            msg = "Failed to get buffer height"
            self.log.error(msg)
            self.error_handler(msg)

        image_format = gst_struct.get_string('format')

        if image_format == 'RGBA' or image_format == 'BGRA':
            channels = 4
        elif image_format == 'GRAY8':
            channels = 1
        else:
            channels = 3

        if image_format is None:
            image_format = 'none'
            
        # Construct meta data
        meta_data = {
            'height': height,
            'width': width,
            'channels': channels,  # NOTE: This should not be constant
            'caps': caps.to_string(),
            'img_format': image_format
        }
        return frame, meta_data

    def _add_pipeline_info_metadata(self, meta_data):

        results = self.get_pipeline_status()
        curr_state = results.state.name
        results = results._asdict()
        results['state'] = curr_state

        meta_data['pipeline'] = {
            'name': self.pipeline_name,
            'version': self.pipeline_version,
            'instance_id': self.pipeline_instance_id,
            'status': results
        }

    def _is_tracking_enabled(self):
        """
        Checks if pipeline has tracking element
        :return: True if gvatrack is used in the pipeline
        :type: Bool
        """
        pipeline = self.app_cfg['pipeline']
        elements = pipeline.split('!')
        if any('gvatrack' in element for element in elements):
            return True
        return False

    def _add_tracking_info(self, meta_data: dict):
        if 'objects' in meta_data.get('annotations', {}):
            for annotation in meta_data['annotations']['objects']:
                id = None
                if self.tracking:
                    self.log.info("Tracking enabled: Deduplicating detections in metadata")
                    bbox = annotation['bbox']
                    for region in meta_data['gva_meta']:
                        gva_bbox = (region['x'],
                                    region['y'],
                                    region['width'] + region['x'],
                                    region['height'] + region['y'])
                        if bbox == list(gva_bbox):
                            id = region['object_id']
                            break
                    annotation.update({'object_id': id})
                else:
                    self.log.debug("Tracking disabled: Setting object id to None")
                    annotation.update({'object_id': id})
            meta_data.update({'gva_meta': []})
        return meta_data

    def _convert_inference_result(self, meta_data: dict):
        """
        Convert the inference result to the standardized DCaaS format
        :param metadata with inference results
        :type: Dict
        :return: metadata with inference results converted to DCaaS format
        :type: Dict
        """

        def convert_x1y1wh_to_x1y1x2y2(boxes: list):
            """
            Convert the bounding box from x1y1wh format (top left co-ordinates, width, height)
            to x1y1x2y2 format(top left and bottom right co-ordinates)

            Args:
                boxes (list): Bounding box in x1y1wh format (top left co-ordinates, width, height).
            """
            boxes = np.array(boxes)
            boxes = np.concatenate([boxes[:, :2], boxes[:, :2] + boxes[:, 2:]],
                                axis=-1)
            return boxes.tolist()

        boxes = []
        labels = []
        scores = []

        for annotation in meta_data['gva_meta']:
            box = [
                annotation['x'], annotation['y'],
                annotation['width'], annotation['height']
            ]
            label = annotation['tensor'][0]['label']
            score = annotation['tensor'][0]['confidence']
            boxes.append(box)
            labels.append(label)
            scores.append(score)

        self.log.debug("boxes are = {}".format(boxes))
        self.log.debug("labels are = {}".format(labels))
        self.log.debug("scores are = {}".format(scores))

        if len(boxes):
            boxes = convert_x1y1wh_to_x1y1x2y2(boxes)

        self.log.debug(
            "x1,y1,w,h to x1,y1,x2,y2 converted boxes = {}".format(boxes))
        converted_result = {'objects': []}

        for box, score, label in zip(boxes, scores, labels):
            converted_result['objects'].append({
                'bbox': box,
                'label': label,
                'score': score,
                'attributes': {
                    'occluded': False,
                    'rotation': 0.0
                }
            })

        self.log.debug(
            "DCaaS format converted inference result = {}".format(
                converted_result))

        meta_data.update({
                'annotations':
                    converted_result,
                'annotation_type':
                    'auto',
                'last_modified':
                    time_ns(),
                'export_code':
                    0
            })
        del meta_data['gva_meta']
        return meta_data

    # Preliminary logic for sequentially incrementing frame id added assuming the frames are not dropped
    # and publisher would receive all frames.
    # Some scenarios to handle in future for a more robust solution:
    # 1. Dropped frames (e.g. by UDFLoader element or videorate element).
    # 2. Add file name to metadata
    # 3. Alternate start-index
    # 4. Multiple video files - reset frame id for each new file.
    # 5. Multiple files read in a loop - reset the frame id for each new file/iteration.
    def _add_frame_id_metadata(self, meta_data):
        meta_data['frame_id'] = self.frame_id
        self.frame_id += 1

    def _publish(self, frame, meta_data):
        """Publish frame/metadata to message bus

        :param frame: video frame
        :type: bytes
        :param meta_data: Meta data
        :type: Dict
        """
        if self.add_timestamp:
            meta_data['time'] = int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1e9)

        for publisher in self.publishers:
            # add data to S3, and block publish for others if enabled
            if isinstance(publisher,S3Writer):
                publisher.queue.append((frame, meta_data))
                                
                if publisher.s3_metadata_write_wait:
                # we assume only one S3 writer is present in the list of publishers, and the very first publisher 
                    if not publisher.s3write_complete.is_set():
                        publisher.s3write_complete.wait()
                    publisher.s3write_complete.clear()
                continue
            
            publisher.queue.append((frame, meta_data))

    def _run(self):
        """Private thread run method.
        """
        self.log.debug('Publisher thread started')

        try:
            while not self.stop_ev.is_set():
                try:
                    results = self.queue.get(timeout=0.5)
                    self.log.debug("Received results from app dest queue")
                    if not results:
                        continue

                    try:
                        frame, meta_data = self._get_gst_buffer_info(
                            results.sample)
                    except ValueError as e:
                        self.log.error(
                            f"Value error occured when getting gst buffer data {e}"
                        )
                        continue

                    if 'img_handle' not in meta_data.keys():
                        meta_data['img_handle'] = self._generate_image_handle(
                            self.img_handle_length)

                    if results.video_frame:
                        utils.get_gva_meta_messages(results.video_frame,
                                                    meta_data)
                        meta_data['gva_meta'] = utils.get_gva_meta_regions(
                            results.video_frame)


                    # raw frame:
                    #    - if encoding params set or publish raw frame is not enabled, encode frame with opencv.
                    #      Any issues with encoding, throw error.
                    #    - Else publish raw frame
                    # (pipeline) encoded frame:
                    #    - Update metadata (encoding type/level)
                    if meta_data['caps'].split(',')[0] == "video/x-raw":
                        self.log.debug("Processing raw frame")
                        if self.mqtt_publish_frame or self.grpc_publish or self.opcua_publish_frame or self.s3_config:
                            if (self.encoding == True) or (not self.publish_raw_frame):
                                self.log.debug("Encoding frame of format {}".format(meta_data["img_format"]))
                                try:
                                    if meta_data.get("task", None) is None and self.send_overlayed_frame:
                                        self.send_overlayed_frame = False
                                        self.log.debug("task key is missing in metadata. overriding overlaying annotation to False")
                                    frame, meta_data['encoding_type'], meta_data[
                                        'encoding_level'] = utils.encode_frame(
                                            self.encoding_type, self.encoding_level,
                                            frame, meta_data['height'],
                                            meta_data['width'],
                                            channels=meta_data['channels'],
                                            meta_data=meta_data)
                                    frame = frame[1].tobytes()
                                    ret_ov = meta_data.pop('overlayText', None)  # upon overlay, discard overlay text, if present
                                    if ret_ov is not None:
                                        self.log.debug("Discarded overlay text from metadata")
                                except ValueError as e:
                                    self.log.error(
                                        f"Value error occured when encoding the image {e}"
                                    )
                                    self.error_handler(e)
                                except cv2.error as e:
                                    self.log.error(
                                        f"CV2 error occured when encoding the image {e}"
                                    )
                                    self.error_handler(e)
                        else:
                            self.log.debug("Publishing raw frame")
                    else:
                        self.log.debug(
                            "Encoded frame received, disabled opencv encoding"
                        )
                        meta_data['encoding_type'], meta_data[
                            'encoding_level'] = self._get_pipeline_encoding_properties(
                            )

                    self._add_pipeline_info_metadata(meta_data)
                    self._add_frame_id_metadata(meta_data)
                    if self.tags:
                        meta_data['tags'] = self.tags
                    self._add_tracking_info(meta_data)
                    if self.convert_metadata_to_dcaas_format:
                        self._convert_inference_result(meta_data)
                    if self.s3_config:
                        s3_metadata = self._add_s3_metadata(meta_data, self.s3_config)
                        meta_data.update(s3_metadata)

                    # TODO: put into clients respective queues
                    self._publish(frame, meta_data)

                    # Discarding frame
                    del frame

                except queue.Empty:
                    continue
        except Exception as e:
            # TODO: Check for more specific errors, attempt reconnect?
            self.log.exception(f'Error in publisher thread: {e}')
            self.error_handler(e)
            
    def _add_s3_metadata(self, meta_data: Dict[str, str], s3_cfg: Dict[str, str]) -> Dict[str, str]:
        """
        Add S3 metadata to the existing metadata
        :param meta_data: Existing metadata
        :type: Dict
        :param s3_cfg: S3 configuration
        :type: Dict
        :return: Return S3 metadata
        :rtype: Dict
        """
        # identify encoding for file extension
        ext = ""
        if meta_data['caps'].split(',')[0] == "image/jpeg":
            ext = ".jpg"
        elif meta_data['caps'].split(',')[0] == "image/png":
            ext = ".png"
        
        s3_metadata = {
            'S3_meta': {
                'bucket': s3_cfg.get('bucket'),
                'key': s3_cfg.get('folder_prefix', "dlstreamer_pipeline_server")+f"/{meta_data['img_handle']}"+ext,
            }
        }
        return s3_metadata