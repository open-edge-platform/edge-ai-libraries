# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer

def get_separators():
    separators = [
        "\n\n",
        "\n",
        " ",
        ".",
        ",",
        "\u200b",  # Zero-width space
        "\uff0c",  # Fullwidth comma
        "\u3001",  # Ideographic comma
        "\uff0e",  # Fullwidth full stop
        "\u3002",  # Ideographic full stop
        "",
    ]
    return separators


def load_html_content(links, chunk_size=1500, chunk_overlap=50):
    loader = AsyncHtmlLoader(links, ignore_load_errors=True, trust_env=True)
    docs = loader.load()
    html2text = Html2TextTransformer()
    docs = list(html2text.transform_documents(docs))
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    docs = text_splitter.split_documents(docs)

    return docs


def parse_html(input, chunk_size, chunk_overlap):
    docs = load_html_content(input, chunk_size, chunk_overlap)
    html_content = ""
    for doc in docs:
        html_content += doc.page_content + "\n"

    return html_content
