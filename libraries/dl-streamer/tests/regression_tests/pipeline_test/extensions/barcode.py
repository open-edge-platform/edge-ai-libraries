# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

import zxingcpp
import pyzbar.pyzbar as pyzbar
from pyzbar.pyzbar import ZBarSymbol
from server.common.utils import logging
from collections import OrderedDict
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.get_logger('barcode', is_static=True)


@dataclass
class DetectedObject:
    x: int
    y: int
    w: int
    h: int
    label: str
    confidence: float


class BarcodeDecoder(ABC):
    def __init__(self) -> None:
        pass

    @abstractmethod
    def decode(self, region_data):
        pass

    def convert_bytestring(self, barcode):
        if str(barcode):
            return barcode
        return barcode.decode('utf-8')


class PyZbar(BarcodeDecoder):
    BARCODE_TYPES = [ZBarSymbol.EAN2,
                     ZBarSymbol.EAN5,
                     ZBarSymbol.EAN8,
                     ZBarSymbol.UPCE,
                     ZBarSymbol.ISBN10,
                     ZBarSymbol.UPCA,
                     ZBarSymbol.EAN13,
                     ZBarSymbol.ISBN13,
                     ZBarSymbol.COMPOSITE,
                     ZBarSymbol.I25,
                     ZBarSymbol.DATABAR,
                     ZBarSymbol.DATABAR_EXP,
                     ZBarSymbol.CODABAR,
                     ZBarSymbol.CODE39,
                     ZBarSymbol.PDF417,
                     ZBarSymbol.SQCODE,
                     ZBarSymbol.CODE93,
                     ZBarSymbol.CODE128]

    def __init__(self) -> None:
        super().__init__()

    def decode(self, region_data):
        barcodes = []
        decodedObjects = pyzbar.decode(
            region_data, PyZbar.BARCODE_TYPES)
        for barcode in decodedObjects:
            (x, y, w, h) = barcode.rect
            new_label = "barcode: {}".format(
                self.convert_bytestring(barcode.data))
            barcode = DetectedObject(x, y, w, h, new_label, 0.9)
            logger.debug("Adding x {} y {} w {} h {} label {}".format(
                x, y, w, h, new_label))
            barcodes.append(barcode)
        return barcodes


class ZxingCpp(BarcodeDecoder):
    def __init__(self) -> None:
        super().__init__()

    def decode(self, region_data):
        barcodes = []
        barcode = zxingcpp.read_barcode(
            region_data, zxingcpp.BarcodeFormat.UPCA)
        if barcode is None:
            return []
        (x, y, w, h) = (barcode.position.top_left.x,
                        barcode.position.top_left.y, 0, 0)
        new_label = "barcode: {}".format(
            self.convert_bytestring(barcode.text))
        barcode = DetectedObject(x, y, w, h, new_label, 0.9)
        barcodes.append(barcode)
        return barcodes


class LRUCache:
    def __init__(self, max_tracked_objects):
        self.data = OrderedDict()
        self.capacity = max_tracked_objects

    def get(self, key: int) -> int:
        if key not in self.data:
            return None
        else:
            self.data.move_to_end(key)
            return self.data[key]

    def put(self, key: int, value: int) -> None:
        self.data[key] = value
        self.data.move_to_end(key)
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)


class BarcodeDetection:
    SUPPORTED_LIBRARIES = ["pyzbar", "zxingcpp"]

    def __init__(self, disable=False, decode_type="zxingcpp", reclassify_interval=-1, max_tracked_objects=100):
        self.disable = disable

        self.reclassify_interval = reclassify_interval
        self.frame_count = 0
        self.tracked_objects = LRUCache(max_tracked_objects)

        if self.disable:
            logger.info("Barcode disabled")

        if decode_type == "pyzbar":
            self.decoder = PyZbar()
        elif decode_type == "zxingcpp":
            self.decoder = ZxingCpp()

    def process_frame(self, frame):

        if self.disable:
            return True
        self.frame_count += 1
        skip_frame_processing = False
        if self.reclassify_interval != -1 and (self.reclassify_interval == 0 or (self.frame_count % self.reclassify_interval != 0)):
            skip_frame_processing = True

        regions = list(frame.regions())
        with frame.data() as frame_data:
            for region in regions:
                region_rect = region.rect()
                (o_x, o_y, _, _) = region_rect
                object_id = region.object_id()

                # Do not reclassify, re-use prior results
                tracked_objects_list = self.tracked_objects.get(object_id)
                if skip_frame_processing and (tracked_objects_list is not None):
                    for tracked in tracked_objects_list:
                        x, y, w, h, label, confidence = tracked.x, tracked.y, tracked.w, tracked.h, tracked.label, tracked.confidence
                        logger.debug("Adding barcode region from tracked objects x {} y {} w {} h {} label {}".format(
                            x, y, w, h, label))
                        frame.add_region(
                            x+o_x, y+o_y, w, h, label+'_tracked', confidence)
                    continue

                region_data = frame_data[region_rect.y:region_rect.y +
                                         region_rect.h, region_rect.x:region_rect.x+region_rect.w]
                barcodes = self.decoder.decode(region_data)
                tracked_barcodes = []
                for barcode in barcodes:
                    logger.debug("Adding barcode region x {} y {} w {} h {} label {}".format(
                        barcode.x+o_x, barcode.y+o_y, barcode.w, barcode.h, barcode.label))
                    frame.add_region(barcode.x+o_x, barcode.y+o_y, barcode.w, barcode.h,
                                     barcode.label, barcode.confidence)
                    tracked_object = DetectedObject(
                        barcode.x, barcode.y, barcode.w, barcode.h, barcode.label, barcode.confidence)
                    tracked_barcodes.append(tracked_object)
                self.tracked_objects.put(object_id, tracked_barcodes)
        return True
