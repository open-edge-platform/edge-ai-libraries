#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import logging
import json

class AddDetectionRoi:

    def __init__(self):
        self.log = logging.getLogger('Add detection ROI')

    def process(self, frame):
        """
            Reads metadata associated with the video frame and if in expected format, adds ROIs to video frame.
        """
        messages = frame.messages()
        print(frame.video_info().height, frame.video_info().width)

        for msg in messages:
            msg = json.loads(msg)

            if 'objects' in msg.get('annotations', {}):  # DCaaS compatible metadata
                for annotation in msg['annotations']['objects']:
                    x1, y1, x2, y2 = annotation['bbox']
                    _ = frame.add_region(
                        x=x1,
                        y=y1,
                        w=x2-x1,
                        h=y2-y1,
                        label=annotation['label'],
                        confidence=annotation['score'],
                        normalized=False)               
        return True