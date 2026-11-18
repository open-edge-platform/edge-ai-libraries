# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A deterministic stand-in for a backbone runtime, for tests without OpenVINO."""

from __future__ import annotations

import numpy as np


class FakeRuntime:
    """Deterministic stand-in for a backbone: letters are single tokens."""

    hidden_size = 8
    device = "CPU"

    def __init__(self):
        self._table = np.random.default_rng(0).normal(size=(4096, self.hidden_size))
        self.tokenizer = self  # check_tokenizer only needs encode

    def encode(self, text):
        return np.asarray([ord(c) % 4096 for c in text], dtype=np.int64)

    chat_style = "qwen"  # hard prompts render in the Qwen template

    def strip_prompt_prefix(self, ids):
        return np.asarray(ids, dtype=np.int64)  # no tokenizer-level prefix

    def embed(self, ids):
        return self._table[np.asarray(ids, dtype=np.int64)][None]

    def last_hidden(self, embeds, mask=None):
        return embeds[0].mean(axis=0)

    def label_rows(self, ids):
        return self._table[np.asarray(ids, dtype=np.int64)]
