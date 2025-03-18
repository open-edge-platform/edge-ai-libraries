#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Simple example UDF.
"""

class Udf:
    """Example UDF
    """
    def __init__(self, address, topic):
        """Constructor
        """
        print(f"In PUBLISHER {__name__}...")
        self.address = address
        self.topic = topic

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
        print("metadata: ", metadata)
        metadata['publisher_metadata'] = {
            'address': self.address,
            'topic': self.topic
            }
        return False, None, metadata
