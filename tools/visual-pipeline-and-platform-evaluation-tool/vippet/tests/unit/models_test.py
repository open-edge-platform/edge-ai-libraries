# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``models.py``.

``SupportedModel`` (path resolution, ``exists_on_disk``) has no DB
dependency and is tested by direct construction. ``SupportedModelsManager``
is an in-memory cache populated from the `models`/`model_variants` DB
tables (see ``managers/model_manager_test.py``'s ``_AsyncDBTestCase`` for
the async-DB-touching sibling of this pattern); since ``reload()`` bridges
into async code via ``asyncio.run()`` internally, these tests stay plain
(non-async) ``TestCase``s and drive DB setup/teardown with their own
``asyncio.run`` calls.
"""

import asyncio
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Any

import database
import models as models_module
from models import GENAI_SENTINEL_FILE, SupportedModel, SupportedModelsManager
from orm_models import Model, ModelVariant


def _reset_supported_models_manager() -> None:
    SupportedModelsManager._instance = None


class TestSupportedModelPathsAndExists(unittest.TestCase):
    """``SupportedModel`` path resolution and ``exists_on_disk`` — no DB involved."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-models-path-")
        self._orig_models_path = models_module.MODELS_PATH
        models_module.MODELS_PATH = self._tmpdir

    def tearDown(self) -> None:
        models_module.MODELS_PATH = self._orig_models_path
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_relative_model_path_and_exists(self) -> None:
        xml_file = os.path.join(self._tmpdir, "modelA.xml")
        with open(xml_file, "w") as f:
            f.write("dummy")

        sm = SupportedModel(
            name="mA",
            display_name="Model A",
            source="public",
            model_type="image_classification",
            model_path="modelA.xml",
            model_proc=None,
        )
        self.assertEqual(sm.model_path_full, xml_file)
        self.assertTrue(sm.exists_on_disk())
        self.assertEqual(sm.model_proc_full, "")

    def test_relative_model_proc_is_joined_with_models_path(self) -> None:
        proc_file = os.path.join(self._tmpdir, "proc.json")
        with open(proc_file, "w") as f:
            f.write("{}")

        sm = SupportedModel(
            name="mB",
            display_name="Model B",
            source="public",
            model_type="object_detection",
            model_path="missing.xml",
            model_proc="proc.json",
        )
        self.assertEqual(sm.model_proc_full, proc_file)
        self.assertFalse(sm.exists_on_disk())

    def test_absolute_model_proc_is_used_as_is(self) -> None:
        proc_file = os.path.join(self._tmpdir, "abs_proc.json")
        with open(proc_file, "w") as f:
            f.write("{}")

        sm = SupportedModel(
            name="mC",
            display_name="Model C",
            source="public",
            model_type="object_detection",
            model_path="missing.xml",
            model_proc=proc_file,
            model_proc_is_full_path=True,
        )
        self.assertEqual(sm.model_proc_full, proc_file)


class TestSupportedModelGenAI(unittest.TestCase):
    """GenAI (vision_language_models) directory-based ``exists_on_disk``."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-models-genai-")
        self._orig_models_path = models_module.MODELS_PATH
        models_module.MODELS_PATH = self._tmpdir

    def tearDown(self) -> None:
        models_module.MODELS_PATH = self._orig_models_path
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make(self) -> SupportedModel:
        return SupportedModel(
            name="gemma3",
            display_name="Gemma 3",
            source="huggingface",
            model_type="vision_language_models",
            model_path="vlm/gemma3",
            model_proc="",
        )

    def test_no_directory_is_not_installed(self) -> None:
        self.assertFalse(self._make().exists_on_disk())

    def test_empty_directory_is_not_installed(self) -> None:
        model_dir = os.path.join(self._tmpdir, "vlm", "gemma3")
        os.makedirs(model_dir)
        self.assertFalse(self._make().exists_on_disk())

    def test_directory_with_unrelated_files_is_not_installed(self) -> None:
        model_dir = os.path.join(self._tmpdir, "vlm", "gemma3")
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, "graph.pbtxt"), "w") as f:
            f.write("dummy")
        self.assertFalse(self._make().exists_on_disk())

    def test_directory_with_sentinel_file_is_installed(self) -> None:
        model_dir = os.path.join(self._tmpdir, "vlm", "gemma3")
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, GENAI_SENTINEL_FILE), "w") as f:
            f.write("<ir/>")
        self.assertTrue(self._make().exists_on_disk())


class _DBTestCase(unittest.TestCase):
    """Base class wiring a fresh temp-file SQLite database + MODELS_PATH per test.

    ``SupportedModelsManager.reload()`` bridges into async code via
    ``asyncio.run()`` internally, so DB setup/teardown here uses its own
    ``asyncio.run`` calls rather than ``IsolatedAsyncioTestCase``.
    """

    def setUp(self) -> None:
        _reset_supported_models_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-models-db-")
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._models_path = os.path.join(self._tmpdir, "models")
        os.makedirs(self._models_path, exist_ok=True)

        self._orig_database_url = database.DATABASE_URL
        database.DATABASE_URL = f"sqlite+aiosqlite:///{self._db_path}"
        self._orig_models_path = models_module.MODELS_PATH
        models_module.MODELS_PATH = self._models_path

        os.environ["DB_SEED_ON_STARTUP"] = "false"
        asyncio.run(database.init_db())

    def tearDown(self) -> None:
        asyncio.run(database.close_db())
        database.DATABASE_URL = self._orig_database_url
        models_module.MODELS_PATH = self._orig_models_path
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_supported_models_manager()

    def _add_model(
        self,
        *,
        name: str,
        display_name: str | None = None,
        category: str = "object_detection",
        source: str = "public",
        hub: str | None = None,
        unsupported_devices: str | None = None,
        variants: list[dict[str, Any]],
    ) -> None:
        async def _insert() -> None:
            now = datetime.now(timezone.utc)
            async with database.async_session_maker() as session:
                model = Model(
                    name=name,
                    display_name=display_name or name,
                    description=None,
                    category=category,
                    source=source,
                    hub=hub or source,
                    unsupported_devices=unsupported_devices,
                    is_custom=False,
                    install_status="not_installed",
                    installed_at=None,
                    download_request=None,
                    created_at=now,
                )
                session.add(model)
                await session.flush()
                for v in variants:
                    session.add(
                        ModelVariant(
                            model_id=model.id,
                            name=v.get("name", name),
                            display_name=v["display_name"],
                            precision=v["precision"],
                            model_path=v["model_path"],
                            model_proc=v.get("model_proc"),
                            installed=v.get("installed", False),
                            installed_at=None,
                        )
                    )
                await session.commit()

        asyncio.run(_insert())

    def _touch(self, relative_path: str) -> None:
        """Create a real file under MODELS_PATH so ``exists_on_disk()`` sees it."""
        full_path = os.path.join(self._models_path, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        open(full_path, "w").close()


class TestSupportedModelsManagerReload(_DBTestCase):
    """``reload()``/``reload_async()`` populate ``_models`` from the DB."""

    def test_reload_builds_one_supported_model_per_variant(self) -> None:
        self._add_model(
            name="inst",
            display_name="Installed Model",
            category="image_classification",
            source="public",
            unsupported_devices="NPU",
            variants=[
                {
                    "precision": "FP32",
                    "model_path": "inst.xml",
                    "display_name": "Installed Model (FP32)",
                }
            ],
        )
        self._touch("inst.xml")

        manager = SupportedModelsManager()
        manager.reload()

        all_supported = manager.get_all_supported_models()
        self.assertEqual(len(all_supported), 1)
        installed_models = manager.get_all_installed_models()
        self.assertEqual(len(installed_models), 1)
        self.assertEqual(installed_models[0].name, "inst")
        self.assertEqual(installed_models[0].canonical_name, "inst")
        self.assertEqual(installed_models[0].unsupported_devices, "NPU")

    def test_reload_async_populates_same_as_reload(self) -> None:
        self._add_model(
            name="a",
            display_name="Model A",
            variants=[{"precision": "FP32", "model_path": "a.xml", "display_name": "Model A (FP32)"}],
        )

        async def _run() -> None:
            await SupportedModelsManager().reload_async()

        asyncio.run(_run())
        self.assertEqual(len(SupportedModelsManager().get_all_supported_models()), 1)

    def test_extra_model_proc_alias_uses_absolute_path_flag(self) -> None:
        """``model_proc_is_full_path`` is derived from ``os.path.isabs``."""
        proc_abs = os.path.join(self._tmpdir, "extra_proc.json")
        with open(proc_abs, "w") as f:
            f.write("{}")

        self._add_model(
            name="eff",
            display_name="EfficientNet",
            variants=[
                {
                    "precision": "INT8",
                    "model_path": "eff.xml",
                    "display_name": "EfficientNet (INT8)",
                    "model_proc": "eff.json",
                },
                {
                    "name": "eff_extra_proc",
                    "precision": "INT8",
                    "model_path": "eff.xml",
                    "display_name": "EfficientNet (INT8) [model-proc: extra_proc]",
                    "model_proc": proc_abs,
                },
            ],
        )
        manager = SupportedModelsManager()
        manager.reload()
        supported = manager.get_all_supported_models()
        by_name = {m.display_name: m for m in supported}

        relative_variant = by_name["EfficientNet (INT8)"]
        self.assertEqual(
            relative_variant.model_proc_full,
            os.path.join(self._models_path, "eff.json"),
        )
        extra_variant = by_name["EfficientNet (INT8) [model-proc: extra_proc]"]
        self.assertEqual(extra_variant.model_proc_full, proc_abs)


class TestFilterModels(_DBTestCase):
    """``filter_*_models`` — 'Disabled' handling and default selection."""

    def test_disabled_option_and_default_selection(self) -> None:
        self._add_model(
            name="a",
            display_name="Model A",
            variants=[{"precision": "FP32", "model_path": "a.xml", "display_name": "Model A (FP32)"}],
        )
        self._add_model(
            name="b",
            display_name="Model B",
            variants=[{"precision": "FP32", "model_path": "b.xml", "display_name": "Model B (FP32)"}],
        )
        self._touch("a.xml")
        self._touch("b.xml")
        manager = SupportedModelsManager()
        manager.reload()

        model_names = ["Disabled", "Model A (FP32)", "Model B (FP32)"]
        filtered, default = manager.filter_object_detection_models(
            model_names, default_model="Disabled"
        )
        self.assertEqual(filtered[0], "Disabled")
        self.assertEqual(default, "Disabled")

        filtered2, default2 = manager.filter_object_detection_models(
            ["Model A (FP32)", "Model B (FP32)"], default_model="NonExistent"
        )
        self.assertIn("Model A (FP32)", filtered2)
        self.assertIn(default2, filtered2)

    def test_no_models_on_disk_yields_empty_filtered_and_none_default(self) -> None:
        self._add_model(
            name="c",
            display_name="Model C",
            variants=[{"precision": "FP32", "model_path": "nofile.xml", "display_name": "Model C (FP32)"}],
        )
        manager = SupportedModelsManager()
        manager.reload()

        filtered, default = manager.filter_object_detection_models(
            ["Model C (FP32)"], default_model="Model C (FP32)"
        )
        self.assertEqual(filtered, [])
        self.assertIsNone(default)


class TestIsModelSupportedOnDevice(_DBTestCase):
    def test_unsupported_devices_parsed_case_insensitively(self) -> None:
        self._add_model(
            name="inst2",
            display_name="Model2",
            category="image_classification",
            unsupported_devices="NPU, TPU",
            variants=[{"precision": "FP32", "model_path": "inst2.xml", "display_name": "Model2 (FP32)"}],
        )
        self._touch("inst2.xml")
        manager = SupportedModelsManager()
        manager.reload()

        self.assertFalse(manager.is_model_supported_on_device("Model2 (FP32)", "npu"))
        self.assertTrue(manager.is_model_supported_on_device("Model2 (FP32)", "GPU"))
        self.assertFalse(manager.is_model_supported_on_device("NoSuchModel", "cpu"))


class TestFindModelByModelAndProcPath(_DBTestCase):
    def test_matches_by_base_and_extra_model_proc(self) -> None:
        extra_proc = os.path.join(self._tmpdir, "extra.json")
        with open(extra_proc, "w") as f:
            f.write("{}")

        self._add_model(
            name="m1",
            display_name="Model Base",
            variants=[
                {
                    "precision": "FP32",
                    "model_path": "shared.xml",
                    "display_name": "Model Base (FP32) [model-proc: base]",
                    "model_proc": "base.json",
                },
                {
                    "name": "m1_extra",
                    "precision": "FP32",
                    "model_path": "shared.xml",
                    "display_name": "Model Base (FP32) [model-proc: extra]",
                    "model_proc": extra_proc,
                },
            ],
        )
        self._touch("shared.xml")
        self._touch("base.json")
        manager = SupportedModelsManager()
        manager.reload()

        model_file = os.path.join(self._models_path, "shared.xml")
        base_proc_file = os.path.join(self._models_path, "base.json")

        found_base = manager.find_model_by_model_and_proc_path(model_file, base_proc_file)
        self.assertIsNotNone(found_base)
        assert found_base is not None
        self.assertIn("model-proc: base", found_base.display_name)

        found_extra = manager.find_model_by_model_and_proc_path(model_file, extra_proc)
        self.assertIsNotNone(found_extra)
        assert found_extra is not None
        self.assertIn("model-proc: extra", found_extra.display_name)

    def test_disambiguates_by_precision_directory(self) -> None:
        self._add_model(
            name="yolov10s",
            display_name="YOLO v10s 640x640",
            variants=[
                {
                    "precision": "INT8",
                    "model_path": "public/yolov10s/INT8/yolov10s.xml",
                    "display_name": "YOLO v10s 640x640 (INT8)",
                },
                {
                    "precision": "FP16",
                    "model_path": "public/yolov10s/FP16/yolov10s.xml",
                    "display_name": "YOLO v10s 640x640 (FP16)",
                },
            ],
        )
        self._touch("public/yolov10s/INT8/yolov10s.xml")
        self._touch("public/yolov10s/FP16/yolov10s.xml")
        manager = SupportedModelsManager()
        manager.reload()

        self.assertEqual(len(manager.get_all_installed_models()), 2)

        int8_path = os.path.join(self._models_path, "public/yolov10s/INT8/yolov10s.xml")
        fp16_path = os.path.join(self._models_path, "public/yolov10s/FP16/yolov10s.xml")

        found_int8 = manager.find_model_by_model_and_proc_path(int8_path)
        assert found_int8 is not None
        self.assertEqual(found_int8.precision, "INT8")

        found_fp16 = manager.find_model_by_model_and_proc_path(fp16_path)
        assert found_fp16 is not None
        self.assertEqual(found_fp16.precision, "FP16")
        self.assertIsNot(found_int8, found_fp16)

    def test_genai_directory_path_resolves_to_configured_entry(self) -> None:
        self._add_model(
            name="gemma3",
            display_name="Gemma 3",
            category="vision_language_models",
            source="huggingface",
            variants=[
                {
                    "precision": "INT8",
                    "model_path": "vlm/gemma3",
                    "display_name": "Gemma 3 (INT8)",
                }
            ],
        )
        model_dir = os.path.join(self._models_path, "vlm", "gemma3")
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, GENAI_SENTINEL_FILE), "w") as f:
            f.write("<ir/>")

        manager = SupportedModelsManager()
        manager.reload()

        found = manager.find_model_by_model_and_proc_path(model_dir)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.canonical_name, "gemma3")
        self.assertEqual(found.model_type, "vision_language_models")


class TestFindInstalledModelByDisplayName(_DBTestCase):
    def test_finds_installed_and_ignores_not_installed(self) -> None:
        self._add_model(
            name="inst",
            display_name="Installed Model",
            variants=[{"precision": "FP32", "model_path": "inst.xml", "display_name": "Installed Model (FP32)"}],
        )
        self._add_model(
            name="miss",
            display_name="Missing Model",
            variants=[{"precision": "FP32", "model_path": "miss.xml", "display_name": "Missing Model (FP32)"}],
        )
        self._touch("inst.xml")
        manager = SupportedModelsManager()
        manager.reload()

        found = manager.find_installed_model_by_display_name("Installed Model (FP32)")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.name, "inst")

        self.assertIsNone(manager.find_installed_model_by_display_name("Missing Model (FP32)"))


class TestSupportedModelsManagerSingleton(_DBTestCase):
    def test_singleton_returns_same_instance(self) -> None:
        a = SupportedModelsManager()
        b = SupportedModelsManager()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
