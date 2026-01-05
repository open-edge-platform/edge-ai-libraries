# This file was downloaded from https://github.com/intel-retail/automated-self-checkout
# This script is not part of the ViPPET tool. It was obtained from the above repository and is used here for the retail pipeline purposes.
'''
* Copyright (C) 2023 Intel Corporation.
*
* SPDX-License-Identifier: Apache-2.0
'''

from json import decoder
import numpy as np
from gstgva import VideoFrame
from gi.repository import Gst, GObject
import sys
import gi
gi.require_version('Gst', '1.0')
Gst.init(sys.argv)

# The net output is a blob with the shape 30, 1, 37
# in the format W, B, L, where:
#    W - output sequence length
#    B - batch size
#    # , where # - special blank character for CTC decoding algorithm.
#    L - confidence distribution across alphanumeric
#           symbols: 0123456789abcdefghijklmnopqrstuvwxyz
# The network output can be decoded by CTC Greedy Decoder/CTC Beam decoder

# This extension implements CTC Greedy Decoder


class OCR:
    W = 30
    B = 1
    L = 37

    ALPHABET = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
                "a", "b", "c", "d", "e", "f", "g",
                "h", "i", "j", "k", "l", "m", "n", "o", "p", "q",
                "r", "s", "t", "u", "v", "w", "x", "y", "z", "#"]

    def __init__(self, threshold=0.5):
        self.threshold = threshold

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
                            if index == OCR.L-1:
                                continue
                            label += OCR.ALPHABET[index]
                        if label:
                            tensor.set_label(label)
        except Exception as e:
            print(str(e))

        return True
