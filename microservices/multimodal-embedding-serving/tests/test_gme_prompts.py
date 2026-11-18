# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for GME prompt selection, in the runtime and in ``GMEHandler``.

GME picks the system prompt from the query/document side, so the same text has
a different embedding as a query than as a document. The runtime is built
without a model package: its processor and language request pool are fakes.
"""

import os
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from src.models.gme_runtime import (
    DEFAULT_INSTRUCTION,
    DEFAULT_QUERY_INSTRUCTION,
    GmeOpenVINO,
)
from src.models.handlers.gme_handler import GMEHandler


class FakeProcessor:
    """Records the prompts and gives every prompt the same four valid tokens."""

    def __init__(self):
        self.prompts = []

    def __call__(self, text, **kwargs):
        self.prompts.append(list(text))
        rows = len(text)
        return {
            "input_ids": np.arange(rows * 4, dtype=np.int64).reshape(rows, 4),
            "attention_mask": np.ones((rows, 4), dtype=np.int64),
        }


class FakePool:
    """Returns the first input id of each feed as a one-value embedding."""

    def run(self, feeds):
        return [feed["input_ids"][:, :1].astype(np.float32) for feed in feeds]


def make_runtime() -> GmeOpenVINO:
    runtime = GmeOpenVINO.__new__(GmeOpenVINO)
    runtime.processor = FakeProcessor()
    runtime.language_pool = FakePool()
    runtime.batch_mode = "per_sample"
    runtime.max_length = 64
    runtime.embedding_dim = 1
    runtime._no_images = np.empty((0, 1), dtype=np.float32)
    return runtime


def system_prompt(prompt: str) -> str:
    return prompt.split("<|im_start|>system\n", 1)[1].split("<|im_end|>", 1)[0]


class TestRuntimeInstruction(unittest.TestCase):
    def test_queries_and_documents_get_different_prompts(self):
        self.assertEqual(GmeOpenVINO._instruction(None, is_query=True), DEFAULT_QUERY_INSTRUCTION)
        self.assertEqual(GmeOpenVINO._instruction(None, is_query=False), DEFAULT_INSTRUCTION)
        self.assertNotEqual(DEFAULT_QUERY_INSTRUCTION, DEFAULT_INSTRUCTION)

    def test_an_explicit_instruction_applies_to_queries_only(self):
        self.assertEqual(GmeOpenVINO._instruction("Find a passage.", is_query=True), "Find a passage.")
        self.assertEqual(GmeOpenVINO._instruction("Find a passage.", is_query=False), DEFAULT_INSTRUCTION)

    def test_text_embeddings_use_the_side_prompt(self):
        runtime = make_runtime()
        runtime.get_text_embeddings(["cat"], is_query=True)
        runtime.get_text_embeddings(["cat"], is_query=False)
        query_prompt, document_prompt = (prompts[0] for prompts in runtime.processor.prompts)
        self.assertEqual(system_prompt(query_prompt), DEFAULT_QUERY_INSTRUCTION)
        self.assertEqual(system_prompt(document_prompt), DEFAULT_INSTRUCTION)
        self.assertTrue(query_prompt.endswith("<|im_start|>user\ncat<|im_end|>\n<|im_start|>assistant\n<|endoftext|>"))


class TestRuntimeBatching(unittest.TestCase):
    def test_text_is_chunked_by_batch_size_in_order(self):
        runtime = make_runtime()
        embeddings = runtime.get_text_embeddings(list("abcde"), batch_size=2)
        self.assertEqual([len(prompts) for prompts in runtime.processor.prompts], [2, 2, 1])
        # Each chunk restarts the fake input ids, so rows show where they came from.
        np.testing.assert_array_equal(embeddings[:, 0], [0, 4, 0, 4, 0])

    def test_no_batch_size_encodes_one_chunk(self):
        runtime = make_runtime()
        self.assertEqual(runtime.get_text_embeddings(list("abcde"), batch_size=None).shape, (5, 1))
        self.assertEqual(len(runtime.processor.prompts), 1)

    def test_image_and_fused_chunks_pair_texts_with_images(self):
        runtime = make_runtime()
        calls = []

        def encode_image_batch(texts, images, instruction):
            calls.append((texts, len(images), instruction))
            return np.zeros((len(images), 1), dtype=np.float32)

        runtime._encode_image_batch = encode_image_batch
        images = [Image.new("RGB", (28, 28))] * 3
        self.assertEqual(runtime.get_image_embeddings(images, is_query=False, batch_size=2).shape, (3, 1))
        self.assertEqual(runtime.get_fused_embeddings(["a", "b", "c"], images, batch_size=2).shape, (3, 1))
        self.assertEqual(calls, [
            ([None, None], 2, DEFAULT_INSTRUCTION),
            ([None], 1, DEFAULT_INSTRUCTION),
            (["a", "b"], 2, DEFAULT_QUERY_INSTRUCTION),
            (["c"], 1, DEFAULT_QUERY_INSTRUCTION),
        ])

    def test_invalid_inputs(self):
        runtime = make_runtime()
        image = Image.new("RGB", (28, 28))
        with self.assertRaises(ValueError):
            runtime.get_text_embeddings([])
        with self.assertRaises(ValueError):
            runtime.get_text_embeddings([None])
        with self.assertRaises(ValueError):
            runtime.get_image_embeddings([])
        with self.assertRaises(ValueError):
            runtime.get_fused_embeddings(["a", "b"], [image])
        with self.assertRaises(ValueError):
            runtime.get_fused_embeddings([], [])


class TestHandlerSides(unittest.TestCase):
    def make_handler(self) -> GMEHandler:
        handler = GMEHandler({
            "hf_model_id": "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct",
            "package_dir": "gme-qwen2-vl-2b-instruct-openvino",
            "use_openvino": True,
        })
        handler.runtime = mock.Mock(spec=GmeOpenVINO)
        for name in ("get_text_embeddings", "get_image_embeddings", "get_fused_embeddings"):
            getattr(handler.runtime, name).side_effect = lambda *args, **kwargs: np.zeros((1, 2), dtype=np.float32)
        return handler

    def test_query_and_document_text_sides(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GME_QUERY_INSTRUCTION", None)
            handler = self.make_handler()
        handler.encode_query("cat")
        handler.encode_documents(["cat"])
        handler.encode_text("cat")
        sides = [
            (call.args[0], call.kwargs["is_query"], call.kwargs["instruction"])
            for call in handler.runtime.get_text_embeddings.call_args_list
        ]
        self.assertEqual(sides, [(["cat"], True, None), (["cat"], False, None), (["cat"], False, None)])

    def test_query_instruction_from_environment(self):
        with mock.patch.dict(os.environ, {"GME_QUERY_INSTRUCTION": "Find a matching slide."}):
            handler = self.make_handler()
        handler.encode_query("cat")
        self.assertEqual(handler.runtime.get_text_embeddings.call_args.kwargs["instruction"], "Find a matching slide.")

    def test_images_and_fused_pairs_are_documents(self):
        handler = self.make_handler()
        image = Image.new("RGB", (28, 28))
        handler.encode_image([image])
        handler.encode_fused(["a"], [image])
        self.assertFalse(handler.runtime.get_image_embeddings.call_args.kwargs["is_query"])
        self.assertFalse(handler.runtime.get_fused_embeddings.call_args.kwargs["is_query"])
        self.assertTrue(handler.supports_fused())


if __name__ == "__main__":
    unittest.main()
