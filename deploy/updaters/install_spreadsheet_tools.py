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
MARKER = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 5"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    for version in (1, 2, 3, 4):
        previous = f"_DHANZ_SPREADSHEET_TOOLS_VERSION = {version}"
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
            for name in (
                "spreadsheet_engine.py",
                "spreadsheet_package.py",
                "spreadsheet_workflow.py",
                "spreadsheet_tools.py",
                "operations_tools.py",
            )
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
    for name in (
        "spreadsheet_engine.py",
        "spreadsheet_package.py",
        "spreadsheet_workflow.py",
        "spreadsheet_tools.py",
        "operations_tools.py",
    ):
        (work / name).write_text(payload()["app/assistant_studio/" + name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-spreadsheet-" + stamp
    image = "dhanz-api:spreadsheet-" + stamp
    docker("tag", info["image"], before)
    directory_path = str(Path(path).parent)
    dockerfile = "FROM " + before + "\nCOPY " + json.dumps(["bootstrap.py", path]) + "\n"
    for name in (
        "spreadsheet_engine.py",
        "spreadsheet_package.py",
        "spreadsheet_workflow.py",
        "spreadsheet_tools.py",
        "operations_tools.py",
    ):
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
