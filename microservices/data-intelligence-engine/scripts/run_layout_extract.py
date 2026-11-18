# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Run the real layout extractor over a PDF on CPU.

Exercises `core.extractor.extract_layout` with its configured backends -- the
OpenVINO PP-DocLayoutV3 detector and the `hybrid` OCR -- rather than the
injected fakes the unit test uses, so it proves the whole chain runs end to end.

    PYTHONPATH=src python scripts/export_pp_doclayout_v3.py

    ENGINE_LAYOUT_DEVICE=CPU \
    PYTHONPATH=src python scripts/run_layout_extract.py <path-to.pdf> [max_pages]
"""

import sys

from core import extractor


class MemoryBlobWriter:
    """Keeps figure bytes in memory and hands back a key, like the object store."""

    def __init__(self):
        self.written = []

    def __call__(self, data, content_type=None):
        self.written.append((data, content_type))
        return f"blobs/{len(self.written)}"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else None

    render = None
    if max_pages is not None:
        from core.extractor import render_pdf

        def render(p, dpi):  # noqa: E306 - only the first `max_pages` pages
            return render_pdf(p, dpi)[:max_pages]

    writer = MemoryBlobWriter()
    stream = extractor.extract_layout(path, "asset-run", writer, render=render)

    kinds = {}
    for block in stream.blocks:
        kinds[block.kind] = kinds.get(block.kind, 0) + 1
    print(f"file            : {stream.metadata['file_name']}")
    print(f"blocks          : {len(stream.blocks)}  {kinds}")
    print(f"figures stored  : {len(writer.written)}")
    print("-" * 72)
    for block in stream.blocks[:20]:
        if block.kind == "text":
            preview = " ".join(block.text.split())[:80]
            print(f"[p{block.page} #{block.reading_order} text  {block.metadata['type']:14s}] {preview}")
        else:
            cap = " ".join((block.caption or "").split())[:60]
            print(
                f"[p{block.page} #{block.reading_order} image {block.metadata['type']:14s}] "
                f"key={block.media_key} bytes={block.metadata['byte_size']} cap={cap!r}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
