# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np

from inference.multimodal.viclip_openvino import ViClipOpenVINOEmbedding


class CosmosOpenVINOEmbedding(ViClipOpenVINOEmbedding):
    """Cosmos-Embed1-224p OpenVINO towers with official pixel preprocessing."""

    PACKAGE_TYPES = {"cosmos-224p": ("cosmos", 256, 128, "bert")}
    MODEL_IDS = {"cosmos-224p": "nvidia/Cosmos-Embed1-224p"}

    def _pixels(self, frames):
        # Torch is used only for CPU pixel preprocessing.
        import torch
        from torchvision.transforms import InterpolationMode
        from torchvision.transforms.functional import resize

        pixels = np.stack([np.asarray(frame.convert("RGB")) for frame in frames])
        tensor = torch.from_numpy(pixels).permute(0, 3, 1, 2)
        if tuple(tensor.shape[-2:]) != (self.image_size, self.image_size):
            tensor = resize(tensor, [self.image_size, self.image_size],
                            InterpolationMode.BILINEAR, antialias=True)
        # Match the official uint8 resize before /255; the graph normalizes internally.
        return np.ascontiguousarray(tensor.float().numpy()[None] / 255.0, dtype=np.float32)