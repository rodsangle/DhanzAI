import importlib.util
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select
from test_operations import OTHER, OWNER, operations, paired  # noqa: F401 - shared authenticated app fixture

from app.assistant_studio import web_updates
from app.assistant_studio.operations_models import OperationGrant, OperationJob
from app.assistant_studio.web_release import package_url, validate_release, version_key

RELEASE = {
    "schema": 1,
    "protocol": 1,
    "version": "0.10.0",
    "build": 28,
    "release": "web-updates-0.10.0-preview.1",
    "asset": "dhanz-web-0.10.0-update.zip",
    "sha256": "a" * 64,
    "source_commit": "b" * 40,
}


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol": 2},
        {"release": "../evil"},
        {"asset": "evil.zip"},
        {"version": "bad"},
        {"sha256": "bad"},
        {"source_commit": "bad"},
        {"build": True},
    ],
)
def test_manifest_rejects_invalid_protocol_paths_and_checksums(changes):
    with pytest.raises(ValueError):
        validate_release({**RELEASE, **changes})


def test_manifest_url_is_derived_from_only_the_trusted_repository():
    data = validate_release({**RELEASE, "url": "https://evil.example/payload.zip"})
    assert package_url(data).startswith("https://github.com/rodsangle/DhanzAI/releases/download/")
    assert "evil" not in package_url(data)
    assert version_key("0.10.0", 28) > version_key("0.9.9", 999)
    assert version_key("0.10.0", 29) > version_key("0.10.0", 28)


@pytest.mark.asyncio
async def test_manual_update_click_is_owned_deduplicated_and_does_not_need_a_permanent_grant(operations, monkeypatch):  # noqa: F811 - pytest fixture
    client, maker, users = operations
    client._transport.app.include_router(web_updates.router, prefix="/api/v1")
    monkeypatch.setattr(web_updates, "fetch_release", lambda: dict(RELEASE))
    packet, token, task = await paired(client)
    task = {"name": "update_web", "description": "Install latest checked web release", "manifest_hash": "c" * 64}
    await client.post("companion/heartbeat", headers=token, json={"tasks": [task]})
    check = await client.get("web-updates", headers=OWNER)
    assert check.status_code == 200 and check.json()["servers"][0]["online"] is True
    assert (await client.get("web-updates", headers=OTHER)).json()["servers"] == []
    body = {"server_id": packet["server"]["id"], "request_key": uuid.uuid4().hex}
    assert (await client.post("web-updates", headers=OTHER, json=body)).status_code == 404
    first = await client.post("web-updates", headers=OWNER, json=body)
    assert first.status_code == 202, first.text
    repeated = await client.post("web-updates", headers=OWNER, json=body)
    another_device = await client.post("web-updates", headers=OWNER, json={**body, "request_key": uuid.uuid4().hex})
    assert repeated.json()["id"] == first.json()["id"] == another_device.json()["id"]
    async with maker() as db:
        assert len(list(await db.scalars(select(OperationJob)))) == 1
        grants = list(await db.scalars(select(OperationGrant)))
        assert len(grants) == 1 and grants[0].remaining == 0
    path = "web-updates/jobs/" + first.json()["id"]
    assert (await client.get(path, headers=OTHER)).status_code == 404
    assert (await client.get(path, headers=OWNER)).json()["status"] == "queued"


def load_host(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "server_extensions/assistant_studio"))
    path = root / "apps/server_companion/apply_web_release.py"
    spec = importlib.util.spec_from_file_location("web_host_updater", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package(extra=None):
    result = io.BytesIO()
    files = {
        "index.html": '<base href="/app/">',
        "main.dart.js": "new app",
        "flutter_bootstrap.js": "loader",
        "version.json": json.dumps({"version": "0.10.0", "build_number": "28"}),
        "release.json": json.dumps(
            {"release_id": RELEASE["release"], "source_commit": RELEASE["source_commit"], "web_update_protocol": 1}
        ),
    }
    files.update(extra or {})
    with zipfile.ZipFile(result, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return result.getvalue()


def test_installer_checks_archive_paths_version_and_protocol(tmp_path, monkeypatch):
    host = load_host(monkeypatch)
    host.unpack(package(), tmp_path / "good", RELEASE)
    with pytest.raises(ValueError, match="Unsafe"):
        host.unpack(package({"../escape.txt": "no"}), tmp_path / "bad", RELEASE)
    with pytest.raises(ValueError, match="metadata"):
        host.unpack(package(), tmp_path / "wrong-version", {**RELEASE, "version": "0.11.0"})
    current = tmp_path / "good"
    assert host.require_base(current, {**RELEASE, "build": 29}) is True
    assert host.require_base(current, RELEASE) is False
    assert host.require_base(current, {**RELEASE, "version": "0.9.9"}) is False


def test_provision_preserves_existing_pairing_token_and_tasks(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    path = root / "apps/server_companion/provision_web_updates.py"
    spec = importlib.util.spec_from_file_location("web_provision", path)
    provision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provision)
    script = tmp_path / "setup/provision_web_updates.py"
    script.parent.mkdir()
    for name in ("apply_web_release.py", "web_release.py"):
        script.with_name(name).write_text("# fixed reviewed updater")
    provision.__file__ = str(script)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(sys, "argv", [str(script)])
    config = tmp_path / ".local/share/dhanz-server-companion/config.json"
    config.parent.mkdir(parents=True)
    original = {
        "token": "fake-private-pairing-token",
        "origin": "https://example.test",
        "tasks": {"health": {"fixed": True}},
    }
    config.write_text(json.dumps(original))
    config.chmod(0o600)
    provision.main()
    updated = json.loads(config.read_text())
    assert updated["token"] == original["token"] and updated["tasks"]["health"] == original["tasks"]["health"]
    assert updated["tasks"]["update_web"]["verified_files"]
