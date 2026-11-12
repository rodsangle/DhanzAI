import json
from dataclasses import replace
from io import BytesIO

from fpdf import FPDF
from openpyxl import load_workbook

from dhanz_ai import ToolCall
from tests.test_phase3 import chat, upload
from tests.test_tools import ToolCallingProvider, make_client, signup


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


def test_attachment_and_instruction_can_produce_a_real_downloadable_workbook(settings, knowledge):
    provider = ToolCallingProvider(
        [
            ToolCall(
                "xlsx",
                "create_spreadsheet",
                {
                    "filename": "Training log",
                    "sheets": [{"name": "Training", "columns": ["Name", "Hours"], "rows": [["Ada", 8]]}],
                },
            )
        ]
    )
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        auth = {"headers": headers}
        doc = upload(client, auth, "training.csv", b"Name,Hours\nAda,8\n").json()
        _, events = chat(client, auth, "Convert the attached file into Excel", attachment_ids=[doc["id"]])
        assert "Ada" in provider.requests[0][0].content
        assert provider.requests[0][-1].content == "Convert the attached file into Excel"
        result = next(m.tool_result for m in provider.requests[-1] if m.role == "tool")
        saved = json.loads(result.content)
        assert saved["saved"] is True and saved["file_type"] == "xlsx"
        download = client.get(f"/api/v1/files/{saved['document_id']}/download", headers=headers)
        assert download.status_code == 200
        workbook = load_workbook(BytesIO(download.content))
        assert list(workbook.active.values) == [("Name", "Hours"), ("Ada", 8)]
        assert events[-1]["type"] == "done"
