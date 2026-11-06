# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Keep dashboard screenshots and migration instructions reachable."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs/user-guide/get-started/terminal-dashboard.md"


def test_dashboard_screenshots_exist_and_have_licenses():
    links = re.findall(r"!\[[^\]]*\]\(\./(images/mm-tui-[^)]+\.png)\)", GUIDE.read_text())
    assert set(links) == {
        "images/mm-tui-overview.png",
        "images/mm-tui-charts.png",
        "images/mm-tui-alerts.png",
    }
    for relative in links:
        image = GUIDE.parent / relative
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        license_text = image.with_suffix(".png.license").read_text()
        assert "SPDX-License-Identifier: Apache-2.0" in license_text
        assert "SPDX-FileCopyrightText:" in license_text


def test_dashboard_guide_includes_unit_migration():
    name = "native-metric-migration.md"
    assert f"](./{name})" in GUIDE.read_text()
    migration = GUIDE.parent / name
    assert migration.is_file()
    assert "SPDX-License-Identifier: Apache-2.0" in migration.read_text()
