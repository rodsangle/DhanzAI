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
