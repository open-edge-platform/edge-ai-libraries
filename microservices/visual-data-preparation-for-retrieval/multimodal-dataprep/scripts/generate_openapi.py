#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generate (or verify) the committed OpenAPI specification.

The specification under ``docs/user-guide/api-docs/openapi.yaml`` is generated from
the FastAPI application and must never be hand-edited.

Usage::

    python scripts/generate_openapi.py            # rewrite the committed spec
    python scripts/generate_openapi.py --check    # fail if the spec is out of date
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "user-guide" / "api-docs" / "openapi.yaml"


def render_spec() -> str:
    """Import the app and serialise its OpenAPI document deterministically."""
    sys.path.insert(0, str(REPO_ROOT))
    from src.main import app  # imported lazily so --help stays fast

    return yaml.safe_dump(app.openapi(), sort_keys=False, width=100, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the committed spec differs from the generated one.",
    )
    args = parser.parse_args()

    generated = render_spec()

    if not args.check:
        SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
        SPEC_PATH.write_text(generated, encoding="utf-8")
        print(f"Wrote {SPEC_PATH.relative_to(REPO_ROOT)}")
        return 0

    if not SPEC_PATH.exists():
        print(f"ERROR: {SPEC_PATH.relative_to(REPO_ROOT)} does not exist.", file=sys.stderr)
        return 1

    committed = SPEC_PATH.read_text(encoding="utf-8")
    if committed == generated:
        print(f"{SPEC_PATH.relative_to(REPO_ROOT)} is up to date.")
        return 0

    diff = difflib.unified_diff(
        committed.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile="committed",
        tofile="generated",
    )
    sys.stderr.writelines(diff)
    print(
        "\nERROR: the committed OpenAPI spec is out of date. "
        "Run: python scripts/generate_openapi.py",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
