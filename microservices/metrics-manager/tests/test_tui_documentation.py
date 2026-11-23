# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Keep dashboard screenshots and migration instructions reachable."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs/user-guide/get-started/terminal-dashboard.md"
PACKAGE_GUIDE = ROOT / "docs/user-guide/get-started/bare-metal-package.md"


@pytest.mark.parametrize("guide", [GUIDE, PACKAGE_GUIDE])
def test_dashboard_screenshots_exist_and_have_licenses(guide):
    links = re.findall(r"!\[[^\]]*\]\(\./(images/mm-tui-[^)]+\.png)\)", guide.read_text())
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


def test_packaged_guide_keeps_relative_image_links():
    spec = yaml.safe_load((ROOT / "native/packaging/nfpm.yaml").read_text())
    contents = {entry.get("src"): entry["dst"] for entry in spec["contents"]}
    readme = Path(contents["dist/doc/README.md"])
    images = Path(contents["dist/doc/images/*"])
    assert images == readme.parent / "images"
    build = (ROOT / "native/build.sh").read_text()
    assert (
        'cp -R "$COMPONENT_DIR/docs/user-guide/get-started/images" "$STAGE_DIR/doc/images"' in build
    )


@pytest.mark.parametrize("name", ["native-metric-migration.md", "terminal-dashboard.md"])
def test_packaged_guides_are_staged_and_installed(name):
    guide = GUIDE.parent / name
    assert guide.is_file()
    assert "SPDX-License-Identifier: Apache-2.0" in guide.read_text()
    spec = yaml.safe_load((ROOT / "native/packaging/nfpm.yaml").read_text())
    contents = {entry.get("src"): entry["dst"] for entry in spec["contents"]}
    assert contents[f"dist/doc/{name}"] == f"/usr/share/doc/metrics-manager/{name}"
    build = (ROOT / "native/build.sh").read_text()
    assert f'"$COMPONENT_DIR/docs/user-guide/get-started/{name}"' in build
    assert f'"$STAGE_DIR/doc/{name}"' in build
    assert "](./native-metric-migration.md)" in PACKAGE_GUIDE.read_text()
