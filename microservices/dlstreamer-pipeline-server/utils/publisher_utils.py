#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Utilities
"""
import base64
import numpy as np
import cv2
import json
import codecs
import pickle

from geti_sdk.utils import show_image_with_annotation_scene

def encode_frame(enc_type, enc_level, frame, height, width, channels, meta_data=None):
    """Helper method to encode given frame

    :param frame: input frame
    :type: bytes
    :param height: height of the input frame
    :type: int
    :param width: width of the input frame
    :type: int
    :return: Return encoded frame
    :rtype: tuple where the first item is (bool, numpy frame) followed by encoding type and level
    """
    enc_img = None
    
    if not enc_type:
        enc_type = "jpeg"
    
    if not enc_level:
        enc_level = 85

    if meta_data is None:
        raise ValueError("Meta data not given!")
    
    data = np.frombuffer(frame, dtype="uint8")
    if (meta_data["img_format"] == "NV12") or (meta_data["img_format"] == "I420"):
        # Create a numpy array from the NV12 buffer
        y_size = width * height
        uv_size = width * height // 2
        y_plane = np.frombuffer(data[:y_size], dtype=np.uint8).reshape((height, width))
        uv_plane = np.frombuffer(data[y_size:y_size + uv_size], dtype=np.uint8).reshape((height // 2, width))
 
        # Merge Y and UV planes into a single NV12 image
        data = np.vstack((y_plane, uv_plane))
    else:
        data = data.reshape((height, width, channels))

    # convert all image data to BGR format
    if meta_data["img_format"] == "RGB":
        bgr_data = cv2.cvtColor(data, cv2.COLOR_RGB2BGR)
    elif meta_data["img_format"] == "GRAY8":
        bgr_data = cv2.cvtColor(data, cv2.COLOR_GRAY2BGR)
    elif meta_data["img_format"] == "NV12":
        # Convert NV12 to BGR format using OpenCV
        bgr_data = cv2.cvtColor(data, cv2.COLOR_YUV2BGR_NV12)
    elif meta_data["img_format"] == "I420":
        # Convert I420 to BGR format using OpenCV
        bgr_data = cv2.cvtColor(data, cv2.COLOR_YUV2BGR_I420)
    else:
        bgr_data = data.copy()     # assuming data is already BGR, remove read-only property
    
    channel_order = "bgr"
    if enc_type == 'jpeg':
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, enc_level]
        enc_img = cv2.imencode('.jpg', bgr_data, encode_param)
    if enc_type == 'png':
        encode_param = [cv2.IMWRITE_PNG_COMPRESSION, enc_level]
        enc_img = cv2.imencode('.png', bgr_data, encode_param)
    return enc_img, enc_type, enc_level

def get_gva_tensors(video_frame):
    """Helper method to get gva tensors

    :param video_frame: Video Frame containing ROI and associated messages
    :type: gstgva.video_frame.VideoFrame
    :return: tensor metadata and tensor blobs
    :rtype: Dict, List
    """
    tensor_meta = {}
    tensor_data=[]
    tensor_meta["dims"] = []
    tensor_meta["name"] = []
    for tensor in (video_frame.tensors()):
        tensor_meta["dims"].append(tensor.dims())
        tensor_meta["name"].append(tensor.name())
        tensor_data.append(base64.b64encode(tensor.data().tobytes()).decode('utf-8'))

    return tensor_meta, tensor_data

def get_gva_meta_regions(video_frame):
    """Helper method to get gva region

    :param video_frame: Video Frame containing ROI and associated messages
    :type: gstgva.video_frame.VideoFrame
    :return: ROI meta data
    :rtype: Dict
    """
    gva_meta = []
    regions = list(video_frame.regions())
    for region in regions:
        rect = region.rect()
        meta = {
            'x': rect.x,
            'y': rect.y,
            'height': rect.h,
            'width': rect.w,
            'object_id': region.object_id(),
        }

        tensors = list(region.tensors())
        tensor_meta = []
        for tensor in tensors:
            tmeta = {
                'name': tensor.name(),
                'confidence': tensor.confidence(),
                'label_id': tensor.label_id()
            }

            if not tensor.is_detection():
                tmeta['label'] = tensor.label()
            else:
                tmeta['label'] = region.label()

            tensor_meta.append(tmeta)

        meta['tensor'] = tensor_meta
        gva_meta.append(meta)

    return gva_meta

def get_gva_meta_messages(video_frame, meta_data):
    """Helper method to get gva messages

    :param video_frame: Video Frame containing ROI and associated messages
    :type: gstgva.video_frame.VideoFrame
    :param meta_data: Meta data
    :type: Dict
    """
    messages = list(video_frame.messages())
    # Add all messages
    for msg in messages:
        msg = json.loads(msg)
        meta_data.update(msg)