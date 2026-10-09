# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib
import os
import sys
import unittest


def _reload_app_version_module():
    """
    (Re)load the app_version module so its module-level VIPPET_VERSION /
    VIPPET_REVISION constants are recomputed from the current environment.
    """
    if "app_version" in sys.modules:
        return importlib.reload(sys.modules["app_version"])
    import app_version as av

    return importlib.reload(av)


class TestAppVersionResolution(unittest.TestCase):
    """
    Unit tests for the VIPPET_VERSION / VIPPET_REVISION resolution logic
    in app_version.py.

    Each test sets the relevant environment variable(s), reloads the
    module so its module-level constants are recomputed, and asserts the
    resulting value. The original environment/module state is restored
    afterwards so other test modules that import ``app_version`` are not
    affected by leftover state.
    """

    def setUp(self):
        self._original_version = os.environ.get("VIPPET_VERSION")
        self._original_revision = os.environ.get("VIPPET_REVISION")
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for name, original in (
            ("VIPPET_VERSION", self._original_version),
            ("VIPPET_REVISION", self._original_revision),
        ):
            if original is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = original
        _reload_app_version_module()

    # ------------------------------------------------------------------
    # VIPPET_VERSION
    # ------------------------------------------------------------------

    def test_explicit_version_is_used_verbatim(self):
        """A real release/build tag is exposed unchanged."""
        os.environ["VIPPET_VERSION"] = "2026.2.0-rc2"
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_VERSION, "2026.2.0-rc2")

    def test_explicit_version_is_stripped_of_surrounding_whitespace(self):
        """Leading/trailing whitespace around a real tag is trimmed."""
        os.environ["VIPPET_VERSION"] = "  2026.2.0-rc2  "
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_VERSION, "2026.2.0-rc2")

    def test_missing_version_env_var_falls_back_to_unknown(self):
        """No VIPPET_VERSION set at all -> "unknown"."""
        os.environ.pop("VIPPET_VERSION", None)
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_VERSION, "unknown")

    def test_empty_version_env_var_falls_back_to_unknown(self):
        """An empty VIPPET_VERSION value behaves like an unset one."""
        os.environ["VIPPET_VERSION"] = ""
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_VERSION, "unknown")

    def test_whitespace_only_version_env_var_falls_back_to_unknown(self):
        """A whitespace-only VIPPET_VERSION value behaves like an unset one."""
        os.environ["VIPPET_VERSION"] = "   "
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_VERSION, "unknown")

    # ------------------------------------------------------------------
    # VIPPET_REVISION
    # ------------------------------------------------------------------

    def test_explicit_revision_is_used_verbatim(self):
        """A real git commit hash is exposed unchanged."""
        os.environ["VIPPET_REVISION"] = "a1b2c3d"
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_REVISION, "a1b2c3d")

    def test_explicit_dirty_revision_is_used_verbatim(self):
        """A "-dirty"-suffixed revision is exposed unchanged."""
        os.environ["VIPPET_REVISION"] = "a1b2c3d-dirty"
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_REVISION, "a1b2c3d-dirty")

    def test_explicit_revision_is_stripped_of_surrounding_whitespace(self):
        """Leading/trailing whitespace around a real revision is trimmed."""
        os.environ["VIPPET_REVISION"] = "  a1b2c3d  "
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_REVISION, "a1b2c3d")

    def test_missing_revision_env_var_falls_back_to_unknown(self):
        """No VIPPET_REVISION set at all -> "unknown"."""
        os.environ.pop("VIPPET_REVISION", None)
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_REVISION, "unknown")

    def test_empty_revision_env_var_falls_back_to_unknown(self):
        """An empty VIPPET_REVISION value behaves like an unset one."""
        os.environ["VIPPET_REVISION"] = ""
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_REVISION, "unknown")

    def test_whitespace_only_revision_env_var_falls_back_to_unknown(self):
        """A whitespace-only VIPPET_REVISION value behaves like an unset one."""
        os.environ["VIPPET_REVISION"] = "   "
        module = _reload_app_version_module()
        self.assertEqual(module.VIPPET_REVISION, "unknown")


if __name__ == "__main__":
    unittest.main()
