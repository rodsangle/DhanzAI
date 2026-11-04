from io import BytesIO
from threading import Event
from unittest.mock import patch

import pytest
from openpyxl import load_workbook

from app.assistant_studio.pdf_excel import (
    Cell,
    ConversionError,
    Page,
    extract_pdf,
    native_rows,
    ocr_rows,
    sheet_name,
    workbook,
)


def test_all_13_pages_become_editable_cells_with_leading_zeros_and_unique_sheets():
    pages = [
        Page(i, [[Cell(0, "Name"), Cell(20, "ID")], [Cell(0, f"Apprentice {i}"), Cell(20, f"{i:05}")]])
        for i in range(1, 14)
    ]
    data, audit = workbook(
        [
            ("apprentice training signing sheet.pdf", pages),
            ("apprentice training signing sheet.pdf", [Page(1, [[Cell(0, "Other data")]])]),
        ]
    )
    book = load_workbook(BytesIO(data))
    assert len(book.sheetnames) == 2 and all(len(n) <= 31 for n in book.sheetnames)
    assert book.sheetnames[0].casefold() != book.sheetnames[1].casefold()
    sheet = book.worksheets[0]
    rows = list(sheet.values)
    assert rows[0] == ("Name", "ID")
    assert [row[0] for row in rows[1:]] == [f"Apprentice {i}" for i in range(1, 14)]
    assert rows[-1][1] == "00013" and sheet["B14"].data_type == "s"
    assert audit[0]["pages"] == 13 and audit[0]["rows"] == 14
    assert list(book.worksheets[1].values) == [("Other data",)]


def test_unclear_ocr_is_flagged_and_formulas_are_text():
    data, _ = workbook([("report.pdf", [Page(1, [[Cell(0, '=HYPERLINK("https://example.com")', 50)]], True)])])
    book = load_workbook(BytesIO(data))
    cell = book.active["A1"]
    assert cell.data_type == "s" and cell.fill.fgColor.rgb.endswith("FFF2CC")
    assert "Verify" in cell.comment.text and "not a claim" in cell.comment.text


def test_sheet_names_are_valid_unique_and_native_rows_preserve_spacing():
    used = set()
    names = [sheet_name("bad:[]*?name.pdf", used), sheet_name("BAD:[]*?name.pdf", used)]
    assert len(set(n.casefold() for n in names)) == 2
    assert not any(c in names[0] for c in "[]:*?/\\")
    rows = native_rows("Item name       Quantity\nPipe section    0012")
    assert [c.text for c in rows[1]] == ["Pipe section", "0012"]


def test_ocr_tsv_groups_cells_and_retains_confidence():
    text = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    text += "5\t1\t1\t1\t1\t1\t10\t10\t30\t10\t93\tName\n"
    text += "5\t1\t2\t1\t1\t1\t150\t10\t40\t10\t44\t00123\n"
    rows = ocr_rows(text)
    assert [c.text for c in rows[0]] == ["Name", "00123"]
    assert rows[0][1].confidence == 44


def test_page_limit_and_disabled_ocr_fail_without_partial_workbook():
    with (
        patch("app.assistant_studio.pdf_excel.shutil.which", return_value="/utility"),
        patch("app.assistant_studio.pdf_excel._call", return_value="Pages: 21\n"),
    ):
        with pytest.raises(ConversionError, match="Nothing was truncated"):
            extract_pdf(b"%PDF", max_pages=20)
    with (
        patch("app.assistant_studio.pdf_excel.shutil.which", return_value="/utility"),
        patch("app.assistant_studio.pdf_excel._call", side_effect=["Pages: 1\n", ""]),
    ):
        with pytest.raises(ConversionError, match="OCR"):
            extract_pdf(b"%PDF", ocr_enabled=False)


def test_cancelled_conversion_cannot_return_complete_data():
    event = Event()
    event.set()
    with (
        patch("app.assistant_studio.pdf_excel.shutil.which", return_value="/utility"),
        patch("app.assistant_studio.pdf_excel._call", return_value="Pages: 1\n"),
    ):
        with pytest.raises(ConversionError, match="stopped"):
            extract_pdf(b"%PDF", cancelled=event)
