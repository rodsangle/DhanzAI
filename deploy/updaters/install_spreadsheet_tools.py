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
MARKER = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 2"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    previous = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 1"
    if previous in current:
        if current.count("    _install_spreadsheet_tools()") != 1:
            raise ValueError("Unknown spreadsheet startup hook. Nothing changed.")
        return current.replace(previous, MARKER)
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
