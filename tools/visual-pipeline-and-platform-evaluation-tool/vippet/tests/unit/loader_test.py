import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db_seed
from db_seed import _validate_benchmark_suite_spec
from pipelines.loader import PipelineLoader


class TestPipelineLoader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def test_list_pipelines(self):
        # Create .yaml files instead of directories
        (Path(self.test_dir.name) / "pipeline1.yaml").write_text("key: value")
        (Path(self.test_dir.name) / "pipeline2.yaml").write_text("key: value")
        (Path(self.test_dir.name) / "not_a_yaml.txt").write_text("text")

        pipelines = PipelineLoader.list(self.test_dir.name)
        self.assertIsInstance(pipelines, list)
        self.assertEqual(len(pipelines), 2)
        # Verify that returned items are Path objects
        for pipeline_path in pipelines:
            self.assertIsInstance(pipeline_path, Path)
            self.assertTrue(str(pipeline_path).endswith(".yaml"))

    def test_config(self):
        config_path = Path(self.test_dir.name) / "test_config.yaml"
        config_path.write_text("key: value")
        config = PipelineLoader.config(config_path)
        self.assertIsInstance(config, dict)
        self.assertEqual(config, {"key": "value"})

    def test_config_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            PipelineLoader.config(Path("non_existent_file.yaml"))


class TestBenchmarkSeedValidation(unittest.TestCase):
    def test_validate_suite_rejects_missing_or_malformed_keys(self):
        malformed = {
            "name": "Broken suite",
            "description": "This should be rejected",
            "workloads": [
                {
                    "pipeline_id": "good",
                    "variants": [{"name": "cpu", "number_of_streams": [1, 4]}],
                },
                {
                    "pipeline_id": "bad",
                    "variants": [{"name": "gpu", "number_of_streams": "oops"}],
                },
                {"pipeline_id": "missing-variants"},
            ],
        }

        validated = _validate_benchmark_suite_spec(malformed, Path("bad-suite.yaml"))

        self.assertIsNotNone(validated)
        assert validated is not None
        self.assertEqual(len(validated["workloads"]), 1)
        self.assertEqual(validated["workloads"][0]["pipeline_id"], "good")

    def test_validate_suite_rejects_non_mapping_payload(self):
        self.assertIsNone(
            _validate_benchmark_suite_spec(["not", "a", "dict"], Path("bad-suite.yaml"))
        )

    def test_load_benchmark_suite_specs_skips_invalid_files_and_keeps_valid_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bench_dir = Path(temp_dir) / "benchmarks"
            bench_dir.mkdir()

            valid_suite = bench_dir / "valid-suite.yaml"
            valid_suite.write_text(
                """
name: Valid Suite
description: This suite should load.
workloads:
  - pipeline_id: pipeline-a
    variants:
      - name: cpu
        number_of_streams: [1, 4]
      - name: gpu
        number_of_streams: [2]
""".strip(),
                encoding="utf-8",
            )

            invalid_suite = bench_dir / "broken-suite.yaml"
            invalid_suite.write_text(
                """
name: Broken Suite
description: This suite should be skipped.
workloads:
  - pipeline_id: pipeline-b
    variants:
      - name: gpu
        number_of_streams: not-a-list
""".strip(),
                encoding="utf-8",
            )

            with patch.object(db_seed, "__file__", str(Path(temp_dir) / "db_seed.py")):
                suite_specs = db_seed._load_benchmark_suite_specs()

            self.assertEqual(len(suite_specs), 1)
            assert suite_specs
            self.assertEqual(suite_specs[0]["name"], "Valid Suite")
            self.assertEqual(
                suite_specs[0]["workloads"][0]["pipeline_id"], "pipeline-a"
            )

    def test_load_benchmark_suite_specs_ignores_bad_yaml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bench_dir = Path(temp_dir) / "benchmarks"
            bench_dir.mkdir()

            bad_yaml = bench_dir / "malformed.yaml"
            bad_yaml.write_text(
                """
name: Broken Yaml
workloads: [
  - pipeline_id: pipeline-a
    variants: [
      - name: cpu
        number_of_streams: [1, 2,
""".strip(),
                encoding="utf-8",
            )

            with patch.object(db_seed, "__file__", str(Path(temp_dir) / "db_seed.py")):
                suite_specs = db_seed._load_benchmark_suite_specs()

            self.assertEqual(suite_specs, [])


if __name__ == "__main__":
    unittest.main()
