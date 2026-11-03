# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Read complete task files once, normalizing them to UTF-8 for both stages."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import stat

from .schemas import ExtractionTask
from .shared import shared_path
from .structure import FileInfo, Tree, _toc_insert

DEFAULT_MAX_TASK_BYTES = 64 * 1024 * 1024


class TaskTooLarge(ValueError):
    pass


def file_text(data: bytes, path: str, media_type: str = "") -> str:
    """No previews or row/page caps: planning must see the entire task."""
    suffix = Path(path).suffix.lower()
    stream = BytesIO(data)
    try:
        if suffix == ".pdf" or media_type == "application/pdf":
            from pypdf import PdfReader

            parts = []
            for number, page in enumerate(PdfReader(stream).pages, 1):
                extracted = page.extract_text() or ""
                if extracted.strip():
                    parts.append(f"[page {number}]\n{extracted}")
            text = "\n\n".join(parts)
        elif suffix == ".docx" or media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph

            document = Document(stream)
            parts = []
            for block in document.iter_inner_content():
                if isinstance(block, Paragraph):
                    parts.append(block.text)
                elif isinstance(block, Table):
                    parts.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
            text = "\n".join(parts)
        elif suffix in (".xlsx", ".xlsm") or media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            from openpyxl import load_workbook

            workbook = load_workbook(stream, read_only=True, data_only=True)
            try:
                parts = []
                for sheet in workbook:
                    parts.append(f"[sheet {sheet.title}]")
                    parts.extend(
                        " | ".join("" if cell is None else str(cell) for cell in row)
                        for row in sheet.iter_rows(values_only=True)
                    )
                text = "\n".join(parts)
            finally:
                workbook.close()
        else:
            # Strict decoding prevents arbitrary binary files from becoming gibberish.
            text = data.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("binary content is not supported by the text reader")
    except Exception as error:
        raise ValueError(f"Cannot read {path!r}: {error}") from error
    if not text.strip():
        raise ValueError(f"No extractable text in {path!r}")
    return text


def materialize_task(
    task: ExtractionTask,
    root: Path,
    chars_per_token: float,
    max_bytes: int = DEFAULT_MAX_TASK_BYTES,
    *, shared_dir: Path | None = None,
) -> Tree:
    """Keep logical source paths even for text blobs named after PDFs/office files.

    The extraction pipeline exposes only read_text on this normalized tree. Thus
    shared PDFs and already-extracted PDF text share the same logical source
    paths. `file_path` is relative to `shared_dir`, not the normalization tree.
    """
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    tree = Tree(root=root)
    total = 0
    normalized_total = 0
    for item in task.items:
        if item.content is not None:
            data = item.content.encode("utf-8")
        else:
            if shared_dir is None or item.file_path is None:
                raise ValueError("File tasks require a shared upload directory")
            source = shared_path(shared_dir, item.file_path)
            if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
                raise ValueError(f"Shared upload file not found or not a regular file: {item.file_path!r}")
            if source.stat().st_size > max_bytes - total:
                raise TaskTooLarge(f"Task exceeds the {max_bytes}-byte input limit")
            with source.open("rb") as stream:
                data = stream.read(max_bytes - total + 1)
        total += len(data)
        if total > max_bytes:
            raise TaskTooLarge(f"Task exceeds the {max_bytes}-byte input limit")
        text = item.content if item.content is not None else file_text(data, item.file_path or item.path, item.media_type)
        if not text.strip():
            raise ValueError(f"No extractable text in {item.path!r}")
        normalized_total += len(text.encode("utf-8"))
        if normalized_total > max_bytes:
            raise TaskTooLarge(f"Normalized task exceeds the {max_bytes}-byte input limit")
        path = root / item.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        tree.files.append(FileInfo(
            rel_path=item.path, abs_path=path, size_bytes=len(text.encode("utf-8")),
            approx_tokens=int(len(text) / chars_per_token), ext="txt",
        ))
        _toc_insert(tree.toc, item.path)
    return tree