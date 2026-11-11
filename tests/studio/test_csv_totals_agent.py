import runpy
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.assistant_studio import csv_totals_agent as agent
from app.assistant_studio import csv_totals_tools as feature
from app.db.base import Base
from app.models import Conversation, KnowledgeDocument, Message, User
from app.services import assistant_tools


def test_trimmed_headers_and_money_are_exact_with_explicit_measure_columns():
    result = agent.calculate(b" ID , price , quantity\n001,0.1,2\n002,0.2,3\n003,unknown,\n", ["price", "quantity"])
    assert result["rows_processed"] == 3 and result["complete"]
    assert result["headers"] == ["ID", "price", "quantity"]
    assert result["columns"][0] == {
        "column": "price",
        "total": "0.3",
        "numeric_values": 2,
        "nonnumeric_values": 1,
        "blank_values": 0,
    }
    assert result["columns"][1]["total"] == "5"
    assert result["columns"][1]["blank_values"] == 1


def test_large_csv_is_computed_from_all_rows_not_a_text_preview():
    result = agent.calculate(b"amount\n" + b"0.1\n" * 60000)
    assert result["rows_processed"] == 60000
    assert result["columns"][0]["total"] == "6000"


def test_bom_semicolon_and_nonnumeric_cells_do_not_execute_formulas():
    result = agent.calculate("\ufeffname;amount\nA;12.5\nB;=10+20\nC;NaN\nD;Infinity\n".encode())
    assert result["delimiter"] == ";"
    assert result["columns"][1]["total"] == "12.5"
    assert result["columns"][1]["nonnumeric_values"] == 3


@pytest.mark.parametrize("data", [b"a,a\n1,2", b"a, a \n1,2", b"a,\n1,2", b"a,b\n1,2,3", b"a,b\n1", b'a\n"broken'])
def test_ambiguous_or_malformed_data_returns_no_partial_totals(data):
    with pytest.raises(ValueError):
        agent.calculate(data, delimiter=",")


def test_limits_and_unknown_column_names_are_explicit(monkeypatch):
    monkeypatch.setattr(agent, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="partial"):
        agent.calculate(b"a\n1\n2")
    with pytest.raises(ValueError, match="existing"):
        agent.calculate(b"a\n1", ["missing"])
    with pytest.raises(ValueError, match="UTF-8"):
        agent.calculate(b"\xff\xfe")
    with pytest.raises(ValueError, match="magnitude"):
        agent.calculate(b"a\n1e999")


@pytest_asyncio.fixture
async def workspace(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    owner, other, chat = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    identifiers = {name: uuid.uuid4() for name in ("current", "old", "foreign", "unrelated", "large")}
    async with maker() as db:
        db.add_all(
            [
                User(id=owner, email="csv-owner@example.test", display_name="Owner"),
                User(id=other, email="csv-other@example.test", display_name="Other"),
            ]
        )
        await db.flush()
        db.add(Conversation(id=chat, user_id=owner, title="CSV chat"))
        for name, identifier in identifiers.items():
            db.add(
                KnowledgeDocument(
                    id=identifier,
                    user_id=other if name == "foreign" else owner,
                    kind="file",
                    url="upload:" + str(identifier),
                    title="sales.csv",
                    file_type="csv",
                    storage_key=name,
                    content="",
                    content_hash="a" * 64,
                    size_bytes=agent.MAX_BYTES + 1 if name == "large" else 25,
                )
            )
        await db.flush()
        db.add(
            Message(
                id=uuid.uuid4(),
                conversation_id=chat,
                position=0,
                role="user",
                status="complete",
                content="Uploaded",
                attachments=[{"id": str(identifiers["old"])}],
            )
        )
        await db.commit()
    calls = []

    async def get(key):
        calls.append(key)
        return b"price\n0.1\n0.2\n"

    ctx = SimpleNamespace(
        settings=SimpleNamespace(),
        maker=maker,
        user_id=owner,
        conversation_id=chat,
        attachment_ids=[identifiers["current"]],
        files=SimpleNamespace(storage=SimpleNamespace(get=get)),
    )
    monkeypatch.setattr(assistant_tools, "TOOLS", {})
    feature.install()
    yield SimpleNamespace(ctx=ctx, ids=identifiers, calls=calls, run=assistant_tools.TOOLS["csv_totals"].run)
    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_tool_prefers_current_attachment_and_remembers_older_chat_file(workspace):
    s = workspace
    result = await s.run(s.ctx, {"filename": "sales.csv", "columns": ["price"]})
    assert result.data["document_id"] == str(s.ids["current"])
    assert result.data["columns"][0]["total"] == "0.3"
    s.ctx.attachment_ids = []
    result = await s.run(s.ctx, {"filename": "sales.csv"})
    assert result.data["document_id"] == str(s.ids["old"])
    assert s.calls == ["current", "old"]


@pytest.mark.asyncio
async def test_chat_tool_denies_other_users_unretained_files_and_host_paths_before_storage(workspace):
    s = workspace
    for args in (
        {"document_id": str(s.ids["foreign"])},
        {"document_id": str(s.ids["unrelated"])},
        {"filename": "/etc/private.csv"},
        {"filename": r"C:\Users\owner\sales.csv"},
    ):
        with pytest.raises(assistant_tools.ToolInputError):
            await s.run(s.ctx, args)
    s.ctx.attachment_ids = [s.ids["foreign"]]
    with pytest.raises(assistant_tools.ToolInputError):
        await s.run(s.ctx, {"document_id": str(s.ids["foreign"])})
    s.ctx.attachment_ids = [s.ids["large"]]
    with pytest.raises(assistant_tools.ToolInputError, match="25 MB"):
        await s.run(s.ctx, {"document_id": str(s.ids["large"])})
    assert not s.calls


def test_installer_preserves_existing_startup_and_embeds_exact_reviewed_sources():
    root = Path(__file__).resolve().parents[2]
    updater = runpy.run_path(str(root / "deploy/updaters/install_csv_totals_agent.py"))
    original = "def install(app):\n    app.include_router(router, prefix=app.state.settings.api_prefix)\n    custom_feature()\n"
    patched = updater["patch_bootstrap"](original)
    assert "custom_feature()" in patched
    assert updater["patch_bootstrap"](patched) == patched
    assert (
        updater["payload"]()["module"] == (root / "server_extensions/assistant_studio/csv_totals_tools.py").read_text()
    )
    assert (
        updater["payload"]()["engine"] == (root / "server_extensions/assistant_studio/csv_totals_agent.py").read_text()
    )


def test_bootstrap_registers_csv_tool_without_starting_work(monkeypatch):
    from fastapi import APIRouter, FastAPI

    from app.core.config import Settings

    monkeypatch.setattr(assistant_tools, 'TOOLS', {})
    root = Path(__file__).resolve().parents[2]
    updater = runpy.run_path(str(root / 'deploy/updaters/install_csv_totals_agent.py'))
    current = 'def install(app):\n    app.include_router(router, prefix=app.state.settings.api_prefix)\n'
    source = updater['patch_bootstrap'](current)
    namespace = {'__name__': 'app.assistant_studio._csv_startup_test',
                 '__package__': 'app.assistant_studio', 'router': APIRouter()}
    exec(compile(source, 'bootstrap.py', 'exec'), namespace)  # noqa: S102 - reviewed installer source
    application = FastAPI()
    application.state.settings = Settings(app_env='test', _env_file=None)
    namespace['install'](application)
    assert 'csv_totals' in assistant_tools.TOOLS
