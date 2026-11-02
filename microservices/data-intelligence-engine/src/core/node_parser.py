# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Simple node parser.

Ported from edgecraftrag/components/node_parser.py:SimpleNodeParser — a thin
wrapper over llama-index's SentenceSplitter (chunk_size / chunk_overlap).
Sentence splitting uses the same untrained Punkt implementation directly, not
LlamaIndex's NLTK downloader. Token counting requires a prepared local cache.
"""

import hashlib
import os
from pathlib import Path
from typing import List

import config
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, Document


class SimpleNodeParser(SentenceSplitter):
    """SentenceSplitter with EdgeCraftRAG's `run(docs=...)` entrypoint."""

    def run(self, docs: List[Document]) -> List[BaseNode]:
        return self.get_nodes_from_documents(docs, show_progress=False)


def _local_tokenizer():
    """Use LlamaIndex's existing token counts without its download fallback."""
    import llama_index.core
    from llama_index.core.utils import get_tokenizer

    if llama_index.core.global_tokenizer is not None:
        return llama_index.core.global_tokenizer
    cache_dir = os.getenv(
        "TIKTOKEN_CACHE_DIR",
        str(Path(llama_index.core.__file__).parent / "_static/tiktoken_cache"),
    )
    # LlamaIndex's default gpt-3.5-turbo tokenizer uses cl100k_base. Validate
    # the same cached artifact/hash as tiktoken before letting it load anything;
    # tiktoken otherwise downloads missing OR corrupt vocabulary files.
    vocabulary = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
    cache_key = hashlib.sha1(vocabulary.encode(), usedforsecurity=False).hexdigest()
    expected_hash = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
    cache_file = Path(cache_dir) / cache_key
    try:
        valid = bool(cache_dir) and hashlib.sha256(cache_file.read_bytes()).hexdigest() == expected_hash
    except OSError:
        valid = False
    if not valid:
        raise FileNotFoundError(
            f"No prepared cl100k_base tokenizer cache at {str(cache_file)!r}. "
            "Prepare the tiktoken vocabulary cache before starting the engine; "
            "the engine does not download tokenizer resources."
        )
    return get_tokenizer()


def build_node_parser(chunk_size: int = None, chunk_overlap: int = None) -> SimpleNodeParser:
    from nltk.tokenize import PunktSentenceTokenizer
    from llama_index.core.node_parser.text.utils import split_by_sentence_tokenizer_internal

    sentence_tokenizer = PunktSentenceTokenizer()
    return SimpleNodeParser(
        chunk_size=chunk_size or config.CHUNK_SIZE,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else config.CHUNK_OVERLAP,
        tokenizer=_local_tokenizer(),
        chunking_tokenizer_fn=lambda text: split_by_sentence_tokenizer_internal(
            text, sentence_tokenizer
        ),
    )
