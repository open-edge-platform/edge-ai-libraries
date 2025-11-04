#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import numpy as np
import cv2
import logging
import argparse
from pathlib import Path
from time import time
from geti_sdk.deployment import Deployment


class GetiDetectionInference:

    def __init__(self, deployment, device, threshold=None):
        self.log = logging.getLogger('GETI_DETECTION_INFERENCE')
        #Load deployment files
        self.deployment = Deployment.from_folder(deployment)
        #Load model file to inference device
        self.deployment.load_inference_models(device=device)
        self.threshold = threshold if threshold else 0.0

        self.log.info('Initializer deployment from {}'.format(deployment))

    def process(self, frame):
        """
            Runs inference on a BGR image and outputs True if it detects object-of-interest and False if not
        """
        start = time()
        with frame.data() as image:
            predictions = self.deployment.infer(image)

            for annotation in predictions.to_dict()['annotations']:
                if annotation['labels'][0]['probability'] < self.threshold:
                    continue
                _ = frame.add_region(
                    x=annotation['shape']['x'],
                    y=annotation['shape']['y'],
                    w=annotation['shape']['width'],
                    h=annotation['shape']['height'],
                    label='{} | {:.2f}'.format(
                        annotation['labels'][0]['name'],
                        annotation['labels'][0]['probability']),
                    confidence=annotation['labels'][0]['probability'],
                    normalized=False)
        end = time()
        self.log.debug("Processing time for frame: {}".format(
            (end - start) * 1000))

        return True
