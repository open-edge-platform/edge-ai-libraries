# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""File readers are exhaustive; unsupported/textless input is never fabricated."""
import io

import pytest
from docx import Document
from openpyxl import Workbook
from pypdf import PdfWriter

from okf_extractor.readers import file_text


def test_docx_preserves_paragraph_and_table_order_and_reads_every_cell():
    document = Document()
    document.add_paragraph("Before table")
    table = document.add_table(rows=2, cols=2)
    for number, row in enumerate(table.rows):
        row.cells[0].text = f"Row {number} first"
        row.cells[1].text = f"Row {number} last"
    document.add_paragraph("After table")
    data = io.BytesIO()
    document.save(data)

    text = file_text(data.getvalue(), "notes.docx")

    assert text.index("Before table") < text.index("Row 0 first") < text.index("Row 1 last") < text.index("After table")


def test_spreadsheet_reads_every_worksheet_and_row_including_the_tail():
    workbook = Workbook()
    workbook.active.title = "First"
    for number in range(350):
        workbook.active.append([number, f"row-{number}"])
    workbook.create_sheet("Last").append(["last-sheet-tail"])
    data = io.BytesIO()
    workbook.save(data)

    text = file_text(data.getvalue(), "table.xlsx")

    assert "row-0" in text and "row-349" in text
    assert "[sheet Last]" in text and text.endswith("last-sheet-tail")


def test_pdf_without_text_requires_ocr_instead_of_becoming_a_page_number_concept():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    data = io.BytesIO()
    writer.write(data)
    with pytest.raises(ValueError, match="No extractable text"):
        file_text(data.getvalue(), "scanned.pdf")