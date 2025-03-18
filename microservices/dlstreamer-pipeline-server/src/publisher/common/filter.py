#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

""" Filter frames/metadata to be published.
"""
from src.common.log import get_logger

class Filter():
    """Filter
    """

    def __init__(self, filter):
        """Constructor
        """

        self.log = get_logger(f'{__name__})')

        try:
            self.type = filter['type']
            self.labels = filter.get('label_score', {})
        except:
            raise KeyError("Type for filter not specified")

    def _check_detection_filter(self, meta_data):
        """Check detection filter criteria
        :param meta_data: Meta data
        :type: Dict
        :return: True if filter criteria met, False if not.
        :rtype: Bool
        """
        #When metadata has detections results e.g 
        # ...'annotations': {'objects': [{'label': 'Person', 'score': 0.6827021241188049,
        # 'bbox': [873, 484, 1045, 702], 'attributes': {'rotation': 0, 'occluded': 0}}],...
        # ...'annotations': [{'labels_to_revisit': None,'shape': {'type': 'RECTANGLE', 'x': 196, 'height': 328, 'y': 567, 'width': 272}, 
        # 'id': None 'labels': [{'id': None, 'probability': 0.527821958065033, 'source': None, 'color': '#25a18eff', 'name': 'Person'}], 'modified': None}...
        #if any of the detected objects in the current frame doesn't meet min threshold, skip
        #if there are no detections, skip       
        try:
            if 'objects' in meta_data.get('annotations', {}):
                detections = meta_data['annotations']['objects']
                for detection in detections:
                    threshold = self.labels[detection['label']]
                    if detection['score'] < threshold:
                        return False
            elif 'annotations' in meta_data.get('predictions', {}):
                detections = meta_data['predictions']['annotations']
                for detection in detections:
                    threshold = self.labels[detection['labels'][0]['name']]
                    if detection['labels'][0]['probability'] < threshold:
                        return False
            else:
                return False
        except:
            return False

        return True

    def _check_classification_filter(self, meta_data):
        """Check classification filter criteria
        :param meta_data: Meta data
        :type: Dict
        :return: True if filter criteria met, False if not.
        :rtype: Bool
        """
        try:
            for label in meta_data['classes']:
                if not self.labels.get(label, None):
                    continue
                if meta_data[label] < self.labels.get(label):
                    return False
            return True

        except KeyError:
            return False

    def check_filter_criteria(self, meta_data):
        """Check filter criteria
        :param meta_data: Meta data
        :type: Dict
        :return: True if filter criteria met, False if not.
        :rtype: Bool
        """
        # ..."filter": {
        #     "type": "detection"
        #     "label_score": {
        #         "person": 0.5,
        #         "vehicle": 0.6
        #     },...
        
        filter = False

        if self.type == "detection":
            filter = self._check_detection_filter(meta_data)
        
        if self.type == "classification":
            filter = self._check_classification_filter(meta_data)

        return filter