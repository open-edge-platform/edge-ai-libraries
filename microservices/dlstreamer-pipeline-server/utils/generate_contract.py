#!/usr/bin/env python3
#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""Generate contract.json from source schema and version information.

Reads:
  - document-versions.yaml  (contract-version)
  - src/server/schema.py    (reserved element names, supported formats)

Writes:
  - contract.json at the service root

Run from the service root:
    python3 utils/generate_contract.py

CI usage (fail if committed file is stale):
    python3 utils/generate_contract.py --check
"""

import argparse
import ast
import json
import os
import sys


SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSIONS_FILE = os.path.join(SERVICE_ROOT, "document-versions.yaml")
SCHEMA_FILE = os.path.join(SERVICE_ROOT, "src", "server", "schema.py")
OUTPUT_FILE = os.path.join(SERVICE_ROOT, "contract.json")


def read_version(versions_path: str) -> str:
    """Parse the version string from document-versions.yaml.

    The file has a single line of the form:
        release/vX.Y.Z:X.Y.Z
    """
    with open(versions_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                # Format: release/vX.Y.Z:X.Y.Z  — take the part after the colon.
                parts = line.split(":")
                if len(parts) >= 2:
                    return parts[-1].strip()
                return line
    raise ValueError(f"Could not parse version from {versions_path}")


def extract_reserved_element_names(schema_path: str) -> list:
    """Walk the schema.py AST to collect string values assigned to 'name'
    keys inside dicts that are themselves the value of an 'element' key.
    This restricts extraction to GStreamer element bindings and excludes
    names from 'filter' or other non-element dicts.

    Returns a sorted, deduplicated list.
    """
    with open(schema_path, encoding="utf-8") as fh:
        source = fh.read()

    tree = ast.parse(source, filename=schema_path)
    names = set()

    def collect_names_from_element_value(node):
        """Recursively collect 'name' string values from an element value node.

        The node may be a dict (object form), a list of dicts (array form),
        or a string constant (string form — the whole value is the element name).
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "name"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    names.add(value.value)
        elif isinstance(node, ast.List):
            for elt in node.elts:
                collect_names_from_element_value(elt)

    class ElementVisitor(ast.NodeVisitor):
        def visit_Dict(self, node):  # noqa: N802
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "element":
                    collect_names_from_element_value(value)
            self.generic_visit(node)

    ElementVisitor().visit(tree)

    # Always include the well-known reserved names even if schema.py is refactored.
    names.update({"source", "destination", "appsink", "metaconvert"})
    return sorted(names)


def build_contract(version: str, reserved_names: list) -> dict:
    return {
        "contract-version": version,
        "element-binding-forms": ["string", "object", "array"],
        "supported-formats": ["element-properties", "json"],
        "reserved-element-names": reserved_names,
        "unresolved-element-behavior": "log-and-continue",
        "unresolved-property-behavior": "log-and-continue",
        "normative-reference": (
            "docs/user-guide/advanced-guide/detailed_usage/"
            "rest_api/parameter_contract.md"
        ),
        "conformance-tests": "tests/test_parameter_contract.py",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 1 if the committed contract.json is stale.",
    )
    args = parser.parse_args()

    version = read_version(VERSIONS_FILE)
    reserved_names = extract_reserved_element_names(SCHEMA_FILE)
    contract = build_contract(version, reserved_names)
    generated = json.dumps(contract, indent=2) + "\n"

    if args.check:
        if not os.path.exists(OUTPUT_FILE):
            print(f"ERROR: {OUTPUT_FILE} does not exist. Run generate_contract.py to create it.")
            sys.exit(1)
        with open(OUTPUT_FILE, encoding="utf-8") as fh:
            committed = fh.read()
        if committed != generated:
            print(
                f"ERROR: {OUTPUT_FILE} is stale.\n"
                "Run  python3 utils/generate_contract.py  and commit the result."
            )
            sys.exit(1)
        print(f"OK: {OUTPUT_FILE} is up to date (contract-version={version})")
        sys.exit(0)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        fh.write(generated)
    print(f"Written {OUTPUT_FILE} (contract-version={version})")


if __name__ == "__main__":
    main()
