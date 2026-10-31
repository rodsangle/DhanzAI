import subprocess
from pathlib import Path

import pytest
from test_documents import make_pdf

from dhanz_knowledge.documents import extract_document
from dhanz_knowledge.ocr import PDFOCR, OCRError


def test_scanned_pdf_recognized_and_text_pdf_not_sent_to_ocr():
    calls = []

    def recognize(page):
        calls.append(page)
        return "Pump serial 12345"

    doc = extract_document("scan.pdf", make_pdf(None), pdf_ocr=recognize)
    assert "## Page 1\nPump serial 12345" in doc.text
    assert "recognition errors" in doc.notes[0]
    extract_document("text.pdf", make_pdf(), pdf_ocr=recognize)
    assert calls == [1]


def test_ocr_failure_is_reported_without_inventing_content():
    def fail(page):
        raise OCRError("OCR processing time limit reached")

    doc = extract_document("scan.pdf", make_pdf(None), pdf_ocr=fail)
    assert doc.text == ""
    assert "time limit" in doc.notes[0]


def test_mixed_pdf_keeps_digital_text_after_ocr_failure():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Digital page remains readable")
    pdf.add_page()
    calls = []

    def fail(page):
        calls.append(page)
        raise OCRError("OCR unavailable; some pages were not read.")

    doc = extract_document("mixed.pdf", bytes(pdf.output()), pdf_ocr=fail)
    assert "## Page 2\nDigital page remains readable" in doc.text
    assert calls == [1]
    assert "some pages were not read" in doc.notes[0]


def test_local_commands_cleanup_and_page_limit(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] > 0
        if args[0] == "tesseract":
            Path(args[2] + ".txt").write_text("Recognized text", encoding="utf-8")

    monkeypatch.setattr(subprocess, "run", run)
    ocr = PDFOCR(b"pdf", max_pages=1)
    assert ocr(3) == "Recognized text"
    assert calls[0][1:5] == ["-f", "3", "-l", "3"]
    assert not Path(calls[0][-1]).parent.exists()
    with pytest.raises(OCRError, match="page limit"):
        ocr(4)


@pytest.mark.parametrize(
    "error", [FileNotFoundError(), subprocess.TimeoutExpired("ocr", 1), subprocess.CalledProcessError(1, "ocr")]
)
def test_command_errors_are_safe_and_temporary_files_removed(monkeypatch, error):
    paths = []

    def run(args, **kwargs):
        paths.append(Path(args[-1]).parent)
        raise error

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(OCRError):
        PDFOCR(b"pdf")(1)
    assert not paths[0].exists()
