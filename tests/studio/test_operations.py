import hashlib
import io
import sqlite3
import sys
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.assistant_studio import operations_service as service
from app.assistant_studio.folder_uploads import read_folder
from app.assistant_studio.operations_models import OperationGrant, OperationJob, OperationServer
from app.assistant_studio.operations_routes import router
from app.core.config import Settings
from app.db.base import Base, utcnow
from app.models import User
from dhanz_knowledge.documents import UnsupportedFile, extract_document

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/server_companion"))
import server_companion as companion  # noqa: E402


@pytest_asyncio.fixture
async def operations(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "operations.db"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    users = [User(id=uuid.uuid4(), email=n + "@example.test", display_name=n) for n in ("one", "two")]
    async with maker() as db:
        db.add_all(users)
        await db.commit()
    app = FastAPI()
    app.state.sessionmaker = maker
    app.state.settings = Settings(app_env="test", _env_file=None)

    async def user(request: Request):
        if not request.headers.get("x-test-user"):
            raise HTTPException(401, "Unauthorized")
        return users[0] if request.headers["x-test-user"] == "one" else users[1]

    app.dependency_overrides[get_current_user] = user
    app.include_router(router, prefix="/api/v1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1/operations", follow_redirects=True
    ) as client:
        yield client, maker, users
    await engine.dispose()


OWNER = {"x-test-user": "one"}
OTHER = {"x-test-user": "two"}


async def paired(client):
    response = await client.post("servers", headers=OWNER, json={"name": "AWS"})
    assert response.status_code == 201, response.text
    packet = response.json()
    token = {"X-Dhanz-Server-Token": packet["token"]}
    task = {"name": "health", "description": "Check readiness", "manifest_hash": "a" * 64}
    assert (await client.post("companion/heartbeat", headers=token, json={"tasks": [task]})).status_code == 200
    return packet, token, task


async def granted(client, packet, **extra):
    response = await client.post(
        "grants",
        headers=OWNER,
        json={
            "kind": "server_task",
            "target": packet["server"]["id"],
            "task": "health",
            "uses": 1,
            "authorize": True,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_owner_scoping_hash_only_tokens_and_revocation(operations):
    client, maker, users = operations
    assert (await client.get("")).status_code == 401
    packet, token, task = await paired(client)
    async with maker() as db:
        row = await db.get(OperationServer, uuid.UUID(packet["server"]["id"]))
        assert row.token_hash == hashlib.sha256(packet["token"].encode()).hexdigest()
        assert packet["token"] not in str(service.public(row))
    assert (await client.get("", headers=OTHER)).json()["servers"] == []
    assert (await client.post("servers/" + packet["server"]["id"] + "/revoke", headers=OTHER)).status_code == 404
    await client.post("servers/" + packet["server"]["id"] + "/revoke", headers=OWNER)
    assert (await client.post("companion/claim", headers=token, json={})).status_code == 401


@pytest.mark.asyncio
async def test_grant_consumed_once_duplicate_claim_and_ownership(operations):
    client, maker, users = operations
    packet, token, task = await paired(client)
    grant = await granted(client, packet)
    body = {"grant_id": grant["id"], "request_key": uuid.uuid4().hex}
    assert (await client.post("run", headers=OTHER, json=body)).status_code == 404
    first = await client.post("run", headers=OWNER, json=body)
    assert first.status_code == 202, first.text
    duplicate = await client.post("run", headers=OWNER, json=body)
    assert duplicate.json()["id"] == first.json()["id"]
    exhausted = await client.post("run", headers=OWNER, json={**body, "request_key": uuid.uuid4().hex})
    assert exhausted.status_code == 403
    claim = (await client.post("companion/claim", headers=token, json={})).json()["job"]
    assert claim["id"] == first.json()["id"]
    assert (await client.post("companion/claim", headers=token, json={})).json()["job"] is None
    for _ in range(2):
        report = await client.post(
            "companion/jobs/" + claim["id"] + "/result", headers=token, json={"status": "completed"}
        )
        assert report.status_code == 200
    assert (
        await client.post("companion/jobs/" + claim["id"] + "/result", headers=token, json={"status": "failed"})
    ).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revoke", "expire", "manifest"])
async def test_changes_before_execution_cancel_queued_jobs(operations, change):
    client, maker, users = operations
    packet, token, task = await paired(client)
    grant = await granted(client, packet)
    job = (
        await client.post("run", headers=OWNER, json={"grant_id": grant["id"], "request_key": uuid.uuid4().hex})
    ).json()
    if change == "revoke":
        await client.post("grants/" + grant["id"] + "/revoke", headers=OWNER)
    elif change == "manifest":
        await client.post("companion/heartbeat", headers=token, json={"tasks": [{**task, "manifest_hash": "b" * 64}]})
    else:
        async with maker() as db:
            row = await db.get(OperationGrant, uuid.UUID(grant["id"]))
            row.expires_at = utcnow() - timedelta(seconds=1)
            await db.commit()
    assert (await client.post("companion/claim", headers=token, json={})).json()["job"] is None
    async with maker() as db:
        assert (await db.get(OperationJob, uuid.UUID(job["id"]))).status == "cancelled"


@pytest.mark.asyncio
async def test_offline_server_and_changed_recipe_never_queue(operations):
    client, maker, users = operations
    packet, token, task = await paired(client)
    grant = await granted(client, packet)
    async with maker() as db:
        server = await db.get(OperationServer, uuid.UUID(packet["server"]["id"]))
        server.last_seen = utcnow() - timedelta(minutes=5)
        await db.commit()
    response = await client.post("run", headers=OWNER, json={"grant_id": grant["id"], "request_key": uuid.uuid4().hex})
    assert response.status_code == 409
    async with maker() as db:
        assert not list(await db.scalars(select(OperationJob)))


def test_companion_durable_receipt_prevents_replay_and_rejects_modified_update(tmp_path, monkeypatch):
    script = tmp_path / "update.py"
    script.write_text("print('approved')")
    recipe = {
        "argv": ["/usr/bin/python3", str(script)],
        "cwd": str(tmp_path),
        "timeout": 5,
        "verified_files": {str(script): hashlib.sha256(script.read_bytes()).hexdigest()},
    }
    config = {"tasks": {"deploy": recipe}}
    job = {"id": str(uuid.uuid4()), "task": "deploy", "manifest_hash": companion.recipe_hash(recipe)}
    journal = sqlite3.connect(":memory:")
    journal.execute("CREATE TABLE receipts(id TEXT PRIMARY KEY,status TEXT NOT NULL)")
    executed = []

    def execute(*args, **kwargs):
        assert journal.execute("SELECT status FROM receipts").fetchone()[0] == "executing"
        executed.append(args)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(companion.subprocess, "run", execute)
    assert companion.run_job(config, job, journal) == "completed"
    assert companion.run_job(config, job, journal) == "completed"
    assert len(executed) == 1
    script.write_text("print('changed')")
    with pytest.raises(ValueError, match="changed"):
        companion.run_job(config, {**job, "id": str(uuid.uuid4())}, journal)
    assert len(executed) == 1
    journal.execute("INSERT INTO receipts VALUES(?,?)", (str(uuid.uuid4()), "executing"))
    unfinished = journal.execute("SELECT id FROM receipts WHERE status='executing'").fetchone()[0]
    assert companion.run_job(config, {**job, "id": unfinished}, journal) == "uncertain"


def archive(files):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return result.getvalue()


def test_folder_preserves_paths_and_marks_unreadable_members():
    result = read_folder(
        archive(
            {"project/a/readme.txt": "first", "project/b/readme.txt": "second", "project/data.unknown": b"\x00\x01"}
        ),
        extract_document,
        Settings(app_env="test", _env_file=None),
    )
    assert "project/a/readme.txt" in result.text and "project/b/readme.txt" in result.text
    assert "first" in result.text and "second" in result.text
    assert "could not be read" in result.text and result.mime_type == "application/zip"


@pytest.mark.parametrize(
    "name", ["../escape.txt", "/absolute.txt", "project/.env", "project/.aws/credentials", "private.pem"]
)
def test_unsafe_folder_members_rejected(name):
    with pytest.raises(UnsupportedFile):
        read_folder(archive({name: "never extract"}), extract_document, Settings(app_env="test", _env_file=None))


def test_folder_ocr_uses_inner_pdf_bytes_and_shares_page_budget(monkeypatch):
    from app.assistant_studio import folder_uploads
    from dhanz_knowledge.documents import ExtractedDocument

    seen = []

    class OCR:
        def __init__(self, data, **kwargs):
            seen.append((data, kwargs["max_pages"]))
            self.attempted = 0

    def extract(name, data, *, pdf_ocr=None):
        if pdf_ocr:
            pdf_ocr.attempted = 1
        return ExtractedDocument("pdf", "application/pdf", "OCR text" if pdf_ocr else "text only")

    monkeypatch.setattr(folder_uploads, "PDFOCR", OCR)
    settings = Settings(app_env="test", ocr_enabled=True, ocr_max_pages=1, _env_file=None)
    result = read_folder(
        archive({"first.pdf": b"first-pdf-bytes", "second.pdf": b"second-pdf-bytes"}), extract, settings
    )
    assert seen == [(b"first-pdf-bytes", 1)]
    assert "OCR text" in result.text and "text only" in result.text


def test_operations_installer_payload_and_bootstrap_preserve_custom_features():
    import importlib.util

    root = Path(__file__).resolve().parents[2]

    def load(name):
        spec = importlib.util.spec_from_file_location(name, root / "deploy/updaters" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    coding = load("install_coding_workspace")
    installer = load("install_connected_operations")
    source = coding.patch_bootstrap((root / "server_extensions/assistant_studio/bootstrap.py").read_text())
    patched = installer.patch_bootstrap(source + "\n# custom weather and OCR remain\n")
    assert "# custom weather and OCR remain" in patched and "_install_coding_workspace(app)" in patched
    assert installer.patch_bootstrap(patched) == patched
    packet = installer.payload()
    for relative, content in packet.items():
        if relative.startswith("app/"):
            path = root / "server_extensions" / relative.removeprefix("app/")
        elif relative.startswith("alembic/"):
            path = root / "server_extensions/migrations" / Path(relative).name
        else:
            assert relative.startswith("companion/")
            path = root / "apps/server_companion" / Path(relative).name
        assert content == path.read_text()
