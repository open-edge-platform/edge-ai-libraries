#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Simple example UDF.
"""

import logging

class Udf:
    """Example UDF
    """
    def __init__(self):
        """Constructor
        """
        print("test")
        self.log = logging.getLogger('DUMMY')
        self.log.debug(f"In {__name__}...")
        print("test")

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
        print(f"processing python")
        metadata["python"] = "Python UDF dummy message"
        return False, None, metadata
