# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer
from .db_config import pool_execution

def check_tables_exist() -> bool:
    """Check if the required tables exist in the database."""
    check_tables_query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'langchain_pg_embedding'
                ) AND EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'langchain_pg_collection'
                );
                """
    tables_exist = pool_execution(check_tables_query, {})

    return tables_exist[0][0]

def get_separators():
    """
    Retrieves a list of separators commonly used for splitting text.
    Returns:
        list: A list of string separators, including common whitespace, punctuation,
        and special characters such as zero-width space, fullwidth comma,
        ideographic comma, fullwidth full stop, and ideographic full stop.
    """

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
    """
    Loads HTML content from the provided links, processes it into text, and splits it into chunks.
    Args:
        links (list): A list of URLs to load HTML content from.
        chunk_size (int, optional): The maximum size of each text chunk. Defaults to 1500.
        chunk_overlap (int, optional): The number of overlapping characters between consecutive chunks. Defaults to 50.
    Returns:
        list: A list of processed and split text documents.
    """

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
    """
    Parses HTML content from the input and combines it into a single string.
    Args:
        input (str): The input source containing the HTML content to be parsed.
        chunk_size (int): The size of each chunk to process the HTML content.
        chunk_overlap (int): The overlap size between consecutive chunks.
    Returns:
        str: A single string containing the combined HTML content from all chunks.
    """

    docs = load_html_content(input, chunk_size, chunk_overlap)
    html_content = ""
    for doc in docs:
        html_content += doc.page_content + "\n"

    return html_content

class Validation:
    @staticmethod
    def sanitize_input(input: str) -> str | None:
        """Takes an string input and strips whitespaces. Returns None if
        string is empty else returns the string.
        """
        input = str.strip(input)
        if len(input) == 0:
            return None

        return input

    @staticmethod
    def strip_input(input: str) -> str:
        """Takes and string input and returns whitespace stripped string."""
        return str.strip(input)