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
MARKER = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 3"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    for version in (1, 2):
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
