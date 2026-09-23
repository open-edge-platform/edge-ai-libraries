#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generate the OEP CLI Installer Web UI config.json from decentralized sources.

The Web UI selector (docs/oep-cli-installer-files/selector.js) loads a single
``config.json``. Rather than hand-editing that large, shared file, the UI
configuration is split into:

* ``docs/oep-cli-installer-files/config.base.json`` -- global/shared settings
  (title, share keys, OS category, output templates, profile ordering).
* ``profile/<name>/web_config.json`` -- one small fragment per profile, co-located
  with the profile definition, describing that profile's label, its modules,
  and its install / Get Started / Resources content.

This script merges those sources into the published ``config.json``. It
auto-injects the boilerplate that developers should not have to repeat:

* every module gets ``supports.PROFILE`` set to its owning profile, and
* every profile-scoped output rule gets its ``when`` condition
  (``{PROFILE: <value>, OP_SYSTEM: <default>}``).

Usage::

    python3 scripts/build-web-config.py            # regenerate config.json
    python3 scripts/build-web-config.py --check     # fail if config.json is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repository layout (paths are relative to this script's location).
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WEB_DIR = ROOT / "docs" / "oep-cli-installer-files"
BASE_PATH = WEB_DIR / "config.base.json"
OUTPUT_PATH = WEB_DIR / "config.json"
PROFILE_DIR = ROOT / "profile"


def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.exit(f"error: required file not found: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"error: invalid JSON in {path}: {exc}")


def _load_fragments() -> dict[str, dict]:
    """Return a mapping of profile value -> fragment, keyed by the fragment's
    own ``profile.value`` so the on-disk directory name is irrelevant."""
    fragments: dict[str, dict] = {}
    for path in sorted(PROFILE_DIR.glob("*/web_config.json")):
        fragment = _load_json(path)
        profile = fragment.get("profile") or {}
        value = profile.get("value")
        if not value:
            sys.exit(f"error: {path} is missing profile.value")
        if value in fragments:
            sys.exit(f"error: duplicate profile value '{value}' in {path}")
        fragment["_path"] = path
        fragments[value] = fragment
    return fragments


def build_config() -> dict:
    base = _load_json(BASE_PATH)
    fragments = _load_fragments()

    default_os = base.get("defaultOpSystem", "UBUNTU")
    order = base.get("profileOrder", [])

    # Every profile listed in profileOrder must have a fragment, and vice versa,
    # so the generated file can never silently drop or duplicate a profile.
    missing = [v for v in order if v not in fragments]
    if missing:
        sys.exit(f"error: profileOrder references profiles without a fragment: {missing}")
    extra = [v for v in fragments if v not in order]
    if extra:
        sys.exit(f"error: profile fragments not listed in profileOrder: {extra}")

    ordered = [fragments[v] for v in order]

    # --- PROFILE category ---
    profile_cat = dict(base["profileCategory"])
    profile_cat["options"] = [dict(frag["profile"]) for frag in ordered]

    # --- MODULE category (supports.PROFILE injected from the owning profile) ---
    module_cat = dict(base["moduleCategory"])
    module_options = []
    for frag in ordered:
        profile_value = frag["profile"]["value"]
        for module in frag.get("modules", []):
            option = {"label": module["label"], "value": module["value"]}
            option["supports"] = {"PROFILE": [profile_value]}
            if module.get("startStop"):
                option["startStop"] = True
            module_options.append(option)
    module_cat["options"] = module_options

    categories = [dict(base["opSystem"]), profile_cat, module_cat]

    # --- outputs ---
    out = base["outputs"]

    install_rules = []
    for frag in ordered:
        install = frag.get("install")
        if not install:
            continue
        install_rules.append(
            {
                "when": {"PROFILE": frag["profile"]["value"], "OP_SYSTEM": default_os},
                "text": install["text"],
            }
        )
    install_rules.append(out["install"]["genericRule"])
    install_output = {
        "id": "install",
        "label": out["install"]["label"],
        "fallback": out["install"]["fallback"],
        "rules": install_rules,
    }

    nextsteps_output = {
        "id": "nextsteps",
        "label": out["nextsteps"]["label"],
        "fallback": out["nextsteps"]["fallback"],
        "startStop": out["nextsteps"]["startStop"],
    }

    getstarted_rules = []
    for frag in ordered:
        gs = frag.get("getStarted")
        if not gs:
            continue
        getstarted_rules.append(
            {
                "when": {"PROFILE": frag["profile"]["value"], "OP_SYSTEM": default_os},
                "text": gs["text"],
                "link": gs["link"],
            }
        )
    getstarted_output = {
        "id": "getstarted",
        "label": out["getstarted"]["label"],
        "fallback": out["getstarted"]["fallback"],
        "rules": getstarted_rules,
    }

    resources_rules = []
    for frag in ordered:
        links = frag.get("resources")
        if not links:
            continue
        resources_rules.append(
            {
                "when": {"PROFILE": frag["profile"]["value"], "OP_SYSTEM": default_os},
                "links": links,
            }
        )
    resources_output = {
        "id": "resources",
        "label": out["resources"]["label"],
        "fallback": out["resources"]["fallback"],
        "rules": resources_rules,
    }

    return {
        "title": base["title"],
        "shareKeys": base["shareKeys"],
        "categories": categories,
        "outputs": [install_output, nextsteps_output, getstarted_output, resources_output],
    }


def _serialize(config: dict) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify config.json is up to date without writing; exit 1 if stale",
    )
    args = parser.parse_args()

    rendered = _serialize(build_config())

    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != rendered:
            print(
                "error: docs/oep-cli-installer-files/config.json is out of date.\n"
                "Run: python3 scripts/build-web-config.py",
                file=sys.stderr,
            )
            return 1
        print("config.json is up to date.")
        return 0

    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
