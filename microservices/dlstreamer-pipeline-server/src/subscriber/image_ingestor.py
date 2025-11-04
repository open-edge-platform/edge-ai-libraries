#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import base64
import io
import threading as th
import queue
import gi
from gi.repository import Gst
from gstgva.util import GVAJSONMeta
import json
import time

from src.common.log import get_logger

gi.require_version('Gst', '1.0')

MAX_REQUEST_QUEUE_SIZE = 100

class ImageIngestor:
    def __init__(self, input_queue, pipeline_config) -> None:
        self.gst_queue = input_queue    # gst compatible items are sent to this queue
        self.request_queue = queue.Queue(maxsize=MAX_REQUEST_QUEUE_SIZE)  # hold item from input request
        self.th = th.Thread(target=self._run, args=(self.request_queue,))
        self.stop_ev = th.Event()
        self.done = False
        self.log = get_logger(f'{__name__}')

    def start(self):
        self.th.start()

    def stop(self):
        self.log.info('stopping image ingestor')
        if self.stop_ev.is_set():
            return
        self.stop_ev.set()
        self.th.join()
        self.th = None

    def error_handler(self, msg):
        self.log.error('Error in ingestor thread: {}'.format(msg))
        self.log.info("clearing pending items from request queue...")
        while not self.request_queue.empty():   # so that it doesnot block the producer thread
            try:
                self.request_queue.get_nowait()
            except queue.Empty:
                break
        self.done = True

    def _run(self, request_queue: queue.Queue) -> None:
        while not self.stop_ev.is_set():
            try:
                item = request_queue.get(timeout=1)
                blob = None
                self.log.debug("Received request by image ingestor queue")

                # fetch any user metadata from the request
                additional_meta = item.get("custom_meta_data", {})

                # TODO: If the item contains a feature_vector, add it to the additional_meta dict

                if item["source"]["type"] == "file":
                    fp = item["source"]["path"]
                    additional_meta.update({"source_path": fp})
                    with open(fp,"rb") as f:
                        # Do something with the image and send it to gst input queue
                        blob = f.read()
                    additional_meta["source_path"] = fp

                elif item["source"]["type"] == "base64_image":
                    # Convert base64 encoded string into image blob
                    base64_str = item["source"]["data"]
                    additional_meta.update({"source_data": "base64_image"})
                    blob = base64.b64decode(base64_str)

                # Creating GstSample from raw bytes blob
                bufferLength = len(blob)

                # Allocate GstBuffer
                buf = Gst.Buffer.new_allocate(None, bufferLength, None)
                buf.fill(0, blob)

                # update any additional metadata
                if additional_meta:
                    GVAJSONMeta.add_json_meta(buf, json.dumps(additional_meta))

                # Create GstSample from GstBuffer
                gva_blob = Gst.Sample(buf, None, None, None)

                self.gst_queue.put(gva_blob)
                self.log.debug("Gst Sample sent to gst queue")
            except queue.Empty:
                time.sleep(0.005)
                continue
            except Exception as errmsg:
                self.error_handler(errmsg)
