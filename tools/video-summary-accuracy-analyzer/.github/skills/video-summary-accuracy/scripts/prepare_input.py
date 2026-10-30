#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Prepare one Markdown upload from a combined text file or two summary files."""

import argparse
import html
from pathlib import Path
import re
import sys
import tempfile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SECTION_LABEL = re.compile(
    r"(?im)^ {0,3}(?:##[ \t]+)?(Reference|Generated)[ \t]*:?[ \t]*$"
)


def read_summary(path: Path) -> str:
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("Input files must have a .md or .txt extension.")
    if not path.is_file():
        raise ValueError(f"Input is not a regular file: {path}")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("Input exceeds the analyzer's 10 MiB upload limit.")
    return path.read_text(encoding="utf-8")


def split_combined_text(text: str) -> tuple[str, str]:
    matches = list(SECTION_LABEL.finditer(text))
    if len(matches) != 2 or {match.group(1).lower() for match in matches} != {
        "reference", "generated"
    } or text[:matches[0].start()].strip():
        raise ValueError(
            "Combined .txt input needs exactly one Reference and one Generated "
            "label on separate lines, with no unlabeled text before them."
        )
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).lower()] = text[match.end():end].strip()
    return sections["reference"], sections["generated"]


def prepare(reference: str, generated: str) -> Path:
    if not reference.strip() or not generated.strip():
        raise ValueError("Reference and Generated summaries must both be non-empty.")

    def section(name: str, text: str) -> str:
        # A single raw HTML block keeps Markdown headings in supplied text from
        # becoming analyzer section boundaries.
        escaped = html.escape(text.strip()).replace("\n", "&#10;")
        return f"## {name}\n<div>{escaped}</div>\n"

    content = section("Reference", reference) + "\n" + section("Generated", generated)
    if len(content.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise ValueError("Combined input exceeds the analyzer's 10 MiB upload limit.")

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="vsa-", suffix=".md", delete=False
    ) as output:
        output.write(content)
        return Path(output.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--combined", type=Path, help="Combined .md or labeled .txt file")
    inputs.add_argument("--reference-file", type=Path, help="Reference .md or .txt file")
    parser.add_argument("--generated-file", type=Path, help="Generated .md or .txt file")
    args = parser.parse_args()
    if bool(args.reference_file) != bool(args.generated_file):
        parser.error("--reference-file and --generated-file must be used together")
    try:
        if args.combined:
            content = read_summary(args.combined)
            if args.combined.suffix.lower() == ".md":
                if not content.strip():
                    raise ValueError("Combined Markdown input must not be empty.")
                result = args.combined.resolve()
            else:
                result = prepare(*split_combined_text(content))
        else:
            result = prepare(read_summary(args.reference_file),
                             read_summary(args.generated_file))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Invalid evaluation input: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
