# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib
import os
import sys
import unittest

# Matches the "%Y%m%dT%H%M%SZ" timestamp suffix produced by app_version.py.
_TIMESTAMP_RE = r"\d{8}T\d{6}Z"


def _reload_app_version_module():
    """
    (Re)load the app_version module so its module-level VIPPET_VERSION
    constant is recomputed from the current environment.
    """
    if "app_version" in sys.modules:
        return importlib.reload(sys.modules["app_version"])
    import app_version as av

    return importlib.reload(av)


class TestAppVersionResolution(unittest.TestCase):
    """
    Unit tests for the VIPPET_VERSION resolution logic in app_version.py.

    Each test sets ``VIPPET_VERSION`` in the environment, reloads the
    module so its module-level constant is recomputed, and asserts the
    resulting value. The original environment/module state is restored
    afterwards so other test modules that import ``app_version`` are not
    affected by leftover state.
    """

    def setUp(self):
        self._original_env = os.environ.get("VIPPET_VERSION")
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._original_env is None:
            os.environ.pop("VIPPET_VERSION", None)
        else:
            os.environ["VIPPET_VERSION"] = self._original_env
        _reload_app_version_module()

    def test_explicit_release_tag_is_used_verbatim(self):
        """A real release/build tag is exposed unchanged, with no timestamp."""
        os.environ["VIPPET_VERSION"] = "2026.2.0-rc2"
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_VERSION, "2026.2.0-rc2")

    def test_explicit_tag_is_stripped_of_surrounding_whitespace(self):
        """Leading/trailing whitespace around a real tag is trimmed."""
        os.environ["VIPPET_VERSION"] = "  2026.2.0-rc2  "
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_VERSION, "2026.2.0-rc2")

    def test_missing_env_var_falls_back_to_timestamped_dev_label(self):
        """No VIPPET_VERSION set at all -> "dev-<timestamp>"."""
        os.environ.pop("VIPPET_VERSION", None)
        module = _reload_app_version_module()
        self.assertRegex(module.VIPPET_VERSION, rf"^dev-{_TIMESTAMP_RE}$")

    def test_empty_env_var_falls_back_to_timestamped_dev_label(self):
        """An empty VIPPET_VERSION value behaves like an unset one."""
        os.environ["VIPPET_VERSION"] = ""
        module = _reload_app_version_module()
        self.assertRegex(module.VIPPET_VERSION, rf"^dev-{_TIMESTAMP_RE}$")

    def test_whitespace_only_env_var_falls_back_to_timestamped_dev_label(self):
        """A whitespace-only VIPPET_VERSION value behaves like an unset one."""
        os.environ["VIPPET_VERSION"] = "   "
        module = _reload_app_version_module()
        self.assertRegex(module.VIPPET_VERSION, rf"^dev-{_TIMESTAMP_RE}$")

    def test_makefile_test_placeholder_falls_back_to_timestamped_test_label(
        self,
    ):
        """The Makefile's DOCKER_TAG="test" override -> "test-<timestamp>"."""
        os.environ["VIPPET_VERSION"] = "test"
        module = _reload_app_version_module()
        self.assertRegex(module.VIPPET_VERSION, rf"^test-{_TIMESTAMP_RE}$")


if __name__ == "__main__":
    unittest.main()
