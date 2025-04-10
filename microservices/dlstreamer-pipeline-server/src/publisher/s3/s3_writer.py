#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""S3 Writer.
Publishes data from a pipeline with gstreamer app destination.
"""

# pylint: disable=wrong-import-position
import json
import os
import base64
import time
import threading as th
from collections import deque

from src.common.log import get_logger
from src.publisher.common.filter import Filter
from utils.s3_client import S3Client


DEFAULT_APPDEST_S3_QUEUE_SIZE = 1000


class S3Writer():
    """S3 Writer.
    """

    def __init__(self, config, qsize=DEFAULT_APPDEST_S3_QUEUE_SIZE):
        """Constructor
        :param json config: S3 publisher config
            the meta-data for the frame (df: True)
        """
        self.queue = deque(maxlen=qsize)
        self.stop_ev = th.Event()

        self.host = os.getenv("S3_STORAGE_HOST")
        self.port = os.getenv("S3_STORAGE_PORT")
        self.s3_storage_user = os.getenv("S3_STORAGE_USER")
        self.s3_storage_pass = os.getenv("S3_STORAGE_PASS")
        
        self.s3_bucket_name = config.get("bucket")
        self.s3_folder_prefix = config.get("folder_prefix", "edge_video_analytics")
        self.s3_metadata_write_wait = config.get("block", False)
        self.s3write_complete = th.Event()

        self.th = None
        self.log = get_logger(f'{__name__} ({self.s3_bucket_name})')
        if not self.host:
            self.log.error(f'Empty value given for S3_STORAGE_HOST. It cannot be blank')
            self.initialized=False
        if not self.port:
            self.log.error(f'Empty value given for S3_STORAGE_PORT. It cannot be blank')
            self.initialized=False
        else:
            self.port = int(self.port)
        if not self.s3_storage_user:
            self.log.error(f'Empty value given for S3_STORAGE_USER. It cannot be blank')
            self.initialized=False
        if not self.s3_storage_pass:
            self.log.error(f'Empty value given for S3_STORAGE_PASS. It cannot be blank')
            self.initialized=False

        self.log.info(f'Initializing S3 Writer for bucket - {self.s3_bucket_name} and key prefix - {self.s3_folder_prefix}')
        self.s3_client = S3Client(self.host, self.port, self.s3_storage_user, self.s3_storage_pass, self.s3_folder_prefix)
        if not self.s3_client.bucket_exists(self.s3_bucket_name):
            self.log.error(f"Given bucket name - {self.s3_bucket_name} does NOT exist or server is inaccessible")
            self.initialized=False    # error state  
            self.log.info("S3 Writer initializion failed")    
        else:
            self.initialized=True    # success state  
            self.log.info("S3 Writer initialized")

    def start(self):
        """Start publisher.
        """
        self.log.info("Starting S3 writer thread")
        self.th = th.Thread(target=self._run)
        self.th.start()

    def stop(self):
        """Stop publisher.
        """
        self.s3write_complete.set()
        if self.stop_ev.set():
            return
        self.stop_ev.set()
        if self.th:
            self.th.join()
            self.th = None
            self.log.info('S3 writer thread stopped')

    def error_handler(self, msg):
        self.log.error('Error in S3 thread: {}'.format(msg))
        self.stop()

    def _run(self):
        """Run method for publisher.
        """
        self.log.info("S3 writer thread started")
        try:
            while not self.stop_ev.is_set():
                try:
                    frame, meta_data = self.queue.popleft()
                    self._publish(frame, meta_data)
                except IndexError:
                    self.log.debug("No data in client queue")
                    time.sleep(0.005)
                    
        except Exception as e:
            self.error_handler(e)
    
    def _publish(self, frame, meta_data):
        """Write object data to s3 storage. 
        Upon successful upload, s3write_complete event is set which is required for unblock other publisher
        when block is set to True.

        :param frame: video frame
        :type: bytes
        :param meta_data: Meta data
        :type: Dict
        """
        ext = ""
        if meta_data['caps'].split(',')[0] == "image/jpeg" or meta_data['encoding_type']=='jpeg':
            ext = ".jpg"
        elif meta_data['caps'].split(',')[0] == "image/png" or meta_data['encoding_type']=='png':
            ext = ".png"
                
        object_path = self.s3_folder_prefix + "/" if not self.s3_folder_prefix.endswith("/") else self.s3_folder_prefix        
        object_name = f"{object_path}{meta_data['img_handle']}" + ext
        self.s3_client.publish(self.s3_bucket_name, object_name, payload=frame)
        self.s3write_complete.set()
