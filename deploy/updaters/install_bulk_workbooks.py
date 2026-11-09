"""Install bulk Excel column copying and larger bounded workbook processing.

Prepare by default. --apply recreates only the API, without migrations or video generation.
"""

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

PAYLOAD = "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"  # noqa: E501 - frozen bulk workbook support
MODULES = ("bootstrap.py", "spreadsheet_engine.py", "spreadsheet_package.py", "workbook_copy.py", "workbook_copy_tools.py")
MARKER = "_DHANZ_BULK_WORKBOOKS_VERSION = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        if current.count("    _install_bulk_workbooks()") != 1:
            raise ValueError("Unknown Bulk workbook startup hook. Nothing changed.")
        return current
    anchor = "    _install_spreadsheet_tools()"
    if current.count(anchor) != 1:
        raise ValueError(
            "Install the existing Excel tools first; their startup interface is required. "
            "Nothing changed; share this message."
        )
    updated = (
        current.replace(
            anchor,
            anchor
            + "\n    from .workbook_copy_tools import install as _install_bulk_workbooks"
            + "\n    _install_bulk_workbooks()",
        )
        + "\n"
        + MARKER
        + "\n"
    )
    compile(updated, "bootstrap.py", "exec")
    return updated


def image_dockerfile(before, path, names):
    parent = str(Path(path).parent)
    return (
        "FROM "
        + before
        + "\n"
        + "".join("COPY --chmod=0755 " + json.dumps([name, parent + "/" + name]) + "\n" for name in names)
    )


def docker(*args, **kwargs):
    try:
        return subprocess.run(  # noqa: S603 - fixed Docker argv; no shell
            ["/usr/bin/sudo", "/usr/bin/docker", *args], check=True, capture_output=True, text=True, **kwargs
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        if args and args[0] == "run":
            for line in (exc.stdout or "").splitlines():
                if line.startswith(("OFFLINE_CHECK_FAILED:", "MODULE:", "FRAME:")):
                    print(line[:240], flush=True)
        raise


def busy():
    return (
        docker(
            "exec",
            "deploy-api-1",
            "python",
            "-c",
            """
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
async def main():
    engine=create_async_engine(get_settings().database_url)
    async with engine.connect() as db:
        query = text("SELECT (SELECT count(*) FROM builder_projects WHERE status IN ('queued','running'))"
                     " + (SELECT count(*) FROM operation_jobs WHERE status IN ('queued','executing'))"
                     " + (SELECT count(*) FROM generation_jobs WHERE status IN ('queued','processing'))")
        print((await db.execute(query)).scalar())
    await engine.dispose()
asyncio.run(main())
""",
        )
        != "0"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    info = json.loads(
        docker(
            "inspect",
            "deploy-api-1",
            "--format",
            '{"image":{{json .Image}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}}}',
        )
    )
    packet = json.loads(
        docker(
            "exec",
            "deploy-api-1",
            "python",
            "-c",
            """
import json,pathlib,hashlib,base64
from app.assistant_studio import bootstrap
path=pathlib.Path(bootstrap.__file__)
modules=[path.with_name(name) for name in ('spreadsheet_engine.py','spreadsheet_package.py','workbook_copy.py','workbook_copy_tools.py')]
result={'path':str(path),'source':base64.b64encode(path.read_bytes()).decode(),
        'module_sha':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in modules},
        'storage':str(pathlib.Path(__import__('app.core.config',fromlist=['get_settings']).get_settings().storage_dir).resolve())}
print(json.dumps(result))
""",
        )
    )
    previous_hashes = {'spreadsheet_engine.py': 'adf6c0c99ef5c58b6b7a6013bdd9eb68a2f724979c6febd9c7a61cc4dcef6794', 'spreadsheet_package.py': 'dfc9ade80179c438cc4e264cb1848d05997baa74ac6b91d68c63ed098a574853'}
    previous_hashes['workbook_copy_tools.py'] = 'b65cebbb543ce933d4b520cdf85e3330d5344c08b1201aaeb246e7eadbf9bf2c'
    known_hashes = {name: {value} for name, value in previous_hashes.items()}
    for name, value in {'spreadsheet_engine.py': '5d239723773733c6a40b1dce3dbedcf0e31100dcd9e2666f4bfe5a602a7976db', 'workbook_copy.py': '2e3cd4ea5d446d1b37d8c894abcadcf05ee30556663d3e0f1ac136bd7d19b45b', 'workbook_copy_tools.py': '6795dc99380bd82de721fe1b6540a74a02a5ecfad817608787f811c20616d0e3'}.items():
        known_hashes.setdefault(name, set()).add(value)
    for name, value in {'spreadsheet_engine.py': 'c8de8455adaafb9935cb09fdc3e91a35de908c44183a080c7a5604a8b2c4df39', 'workbook_copy.py': '4bdb35034d04cadd64c2eb1744a4fe8f5306ec44faa54fdada1c78f69cd6b0fe', 'workbook_copy_tools.py': '9fd0f080f5948a29da8b7ad4f404439c3e3fca4e345e85063a2349aa5f1a9120'}.items():
        known_hashes.setdefault(name, set()).add(value)
    bundle = payload()
    for name, source in bundle.items():
        expected = hashlib.sha256(source.encode()).hexdigest()
        if packet["module_sha"].get(name) not in ({None, expected} | known_hashes.get(name, set())):
            raise ValueError("The Bulk workbook module was customized. Nothing changed.")
    current = base64.b64decode(packet["source"]).decode()
    updated = patch_bootstrap(current)
    sources = {"bootstrap.py": updated, **bundle}
    if updated == current and all(packet["module_sha"].get(n) == hashlib.sha256(s.encode()).hexdigest() for n, s in bundle.items()):
        print("Bulk workbook support is already installed. No video was submitted.")
        return
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/bootstrap.py"):
        raise ValueError("Unexpected bootstrap path. Nothing changed.")
    for mount in info["mounts"]:
        dest = mount["Destination"].rstrip("/")
        targets = [str(Path(path).with_name(name)) for name in MODULES]
        if any(target == dest or target.startswith(dest + "/") for target in targets):
            raise ValueError("Bootstrap source is mounted over the image. Nothing changed.")
    if not any(packet["storage"] == m["Destination"].rstrip("/") or packet["storage"].startswith(m["Destination"].rstrip("/") + "/") for m in info["mounts"]):
        raise ValueError("Private upload storage is not persistent. Nothing changed.")
    labels = info["labels"]
    files = labels["com.docker.compose.project.config_files"].split(",")
    directory = Path(labels["com.docker.compose.project.working_dir"])
    project = labels["com.docker.compose.project"]
    if not directory.is_dir() or not project or not all(Path(p).is_absolute() and Path(p).is_file() for p in files):
        raise ValueError("The active Compose configuration is unavailable. Nothing changed.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", info["image"]):
        raise ValueError("Cannot identify the current API image.")
    if busy():
        raise ValueError(
            "A build or server task is queued/running. Wait for it to finish, then rerun; nothing changed."
        )
    work = Path(tempfile.mkdtemp(prefix="dhanz-bulk-workbooks-", dir=Path.home()))
    os.chmod(work, 0o700)
    for name in MODULES:
        (work / name).write_text(sources[name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-bulk-workbooks-" + stamp
    image = "dhanz-api:bulk-workbooks-" + stamp
    docker("tag", info["image"], before)
    dockerfile = image_dockerfile(before, path, MODULES)
    (work / "Dockerfile").write_text(dockerfile)
    print("Building a small update from the current API image...", flush=True)
    docker("build", "--network=none", "-t", image, str(work), timeout=180)
    print("Checking startup as the image configured user...", flush=True)
    docker(
        "run",
        "--rm",
        "--network=none",
        "-e",
        "APP_ENV=test",
        "--entrypoint",
        "python",
        image,
        "-c",
        """
try:
    from app.main import create_app
    from app.core.config import Settings
    from app.assistant_studio import spreadsheet_engine as engine
    from app.assistant_studio.workbook_copy import copy_column
    from openpyxl import Workbook,load_workbook
    import io
    source=Workbook()
    source.active.title='SOW'
    source.active.append(['Tool ID'])
    source.active.append(['000012'])
    destination=Workbook()
    destination.active.title='Template'
    destination.active.append(['LID'])
    a,b=io.BytesIO(),io.BytesIO()
    source.save(a)
    destination.save(b)
    data,summary=copy_column(a.getvalue(),b.getvalue(),source_sheet='SOW',source_header='Tool ID',destination_sheet='Template',destination_header='LID')
    assert load_workbook(io.BytesIO(data)).active['A2'].value=='000012'
    assert summary['rows_copied']==1
    assert engine.MAX_CELLS==200000
    application=create_app(Settings(app_env='test',_env_file=None))
    from app.services import assistant_tools
    assert 'copy_workbook_column' in assistant_tools.TOOLS
    assert 'excel_workbook' in assistant_tools.TOOLS
    print('Bulk workbook startup checks passed. No model download or generation was started.')
except Exception as exc:
    import traceback
    print('OFFLINE_CHECK_FAILED:'+type(exc).__name__)
    if isinstance(exc,ImportError):print('MODULE:'+str(exc.name))
    for frame in traceback.extract_tb(exc.__traceback__)[-4:]:print('FRAME:'+frame.filename+':'+str(frame.lineno))
    raise SystemExit(1)
""",
        timeout=60,
    )
    overlay = work / "compose.json"
    overlay.write_text(
        json.dumps(
            {
                "services": {
                    "api": {
                        "image": image,
                        "pull_policy": "never",
                    }
                }
            }
        )
    )
    rollback_file = work / "rollback.json"
    rollback_file.write_text(
        json.dumps(
            {
                "services": {
                    "api": {
                        "image": before,
                        "pull_policy": "never",
                    }
                }
            }
        )
    )
    base = ["compose", "--project-directory", str(directory), "-p", project]
    for file in files:
        base += ["-f", file]
    command = base + ["-f", str(overlay)]
    rollback = [
        "/usr/bin/sudo",
        "/usr/bin/docker",
        *base,
        "-f",
        str(rollback_file),
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "api",
    ]
    (work / "rollback-command.txt").write_text(shlex.join(rollback) + "\n")
    docker(*command, "config", "--quiet", cwd=directory)
    if not args.apply:
        print("Updated image passed offline checks. Production unchanged; rerun with --apply to enable.")
        return
    if docker("inspect", "deploy-api-1", "--format", "{{.Image}}") != info["image"] or busy():
        raise ValueError("The API changed or another build started. Nothing deployed; rerun after builds finish.")
    try:
        docker(*command, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "api", cwd=directory, timeout=120)
        for _ in range(45):
            state = docker(
                "inspect",
                "deploy-api-1",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
            )
            if state == "healthy":
                break
            time.sleep(2)
        else:
            raise ValueError("Updated API did not become healthy.")
    except Exception:
        subprocess.run(rollback, check=True, capture_output=True)  # noqa: S603 - fixed Docker rollback argv, no shell.
        print("Previous API image restored. No server task was queued or retried.")
        raise
    print(
        "Bulk workbook support installed. API healthy; existing connections, permissions and saved skills preserved."
    )
    print(
        "Streaming source reader installed; saved values from externally linked sources can be copied offline. Source links are not followed or transferred. Size/memory limits and strict destination validation remain in place. No workbook was processed during installation."
    )
    print("Rollback command: " + str(work / "rollback-command.txt"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit(
            "An installer step failed; raw output was withheld to protect secrets. Share this message."
        ) from None
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from None
