# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Drift guard: every Pydantic Settings field in app/settings.py must be
mentioned (commented or active) in .env.example.

This test is the reason new settings get documented at the same commit
they are introduced - if you add a Field() and forget to update
.env.example, this test fails in CI.
"""

import re
from pathlib import Path

from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# These are intentionally not surfaced in .env.example because they are
# either Docker-only (PROJECT_NAME etc., which ARE in the file but aren't
# Settings fields) or explicitly internal. Add a name here only when it
# is a Settings field that should not appear in the user-facing template.
INTENTIONALLY_OMITTED: set[str] = set()

# Fields whose canonical env-var name differs from the field name.
ALIAS_OVERRIDES: dict[str, str] = {
    # cors_origins_raw is exposed as CORS_ORIGINS via validation_alias.
    "cors_origins_raw": "CORS_ORIGINS",
}


def _expected_env_names() -> set[str]:
    names: set[str] = set()
    for field_name in Settings.model_fields:
        if field_name in INTENTIONALLY_OMITTED:
            continue
        env_name = ALIAS_OVERRIDES.get(field_name, field_name).upper()
        names.add(env_name)
    return names


def _names_in_env_example() -> set[str]:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    # Match both `FOO=...` and commented `#FOO=...` / `# FOO=...` lines.
    pattern = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)
    return {m.group(1) for m in pattern.finditer(text)}


class TestEnvExampleCoverage:
    def test_every_settings_field_documented(self):
        expected = _expected_env_names()
        present = _names_in_env_example()
        missing = expected - present
        assert not missing, (
            "These app/settings.py fields are not mentioned in .env.example "
            f"(add them, even if commented out): {sorted(missing)}"
        )

    def test_metrics_manager_hostname_documented(self):
        # Not a Settings field (it's read directly by qmassa_reader / npu_reader
        # / telegraf.conf), but users still need to discover it from the
        # template.
        assert "METRICS_MANAGER_HOSTNAME" in _names_in_env_example()
