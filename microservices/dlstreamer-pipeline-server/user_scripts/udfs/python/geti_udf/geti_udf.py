#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import cv2
import logging
import os
import datetime
from time import time
from time import time_ns
from geti_sdk.deployment import Deployment
from geti_sdk.utils import show_image_with_annotation_scene

import geti_od_inference_converter

EII_MODE = True if os.getenv('RUN_MODE') == "EII" else False

metadata_converters = {
    'geti_to_dcaas': geti_od_inference_converter.GetiODInferenceConverter()
}


def _get_default_prediction(frame):
    prediction = {
        'annotations': [{
            'labels': [{
                'probability': 1,
                'name': 'No object',
                'color': '#000000ff',
                'id': None,
                'source': None
            }],
            'shape': {
                'x': 0,
                'y': 0,
                'width': frame.shape[1],
                'height': frame.shape[0],
                'type': 'RECTANGLE'
            },
            'modified': None,
            'id': None,
            'labels_to_revisit': None
        }],
        'media_identifier': None,
        'id': None,
        'modified': None,
        'labels_to_revisit_full_scene': None,
        'annotation_state_per_task': None,
        'kind': 'prediction',
        'maps': [],
        'feature_vector': None,
        'created': None
    }
    return prediction


class Udf:

    def __init__(self, deployment, device, visualize, metadata_converter=None):
        self.log = logging.getLogger('GETI_UDF')
        self.log.setLevel(logging.INFO)
        try:
            #Load deployment files
            self.deployment = Deployment.from_folder(deployment)
            #Load model file to inference device
            self.deployment.load_inference_models(device=device)
            self.viz = visualize

            self.log.info('Initializer deployment from %s',deployment)

            self.metadata_converter = metadata_converters[metadata_converter]

        except Exception as exc:
            if isinstance(exc, KeyError):
                self.log.debug(
                    "Invalid metadata converter specified! Using default metadata format"
                )
                self.metadata_converter = None
            else:
                self.log.error(exc)

    def process(self, frame, metadata):
        """
            Runs inference on a BGR image and outputs True if it detects object-of-interest and False if not
        """
        start = time()
        try:
            prediction = self.deployment.infer(frame)
            inf = time()
            if self.viz.upper() == 'TRUE':
                img_format = metadata['format']
                output = show_image_with_annotation_scene(frame,
                                                          prediction,
                                                          channel_order=img_format.lower(),
                                                          show_results=False)
                # output above is always bgr
                if img_format == 'RGB':
                    output= cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
            else:
                output = frame
            
            prediction.deidentify()
            prediction = prediction.to_dict()
        except AssertionError:
            self.log.warning('Encountered AssertionError')
            prediction = _get_default_prediction(frame)
            inf = time()
            output = frame

        metadata["task"] = "object_detection"
        if self.metadata_converter:
            metadata.update({
                'annotations':
                self.metadata_converter.convert_inference_result(
                    {'predictions': prediction}),
                'annotation_type': 'auto',
                'last_modified': time_ns(),
                'export_code': 0
            })
        else:
            metadata['predictions'] = prediction
        end = time()
        self.log.debug(
            "Inference time: {} \nViz time: {} \nTotal time: {}".format(
                ((inf - start) * 1000), ((end - inf) * 1000),
                ((end - start) * 1000)))
        self.log.debug("Predictions: {}".format(prediction))
        if os.getenv("ADD_UTCTIME_TO_METADATA","").lower() == "true" and "time" not in metadata:
            metadata["time"] = int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1e9)
        return False, output, metadata
