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
MARKER = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 4"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    for version in (1, 2, 3):
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
    for name in ("spreadsheet_engine.py", "spreadsheet_package.py", "spreadsheet_tools.py", "operations_tools.py"):
        (work / name).write_text(payload()["app/assistant_studio/" + name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-spreadsheet-" + stamp
    image = "dhanz-api:spreadsheet-" + stamp
    docker("tag", info["image"], before)
    directory_path = str(Path(path).parent)
    dockerfile = "FROM " + before + "\nCOPY " + json.dumps(["bootstrap.py", path]) + "\n"
    for name in ("spreadsheet_engine.py", "spreadsheet_package.py", "spreadsheet_tools.py", "operations_tools.py"):
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
