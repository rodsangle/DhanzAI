import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.assistant_studio import pdf_turn
from app.assistant_studio.pdf_excel import Cell, ConversionError, Page
from app.services import files_service


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_conversion_only_claims_a_download_after_real_storage(monkeypatch, failure):
    user_id = uuid.uuid4()
    doc = SimpleNamespace(user_id=user_id, file_type="pdf", storage_key="private/source.pdf", title="source.pdf")

    class Db:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, *_):
            return doc

        commit = AsyncMock()

    def extract(*_, **__):
        if failure:
            raise ConversionError("OCR could not read this file")
        return [Page(1, [[Cell(0, "00001")]])]

    store = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), title="Combined_PDF_to_Excel.xlsx"))
    monkeypatch.setattr(pdf_turn, "extract_pdf", extract)
    monkeypatch.setattr(files_service, "store_upload", store)
    finalize = AsyncMock(return_value=None)
    settings = SimpleNamespace(ocr_language="eng", ocr_max_pages=20, ocr_enabled=True, ocr_timeout_seconds=90)
    turn = SimpleNamespace(user_id=user_id, attachment_ids=[uuid.uuid4()], assistant_message_id=uuid.uuid4())
    files = SimpleNamespace(storage=SimpleNamespace(get=AsyncMock(return_value=b"%PDF-test")))
    events = [event async for event in pdf_turn.run(Db, settings, turn, files, finalize, AsyncMock(return_value=False))]
    result = finalize.call_args.kwargs
    if failure:
        store.assert_not_called()
        assert result["outcome"] == "error"
        assert result["tool_activity"][0]["action"] is None
        assert "No workbook was created" in result["text"]
    else:
        assert store.call_args.kwargs["data"].startswith(b"PK")
        assert result["outcome"] == "complete"
        assert result["tool_activity"][0]["action"]["type"] == "download_file"
        assert events[-1]["type"] == "done"
