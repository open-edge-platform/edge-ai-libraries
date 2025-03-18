#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Simple example UDF.
"""

import logging
from time import time_ns


class Udf:
    """Example UDF
    """

    def __init__(self, anomalous):
        """Constructor
        """
        self.anomalous = anomalous
        self.log = logging.getLogger("DUMMY ADD LABEL")
        self.log.debug(f"In {__name__}...")

    def process(self, frame, metadata):
        """[summary]

        :param frame: frame blob
        :type frame: numpy.ndarray
        :param metadata: frame's metadata
        :type metadata: str
        :return:  (should the frame be dropped, has the frame been updated,
                   new metadata for the frame if any)
        :rtype: (bool, numpy.ndarray, str)
        """
        class_list = []
        metadata["task"] = "classification"
        if self.anomalous.lower() == 'true':
            class_list.append('anomalous')
            metadata['detected_class'] = "anomalous"
            # For compatibility with DCaaS
            metadata['anomalous'] = 0.8
            metadata['non_anomalous'] = 0.2
        else:
            class_list.append('non_anomalous')
            metadata['detected_class'] = "non_anomalous"
            # For compatibility with DCaaS
            metadata['anomalous'] = 0.2
            metadata['non_anomalous'] = 0.8
        metadata["classes"] = class_list
        metadata["last_modified"] = time_ns()
        metadata["export_code"] = 0
        metadata["annotation_type"] = "auto"
        metadata["annotations"] = {"objects":[]}
        # metadata[self.class_name] = self.class_value
        # metadata["vehicle"] = "false"
        # metadata["Person"] = "true"
        # metadata["Person_score"] = 0.8
        # metadata["last_modified"] = time_ns()
        # metadata["export_code"] = 0
        # metadata["annotation_type"] = "auto"
        # metadata["annotations"] = {
        #     "objects": [
        #         {
        #             "bbox": [1122.0, 422.0, 1437.0, 880.0],
        #             "center": (1279.5, 1158.5),
        #             "label": "Person",
        #             "score": 0.6475692391395569,
        #             "attributes": {"dummy":"dummy"}
        #         }
        #     ]
        # }
        return False, None, metadata
