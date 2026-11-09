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
    bundle = payload()
    for name, source in bundle.items():
        expected = hashlib.sha256(source.encode()).hexdigest()
        if packet["module_sha"].get(name) not in (None, expected, previous_hashes.get(name)):
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
        "Source workbooks: up to 500000 populated cells. Destination workbooks: up to 200000 cells. Up to 100000 rows including headers. No workbook was processed during installation."
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
