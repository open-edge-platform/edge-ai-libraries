# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Document loading.

Ported from edgecraftrag/components/data.py: turn file paths / raw text into
llama-index Documents via SimpleDirectoryReader.
"""

from pathlib import Path
from typing import List

from llama_index.core.schema import Document

# Extensions the plain-text reader accepts, and so -- with media files -- the file
# types an asset may be (`core/extractor.py:is_supported`). Enforced here rather
# than left to `required_exts`, which SimpleDirectoryReader applies only when it
# scans a directory, never to a file it is handed. Figures are extracted before
# this reader is reached (`core/extractor.py:extract`), for:
#   .pdf                         page + pixel bbox, from layout detection
#   .docx .pptx .xlsx .html .htm reading order (slide / sheet as page), when the
#                                file embeds pictures; xlsx charts are re-plotted
#   image files (by MIME type)   the file itself is one figure
# Everything else here, and those files without pictures, yields text only.
# Legacy binary .doc/.ppt and .epub are left out: llama-index has no .doc reader
# (the bytes would be read as text), its PptxReader opens only OOXML, and its
# EpubReader needs GPL-licensed packages.
SUPPORTED_EXTS = [".pdf", ".txt", ".docx", ".pptx", ".xlsx", ".csv", ".md", ".html", ".htm", ".rst"]


def text_to_documents(text: str) -> List[Document]:
    return [Document(text=text, metadata={"file_name": "text"})]


def file_to_documents(file_path: str) -> List[Document]:
    from llama_index.core import SimpleDirectoryReader
    path = Path(file_path)
    if path.is_dir():
        return SimpleDirectoryReader(input_dir=str(path), recursive=True, required_exts=SUPPORTED_EXTS).load_data()
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_EXTS:
            raise ValueError(f"Unsupported file type {path.suffix or '(none)'!r}: {path.name}")
        return SimpleDirectoryReader(input_files=[str(path)]).load_data()
    return []
