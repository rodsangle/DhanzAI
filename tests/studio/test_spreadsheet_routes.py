import io
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.assistant_studio import spreadsheet_engine as workbooks
from app.assistant_studio.spreadsheet_routes import install
from app.core.config import Settings
from app.db.base import Base
from app.models import KnowledgeDocument, User
from app.services.files_service import build_files_runtime, store_upload


@pytest_asyncio.fixture
async def workbook_service(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "workbook.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(app_env="test", _env_file=None, storage_dir=str(tmp_path / "files"))
    files = build_files_runtime(settings)
    one = User(id=uuid.uuid4(), email="one@workbook.test", display_name="One")
    two = User(id=uuid.uuid4(), email="two@workbook.test", display_name="Two")
    original = workbooks.edit(
        None, [{"type": "set_cells", "sheet": "Sheet", "range": "A1:B2", "values": [["ID", "Amount"], ["0001", 10]]}]
    )
    async with maker() as db:
        db.add_all([one, two])
        await db.flush()
        doc = await store_upload(
            db, settings, files, None, user_id=one.id, filename="Source.xlsx", data=original, project_id=None
        )
        await db.commit()
    app = FastAPI()
    app.state.sessionmaker = maker
    app.state.settings = settings
    app.state.files = files

    async def current(request: Request):
        who = request.headers.get("x-user")
        if not who:
            raise HTTPException(401, "Not signed in")
        return one if who == "one" else two

    app.dependency_overrides[get_current_user] = current
    install(app)
    count = len(app.routes)
    install(app)
    assert len(app.routes) == count
    assert "/api/v1/spreadsheets/{document_id}" in app.openapi()["paths"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, maker, files, doc, original
    await engine.dispose()


@pytest.mark.asyncio
async def test_view_is_owned_bounded_and_private(workbook_service):
    client, _, _, doc, _ = workbook_service
    url = "/api/v1/spreadsheets/" + str(doc.id)
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers={"x-user": "two"})).status_code == 404
    result = await client.get(url, headers={"x-user": "one"}, params={"area": "A1:B2"})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    assert result.json()["cells"][2]["value"] == "0001"
    assert result.json()["sheets"] == ["Sheet"]
    assert (await client.get(url, headers={"x-user": "one"}, params={"area": "A1:AN100"})).status_code == 422


@pytest.mark.asyncio
async def test_copy_save_is_owned_idempotent_and_original_unchanged(workbook_service):
    client, maker, files, doc, original = workbook_service
    url = "/api/v1/spreadsheets/" + str(doc.id) + "/edits"
    body = {
        "request_key": "copy_save_123456789",
        "filename": "Saved.xlsx",
        "actions": [
            {"type": "set_formula", "sheet": "Sheet", "range": "B3", "formula": "=SUM(B2:B2)"},
            {
                "type": "format_range",
                "sheet": "Sheet",
                "range": "A1:B1",
                "format": {"bold": True, "fill_color": "E2EFDA", "underline": True, "font_size": 18},
            },
        ],
    }
    assert (await client.post(url, headers={"x-user": "two"}, json=body)).status_code == 404
    first = await client.post(url, headers={"x-user": "one"}, json=body)
    assert first.status_code == 200, first.text
    second = await client.post(url, headers={"x-user": "one"}, json=body)
    assert first.json()["id"] == second.json()["id"]
    async with maker() as db:
        saved = await db.get(KnowledgeDocument, uuid.UUID(first.json()["id"]))
        assert saved.id != doc.id and saved.user_id == doc.user_id
        output = load_workbook(io.BytesIO(await files.storage.get(saved.storage_key))).active
        assert output["A2"].value == "0001" and output["B3"].value == "=SUM(B2:B2)"
        assert output["A1"].font.bold
        assert output["A1"].font.sz == 18 and output["A1"].font.underline == "single"
        assert await files.storage.get(doc.storage_key) == original
    body["filename"] = "Different.xlsx"
    assert (await client.post(url, headers={"x-user": "one"}, json=body)).status_code == 409


@pytest.mark.asyncio
async def test_unsafe_changes_do_not_create_copy(workbook_service):
    client, maker, _, doc, _ = workbook_service
    body = {
        "request_key": "copy_save_unsafe_123",
        "filename": "Saved.xlsx",
        "actions": [
            {"type": "set_formula", "sheet": "Sheet", "range": "B3", "formula": '=WEBSERVICE("https://example.com")'}
        ],
    }
    result = await client.post("/api/v1/spreadsheets/" + str(doc.id) + "/edits", headers={"x-user": "one"}, json=body)
    assert result.status_code == 422
    async with maker() as db:
        assert len(list(await db.scalars(select(KnowledgeDocument)))) == 1
