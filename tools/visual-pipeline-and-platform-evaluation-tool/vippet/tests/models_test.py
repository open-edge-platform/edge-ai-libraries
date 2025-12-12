import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


# Helper to reload the models module with environment variables set.
def _reload_models_module(supported_models_file: str, models_path: str):
    """
    Reload the models module after setting environment variables.
    Ensures module-level constants are read from our test environment.
    """
    os.environ["SUPPORTED_MODELS_FILE"] = supported_models_file
    os.environ["MODELS_PATH"] = models_path
    # Load/reload the top-level 'models' module.
    if "models" in sys.modules:
        return importlib.reload(sys.modules["models"])
    else:
        import models as m

        return importlib.reload(m)


class TestModels(unittest.TestCase):
    def test_supported_model_paths_and_exists(self):
        """Test SupportedModel path and model_proc resolution and exists_on_disk."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models_dir = td_path / "models_dir"
            models_dir.mkdir()
            xml_file = models_dir / "modelA.xml"
            xml_file.write_text("dummy")
            yaml_file = td_path / "supported.yaml"
            yaml_file.write_text("[]")

            m = _reload_models_module(str(yaml_file), str(models_dir))

            # instantiate SupportedModel with no model_proc
            sm1 = m.SupportedModel(
                name="mA",
                display_name="Model A",
                source="public",
                model_type="classification",
                model_path="modelA.xml",
                model_proc=None,
            )
            # model_path_full should point inside MODELS_PATH and exists_on_disk should be True
            self.assertEqual(sm1.model_path_full, str(models_dir / "modelA.xml"))
            self.assertTrue(sm1.exists_on_disk())
            # model_proc_full should be empty when model_proc is None
            self.assertEqual(sm1.model_proc_full, "")

            # instantiate with non-empty model_proc
            proc_file = models_dir / "proc.json"
            proc_file.write_text("{}")
            sm2 = m.SupportedModel(
                name="mB",
                display_name="Model B",
                source="public",
                model_type="detection",
                model_path="missing.xml",
                model_proc="proc.json",
            )
            # model_proc_full should point to MODELS_PATH/proc.json
            self.assertEqual(sm2.model_proc_full, str(models_dir / "proc.json"))
            # model_path_full exists_on_disk should be False for missing.xml
            self.assertFalse(sm2.exists_on_disk())

    def test_supported_models_manager_loads_and_basic_lookups(self):
        """Test SupportedModelsManager loads YAML and lookup helpers."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models_dir = td_path / "models"
            models_dir.mkdir()
            installed = models_dir / "inst.xml"
            installed.write_text("x")
            yaml_content = """
- name: inst
  display_name: Installed Model
  source: public
  type: classification
  model_path: inst.xml
  model_proc: ""
  unsupported_devices: "NPU"
  precision: FP32
  default: true
- name: miss
  display_name: Missing Model
  source: public
  type: detection
  model_path: miss.xml
  model_proc: ""
  unsupported_devices: ""
  precision: FP32
  default: false
"""
            yaml_file = td_path / "supported_models.yaml"
            yaml_file.write_text(yaml_content)

            m = _reload_models_module(str(yaml_file), str(models_dir))
            # Reset singleton for safe instantiation
            if hasattr(m, "_supported_models_manager_instance"):
                setattr(m, "_supported_models_manager_instance", None)

            manager = m.SupportedModelsManager()
            # all supported models should be two
            all_supported = manager.get_all_supported_models()
            self.assertEqual(len(all_supported), 2)
            # installed models should be only one
            installed_models = manager.get_all_installed_models()
            self.assertEqual(len(installed_models), 1)
            self.assertEqual(installed_models[0].name, "inst")

            # find by internal name
            found_by_name = manager.find_installed_model_by_name("inst")
            self.assertIsNotNone(found_by_name)
            self.assertEqual(found_by_name.display_name, "Installed Model")
            self.assertIsNone(manager.find_installed_model_by_name("miss"))

            # find by display name
            found_by_disp = manager.find_installed_model_by_display_name(
                "Installed Model"
            )
            self.assertIsNotNone(found_by_disp)
            self.assertEqual(found_by_disp.name, "inst")

            # find by model_path_full
            found_by_path = manager.find_installed_model_by_model_path_full(
                str(installed)
            )
            self.assertIsNotNone(found_by_path)
            self.assertEqual(found_by_path.name, "inst")

    def test_filter_models_disabled_and_default_selection(self):
        """Test filtering logic including 'Disabled' option and default selection rules."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models_dir = td_path / "md"
            models_dir.mkdir()
            a = models_dir / "a.xml"
            b = models_dir / "b.xml"
            a.write_text("a")
            b.write_text("b")
            yaml_content = """
- name: a
  display_name: Model A
  source: public
  type: detection
  model_path: a.xml
  model_proc: ""
  unsupported_devices: ""
  precision: FP32
  default: false
- name: b
  display_name: Model B
  source: public
  type: detection
  model_path: b.xml
  model_proc: ""
  unsupported_devices: ""
  precision: FP32
  default: false
"""
            yaml_file = td_path / "supported.yaml"
            yaml_file.write_text(yaml_content)

            m = _reload_models_module(str(yaml_file), str(models_dir))
            if hasattr(m, "_supported_models_manager_instance"):
                setattr(m, "_supported_models_manager_instance", None)
            manager = m.SupportedModelsManager()

            # If "Disabled" present in model_names, it should appear first
            model_names = ["Disabled", "Model A", "Model B"]
            filtered, default = manager.filter_detection_models(
                model_names, default_model="Disabled"
            )
            self.assertEqual(filtered[0], "Disabled")
            self.assertEqual(default, "Disabled")

            # If default_model not present on disk, pick first available non-Disabled
            filtered2, default2 = manager.filter_detection_models(
                ["Model A", "Model B"], default_model="NonExistent"
            )
            self.assertIn("Model A", filtered2)
            self.assertIn(default2, filtered2)

            # No models on disk: filtered empty and default None
            yaml_file2 = td_path / "supported2.yaml"
            yaml_file2.write_text(
                """
- name: c
  display_name: Model C
  source: public
  type: detection
  model_path: nofile.xml
  model_proc: ""
  unsupported_devices: ""
  precision: FP32
  default: false
"""
            )
            m2 = _reload_models_module(str(yaml_file2), str(models_dir))
            if hasattr(m2, "_supported_models_manager_instance"):
                setattr(m2, "_supported_models_manager_instance", None)
            manager2 = m2.SupportedModelsManager()
            filtered3, default3 = manager2.filter_detection_models(
                ["Model C"], default_model="Model C"
            )
            self.assertEqual(filtered3, [])
            self.assertIsNone(default3)

    def test_is_model_supported_on_device_and_missing_model(self):
        """Test device support parsing and behavior when model not found."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models_dir = td_path / "md2"
            models_dir.mkdir()
            inst = models_dir / "inst2.xml"
            inst.write_text("x")
            yaml_file = td_path / "sup.yaml"
            yaml_file.write_text(
                """
- name: inst2
  display_name: Model2
  source: public
  type: classification
  model_path: inst2.xml
  model_proc: ""
  unsupported_devices: "NPU, TPU"
  precision: FP32
  default: true
"""
            )
            m = _reload_models_module(str(yaml_file), str(models_dir))
            if hasattr(m, "_supported_models_manager_instance"):
                setattr(m, "_supported_models_manager_instance", None)
            manager = m.SupportedModelsManager()

            # 'npu' should be unsupported (case-insensitive)
            self.assertFalse(manager.is_model_supported_on_device("Model2", "npu"))
            # 'gpu' should be supported
            self.assertTrue(manager.is_model_supported_on_device("Model2", "GPU"))
            # model not found should return False
            self.assertFalse(manager.is_model_supported_on_device("NoSuchModel", "cpu"))

    def test_init_errors_invalid_yaml_and_empty_list(self):
        """Test that invalid YAML formats and empty lists raise RuntimeError during manager init."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models_dir = td_path / "md3"
            models_dir.mkdir()

            # Invalid format: top-level YAML is a dict, not list
            bad_yaml = td_path / "bad.yaml"
            bad_yaml.write_text("key: value\n")
            m = _reload_models_module(str(bad_yaml), str(models_dir))
            if hasattr(m, "_supported_models_manager_instance"):
                setattr(m, "_supported_models_manager_instance", None)
            with self.assertRaises(RuntimeError):
                m.SupportedModelsManager()

            # Missing required field in entry (no 'name')
            missing_field_yaml = td_path / "missfield.yaml"
            missing_field_yaml.write_text(
                """
- display_name: Missing Name
  source: public
  type: classification
  model_path: something.xml
"""
            )
            m2 = _reload_models_module(str(missing_field_yaml), str(models_dir))
            if hasattr(m2, "_supported_models_manager_instance"):
                setattr(m2, "_supported_models_manager_instance", None)
            with self.assertRaises(RuntimeError):
                m2.SupportedModelsManager()

            # Empty list should also raise
            empty_yaml = td_path / "empty.yaml"
            empty_yaml.write_text("[]\n")
            m3 = _reload_models_module(str(empty_yaml), str(models_dir))
            if hasattr(m3, "_supported_models_manager_instance"):
                setattr(m3, "_supported_models_manager_instance", None)
            with self.assertRaises(RuntimeError):
                m3.SupportedModelsManager()

    def test_get_supported_models_manager_singleton_and_sys_exit(self):
        """Test get_supported_models_manager returns singleton and sys.exit path on failure."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models_dir = td_path / "md4"
            models_dir.mkdir()
            yaml_file = td_path / "ok.yaml"
            yaml_file.write_text(
                """
- name: s1
  display_name: S1
  source: public
  type: classification
  model_path: nofile.xml
  model_proc: ""
  unsupported_devices: ""
  precision: FP32
  default: false
"""
            )
            m = _reload_models_module(str(yaml_file), str(models_dir))
            if hasattr(m, "_supported_models_manager_instance"):
                setattr(m, "_supported_models_manager_instance", None)
            mgr = m.get_supported_models_manager()
            # Should be stored as the singleton
            self.assertIs(mgr, m._supported_models_manager_instance)

            # Now point SUPPORTED_MODELS_FILE to a non-existing path and reload module,
            # expect SystemExit when get_supported_models_manager tries to initialize manager.
            bad_yaml = td_path / "does_not_exist.yaml"
            os.environ["SUPPORTED_MODELS_FILE"] = str(bad_yaml)
            os.environ["MODELS_PATH"] = str(models_dir)
            # reload module to pick new env vars
            bad_mod = importlib.reload(sys.modules["models"])
            if hasattr(bad_mod, "_supported_models_manager_instance"):
                setattr(bad_mod, "_supported_models_manager_instance", None)
            with self.assertRaises(SystemExit):
                bad_mod.get_supported_models_manager()


if __name__ == "__main__":
    unittest.main()
