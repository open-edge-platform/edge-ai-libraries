# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from langchain_community.document_transformers import Html2TextTransformer
from langchain_core.documents import Document
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

def parse_html_content(html_content: str, source_url: str = "") -> str:
    """
    Parses HTML content (already fetched) and converts it to plain text.
    This function does NOT fetch URLs - it only transforms HTML to text.

    Args:
        html_content (str): The HTML content to parse.
        source_url (str, optional): The source URL for metadata purposes only.

    Returns:
        str: Plain text extracted from the HTML.
    """

    html2text = Html2TextTransformer()
    doc = Document(page_content=html_content, metadata={"source": source_url})
    transformed_docs = html2text.transform_documents([doc])

    return transformed_docs[0].page_content if transformed_docs else ""

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