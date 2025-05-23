# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

from json import decoder
import numpy as np
from gstgva import VideoFrame
from gi.repository import Gst, GObject
import sys
import gi
gi.require_version('Gst', '1.0')
Gst.init(sys.argv)

# For text-recognition-0012:
#  The net output is a blob with the shape 30, 1, 37 in the format W, B, L, where:
#    W - output sequence length
#    B - batch size
#    # , where # - special blank character for CTC decoding algorithm.
#    L - confidence distribution across alphanumeric symbols: 0123456789abcdefghijklmnopqrstuvwxyz
# The network output can be decoded by CTC Greedy Decoder/CTC Beam decoder
# This extension implements CTC Greedy Decoder

class OCR:
    MODEL_ATTRIBUTES = {"text-recognition-0012":
                            {
                                "W": 30,
                                "B": 1,
                                "L": 37,
                                "ALPHABET": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f", "g",
                                "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "#"]
                            },
                        "text-recognition-0014": {
                                "W": 16,
                                "B": 1,
                                "L": 37,
                                "ALPHABET": ["#", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f", "g",
                                "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"]
                            }
                        }


    def __init__(self, threshold=0.5, model="text-recognition-0012"):
        self.threshold = threshold
        self.model = model
        self.W = OCR.MODEL_ATTRIBUTES[model].get("W")
        self.B = OCR.MODEL_ATTRIBUTES[model].get("B")
        self.L = OCR.MODEL_ATTRIBUTES[model].get("L")
        self.ALPHABET = OCR.MODEL_ATTRIBUTES[model].get("ALPHABET")
        self.skip_index = self.ALPHABET.index("#")

    def softmax(self, value):
        e_value = np.exp(value - np.max(value))
        return e_value / e_value.sum()

    def process_frame(self, frame):
        try:
            for region in frame.regions():
                for tensor in region.tensors():
                    label = ""
                    if tensor["converter"] == "raw_data_copy":
                        data = tensor.data()
                        data = data.reshape(self.W, self.L)
                        for i in range(self.W):
                            conf_list = self.softmax(data[i][:])
                            x = self.softmax(conf_list)
                            highest_prob = max(x)
                            if highest_prob < self.threshold:
                                pass
                            index = np.where(x == highest_prob)[0][0]
                            if index == self.skip_index:
                                continue
                            label += self.ALPHABET[index]
                        if label:
                            tensor.set_label(label)
        except Exception as e:
            print(str(e))

        return True
