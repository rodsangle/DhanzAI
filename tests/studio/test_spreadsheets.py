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
    previous = patched.replace("_DHANZ_SPREADSHEET_TOOLS_VERSION = 6", "_DHANZ_SPREADSHEET_TOOLS_VERSION = 1")
    assert module.MARKER in module.patch_bootstrap(previous)
    assert module.patch_bootstrap(previous).count("    _install_spreadsheet_tools()") == 1
    for name in (
        "spreadsheet_engine.py",
        "spreadsheet_package.py",
        "spreadsheet_workflow.py",
        "spreadsheet_routes.py",
        "spreadsheet_tools.py",
        "operations_tools.py",
    ):
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


def test_existing_long_formula_does_not_block_formatting_or_totals():
    from openpyxl import Workbook
    from openpyxl.worksheet.formula import ArrayFormula

    book = Workbook()
    sheet = book.active
    sheet["A1"] = "=SUM(" + ",".join(["1"] * 1100) + ")"
    sheet["B1"] = ArrayFormula(ref="B1:B2", text="=SUM(1,2)")
    stream = io.BytesIO()
    book.save(stream)
    output = engine.edit(
        stream.getvalue(),
        [
            {"type": "format_range", "sheet": "Sheet", "range": "G1:AI31", "format": {"border": True}},
            {"type": "set_formula", "sheet": "Sheet", "range": "G32:AI32", "formula": "=SUM(G2:G31)"},
        ],
    )
    result = load_workbook(io.BytesIO(output)).active
    assert result["A1"].value == sheet["A1"].value
    assert result["B1"].value.text == "=SUM(1,2)"
    assert result["G32"].value == "=SUM(G2:G31)"
    assert result["AI32"].value == "=SUM(AI2:AI31)"
    assert result["G2"].border.left.style == "thin"


def test_existing_formula_error_identifies_original_cell():
    from openpyxl import Workbook

    book = Workbook()
    book.active["C7"] = '=WEBSERVICE("https://example.com")'
    stream = io.BytesIO()
    book.save(stream)
    with pytest.raises(ValueError, match=r"Existing formula in Sheet!C7"):
        engine.inspect(stream.getvalue())


@pytest.mark.parametrize(
    "existing",
    [
        "=LET(amount,SUM(G2:G31),amount*2)",
        "=_xlfn.LET(amount,SUM(G2:G31),amount*2)",
        "=_xlfn.LET(data,_xlfn._xlws.FILTER(G2:G31,G2:G31>0),SUM(data))",
    ],
)
def test_existing_let_preserved_with_formatting_and_totals(existing):
    from openpyxl import Workbook

    book = Workbook()
    book.active["B7"] = existing
    stream = io.BytesIO()
    book.save(stream)
    output = engine.edit(
        stream.getvalue(),
        [
            {"type": "format_range", "sheet": "Sheet", "range": "A1:AI31", "format": {"border": True}},
            {"type": "set_formula", "sheet": "Sheet", "range": "G32:AI32", "formula": "=SUM(G2:G31)"},
        ],
    )
    result = load_workbook(io.BytesIO(output)).active
    assert result["B7"].value == existing
    assert result["AI32"].value == "=SUM(AI2:AI31)"
    assert result["A1"].border.left.style == "thin"
    assert engine.formula("=LET(x,2,x+1)") == "=LET(x,2,x+1)"
    with pytest.raises(ValueError, match="Unsupported formula"):
        engine.formula('=LET(x,WEBSERVICE("https://example.com"),x)')


def test_preserve_standard_existing_formulas_and_inspect_totals_row():
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "82C Daily Progress"
    formulas = ["=LOOKUP(2,1/(G2:G31<>0),G2:G31)", "=ISERROR(A1)", "=POWER(2,3)", "=LET(x,2,x+1)"]
    for index, value in enumerate(formulas, 1):
        sheet.cell(index, 2, value)
    source = io.BytesIO()
    book.save(source)
    assert engine.inspect(source.getvalue(), sheet.title, "A32:AI32")["all_empty"]
    output = engine.edit(
        source.getvalue(),
        [
            {"type": "format_range", "sheet": sheet.title, "range": "A1:AI31", "format": {"border": True}},
            {"type": "set_formula", "sheet": sheet.title, "range": "G32:AI32", "formula": "=SUM(G2:G31)"},
        ],
    )
    result = load_workbook(io.BytesIO(output)).active
    assert [result.cell(i, 2).value for i in range(1, 5)] == formulas
    assert result["AI32"].value == "=SUM(AI2:AI31)"
    inspected = engine.inspect(output, sheet.title, "A32:AI32")
    assert not inspected["all_empty"] and len(inspected["occupied_cells"]) == 29
    assert inspected["cells"][6]["value"] == "=SUM(G2:G31)"
    with pytest.raises(ValueError):
        engine.inspect(output, sheet.title, "A1:AI32")
    with pytest.raises(ValueError):
        engine.formula('=WEBSERVICE("https://example.com")', existing=True)


def test_ooxml_extensions_caches_and_unmodified_sheets_preserved():
    from lxml import etree as XML
    from openpyxl import Workbook

    from app.assistant_studio.spreadsheet_package import NS

    book = Workbook()
    book.active["A1"] = "=LOOKUP(2,{1,2},{10,20})"
    book.create_sheet("Unchanged")["A1"] = "Keep exactly"
    raw = io.BytesIO()
    book.save(raw)
    with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    root = XML.fromstring(parts["xl/worksheets/sheet1.xml"])
    extension = XML.SubElement(root, "{" + NS + "}extLst")
    item = XML.SubElement(extension, "{" + NS + "}ext", uri="{test-preserve-extension}")
    XML.SubElement(item, "{urn:test-extension}customFormatting", enabled="1")
    root.find(".//{" + NS + "}c/{" + NS + "}v").text = "20"
    parts["xl/worksheets/sheet1.xml"] = XML.tostring(root)
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    with pytest.warns(UserWarning):
        output = engine.edit(
            raw.getvalue(),
            [
                {
                    "type": "format_range",
                    "sheet": "Sheet",
                    "range": "A1:B3",
                    "format": {"bold": True, "number_format": "0.00"},
                },
                {"type": "set_cells", "sheet": "Sheet", "range": "B1", "values": [["00001"]]},
                {"type": "set_formula", "sheet": "Sheet", "range": "B3", "formula": "=SUM(B1:B2)"},
            ],
        )
    with zipfile.ZipFile(io.BytesIO(output)) as z:
        assert z.read("xl/worksheets/sheet2.xml") == parts["xl/worksheets/sheet2.xml"]
        changed = XML.fromstring(z.read("xl/worksheets/sheet1.xml"))
        assert XML.tostring(changed.find("{" + NS + "}extLst"), method="c14n") == XML.tostring(extension, method="c14n")
        assert changed.find(".//{" + NS + "}c/{" + NS + "}v").text == "20"
    with pytest.warns(UserWarning):
        result = load_workbook(io.BytesIO(output)).active
    assert result["A1"].value == "=LOOKUP(2,{1,2},{10,20})"
    assert result["A1"].font.bold and result["A1"].number_format == "0.00"
    assert result["B1"].value == "00001"


def test_add_sheet_retains_original_package():
    source = engine.edit(None, [{"type": "set_cells", "sheet": "Sheet", "range": "A1", "values": [["original"]]}])
    output = engine.edit(
        source,
        [
            {"type": "add_sheet", "sheet": "New"},
            {"type": "set_cells", "sheet": "New", "range": "A1", "values": [["new"]]},
            {"type": "format_range", "sheet": "New", "range": "A1", "format": {"bold": True}},
        ],
    )
    book = load_workbook(io.BytesIO(output))
    assert book["Sheet"]["A1"].value == "original"
    assert book["New"]["A1"].value == "new" and book["New"]["A1"].font.bold
    with zipfile.ZipFile(io.BytesIO(source)) as a, zipfile.ZipFile(io.BytesIO(output)) as b:
        assert a.read("xl/worksheets/sheet1.xml") == b.read("xl/worksheets/sheet1.xml")
