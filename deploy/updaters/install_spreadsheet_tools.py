"""Enable Excel editing/formulas and authorized AWS chat commands.

Prepare by default. --apply recreates only the API, with no migrations or model calls.
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

PAYLOAD = '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'  # noqa: E501 - frozen public modules
MARKER = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    if "_DHANZ_CONNECTED_OPERATIONS_VERSION = 1" not in current:
        raise ValueError("Install the existing 0.9.8 connected-operations backend first. Nothing changed.")
    anchor = "    _install_connected_operations(app)"
    if current.count(anchor) != 1:
        raise ValueError("Unknown bootstrap interface. Nothing changed.")
    updated = current.replace(
        anchor,
        anchor
        + "\n    from .spreadsheet_tools import install as _install_spreadsheet_tools\n    _install_spreadsheet_tools()",  # noqa: E501 - descriptive tool text
    )
    updated += "\n" + MARKER + "\n"
    compile(updated, "bootstrap.py", "exec")
    return updated


def host_setup():
    root = Path.home() / "dhanz-spreadsheet-setup"
    root.mkdir(exist_ok=True, mode=0o700)
    root.chmod(0o700)
    target = root / "add_server_command.py"
    target.write_text(payload()["host/add_server_command.py"])
    target.chmod(0o600)
    print("Optional named-command setup: python3 " + str(target))


def docker(*args, **kwargs):
    return subprocess.run(  # noqa: S603 - fixed Docker executable and argument arrays, no shell.
        ["/usr/bin/sudo", "/usr/bin/docker", *args], check=True, capture_output=True, text=True, **kwargs
    ).stdout.strip()


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
                     " + (SELECT count(*) FROM operation_jobs WHERE status IN ('queued','executing'))")
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
import base64,json,pathlib
from app.assistant_studio import bootstrap
path=pathlib.Path(bootstrap.__file__)
packet={'path':str(path),'source':base64.b64encode(path.read_bytes()).decode()}
packet['operations_sha']=__import__('hashlib').sha256(path.with_name('operations_tools.py').read_bytes()).hexdigest()
print(json.dumps(packet))
""",
        )
    )
    current = base64.b64decode(packet["source"]).decode()
    expected = hashlib.sha256(payload()["app/assistant_studio/operations_tools.py"].encode()).hexdigest()
    known = {
        expected,
        "c5a4d81ef40d95c9c6939d3cfe84df8db01cfa1be4a3cfa9e83bdccc20e6eee6",
        "0572c8cc05a2542f0b18d97494d575d02f559124343f45c261d70f4607e78237",
    }
    if packet["operations_sha"] not in known:
        raise ValueError("The existing operations chat module is customized. Nothing changed; share this message.")
    patched = patch_bootstrap(current)
    if patched == current:
        print("Excel and connected-command chat tools are already installed.")
        if args.apply:
            host_setup()
        return
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/bootstrap.py"):
        raise ValueError("Unexpected operations-tool path. Nothing changed.")
    for mount in info["mounts"]:
        dest = mount["Destination"].rstrip("/")
        targets = [path] + [
            str(Path(path).with_name(name))
            for name in ("spreadsheet_engine.py", "spreadsheet_tools.py", "operations_tools.py")
        ]
        if any(target == dest or target.startswith(dest + "/") for target in targets):
            raise ValueError("Operations source is mounted over the image. Nothing changed.")
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
    work = Path(tempfile.mkdtemp(prefix="dhanz-spreadsheet-", dir=Path.home()))
    os.chmod(work, 0o700)
    (work / "bootstrap.before.py").write_text(current)
    (work / "bootstrap.py").write_text(patched)
    for name in ("spreadsheet_engine.py", "spreadsheet_tools.py", "operations_tools.py"):
        (work / name).write_text(payload()["app/assistant_studio/" + name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-spreadsheet-" + stamp
    image = "dhanz-api:spreadsheet-" + stamp
    docker("tag", info["image"], before)
    directory_path = str(Path(path).parent)
    dockerfile = "FROM " + before + "\nCOPY " + json.dumps(["bootstrap.py", path]) + "\n"
    for name in ("spreadsheet_engine.py", "spreadsheet_tools.py", "operations_tools.py"):
        dockerfile += "COPY " + json.dumps([name, directory_path + "/" + name]) + "\n"
    (work / "Dockerfile").write_text(dockerfile)
    print("Building a small update from the current API image...", flush=True)
    docker("build", "--network=none", "-t", image, str(work), timeout=180)
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
from app.main import create_app
from app.core.config import Settings
application=create_app(Settings(app_env='test',_env_file=None))
from app.services import assistant_tools
assert 'excel_workbook' in assistant_tools.TOOLS
assert 'run_connected_task' in assistant_tools.TOOLS
from app.assistant_studio.spreadsheet_engine import edit, inspect
content=edit(None,[{'type':'set_cells','sheet':'Sheet','range':'A1','values':[['0001']]}])
assert inspect(content)['sheets'][0]['preview'][0][0]=='0001'
assert '/api/v1/coding/drafts' in application.openapi()['paths']

""",
        timeout=60,
    )
    overlay = work / "compose.json"
    overlay.write_text(json.dumps({"services": {"api": {"image": image, "pull_policy": "never"}}}))
    rollback_file = work / "rollback.json"
    rollback_file.write_text(json.dumps({"services": {"api": {"image": before, "pull_policy": "never"}}}))
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
        "Excel and connected-command chat tools installed and healthy. Existing server pairing and settings preserved."
    )
    print("API rollback command: " + str(work / "rollback-command.txt"))
    host_setup()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit(
            "An installer step failed; raw output was withheld to protect secrets. Share this message."
        ) from None
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from None
