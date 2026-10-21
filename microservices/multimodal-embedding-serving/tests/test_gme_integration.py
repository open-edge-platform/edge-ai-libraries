# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the GME handler, the query/document/fused SDK paths and REST.

The OpenVINO runtime is replaced by a fake that records every call, so nothing
here compiles or runs the multi-GB GME package. Package resolution itself
(``package_ir_files``) is pure Python and runs for real against a fake
package of empty-but-present files.
"""

import base64
import json
import os
import tempfile
import threading
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

import numpy as np
import torch
from fastapi.testclient import TestClient
from PIL import Image

import src.app as app_module
from src.models import get_model_handler, list_available_models
from src.models.base import BaseEmbeddingModel
from src.models.config import get_model_config, resolve_model_id
from src.models.gme_runtime import GmeOpenVINO, package_ir_files
from src.models.handlers import gme_handler
from src.models.handlers.gme_handler import GMEHandler
from src.wrapper import EmbeddingModel

MODEL_ID = "GME/gme-qwen2-vl-2b-instruct"
PACKAGE = "gme-qwen2-vl-2b-instruct-openvino"
DIM = 1536
ALL_PRECISIONS = ("fp32", "int8", "int4")


def _vector(seed: str) -> np.ndarray:
    """A deterministic unit vector per input, so order and pairing are checkable."""
    rng = np.random.default_rng(int.from_bytes(seed.encode(), "little") % (2**32))
    vector = rng.standard_normal(DIM).astype(np.float32)
    return vector / np.linalg.norm(vector)


def _image_key(image: Image.Image) -> str:
    return "img:" + ",".join(map(str, image.convert("RGB").getpixel((0, 0))))


class FakeTokenizer:
    def __call__(self, text):
        return {"input_ids": list(range(len(text.split())))}


class FakeRuntime:
    """Records calls the way GmeOpenVINO would receive them."""

    _prompt = staticmethod(GmeOpenVINO._prompt)

    def __init__(self, model_dir, device="CPU", precision=None, streams=1, cache_dir=None, **_):
        self.model_dir = Path(model_dir)
        self.config = json.loads((self.model_dir / "gme_openvino_config.json").read_text())
        self.precision, _, _ = package_ir_files(self.model_dir, self.config, precision)
        self.device = device
        self.streams = streams
        self.cache_dir = cache_dir
        self.embedding_dim = int(self.config["embedding_dim"])
        self.max_length = self.config["processor"]["max_length"]
        self.batch_mode = "per_sample"
        self.processor = type("P", (), {"tokenizer": FakeTokenizer()})()
        self.calls = []
        self.delay = 0.0

    def _record(self, kind, keys, **kwargs):
        self.calls.append((kind, list(keys), kwargs))
        if self.delay:
            time.sleep(self.delay)
        return np.stack([_vector(f"{kind}|{key}") for key in keys])

    def get_text_embeddings(self, texts, instruction=None, is_query=True, batch_size=32, show_progress_bar=True):
        return self._record("text", texts, instruction=instruction, is_query=is_query,
                            batch_size=batch_size, show_progress_bar=show_progress_bar)

    def get_image_embeddings(self, images, instruction=None, is_query=True, batch_size=32, show_progress_bar=True):
        assert all(isinstance(image, Image.Image) for image in images)
        return self._record("image", [_image_key(image) for image in images], instruction=instruction,
                            is_query=is_query, batch_size=batch_size, show_progress_bar=show_progress_bar)

    def get_fused_embeddings(self, texts, images, instruction=None, is_query=True, batch_size=32,
                             show_progress_bar=True):
        assert all(isinstance(image, Image.Image) for image in images)
        keys = [f"{text}+{_image_key(image)}" for text, image in zip(texts, images)]
        return self._record("fused", keys, instruction=instruction, is_query=is_query,
                            batch_size=batch_size, show_progress_bar=show_progress_bar)


def _image(color=(255, 0, 0)) -> Image.Image:
    return Image.new("RGB", (32, 32), color)


def _image_b64(color=(255, 0, 0)) -> str:
    buffer = BytesIO()
    _image(color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _write_package(root: Path, shipped=("int8",), skip=(), default="int4", dim=DIM) -> Path:
    """A package whose config lists all precisions but which ships only ``shipped``."""
    package = Path(root) / PACKAGE
    package.mkdir(parents=True)
    config = {
        "embedding_dim": dim,
        "processor": {"min_image_tokens": 256, "max_image_tokens": 1280, "max_length": 1800, "padding_side": "right"},
        "precisions": {p: {"language": f"gme_language_{p}.xml", "visual": f"gme_visual_{p}.xml"}
                       for p in ALL_PRECISIONS},
        "default_precision": default,
    }
    (package / "gme_openvino_config.json").write_text(json.dumps(config))
    names = list(GMEHandler.PROCESSOR_FILES)
    for p in shipped:
        names += [f"gme_language_{p}.xml", f"gme_language_{p}.bin", f"gme_visual_{p}.xml", f"gme_visual_{p}.bin"]
    for name in names:
        if name not in skip:
            (package / name).write_text("x")
    return package


class GMETestCase(unittest.TestCase):
    """Provides a temporary models directory and the fake runtime."""

    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for name in ("OV_PERFORMANCE_MODE", "OPENVINO_PERFORMANCE_MODE", "OV_ENABLE_MODEL_CACHE",
                     "OV_CACHE_DIR", "EMBEDDING_OV_CACHE_DIR", "INFER_BATCH_SIZE"):
            os.environ.pop(name, None)
        self._tmp = tempfile.TemporaryDirectory()
        self.models_dir = Path(self._tmp.name)
        self._runtime = mock.patch.object(gme_handler, "GmeOpenVINO", FakeRuntime)
        self._runtime.start()

    def tearDown(self):
        self._runtime.stop()
        self._tmp.cleanup()
        self._env.stop()

    def make_handler(self, load=True, use_openvino=True, device="CPU", **env):
        os.environ.update(env)
        if load and not (self.models_dir / PACKAGE).exists():
            _write_package(self.models_dir)
        handler = get_model_handler(MODEL_ID, device=device, ov_models_dir=str(self.models_dir),
                                    use_openvino=use_openvino)
        if load:
            handler.load_model()
        return handler


class TestRegistryAndPackage(GMETestCase):
    def test_registered_and_listed(self):
        self.assertIn("gme-qwen2-vl-2b-instruct", list_available_models()["GME"])
        self.assertIsInstance(self.make_handler(load=False), GMEHandler)
        self.assertEqual(resolve_model_id("Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"), MODEL_ID)
        self.assertEqual(resolve_model_id("gme-qwen2-vl-2b-instruct"), MODEL_ID)
        with self.assertRaises(ValueError):
            resolve_model_id("GME/unknown")

    def test_no_gme_specific_settings(self):
        config = get_model_config(MODEL_ID)
        self.assertEqual(config["package_dir"], PACKAGE)
        for key in ("precision", "embedding_dim", "query_instruction", "fused_instruction"):
            self.assertNotIn(key, config)

    def test_precision_is_the_one_the_package_ships(self):
        # The config's default_precision is int4, but only int8 IRs are present.
        handler = self.make_handler()
        self.assertEqual(handler.precision, "int8")
        self.assertEqual(handler.runtime.precision, "int8")

    def test_default_precision_breaks_a_tie(self):
        _write_package(self.models_dir, shipped=ALL_PRECISIONS, default="fp32")
        self.assertEqual(self.make_handler().precision, "fp32")

    def test_ambiguous_package_fails(self):
        _write_package(self.models_dir, shipped=("fp32", "int8"), default="int4")
        with self.assertRaisesRegex(ValueError, "keep a single precision"):
            self.make_handler(load=False).load_model()

    def test_dim_comes_from_the_package(self):
        _write_package(self.models_dir, dim=1536)
        handler = self.make_handler()
        self.assertEqual(handler.get_embedding_dim(), 1536)
        self.assertEqual(EmbeddingModel(handler).get_embedding_length(), 1536)

    def test_metadata(self):
        handler = self.make_handler()
        self.assertTrue(handler.supports_text())
        self.assertTrue(handler.supports_image())
        self.assertTrue(handler.supports_video())
        self.assertTrue(handler.supports_fused())
        # The fixed template overhead is subtracted from the package max_length.
        self.assertLess(handler.get_max_text_tokens(), 1800)
        self.assertGreater(handler.get_max_text_tokens(), 1700)
        with self.assertRaises(NotImplementedError):
            handler.convert_to_openvino(str(self.models_dir))

    def test_cache_dir_is_opt_in_and_outside_the_package(self):
        self.assertIsNone(self.make_handler().runtime.cache_dir)
        cache = self.models_dir / "cache"
        handler = self.make_handler(OV_ENABLE_MODEL_CACHE="1", OV_CACHE_DIR=str(cache))
        self.assertEqual(handler.runtime.cache_dir, str(cache / PACKAGE))
        default = self.make_handler(OV_CACHE_DIR="", OV_ENABLE_MODEL_CACHE="true")
        self.assertEqual(default.runtime.cache_dir, str(self.models_dir / "ov_cache" / PACKAGE))

    def test_performance_mode_selects_streams(self):
        self.assertEqual(self.make_handler().runtime.streams, 1)
        self.assertEqual(self.make_handler(OV_PERFORMANCE_MODE="THROUGHPUT").runtime.streams, "auto")

    def test_indexed_gpu_device_is_passed_through(self):
        self.assertEqual(self.make_handler(device="GPU.0").runtime.device, "GPU.0")


class TestLoadFailures(GMETestCase):
    def test_openvino_disabled(self):
        _write_package(self.models_dir)
        with self.assertRaisesRegex(RuntimeError, "EMBEDDING_USE_OV=true"):
            self.make_handler(load=False, use_openvino=False).load_model()

    def test_missing_directory(self):
        with self.assertRaisesRegex(FileNotFoundError, "not found"):
            self.make_handler(load=False).load_model()

    def test_missing_package_config(self):
        (_write_package(self.models_dir) / "gme_openvino_config.json").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "gme_openvino_config.json"):
            self.make_handler(load=False).load_model()

    def test_no_complete_ir_pair(self):
        for missing in ("gme_language_int8.xml", "gme_visual_int8.bin"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as root:
                _write_package(Path(root), skip=(missing,))
                handler = get_model_handler(MODEL_ID, ov_models_dir=root, use_openvino=True)
                with self.assertRaisesRegex(FileNotFoundError, "no complete language/visual IR pair"):
                    handler.load_model()

    def test_empty_weights(self):
        (_write_package(self.models_dir) / "gme_language_int8.bin").write_text("")
        with self.assertRaisesRegex(FileNotFoundError, "gme_language_int8.bin"):
            self.make_handler(load=False).load_model()

    def test_missing_processor_file(self):
        _write_package(self.models_dir, skip=("tokenizer.json",))
        with self.assertRaisesRegex(FileNotFoundError, "tokenizer.json"):
            self.make_handler(load=False).load_model()

    def test_unavailable_device_is_reported(self):
        _write_package(self.models_dir)

        def unavailable(*args, **kwargs):
            raise RuntimeError("OpenVINO device 'GPU' unavailable; found ['CPU']")

        with mock.patch.object(gme_handler, "GmeOpenVINO", unavailable):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                self.make_handler(load=False, device="GPU").load_model()

    def test_encode_before_load(self):
        with self.assertRaisesRegex(RuntimeError, "load_model"):
            self.make_handler(load=False).encode_documents(["a"])


class TestQueryDocumentFused(GMETestCase):
    def test_query_and_document_sides(self):
        handler = self.make_handler()
        model = EmbeddingModel(handler)
        query = model.embed_query("q")
        docs = model.embed_documents(["d1", "d2"])
        single = model.embed_documents(["d1"])
        self.assertEqual(
            [(kind, keys, kw["is_query"]) for kind, keys, kw in handler.runtime.calls],
            [
                ("text", ["q"], True),
                ("text", ["d1", "d2"], False),
                ("text", ["d1"], False),  # a one-element list is still a document batch
            ],
        )
        # The handler adds no prompt and no instruction: the runtime's default applies.
        self.assertTrue(all(kw["instruction"] is None for _, _, kw in handler.runtime.calls))
        self.assertTrue(all(kw["show_progress_bar"] is False for _, _, kw in handler.runtime.calls))
        self.assertEqual(np.asarray(query).shape, (DIM,))
        self.assertEqual(np.asarray(docs).shape, (2, DIM))
        self.assertEqual(np.asarray(single).shape, (1, DIM))
        np.testing.assert_allclose(docs[1], _vector("text|d2"), atol=1e-6)

    def test_encode_text_is_document_side(self):
        handler = self.make_handler()
        out = handler.encode_text("only")
        self.assertEqual(out.shape, (1, DIM))
        self.assertEqual(out.dtype, torch.float32)
        self.assertEqual(handler.runtime.calls[0][2]["is_query"], False)

    def test_batch_size_follows_infer_batch_size(self):
        handler = self.make_handler(INFER_BATCH_SIZE="7")
        handler.encode_documents(["a"])
        handler.encode_fused(["a"], [_image()])
        self.assertEqual([kw["batch_size"] for _, _, kw in handler.runtime.calls], [7, 7])

    def test_fused_pairs_in_order(self):
        handler = self.make_handler()
        model = EmbeddingModel(handler)
        red, green = (255, 0, 0), (0, 255, 0)
        out = model.get_fused_embeddings(["a", "b"], [_image(red), np.array(_image(green))])
        self.assertEqual(np.asarray(out).shape, (2, DIM))
        np.testing.assert_allclose(out[0], _vector(f"fused|a+{_image_key(_image(red))}"), atol=1e-6)
        np.testing.assert_allclose(out[1], _vector(f"fused|b+{_image_key(_image(green))}"), atol=1e-6)
        self.assertEqual(handler.runtime.calls[-1][2]["is_query"], False)
        self.assertEqual(np.asarray(model.get_fused_embedding("a", _image(red))).shape, (DIM,))

    def test_fused_accepts_encoded_bytes(self):
        model = EmbeddingModel(self.make_handler())
        out = model.get_fused_embeddings(["a"], [base64.b64decode(_image_b64())])
        self.assertEqual(np.asarray(out).shape, (1, DIM))

    def test_fused_rejects_bad_batches(self):
        model = EmbeddingModel(self.make_handler())
        with self.assertRaisesRegex(ValueError, "paired"):
            model.get_fused_embeddings(["a", "b"], [_image()])
        with self.assertRaisesRegex(ValueError, "at least one"):
            model.get_fused_embeddings([], [])
        with self.assertRaisesRegex(ValueError, "strings"):
            model.get_fused_embeddings([1], [_image()])
        with self.assertRaises(ValueError):
            model.get_fused_embeddings(["a"], ["/etc/passwd"])  # paths are never opened

    def test_image_and_video_paths(self):
        handler = self.make_handler()
        model = EmbeddingModel(handler)
        self.assertEqual(np.asarray(model.get_image_embedding_from_base64(_image_b64())).shape, (DIM,))
        self.assertIsInstance(handler.encode_image([_image()]), torch.Tensor)
        metrics = handler.encode_image([_image(), np.zeros((8, 8, 3), dtype=np.uint8)], metrics_out=True)
        self.assertEqual(set(metrics), {"embeddings", "inference_time_s", "processed_images"})
        self.assertEqual(metrics["processed_images"], 2)
        self.assertEqual(metrics["embeddings"].shape, (2, DIM))
        self.assertGreaterEqual(metrics["inference_time_s"], 0.0)
        frames = model.get_video_embeddings([[_image((1, 2, 3)), _image((4, 5, 6)), _image((7, 8, 9))]])
        self.assertEqual(np.asarray(frames).shape, (3, DIM))
        self.assertEqual(handler.runtime.calls[0][0], "image")
        self.assertFalse(handler.runtime.calls[0][2]["is_query"])

    def test_sampled_video_uses_metrics_path(self):
        model = EmbeddingModel(self.make_handler())
        batches = [[_image((1, 1, 1)), _image((2, 2, 2))], [_image((3, 3, 3))]]
        with mock.patch("src.wrapper.extract_batched_frames", return_value=iter(batches)):
            out = model.get_video_sampled_embeddings("video.mp4")
        self.assertEqual(np.asarray(out).shape, (3, DIM))

    def test_concurrent_calls_keep_inputs_apart(self):
        handler = self.make_handler()
        handler.runtime.delay = 0.005
        model = EmbeddingModel(handler)
        results, errors = {}, []
        active = {"now": 0, "max": 0}
        original = handler.runtime._record

        def tracking(kind, keys, **kwargs):
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
            try:
                return original(kind, keys, **kwargs)
            finally:
                active["now"] -= 1

        handler.runtime._record = tracking

        def work(index):
            try:
                if index % 3 == 0:
                    results[index] = (f"text|q{index}", model.embed_query(f"q{index}"))
                elif index % 3 == 1:
                    results[index] = (f"text|d{index}", model.embed_documents([f"d{index}"])[0])
                else:
                    image = _image((index, 0, 0))
                    results[index] = (f"fused|f{index}+{_image_key(image)}",
                                      model.get_fused_embeddings([f"f{index}"], [image])[0])
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(24)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 24)
        self.assertEqual(active["max"], 1)  # one public call at a time
        sides = {keys[0]: kw["is_query"] for _, keys, kw in handler.runtime.calls}
        for index, (key, vector) in results.items():
            np.testing.assert_allclose(vector, _vector(key), atol=1e-6)
        self.assertTrue(all(sides[f"q{i}"] for i in range(0, 24, 3)))
        self.assertFalse(any(sides[f"d{i}"] for i in range(1, 24, 3)))


class RecordingHandler(BaseEmbeddingModel):
    """A legacy-style handler that only implements the original hooks."""

    def __init__(self):
        super().__init__({"device": "CPU"})
        self.model = object()
        self.calls = []

    def load_model(self):
        pass

    def prepare_query(self, text):
        self.calls.append(("prepare_query", text))
        return f"Q:{text}"

    def prepare_documents(self, texts):
        self.calls.append(("prepare_documents", list(texts)))
        return [f"D:{text}" for text in texts]

    def encode_text(self, texts):
        self.calls.append(("encode_text", list(texts)))
        return torch.ones(len(texts), 4)

    def encode_image(self, images, metrics_out=False):
        return torch.ones(len(images), 4)

    def convert_to_openvino(self, ov_models_dir):
        return ()


class TestLegacyHandlers(unittest.TestCase):
    def test_default_dispatch_is_unchanged(self):
        handler = RecordingHandler()
        model = EmbeddingModel(handler)
        self.assertEqual(model.embed_query("x"), [1.0] * 4)
        self.assertEqual(model.embed_documents(["a", "b"]), [[1.0] * 4] * 2)
        self.assertEqual(handler.calls, [
            ("prepare_query", "x"),
            ("encode_text", ["Q:x"]),
            ("prepare_documents", ["a", "b"]),
            ("encode_text", ["D:a", "D:b"]),
        ])

    def test_legacy_handlers_are_not_fused(self):
        handler = RecordingHandler()
        model = EmbeddingModel(handler)
        self.assertFalse(model.supports_fused())
        with self.assertRaisesRegex(RuntimeError, "not supported"):
            model.get_fused_embeddings(["a"], [_image()])
        with self.assertRaises(NotImplementedError):
            handler.encode_fused(["a"], [_image()])


class RESTTestCase(GMETestCase):
    def setUp(self):
        super().setUp()
        self._model_name = mock.patch.object(app_module.settings, "EMBEDDING_MODEL_NAME", MODEL_ID)
        self._model_name.start()
        self.handler = self.make_handler()
        self._model = mock.patch.object(app_module, "embedding_model", EmbeddingModel(self.handler))
        self._model.start()
        self.client = TestClient(app_module.app)

    def tearDown(self):
        self._model.stop()
        self._model_name.stop()
        super().tearDown()

    def post(self, payload, model=MODEL_ID, path="/embeddings"):
        return self.client.post(path, json={"model": model, **payload})

    @staticmethod
    def fused(*items):
        return {"input": {"type": "fused", "items": list(items)}}


class TestFusedREST(RESTTestCase):
    def test_base64_single_item_stays_two_dimensional(self):
        response = self.post(self.fused(
            {"text": "Figure 3 throughput", "image": {"type": "image_base64", "image_base64": _image_b64()}}))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(np.asarray(response.json()["embedding"]).shape, (1, DIM))
        self.assertEqual(self.handler.runtime.calls[-1][1][0].split("+")[0], "Figure 3 throughput")

    def test_data_url_base64(self):
        response = self.post(self.fused(
            {"text": "a", "image": {"type": "image_base64", "image_base64": "data:image/png;base64," + _image_b64()}}))
        self.assertEqual(response.status_code, 200, response.text)

    def test_url_items_use_the_safe_downloader(self):
        downloads = []

        async def fake_download(url):
            downloads.append(url)
            return np.array(_image((0, 0, 255)))

        with mock.patch.object(app_module, "download_image", fake_download):
            response = self.post(self.fused(
                {"text": "a", "image": {"type": "image_url", "image_url": "https://example.com/a.png"}},
                {"text": "b", "image": {"type": "image_base64", "image_base64": _image_b64()}},
            ))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(downloads, ["https://example.com/a.png"])
        self.assertEqual(np.asarray(response.json()["embedding"]).shape, (2, DIM))
        self.assertEqual([key.split("+")[0] for key in self.handler.runtime.calls[-1][1]], ["a", "b"])

    def test_private_and_local_urls_are_rejected(self):
        for url in ("http://127.0.0.1/secret.png", "file:///etc/passwd", "http://user:pw@example.com/a.png"):
            with self.subTest(url=url):
                response = self.post(self.fused({"text": "a", "image": {"type": "image_url", "image_url": url}}))
                self.assertEqual(response.status_code, 500)
                self.assertIn("allowed", response.json()["detail"])
        self.assertEqual(self.handler.runtime.calls, [])

    def test_invalid_structures_are_422(self):
        bad_inputs = [
            {"type": "fused", "items": []},
            {"type": "fused"},
            {"type": "fused", "text": "no items"},
            {"type": "fused", "items": [{"text": "a"}]},
            {"type": "fused", "items": [{"image": {"type": "image_base64", "image_base64": "x"}}]},
            {"type": "fused", "items": [{"text": 1, "image": {"type": "image_base64", "image_base64": "x"}}]},
            {"type": "fused", "items": [{"text": "a", "image": {"type": "video_url", "video_url": "x"}}]},
            {"type": "fused", "items": [{"text": "a", "image": {
                "type": "image_base64", "image_base64": "x", "image_url": "https://example.com/a.png"}}]},
            {"type": "fused", "items": [{"text": "a", "image": {"type": "image_url"}}]},
            {"type": "fused", "items": [{"text": "a", "image": "https://example.com/a.png"}]},
        ]
        for payload in bad_inputs:
            with self.subTest(payload=payload):
                response = self.post({"input": payload})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.handler.runtime.calls, [])

    def test_unsupported_model_is_400(self):
        with mock.patch.object(app_module, "embedding_model", EmbeddingModel(RecordingHandler())):
            response = self.post(self.fused(
                {"text": "a", "image": {"type": "image_base64", "image_base64": _image_b64()}}))
        self.assertEqual(response.status_code, 400)

    def test_uninitialized_model_is_503(self):
        with mock.patch.object(app_module, "embedding_model", None):
            response = self.post(self.fused(
                {"text": "a", "image": {"type": "image_base64", "image_base64": _image_b64()}}))
        self.assertEqual(response.status_code, 503)

    def test_capabilities(self):
        body = self.client.get("/model/capabilities").json()
        self.assertTrue(body["supports_fused"])
        self.assertEqual(body["modalities"], ["image", "text"])
        self.assertTrue(body["supports_video"])
        with mock.patch.object(app_module, "embedding_model", EmbeddingModel(RecordingHandler())):
            self.assertFalse(self.client.get("/model/capabilities").json()["supports_fused"])


class TestExistingREST(RESTTestCase):
    def test_text_string_is_query_and_list_is_documents(self):
        query = self.post({"input": {"type": "text", "text": "q"}})
        docs = self.post({"input": {"type": "text", "text": ["d"]}})
        self.assertEqual(np.asarray(query.json()["embedding"]).shape, (DIM,))
        self.assertEqual(np.asarray(docs.json()["embedding"]).shape, (1, DIM))
        self.assertEqual([kw["is_query"] for _, _, kw in self.handler.runtime.calls], [True, False])

    def test_image_base64(self):
        response = self.post({"input": {"type": "image_base64", "image_base64": _image_b64()}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(np.asarray(response.json()["embedding"]).shape, (DIM,))

    def test_video_frames(self):
        frames = [{"type": "image_base64", "image_base64": _image_b64(c)} for c in ((1, 1, 1), (2, 2, 2))]
        response = self.post({"input": {"type": "video_frames", "video_frames": frames}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(np.asarray(response.json()["embedding"]).shape, (2, DIM))

    def test_model_mismatch_is_400(self):
        self.assertEqual(self.post({"input": {"type": "text", "text": "q"}}, model="CLIP/clip-vit-b-32").status_code,
                         400)


class TestOpenAIREST(RESTTestCase):
    def post_openai(self, payload, model=MODEL_ID):
        return self.post(payload, model=model, path="/v1/embeddings")

    def test_list_input(self):
        response = self.post_openai({"input": ["a", "b"]})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["object"], "list")
        self.assertEqual(body["model"], MODEL_ID)
        self.assertEqual([(item["object"], item["index"]) for item in body["data"]],
                         [("embedding", 0), ("embedding", 1)])
        self.assertEqual(np.asarray([item["embedding"] for item in body["data"]]).shape, (2, DIM))
        np.testing.assert_allclose(body["data"][1]["embedding"], _vector("text|b"), atol=1e-6)
        self.assertEqual(body["usage"], {"prompt_tokens": 0, "total_tokens": 0})
        # The OpenAI protocol has no query side: every input is a document.
        self.assertEqual(self.handler.runtime.calls[-1][2]["is_query"], False)

    def test_string_input_and_base64(self):
        response = self.post_openai({"input": "a", "encoding_format": "base64"})
        self.assertEqual(response.status_code, 200, response.text)
        decoded = np.frombuffer(base64.b64decode(response.json()["data"][0]["embedding"]), dtype="<f4")
        np.testing.assert_allclose(decoded, _vector("text|a"), atol=1e-6)

    def test_aliases_of_the_loaded_model_are_accepted(self):
        for name in ("Alibaba-NLP/gme-Qwen2-VL-2B-Instruct", "gme-qwen2-vl-2b-instruct"):
            with self.subTest(name=name):
                self.assertEqual(self.post_openai({"input": ["a"]}, model=name).status_code, 200)
        self.assertEqual(self.post_openai({"input": ["a"]}, model="CLIP/clip-vit-b-32").status_code, 400)
        self.assertEqual(self.post_openai({"input": ["a"]}, model="unknown").status_code, 400)

    def test_dimensions(self):
        self.assertEqual(self.post_openai({"input": ["a"], "dimensions": DIM}).status_code, 200)
        self.assertEqual(self.post_openai({"input": ["a"], "dimensions": 512}).status_code, 400)

    def test_invalid_inputs_are_422(self):
        for payload in ({"input": []}, {"input": [1, 2]}, {"input": [[1, 2]]},
                        {"input": "a", "encoding_format": "x"}, {}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post_openai(payload).status_code, 422)

    def test_uninitialized_model_is_503(self):
        with mock.patch.object(app_module, "embedding_model", None):
            self.assertEqual(self.post_openai({"input": ["a"]}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
