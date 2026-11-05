import importlib.util
import io
import zipfile
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.assistant_studio import spreadsheet_engine as engine


def test_edit_preserves_values_and_applies_formulas_formatting():
    source = engine.edit(
        None,
        [
            {
                "type": "set_cells",
                "sheet": "Sheet",
                "range": "A1:C3",
                "values": [["ID", "Qty", "Price"], ["000012", 2, 10], ["000013", 3, 15]],
            }
        ],
    )
    original = source[:]
    output = engine.edit(
        source,
        [
            {"type": "set_formula", "sheet": "Sheet", "range": "D2:D3", "formula": "=B2*C2"},
            {"type": "set_formula", "sheet": "Sheet", "range": "D4", "formula": "=SUM(D2:D3)"},
            {
                "type": "format_range",
                "sheet": "Sheet",
                "range": "A1:D1",
                "format": {"bold": True, "fill_color": "123456", "border": True, "wrap_text": True, "column_width": 24},
            },
            {"type": "freeze_panes", "sheet": "Sheet", "range": "A2"},
        ],
    )
    book = load_workbook(io.BytesIO(output))
    s = book.active
    assert source == original
    assert s["A2"].value == "000012"
    assert s["D3"].value == "=B3*C3"
    assert s["D4"].value == "=SUM(D2:D3)"
    assert s["A1"].font.bold and s["A1"].fill.fgColor.rgb.endswith("123456")
    assert s["A1"].border.left.style == "thin"
    assert s.freeze_panes == "A2"
    assert book.calculation.fullCalcOnLoad
    assert load_workbook(io.BytesIO(output), data_only=True).active["D4"].value is None


@pytest.mark.parametrize(
    "formula",
    [
        '=WEBSERVICE("https://example.com")',
        '=HYPERLINK("https://example.com")',
        "='[Other.xlsx]Sheet'!A1",
        "=cmd|' /C calc'!A1",
        '=INDIRECT("A1")',
    ],
)
def test_reject_external_or_dynamic_formulas(formula):
    with pytest.raises(ValueError):
        engine.edit(None, [{"type": "set_formula", "sheet": "Sheet", "range": "A1", "formula": formula}])


def test_literal_formula_and_range_limits():
    result = engine.edit(None, [{"type": "set_cells", "sheet": "Sheet", "range": "A1", "values": [["=literal"]]}])
    assert load_workbook(io.BytesIO(result)).active["A1"].data_type == "s"
    for value in ["A:A", "A1:XFD20000", "A0", "A1:A20001"]:
        with pytest.raises(ValueError):
            engine.rectangle(value)
    with pytest.raises(ValueError):
        engine.edit(result, [{"type": "set_cells", "sheet": "Sheet", "range": "A1:B2", "values": [[1]]}])


def test_archive_external_links_and_entities_rejected():
    for name, data in [
        ("xl/externalLinks/externalLink1.xml", b"<x/>"),
        ("xl/worksheets/sheet1.xml", b"<!DOCTYPE x><x/>"),
    ]:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            z.writestr(name, data)
        with pytest.raises(ValueError):
            engine.load(output.getvalue())


def test_installer_is_additive_and_payload_matches():
    path = Path(__file__).parents[2] / "deploy/updaters/install_spreadsheet_tools.py"
    spec = importlib.util.spec_from_file_location("spreadsheet_installer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    current = "_DHANZ_CONNECTED_OPERATIONS_VERSION = 1\ndef run(app):\n    _install_connected_operations(app)\n"
    patched = module.patch_bootstrap(current)
    assert "    _install_spreadsheet_tools()" in patched
    assert module.patch_bootstrap(patched) == patched
    for name in ("spreadsheet_engine.py", "spreadsheet_tools.py", "operations_tools.py"):
        assert (
            module.payload()["app/assistant_studio/" + name]
            == (Path(__file__).parents[2] / "server_extensions/assistant_studio" / name).read_text()
        )


@pytest.mark.asyncio
async def test_owned_edit_download_and_cross_account_rejected(tmp_path):
    import uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.assistant_studio.spreadsheet_tools import install
    from app.core.config import Settings
    from app.db.base import Base
    from app.models import KnowledgeDocument, User
    from app.services import assistant_tools as tools
    from app.services.files_service import build_files_runtime, store_upload

    sql = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "test.db"))
    async with sql.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(sql, expire_on_commit=False)
    settings = Settings(app_env="test", _env_file=None, storage_dir=str(tmp_path / "files"))
    files = build_files_runtime(settings)
    a = User(id=uuid.uuid4(), email="excel1@example.test", display_name="One", routing_policy="balanced")
    b = User(id=uuid.uuid4(), email="excel2@example.test", display_name="Two", routing_policy="balanced")
    source = engine.edit(None, [{"type": "set_cells", "sheet": "Sheet", "range": "A1", "values": [["00001"]]}])
    async with maker() as db:
        db.add_all([a, b])
        await db.flush()
        doc = await store_upload(
            db, settings, files, None, user_id=a.id, filename="Source.xlsx", data=source, project_id=None
        )
        await db.commit()
    install()
    ctx = tools.ToolContext(maker, a.id, uuid.uuid4(), settings=settings, files=files, attachment_ids=[doc.id])
    args = {
        "operation": "edit",
        "actions": [{"type": "set_formula", "sheet": "Sheet", "range": "B1", "formula": "=SUM(1,2)"}],
    }
    result = await tools.TOOLS["excel_workbook"].run(ctx, args)
    repeat = await tools.TOOLS["excel_workbook"].run(ctx, args)
    assert result.action["id"] == repeat.action["id"] and result.action["type"] == "download_file"
    async with maker() as db:
        created = await db.get(KnowledgeDocument, uuid.UUID(result.action["id"]))
        assert created.user_id == a.id and created.id != doc.id
        assert await files.storage.get(doc.storage_key) == source
        assert load_workbook(io.BytesIO(await files.storage.get(created.storage_key))).active["B1"].value == "=SUM(1,2)"
    other = tools.ToolContext(maker, b.id, uuid.uuid4(), settings=settings, files=files)
    with pytest.raises(tools.ToolInputError, match="unavailable"):
        await tools.TOOLS["excel_workbook"].run(other, {"operation": "inspect", "document_id": str(doc.id)})
    await sql.dispose()


def test_command_wizard_pins_script_and_rejects_overwrite(tmp_path):
    path = Path(__file__).parents[2] / "apps/server_companion/add_server_command.py"
    spec = importlib.util.spec_from_file_location("command_wizard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    script = tmp_path / "health.py"
    script.write_text('print("ok")')
    task = module.prepare({}, "custom_health", "Check custom service", "python3 health.py", str(tmp_path))
    assert task["argv"][1] == str(script.resolve())
    assert str(script) in task["verified_files"]
    with pytest.raises(ValueError):
        module.prepare({"custom_health": task}, "custom_health", "overwrite", "true", str(tmp_path))
