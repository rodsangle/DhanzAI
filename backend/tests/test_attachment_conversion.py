from dataclasses import replace

from fpdf import FPDF

from tests.test_phase3 import chat, upload


def test_conversion_request_receives_all_thirteen_ocr_pages(client, auth, settings, provider, monkeypatch):
    settings.ocr_enabled = True
    monkeypatch.setattr(
        "app.services.files_service.PDFOCR.__call__",
        lambda self, page: (
            f"TRAINING_PAGE_{page}_START\n" + ("Apprentice I Hours 8\n" * 90) + f"TRAINING_PAGE_{page}_END"
        ),
    )
    pdf = FPDF()
    for _ in range(13):
        pdf.add_page()
    response = upload(client, auth, "training.pdf", bytes(pdf.output()))
    assert response.status_code == 201
    doc = response.json()
    _, events = chat(client, auth, "Convert all 13 pages into an Excel workbook", attachment_ids=[doc["id"]])
    assert events[-1]["type"] == "done"
    system = provider.last_messages[0].content
    for page in range(1, 14):
        assert f"TRAINING_PAGE_{page}_START" in system and f"TRAINING_PAGE_{page}_END" in system
    assert "do not substitute a summary for a conversion" in system
    assert provider.last_messages[-1].content == "Convert all 13 pages into an Excel workbook"


def test_small_model_reports_partial_conversion_instead_of_claiming_complete(client, auth, provider, monkeypatch):
    models = provider.models()
    monkeypatch.setattr(provider, "models", lambda: [replace(models[0], context_window=4096)])
    doc = upload(client, auth, "large.txt", ("Training hours and names\n" * 1000 + "LAST_ROW_MARKER").encode()).json()
    chat(client, auth, "Convert the entire file into Excel", attachment_ids=[doc["id"]])
    system = provider.last_messages[0].content
    assert "Do not claim a complete conversion" in system
    assert "LAST_ROW_MARKER" not in system


def test_empty_pdf_is_identified_as_attached_with_unreadable_content(client, auth, provider):
    pdf = FPDF()
    pdf.add_page()
    doc = upload(client, auth, "scanned.pdf", bytes(pdf.output())).json()
    chat(client, auth, "Convert this PDF to Excel", attachment_ids=[doc["id"]])
    system = provider.last_messages[0].content
    assert "IS attached, but no readable text was extracted" in system
    assert "Do not say no file was attached" in system
