import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from api.api_schemas import PipelineSource
from managers.pipeline_template_manager import (
    PipelineTemplateManager,
    TEMPLATES_DIR_NAME,
)


# ------------------------------------------------------------------
# Shared mock template configs
# ------------------------------------------------------------------

MOCK_TEMPLATE_CONFIGS = [
    {
        "name": "Detect Only",
        "definition": "Template pipeline with a single object detection model.",
        "tags": ["template", "detection"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_description": (
                    'filesrc location="" ! decodebin !'
                    ' gvadetect device=CPU model="" ! fakesink'
                ),
            },
            {
                "name": "GPU",
                "pipeline_description": (
                    'filesrc location="" ! decodebin !'
                    ' gvadetect device=GPU model="" ! fakesink'
                ),
            },
        ],
    },
    {
        "name": "Detect and Classify",
        "definition": "Template pipeline with detection and classification.",
        "tags": ["template", "detection", "classification"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_description": (
                    'filesrc location="" ! decodebin !'
                    ' gvadetect device=CPU model="" !'
                    ' gvaclassify device=CPU model="" ! fakesink'
                ),
            },
        ],
    },
]


def _mock_config_for_path(config_path: str) -> dict:
    """Return mock template config based on path filename index."""
    basename = os.path.basename(config_path)
    index = int(basename.split("_")[1].split(".")[0])
    return MOCK_TEMPLATE_CONFIGS[index]


class TestPipelineTemplateManagerSingleton(unittest.TestCase):
    """
    Unit tests for the singleton pattern of PipelineTemplateManager.

    The tests focus on:
      * returning the same instance on repeated construction,
      * initializing internal state only once.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        PipelineTemplateManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineTemplateManager._instance = None

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_singleton_returns_same_instance(self, mock_loader_cls):
        """PipelineTemplateManager() should return the same instance on multiple calls."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        instance1 = PipelineTemplateManager()
        instance2 = PipelineTemplateManager()

        self.assertIs(instance1, instance2)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_singleton_only_initializes_once(self, mock_loader_cls):
        """Multiple calls to PipelineTemplateManager() must not re-initialize the singleton."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager1 = PipelineTemplateManager()
        original_templates = manager1.templates

        manager2 = PipelineTemplateManager()

        # The templates list object must be the exact same reference.
        self.assertIs(manager2.templates, original_templates)


class TestPipelineTemplateManagerGetTemplates(unittest.TestCase):
    """
    Unit tests for PipelineTemplateManager.get_templates().

    The tests focus on:
      * returning all templates,
      * returning deep copies so the internal state cannot be mutated,
      * correct structure of returned Pipeline objects.
    """

    def setUp(self):
        """Reset singleton and create manager with no templates directory."""
        PipelineTemplateManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineTemplateManager._instance = None

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_templates_returns_empty_list_when_no_templates(self, mock_loader_cls):
        """get_templates() returns an empty list when no templates are loaded."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager = PipelineTemplateManager()
        result = manager.get_templates()

        self.assertEqual(result, [])

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_templates_returns_all_templates(self, mock_loader_cls):
        """get_templates() returns exactly the templates stored internally."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager = PipelineTemplateManager()
        manager.templates = []

        # Inject two dummy templates directly
        for config in MOCK_TEMPLATE_CONFIGS:
            manager.templates.append(
                manager._build_template_from_config(
                    config, "dummy.yaml", manager.templates
                )
            )

        result = manager.get_templates()

        self.assertEqual(len(result), len(MOCK_TEMPLATE_CONFIGS))
        names = [t.name for t in result]
        for config in MOCK_TEMPLATE_CONFIGS:
            self.assertIn(config["name"], names)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_templates_returns_deep_copies(self, mock_loader_cls):
        """get_templates() must return deep copies, not direct references."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager = PipelineTemplateManager()
        manager.templates = [
            manager._build_template_from_config(
                MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
            )
        ]

        result = manager.get_templates()
        result[0].name = "MUTATED"

        # Original must be unaffected.
        self.assertNotEqual(manager.templates[0].name, "MUTATED")

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_templates_all_have_source_template(self, mock_loader_cls):
        """All returned templates must have source=TEMPLATE."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager = PipelineTemplateManager()
        manager.templates = [
            manager._build_template_from_config(config, "dummy.yaml", [])
            for config in MOCK_TEMPLATE_CONFIGS
        ]

        for template in manager.get_templates():
            self.assertEqual(template.source, PipelineSource.TEMPLATE)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_templates_all_variants_are_read_only(self, mock_loader_cls):
        """All variants of all returned templates must have read_only=True."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager = PipelineTemplateManager()
        manager.templates = [
            manager._build_template_from_config(config, "dummy.yaml", [])
            for config in MOCK_TEMPLATE_CONFIGS
        ]

        for template in manager.get_templates():
            for variant in template.variants:
                self.assertTrue(variant.read_only)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_templates_thumbnail_is_none(self, mock_loader_cls):
        """All returned templates must have thumbnail=None."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager = PipelineTemplateManager()
        manager.templates = [
            manager._build_template_from_config(config, "dummy.yaml", [])
            for config in MOCK_TEMPLATE_CONFIGS
        ]

        for template in manager.get_templates():
            self.assertIsNone(template.thumbnail)


class TestPipelineTemplateManagerGetTemplateById(unittest.TestCase):
    """
    Unit tests for PipelineTemplateManager.get_template_by_id().

    The tests focus on:
      * successful lookup by ID,
      * raising ValueError for unknown IDs,
      * returning a deep copy to protect internal state.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        PipelineTemplateManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineTemplateManager._instance = None

    def _create_manager_with_templates(
        self, mock_loader_cls
    ) -> PipelineTemplateManager:
        """Helper that creates a manager pre-loaded with MOCK_TEMPLATE_CONFIGS."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"
        manager = PipelineTemplateManager()
        manager.templates = []
        for config in MOCK_TEMPLATE_CONFIGS:
            manager.templates.append(
                manager._build_template_from_config(
                    config, "dummy.yaml", manager.templates
                )
            )
        return manager

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_template_by_id_returns_correct_template(self, mock_loader_cls):
        """get_template_by_id() returns the template matching the given ID."""
        manager = self._create_manager_with_templates(mock_loader_cls)

        target = manager.templates[0]
        result = manager.get_template_by_id(target.id)

        self.assertEqual(result.id, target.id)
        self.assertEqual(result.name, target.name)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_template_by_id_raises_for_unknown_id(self, mock_loader_cls):
        """get_template_by_id() raises ValueError when the ID does not exist."""
        manager = self._create_manager_with_templates(mock_loader_cls)

        with self.assertRaises(ValueError) as context:
            manager.get_template_by_id("nonexistent-template-id")

        self.assertIn("nonexistent-template-id", str(context.exception))

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_template_by_id_returns_deep_copy(self, mock_loader_cls):
        """get_template_by_id() must return a deep copy, not a direct reference."""
        manager = self._create_manager_with_templates(mock_loader_cls)

        target_id = manager.templates[0].id
        result = manager.get_template_by_id(target_id)
        result.name = "MUTATED"

        # The internal template must remain unchanged.
        self.assertNotEqual(manager.templates[0].name, "MUTATED")

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_template_by_id_source_is_template(self, mock_loader_cls):
        """Template returned by get_template_by_id() must have source=TEMPLATE."""
        manager = self._create_manager_with_templates(mock_loader_cls)

        target_id = manager.templates[0].id
        result = manager.get_template_by_id(target_id)

        self.assertEqual(result.source, PipelineSource.TEMPLATE)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_get_template_by_id_all_variants_read_only(self, mock_loader_cls):
        """All variants of the returned template must have read_only=True."""
        manager = self._create_manager_with_templates(mock_loader_cls)

        target_id = manager.templates[0].id
        result = manager.get_template_by_id(target_id)

        for variant in result.variants:
            self.assertTrue(variant.read_only)


class TestLoadTemplates(unittest.TestCase):
    """
    Unit tests for PipelineTemplateManager._load_templates().

    Uses a real temporary directory so that Path.glob() works without
    complex mocking, while still mocking PipelineLoader.config() to
    avoid reading actual YAML from disk.
    """

    def setUp(self):
        """Reset singleton state and create a temporary directory."""
        PipelineTemplateManager._instance = None
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Reset singleton state and remove the temporary directory."""
        PipelineTemplateManager._instance = None
        shutil.rmtree(self.tmpdir)

    def _make_template_yaml_stubs(self, count: int) -> str:
        """
        Create *count* empty YAML stub files inside ``<tmpdir>/templates/``
        and return the path to the templates subdirectory.
        """
        templates_dir = os.path.join(self.tmpdir, TEMPLATES_DIR_NAME)
        os.makedirs(templates_dir, exist_ok=True)
        for i in range(count):
            open(os.path.join(templates_dir, f"template_{i:02d}.yaml"), "w").close()
        return templates_dir

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_missing_directory_returns_empty(self, mock_loader_cls):
        """_load_templates() returns [] when the templates directory does not exist."""
        mock_loader_cls.get_pipelines_directory.return_value = "/nonexistent/path"

        manager = PipelineTemplateManager()

        self.assertEqual(manager.templates, [])

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_empty_directory_returns_empty(self, mock_loader_cls):
        """_load_templates() returns [] when the templates directory contains no YAML files."""
        # Create an empty templates directory.
        os.makedirs(os.path.join(self.tmpdir, TEMPLATES_DIR_NAME))
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir

        manager = PipelineTemplateManager()

        self.assertEqual(manager.templates, [])

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_loads_all_yaml_files(self, mock_loader_cls):
        """_load_templates() loads one Pipeline per YAML file in the templates directory."""
        self._make_template_yaml_stubs(len(MOCK_TEMPLATE_CONFIGS))
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        mock_loader_cls.config.side_effect = _mock_config_for_path

        manager = PipelineTemplateManager()

        self.assertEqual(len(manager.templates), len(MOCK_TEMPLATE_CONFIGS))

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_sets_source_template(self, mock_loader_cls):
        """All loaded templates must have source=TEMPLATE."""
        self._make_template_yaml_stubs(len(MOCK_TEMPLATE_CONFIGS))
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        mock_loader_cls.config.side_effect = _mock_config_for_path

        manager = PipelineTemplateManager()

        for template in manager.templates:
            self.assertEqual(template.source, PipelineSource.TEMPLATE)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_all_variants_read_only(self, mock_loader_cls):
        """All variants of loaded templates must have read_only=True."""
        self._make_template_yaml_stubs(len(MOCK_TEMPLATE_CONFIGS))
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        mock_loader_cls.config.side_effect = _mock_config_for_path

        manager = PipelineTemplateManager()

        for template in manager.templates:
            for variant in template.variants:
                self.assertTrue(variant.read_only)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_names_match_configs(self, mock_loader_cls):
        """Loaded template names must match the names from the config files."""
        self._make_template_yaml_stubs(len(MOCK_TEMPLATE_CONFIGS))
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        mock_loader_cls.config.side_effect = _mock_config_for_path

        manager = PipelineTemplateManager()

        loaded_names = {t.name for t in manager.templates}
        expected_names = {cfg["name"] for cfg in MOCK_TEMPLATE_CONFIGS}
        self.assertEqual(loaded_names, expected_names)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_ids_are_unique(self, mock_loader_cls):
        """Each loaded template must receive a unique ID."""
        self._make_template_yaml_stubs(len(MOCK_TEMPLATE_CONFIGS))
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        mock_loader_cls.config.side_effect = _mock_config_for_path

        manager = PipelineTemplateManager()

        ids = [t.id for t in manager.templates]
        self.assertEqual(len(ids), len(set(ids)))

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_timestamps_are_utc_datetimes(self, mock_loader_cls):
        """Timestamps on loaded templates must be timezone-aware UTC datetime objects."""
        self._make_template_yaml_stubs(len(MOCK_TEMPLATE_CONFIGS))
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        mock_loader_cls.config.side_effect = _mock_config_for_path

        manager = PipelineTemplateManager()

        for template in manager.templates:
            self.assertIsInstance(template.created_at, datetime)
            self.assertIsInstance(template.modified_at, datetime)
            self.assertEqual(template.created_at.tzinfo, timezone.utc)
            self.assertEqual(template.modified_at.tzinfo, timezone.utc)

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_raises_on_bad_config(self, mock_loader_cls):
        """_load_templates() propagates exceptions raised by a broken config."""
        self._make_template_yaml_stubs(1)
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        # Return a config that is missing the required "name" field.
        mock_loader_cls.config.return_value = {
            "definition": "broken",
            "variants": [
                {
                    "name": "CPU",
                    "pipeline_description": "fakesrc ! fakesink",
                }
            ],
        }

        with self.assertRaises(Exception):
            PipelineTemplateManager()

    @patch("managers.pipeline_template_manager.PipelineLoader")
    def test_load_templates_single_yaml_file(self, mock_loader_cls):
        """_load_templates() correctly handles a directory with a single YAML file."""
        self._make_template_yaml_stubs(1)
        mock_loader_cls.get_pipelines_directory.return_value = self.tmpdir
        mock_loader_cls.config.side_effect = _mock_config_for_path

        manager = PipelineTemplateManager()

        self.assertEqual(len(manager.templates), 1)
        self.assertEqual(manager.templates[0].name, MOCK_TEMPLATE_CONFIGS[0]["name"])


class TestBuildTemplateFromConfig(unittest.TestCase):
    """
    Unit tests for PipelineTemplateManager._build_template_from_config().

    The tests focus on:
      * correct Pipeline construction from a valid config dict,
      * validation of required fields (name, variant names, pipeline_description),
      * ID generation and uniqueness,
      * correct assignment of source, read_only, and thumbnail.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        PipelineTemplateManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineTemplateManager._instance = None

    def _make_manager(self) -> PipelineTemplateManager:
        """Return a manager instance with an empty templates list."""
        with patch("managers.pipeline_template_manager.PipelineLoader") as mock_ldr:
            mock_ldr.get_pipelines_directory.return_value = "/nonexistent/path"
            manager = PipelineTemplateManager()
        manager.templates = []
        return manager

    def test_build_template_sets_name(self):
        """_build_template_from_config() sets the template name from config."""
        manager = self._make_manager()
        config = MOCK_TEMPLATE_CONFIGS[0]

        template = manager._build_template_from_config(config, "dummy.yaml", [])

        self.assertEqual(template.name, config["name"])

    def test_build_template_sets_description(self):
        """_build_template_from_config() uses 'definition' as description."""
        manager = self._make_manager()
        config = MOCK_TEMPLATE_CONFIGS[0]

        template = manager._build_template_from_config(config, "dummy.yaml", [])

        self.assertEqual(template.description, config["definition"])

    def test_build_template_sets_tags(self):
        """_build_template_from_config() sets tags from config."""
        manager = self._make_manager()
        config = MOCK_TEMPLATE_CONFIGS[0]

        template = manager._build_template_from_config(config, "dummy.yaml", [])

        self.assertEqual(template.tags, config["tags"])

    def test_build_template_source_is_template(self):
        """_build_template_from_config() must set source=TEMPLATE."""
        manager = self._make_manager()

        template = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )

        self.assertEqual(template.source, PipelineSource.TEMPLATE)

    def test_build_template_thumbnail_is_none(self):
        """_build_template_from_config() must set thumbnail=None."""
        manager = self._make_manager()

        template = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )

        self.assertIsNone(template.thumbnail)

    def test_build_template_correct_variant_count(self):
        """Number of variants matches the number of variant entries in the config."""
        manager = self._make_manager()

        for config in MOCK_TEMPLATE_CONFIGS:
            template = manager._build_template_from_config(config, "dummy.yaml", [])
            self.assertEqual(len(template.variants), len(config["variants"]))

    def test_build_template_all_variants_read_only(self):
        """All variants must have read_only=True."""
        manager = self._make_manager()

        template = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )

        for variant in template.variants:
            self.assertTrue(variant.read_only)

    def test_build_template_variant_ids_are_unique(self):
        """All variant IDs within a single template must be unique."""
        manager = self._make_manager()
        # Use the first config which has two variants (CPU, GPU).
        template = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )

        ids = [v.id for v in template.variants]
        self.assertEqual(len(ids), len(set(ids)))

    def test_build_template_variant_names_match_config(self):
        """Variant names must match those specified in the config."""
        manager = self._make_manager()
        config = MOCK_TEMPLATE_CONFIGS[0]

        template = manager._build_template_from_config(config, "dummy.yaml", [])

        variant_names = {v.name for v in template.variants}
        expected_names = {v["name"] for v in config["variants"]}
        self.assertEqual(variant_names, expected_names)

    def test_build_template_variant_has_pipeline_graphs(self):
        """Each variant must have non-None pipeline_graph and pipeline_graph_simple."""
        manager = self._make_manager()

        template = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )

        for variant in template.variants:
            self.assertIsNotNone(variant.pipeline_graph)
            self.assertIsNotNone(variant.pipeline_graph_simple)

    def test_build_template_timestamps_are_utc_datetimes(self):
        """Template and variant timestamps must be UTC-aware datetime objects."""
        manager = self._make_manager()

        template = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )

        self.assertIsInstance(template.created_at, datetime)
        self.assertIsInstance(template.modified_at, datetime)
        self.assertEqual(template.created_at.tzinfo, timezone.utc)
        self.assertEqual(template.modified_at.tzinfo, timezone.utc)

        for variant in template.variants:
            self.assertIsInstance(variant.created_at, datetime)
            self.assertIsInstance(variant.modified_at, datetime)
            self.assertEqual(variant.created_at.tzinfo, timezone.utc)
            self.assertEqual(variant.modified_at.tzinfo, timezone.utc)

    def test_build_template_id_generated_from_name(self):
        """Template ID must be a slugified version of the name."""
        manager = self._make_manager()

        template = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )

        # "Detect Only" → "detect-only"
        self.assertEqual(template.id, "detect-only")

    def test_build_template_id_unique_across_existing(self):
        """Template ID must not collide with IDs already in existing_templates."""
        manager = self._make_manager()

        first = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", []
        )
        # Build the same config again; the ID should be suffixed to avoid collision.
        second = manager._build_template_from_config(
            MOCK_TEMPLATE_CONFIGS[0], "dummy.yaml", [first]
        )

        self.assertNotEqual(first.id, second.id)

    def test_build_template_empty_name_raises(self):
        """_build_template_from_config() raises ValueError when name is empty."""
        manager = self._make_manager()
        bad_config = {
            "name": "   ",
            "definition": "Test",
            "variants": [
                {
                    "name": "CPU",
                    "pipeline_description": "fakesrc ! fakesink",
                }
            ],
        }

        with self.assertRaises(ValueError) as context:
            manager._build_template_from_config(bad_config, "bad.yaml", [])

        self.assertIn("name cannot be empty", str(context.exception))

    def test_build_template_empty_variant_name_raises(self):
        """_build_template_from_config() raises ValueError when a variant name is empty."""
        manager = self._make_manager()
        bad_config = {
            "name": "Valid Template",
            "definition": "Test",
            "variants": [
                {
                    "name": "   ",
                    "pipeline_description": "fakesrc ! fakesink",
                }
            ],
        }

        with self.assertRaises(ValueError) as context:
            manager._build_template_from_config(bad_config, "bad.yaml", [])

        self.assertIn("Variant name cannot be empty", str(context.exception))

    def test_build_template_empty_pipeline_description_raises(self):
        """_build_template_from_config() raises ValueError when pipeline_description is empty."""
        manager = self._make_manager()
        bad_config = {
            "name": "Valid Template",
            "definition": "Test",
            "variants": [
                {
                    "name": "CPU",
                    "pipeline_description": "   ",
                }
            ],
        }

        with self.assertRaises(ValueError) as context:
            manager._build_template_from_config(bad_config, "bad.yaml", [])

        self.assertIn("pipeline_description cannot be empty", str(context.exception))

    def test_build_template_missing_tags_defaults_to_empty_list(self):
        """_build_template_from_config() defaults tags to [] when absent from config."""
        manager = self._make_manager()
        config_no_tags = {
            "name": "No Tags Template",
            "definition": "Test",
            "variants": [
                {
                    "name": "CPU",
                    "pipeline_description": "fakesrc ! fakesink",
                }
            ],
        }

        template = manager._build_template_from_config(config_no_tags, "dummy.yaml", [])

        self.assertEqual(template.tags, [])

    def test_build_template_non_list_tags_defaults_to_empty_list(self):
        """_build_template_from_config() treats non-list tags value as []."""
        manager = self._make_manager()
        config_bad_tags = {
            "name": "Bad Tags Template",
            "definition": "Test",
            "tags": "not-a-list",
            "variants": [
                {
                    "name": "CPU",
                    "pipeline_description": "fakesrc ! fakesink",
                }
            ],
        }

        template = manager._build_template_from_config(
            config_bad_tags, "dummy.yaml", []
        )

        self.assertEqual(template.tags, [])


if __name__ == "__main__":
    unittest.main()
