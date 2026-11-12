from io import BytesIO
from shutil import which

import pytest
from fpdf import FPDF
from openpyxl import load_workbook

from app.assistant_studio.pdf_excel import extract_pdf, workbook


def test_real_thirteen_page_pdf_is_not_reduced_to_retrieved_passages():
    if not all(which(p) for p in ("pdfinfo", "pdftotext")):
        pytest.skip("Poppler required for integration test")
    pdf = FPDF()
    for page in range(1, 14):
        pdf.add_page()
        pdf.set_font("Courier", size=10)
        pdf.cell(0, 7, "Name                    ID", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, f"Apprentice {page:<12}   {page:05}", new_x="LMARGIN", new_y="NEXT")
        for line in range(8):
            pdf.cell(
                0,
                7,
                f"Description line {line} has editable training details for apprentice page {page}",
                new_x="LMARGIN",
                new_y="NEXT",
            )
    pages = extract_pdf(bytes(pdf.output()), ocr_enabled=False)
    assert len(pages) == 13
    data, audit = workbook([("training.pdf", pages)])
    book = load_workbook(BytesIO(data))
    assert audit[0]["pages"] == 13
    values = [cell.value for row in book.active for cell in row]
    for page in range(1, 14):
        assert f"{page:05}" in values
    assert not any(page.ocr for page in pages)
