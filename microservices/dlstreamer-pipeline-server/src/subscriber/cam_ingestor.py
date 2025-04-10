#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import ctypes
from ctypes import *
import os
import threading as th
import time
import numpy as np
import cv2
import queue
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import signal
from src.common.log import get_logger




class Frame(Structure):
        _fields_ = [('data', POINTER(c_char)),
                    ('height', c_int),
                    ('width', c_int),
                    ('channels', c_int),
                    ('bit_depth', c_int)]

class XirisCamIngestor:

    def __init__(self, queue, app_cfg):
        self.log = get_logger(f'{__name__}')
        self.queue = queue
        self.stop_ev = th.Event()
        self.done = False
        self.lib = ctypes.CDLL("/home/pipeline-server/xiris/build/libLinuxSample.so")
        self.lib.get_frame.restype = Frame
        self.lib.free_frame.argtypes = [ctypes.POINTER(ctypes.c_char)]
        self.lib.free_frame.restype = None
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGABRT, self.signal_handler)
        if 'xiris' in app_cfg.keys():
            if app_cfg['xiris']['ip_address']:
                os.environ["XirisCameraIP"] = app_cfg['xiris']['ip_address']
            os.environ["shutter_mode"] = str(app_cfg['xiris']['shutter_mode'])
            os.environ["FrameRate"] = str(app_cfg['xiris']['frame_rate'])
            os.environ["pixel_depth"] = str(app_cfg['xiris']['pixel_depth'])
            os.environ["flip_mode"] = str(app_cfg['xiris']['flip_mode'])
            os.environ["set_sharpen"] = str(app_cfg['xiris']['set_sharpen'])
            os.environ["focus"] = str(app_cfg['xiris']['focus'])
            os.environ["tone_map_curve_type"] = str(app_cfg['xiris']['tone_map_curve_type'])
            os.environ["tone_map_curve_value"] = str(app_cfg['xiris']['tone_map_curve_value'])
            os.environ["exposure_time"] = str(app_cfg['xiris']['exposure_time'])
            os.environ["auto_exposure_mode"] = str(app_cfg['xiris']['auto_exposure_mode'])
            os.environ["pilot_light_on"] = str(app_cfg['xiris']['pilot_light_on'])
            os.environ["pilot_light_power"] = str(app_cfg['xiris']['pilot_light_power'])


        self.camera_thread = th.Thread(target=self.camera_start)
        self.camera_thread.start()

    def error_handler(self, msg):
        self.log.error('Error in ingestor thread: {}'.format(msg))
        self.done = True

    def signal_handler(self, *args):
        self.log.info('Running signal handler and stopping camera..')
        self.lib.stop()

    def camera_start(self):
        self.log.info('starting camera application from ingestor')
        self.lib.start()

    def start(self):
        self.log.info('Starting ingestor thread')
        self.th = th.Thread(target=self._run)
        self.th.start()

    def stop(self):
        self.log.info('stopping camera app from ingestor stop function')
        self.lib.stop()
        if self.stop_ev.is_set():
            return
        self.stop_ev.set()
        self.th.join()
        self.th = None

    def _run(self):
        try:
            while not self.stop_ev.is_set():
                try:
                    res = self.lib.get_frame()
                    # length of the buffer in bytes is always as you expected via width * height * channels * depth/8
                    blob_size = res.height*res.width*res.channels*int(res.bit_depth/8)
                    if blob_size <= 0:
                        continue
                    # blob = res.data[:blob_size]
                    self.log.debug('Received blob from camera app height={} width={} channels={} depth={}'.format(res.height,res.width,res.channels,res.bit_depth))
                    # buf = Gst.Buffer.new_allocate(None, len(blob), None)
                    buf = Gst.Buffer.new_allocate(None, blob_size, None)
                    # buf.fill(0, blob)
                    buf.fill(0, res.data[:blob_size])
                    gst_blob = Gst.Sample(buf, None, None, None)
                    self.queue.put(gst_blob)
                    self.log.debug('gst blob added to input queue')
                    self.lib.free_frame(res.data)
                    # del blob
                except Exception as e:
                    self.lib.stop()
                    self.error_handler(e)
        except Exception as e:
            self.lib.stop()
            self.error_handler(e)
