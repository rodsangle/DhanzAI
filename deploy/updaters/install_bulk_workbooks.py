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
        "Streaming source column reader installed; no total source-cell cap. Source file/expanded XML and text/style metadata remain bounded. Destination: 200000 cells and 100000 rows including headers. No workbook was processed during installation."
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
