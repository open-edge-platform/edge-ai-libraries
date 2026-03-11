# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Simple Summary."""

from typing import Any, Dict, List, Optional, List

from llama_index.core.llama_pack import BaseLlamaPack
from llama_index.core.schema import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import SimpleDirectoryReader, get_response_synthesizer
from llama_index.core import DocumentSummaryIndex, Settings
from llama_index.core.llms import LLM

from app.config import Settings as ConfigSetting

config = ConfigSetting()

class SimpleSummaryPack(BaseLlamaPack):
    """
    A class used to represent a Simple Summary Pack.

    Attributes
    ----------
    response_synthesizer : BaseSynthesizer
        A response synthesizer for generating summaries.
    splitter : SentenceSplitter
        Node parsers. Parse text with a preference for complete sentences.
    doc_summary_index : DocumentSummaryIndex
        The document summary index will extract a summary from each document.

    Methods
    -------
    __init__(documents: List[Document], verbose: bool = False, query: str, llm: Optional[LLM] = None)
        Initializes the SimpleSummaryPack with the provided documents, query, verbosity, and LLM.
    run(fileName: str) -> str
        Generates the summary for the document
    """
    """"""
    def __init__(
        self,
        documents: List[Document],
        query: str,
        verbose: bool = False,
        llm: Optional[LLM] = None,
    ) -> None:
        """Init params."""

        Settings.embed_model = None
        Settings.llm = llm
        self.verbose = verbose
        self.splitter = SentenceSplitter(chunk_size=config.CHUNK_SIZE or 4096)

        self.response_synthesizer = get_response_synthesizer(
            response_mode="tree_summarize", use_async=True)
        self.doc_summary_index = DocumentSummaryIndex.from_documents(
            documents,
            summary_query=query,
            llm=llm,
            transformations=[self.splitter],
            response_synthesizer=self.response_synthesizer,
            show_progress=True,
        )

    def run(self, fileName: str) -> str:
        """Return the summary."""
        return self.doc_summary_index.get_document_summary(fileName)
