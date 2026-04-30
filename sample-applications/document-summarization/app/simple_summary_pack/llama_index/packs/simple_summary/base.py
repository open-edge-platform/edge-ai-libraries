# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Simple Summary."""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from llama_index.core.schema import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import get_response_synthesizer, Settings
from llama_index.core.llms import LLM

from app.config import Settings as ConfigSetting

config = ConfigSetting()


class BaseLlamaPack(ABC):
    """Minimal base class replacing the removed llama_index.core.llama_pack.BaseLlamaPack."""

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Run the pack."""


class SimpleSummaryPack(BaseLlamaPack):
    """
    Summarizes a list of documents using tree_summarize in a single pass.

    Instead of building a DocumentSummaryIndex (one LLM call per chunk),
    all document nodes are passed directly to a tree_summarize synthesizer
    which reduces N sequential calls to O(log N) hierarchical calls.

    Attributes
    ----------
    nodes : list
        Text nodes parsed from the input documents.
    response_synthesizer : BaseSynthesizer
        Tree-summarize response synthesizer.
    query : str
        The summarization query/instruction.

    Methods
    -------
    run() -> str
        Synthesizes and returns the summary.
    """

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
        self.query = query

        splitter = SentenceSplitter(chunk_size=config.CHUNK_SIZE or 4096)
        self.nodes = splitter.get_nodes_from_documents(documents)
        self.response_synthesizer = get_response_synthesizer(
            response_mode="tree_summarize", use_async=False
        )

    def run(self, *args: Any, **kwargs: Any) -> str:
        """Return the summary by synthesizing all nodes in a single tree_summarize pass."""
        response = self.response_synthesizer.synthesize(self.query, nodes=self.nodes)
        return str(response)
