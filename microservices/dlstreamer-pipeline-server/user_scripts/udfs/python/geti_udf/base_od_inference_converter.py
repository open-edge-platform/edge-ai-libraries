#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import numpy as np
from abc import abstractmethod, ABC


class BaseODInferenceConverter(ABC):
    """Base class for object detection inference format conversion for ingestion into DCaaS"""

    def __init__(self):
        """
        Constructor
        """

    def convert_x1y1wh_to_x1y1x2y2(self, boxes: list):
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

    @abstractmethod
    def convert_inference_result():
        raise NotImplementedError
