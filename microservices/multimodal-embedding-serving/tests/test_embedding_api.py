# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the query/document/fused handler hooks and the endpoints using them.

Covers the ``BaseEmbeddingModel`` defaults, the ``EmbeddingModel`` dispatch to
them, the ``fused`` input of ``POST /embeddings`` and ``POST /v1/embeddings``.
Handlers are in-process fakes, so no model is downloaded or loaded.
"""

import base64
import io
import unittest
from typing import List
from unittest import mock

import numpy as np
import torch
from fastapi.testclient import TestClient
from PIL import Image

from src import app as app_module
from src.models.base import BaseEmbeddingModel
from src.wrapper import EmbeddingModel

GME_MODEL = "GME/gme-qwen2-vl-2b-instruct"


def _png_base64(color=(255, 0, 0), size=(4, 2)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class FakeTextHandler(BaseEmbeddingModel):
    """Embeds text ``t`` as ``[len(t), 0, 1]`` and records every ``encode_text`` call."""

    def __init__(self):
        super().__init__({"device": "CPU"})
        self.encode_text_calls: List[List[str]] = []

    def load_model(self) -> None:
        pass

    def encode_text(self, texts):
        texts = [texts] if isinstance(texts, str) else list(texts)
        self.encode_text_calls.append(texts)
        return torch.tensor([[float(len(text)), 0.0, 1.0] for text in texts])

    def encode_image(self, images, metrics_out=False):
        raise NotImplementedError

    def convert_to_openvino(self, ov_models_dir: str) -> tuple:
        return ()

    def get_embedding_dim(self) -> int:
        return 3


class PrefixingHandler(FakeTextHandler):
    """Marks queries and documents in the text, like instruction-wrapping handlers."""

    def prepare_query(self, text: str) -> str:
        return f"query: {text}"

    def prepare_documents(self, texts: List[str]) -> List[str]:
        return [f"doc: {text}" for text in texts]


class FakeFusedHandler(FakeTextHandler):
    """Fused-capable handler: pair ``i`` embeds as ``[len(text), width, height]``."""

    def __init__(self):
        super().__init__()
        self.encode_fused_calls = []

    def supports_fused(self) -> bool:
        return True

    def encode_fused(self, texts, images):
        self.encode_fused_calls.append((list(texts), list(images)))
        return torch.tensor(
            [[float(len(text)), float(image.width), float(image.height)] for text, image in zip(texts, images)]
        )


class TestBaseHandlerDefaults(unittest.TestCase):
    def test_encode_query_prepares_then_encodes_one_text(self):
        handler = PrefixingHandler()
        embedding = handler.encode_query("cat")
        self.assertEqual(handler.encode_text_calls, [["query: cat"]])
        self.assertEqual(tuple(embedding.shape), (1, 3))

    def test_encode_documents_prepares_then_encodes_the_batch(self):
        handler = PrefixingHandler()
        embeddings = handler.encode_documents(["a", "bb"])
        self.assertEqual(handler.encode_text_calls, [["doc: a", "doc: bb"]])
        self.assertEqual(tuple(embeddings.shape), (2, 3))

    def test_fused_is_unsupported_by_default(self):
        handler = FakeTextHandler()
        self.assertFalse(handler.supports_fused())
        with self.assertRaises(NotImplementedError):
            handler.encode_fused(["a"], [Image.new("RGB", (2, 2))])


class TestWrapperDispatch(unittest.TestCase):
    def test_embed_query_uses_handler_encode_query(self):
        handler = PrefixingHandler()
        with mock.patch.object(handler, "encode_query", wraps=handler.encode_query) as encode_query:
            vector = EmbeddingModel(handler).embed_query("cat")
        encode_query.assert_called_once_with("cat")
        self.assertEqual(vector, [float(len("query: cat")), 0.0, 1.0])

    def test_embed_documents_uses_handler_encode_documents(self):
        handler = PrefixingHandler()
        with mock.patch.object(handler, "encode_documents", wraps=handler.encode_documents) as encode_documents:
            vectors = EmbeddingModel(handler).embed_documents(["a", "bb"])
        encode_documents.assert_called_once_with(["a", "bb"])
        self.assertEqual([row[0] for row in vectors], [float(len("doc: a")), float(len("doc: bb"))])

    def test_supports_fused_follows_the_handler(self):
        self.assertFalse(EmbeddingModel(FakeTextHandler()).supports_fused())
        self.assertTrue(EmbeddingModel(FakeFusedHandler()).supports_fused())

    def test_fused_embeddings_convert_every_image_type_to_rgb(self):
        handler = FakeFusedHandler()
        images = [
            Image.new("L", (3, 2)),
            np.zeros((5, 4, 3), dtype=np.uint8),
            base64.b64decode(_png_base64(size=(7, 6))),
        ]
        vectors = EmbeddingModel(handler).get_fused_embeddings(["a", "bb", "ccc"], images)
        _, passed = handler.encode_fused_calls[0]
        self.assertTrue(all(isinstance(image, Image.Image) and image.mode == "RGB" for image in passed))
        self.assertEqual(vectors, [[1.0, 3.0, 2.0], [2.0, 4.0, 5.0], [3.0, 7.0, 6.0]])

    def test_fused_embedding_returns_one_vector(self):
        vector = EmbeddingModel(FakeFusedHandler()).get_fused_embedding("ab", Image.new("RGB", (3, 2)))
        self.assertEqual(vector, [2.0, 3.0, 2.0])

    def test_fused_embeddings_reject_bad_input_before_the_handler(self):
        handler = FakeFusedHandler()
        model = EmbeddingModel(handler)
        image = Image.new("RGB", (2, 2))
        for texts, images in (([], []), (["a", "b"], [image]), ([1], [image]), (["a"], ["not an image"])):
            with self.subTest(texts=texts, images=images), self.assertRaises(ValueError):
                model.get_fused_embeddings(texts, images)
        self.assertEqual(handler.encode_fused_calls, [])

    def test_fused_embeddings_need_a_fused_model(self):
        with self.assertRaises(RuntimeError):
            EmbeddingModel(FakeTextHandler()).get_fused_embeddings(["a"], [Image.new("RGB", (2, 2))])


class EndpointTestCase(unittest.TestCase):
    """Runs the app with ``handler`` loaded as ``GME_MODEL``, without the startup hook."""

    handler_class = FakeFusedHandler

    def setUp(self):
        self.handler = self.handler_class()
        patches = [
            mock.patch.object(app_module, "embedding_model", EmbeddingModel(self.handler)),
            mock.patch.object(app_module.settings, "EMBEDDING_MODEL_NAME", GME_MODEL),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        # Not used as a context manager, so the startup hook does not load a real model.
        self.client = TestClient(app_module.app)


class TestEmbeddingsEndpoint(EndpointTestCase):
    def post(self, payload):
        return self.client.post("/embeddings", json={"model": GME_MODEL, "input": payload})

    def test_single_text_is_a_query_and_a_list_is_documents(self):
        with mock.patch.object(self.handler, "encode_query", wraps=self.handler.encode_query) as encode_query, \
                mock.patch.object(self.handler, "encode_documents", wraps=self.handler.encode_documents) as encode_documents:
            self.assertEqual(self.post({"type": "text", "text": "cat"}).status_code, 200)
            self.assertEqual(self.post({"type": "text", "text": ["a", "b"]}).status_code, 200)
        encode_query.assert_called_once_with("cat")
        encode_documents.assert_called_once_with(["a", "b"])

    def test_fused_items_are_embedded_in_order(self):
        downloaded = Image.new("RGB", (9, 8))
        with mock.patch.object(app_module, "download_image", mock.AsyncMock(return_value=downloaded)) as download:
            response = self.post({
                "type": "fused",
                "items": [
                    {"text": "first", "image": {"type": "image_url", "image_url": "https://example.com/a.png"}},
                    {"text": "second!", "image": {"type": "image_base64", "image_base64": _png_base64(size=(4, 2))}},
                ],
            })
        self.assertEqual(response.status_code, 200, response.text)
        download.assert_awaited_once_with("https://example.com/a.png")
        self.assertEqual(response.json()["embedding"], [[5.0, 9.0, 8.0], [7.0, 4.0, 2.0]])
        texts, _ = self.handler.encode_fused_calls[0]
        self.assertEqual(texts, ["first", "second!"])

    def test_fused_input_shape_is_validated(self):
        image = {"type": "image_base64", "image_base64": _png_base64()}
        bad_inputs = {
            "no items": {"type": "fused", "text": "a"},
            "empty items": {"type": "fused", "items": []},
            "missing image": {"type": "fused", "items": [{"text": "a"}]},
            "unknown image type": {"type": "fused", "items": [{"text": "a", "image": {"type": "video_url", "video_url": "x"}}]},
            "extra field": {"type": "fused", "items": [{"text": "a", "image": image, "extra": 1}]},
            "non-string text": {"type": "fused", "items": [{"text": 1, "image": image}]},
        }
        for name, payload in bad_inputs.items():
            with self.subTest(name):
                self.assertEqual(self.post(payload).status_code, 422)
        self.assertEqual(self.handler.encode_fused_calls, [])


class TestFusedUnsupported(EndpointTestCase):
    handler_class = FakeTextHandler

    def test_fused_input_needs_a_fused_model(self):
        response = self.client.post("/embeddings", json={
            "model": GME_MODEL,
            "input": {"type": "fused", "items": [{"text": "a", "image": {"type": "image_base64", "image_base64": _png_base64()}}]},
        })
        self.assertEqual(response.status_code, 400)

    def test_capabilities_report_fused_support(self):
        self.assertFalse(self.client.get("/model/capabilities").json()["supports_fused"])


class TestOpenAIEmbeddingsEndpoint(EndpointTestCase):
    def post(self, **fields):
        return self.client.post("/v1/embeddings", json={"model": GME_MODEL, **fields})

    def test_inputs_are_embedded_as_documents(self):
        with mock.patch.object(self.handler, "encode_documents", wraps=self.handler.encode_documents) as encode_documents:
            response = self.post(input=["a", "bbb"])
        self.assertEqual(response.status_code, 200, response.text)
        encode_documents.assert_called_once_with(["a", "bbb"])
        body = response.json()
        self.assertEqual(body["object"], "list")
        self.assertEqual(body["model"], GME_MODEL)
        self.assertEqual(body["usage"], {"prompt_tokens": 0, "total_tokens": 0})
        self.assertEqual(
            body["data"],
            [
                {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 1.0]},
                {"object": "embedding", "index": 1, "embedding": [3.0, 0.0, 1.0]},
            ],
        )

    def test_a_single_string_gives_one_embedding(self):
        response = self.post(input="ab")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"][0]["embedding"], [2.0, 0.0, 1.0])
        self.assertEqual(self.handler.encode_text_calls, [["ab"]])

    def test_base64_is_little_endian_float32(self):
        response = self.post(input="ab", encoding_format="base64")
        self.assertEqual(response.status_code, 200, response.text)
        encoded = response.json()["data"][0]["embedding"]
        np.testing.assert_array_equal(np.frombuffer(base64.b64decode(encoded), dtype="<f4"), [2.0, 0.0, 1.0])

    def test_model_may_be_named_by_alias_or_bare_name(self):
        for model in ("Alibaba-NLP/gme-Qwen2-VL-2B-Instruct", "gme-qwen2-vl-2b-instruct"):
            with self.subTest(model):
                response = self.client.post("/v1/embeddings", json={"model": model, "input": "a"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["model"], model)

    def test_rejected_requests(self):
        cases = {
            "other model": ({"model": "CLIP/clip-vit-b-16", "input": "a"}, 400),
            "unknown model": ({"model": "no-such-model", "input": "a"}, 400),
            "other dimensions": ({"model": GME_MODEL, "input": "a", "dimensions": 2}, 400),
            "empty list": ({"model": GME_MODEL, "input": []}, 422),
            "token ids": ({"model": GME_MODEL, "input": [1, 2]}, 422),
            "unknown encoding": ({"model": GME_MODEL, "input": "a", "encoding_format": "int8"}, 422),
        }
        for name, (payload, status) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.client.post("/v1/embeddings", json=payload).status_code, status)
        self.assertEqual(self.handler.encode_text_calls, [])

    def test_matching_dimensions_are_accepted(self):
        self.assertEqual(self.post(input="a", dimensions=3).status_code, 200)

    def test_model_not_loaded(self):
        with mock.patch.object(app_module, "embedding_model", None):
            self.assertEqual(self.post(input="a").status_code, 503)


if __name__ == "__main__":
    unittest.main()
