import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.assistant_studio import github_compat as feature
from app.assistant_studio import operations_models  # noqa: F401 - register the connected-workflow tables before fixtures
from app.services import assistant_tools as tools
from app.services import github_service as gh
from dhanz_ai import ToolSpec


@pytest.fixture
def setup(monkeypatch):
    reads, writes = [], []

    async def read(db, settings, user_id, **args):
        reads.append((user_id, args))
        return {"access": "read-only", "content": "# README", "notice": "No writes are available."}

    async def workspace(ctx, args):
        writes.append(args)
        return tools.ToolOutcome({"draft": "queued"}, "Queued")

    monkeypatch.setattr(gh, "read", read)
    monkeypatch.setattr(gh, "public_connection", lambda *a, **k: {"connected": True, "access": "read-only"})
    monkeypatch.setattr(gh, "SOURCE_NOTICE", gh.SOURCE_NOTICE)
    monkeypatch.setattr(tools, "GITHUB_TOOL", tools.GITHUB_TOOL)
    monkeypatch.setattr(
        tools,
        "TOOLS",
        {
            "github_workspace": tools.Tool(
                ToolSpec(
                    "github_workspace", "Existing authorized workflow", {"properties": {"branch": {"type": "string"}}}
                ),
                "Working",
                workspace,
            )
        },
    )

    @asynccontextmanager
    async def maker():
        yield object()

    ctx = SimpleNamespace(settings=object(), maker=maker, user_id=uuid.uuid4())
    feature.install()
    return ctx, reads, writes


@pytest.mark.asyncio
async def test_branch_alias_reaches_legacy_reader_with_ref_and_same_account(setup):
    ctx, reads, _ = setup
    result = await tools.GITHUB_TOOL.run(
        ctx, {"operation": "file", "repository": "rodsangle/DHANZ-CLAUDE", "path": "README.md", "branch": "main"}
    )
    assert reads == [
        (ctx.user_id, {"operation": "file", "repository": "rodsangle/DHANZ-CLAUDE", "path": "README.md", "ref": "main"})
    ]
    assert result.data["token_write_access"] == "not_verified"
    assert result.data["access"] == "connected"
    assert result.data["reader_access"] == "read-only"
    assert result.data["coding_workflow_available"] is True
    assert "branch" in tools.GITHUB_TOOL.spec.parameters["properties"]


@pytest.mark.asyncio
async def test_conflicting_refs_and_unrecognized_privilege_fields_are_rejected(setup):
    ctx, reads, _ = setup
    for args in ({"operation": "file", "branch": "main", "ref": "other"}, {"operation": "file", "write": True}):
        with pytest.raises(tools.ToolInputError):
            await tools.GITHUB_TOOL.run(ctx, args)
    assert reads == []


@pytest.mark.asyncio
async def test_workspace_ref_alias_preserves_authorized_delegate_and_is_idempotent(setup):
    ctx, _, calls = setup
    old = tools.GITHUB_TOOL.run
    feature.install()
    assert tools.GITHUB_TOOL.run is old
    result = await tools.TOOLS["github_workspace"].run(ctx, {"operation": "file", "ref": "main", "path": "README.md"})
    assert calls == [{"operation": "file", "branch": "main", "path": "README.md"}]
    assert result.data == {"draft": "queued"}
    assert gh.public_connection(None, None)["token_write_access"] == "not_verified"


def test_updater_keeps_current_bootstrap_hooks_and_exact_bridge_source():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("github_installer", root / "deploy/updaters/install_github_compat.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    current = "def install(app):\n    _install_connected_operations(app)\n    _install_spreadsheets()\n"
    current += "\nEXISTING_FEATURE = True\n"
    updated = installer.patch_bootstrap(current)
    assert "_install_spreadsheets()" in updated and "EXISTING_FEATURE = True" in updated
    assert installer.patch_bootstrap(updated) == updated
    compile(updated, "bootstrap.py", "exec")
    assert installer.payload()["module"] == (root / "server_extensions/assistant_studio/github_compat.py").read_text()
    assert "COPY --chmod=0755" in installer.image_dockerfile("base:fixed", "/srv/app/bootstrap.py", installer.MODULES)
