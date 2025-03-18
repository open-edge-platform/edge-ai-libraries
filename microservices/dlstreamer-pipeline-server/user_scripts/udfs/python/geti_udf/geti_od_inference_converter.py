#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import logging

import base_od_inference_converter


class GetiODInferenceConverter(
        base_od_inference_converter.BaseODInferenceConverter):
    """Parses inference result from Geti OD model for ingestion into DCaaS"""

    def __init__(self):
        """
        Constructor
        """
        self.logger = logging.getLogger(__name__)

    def convert_inference_result(self, inference_result: dict):
        """
        Convert the inference result from Geti (COCO) format to the standardized DCaaS format

        Args:
            inference_result (dict): The inference result
        """
        boxes = []
        labels = []
        scores = []

        for annotation in inference_result['predictions']['annotations']:
            box = [
                annotation['shape']['x'], annotation['shape']['y'],
                annotation['shape']['width'], annotation['shape']['height']
            ]
            label = annotation['labels'][0]['name']
            score = annotation['labels'][0]['probability']
            boxes.append(box)
            labels.append(label)
            scores.append(score)

        self.logger.debug("boxes are = {}".format(boxes))
        self.logger.debug("labels are = {}".format(labels))
        self.logger.debug("scores are = {}".format(scores))

        if len(boxes):
            boxes = self.convert_x1y1wh_to_x1y1x2y2(boxes)

        self.logger.debug(
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

        self.logger.debug(
            "Geti to DCaaS format converted inference result = {}".format(
                converted_result))

        return converted_result
