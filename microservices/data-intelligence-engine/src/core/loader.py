# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import List

from llama_index.core.schema import Document

# Extensions the plain-text reader accepts; SimpleDirectoryReader ignores `required_exts`
# for explicit files, so single files are checked here.
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
