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
MARKER = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 6"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    for version in (1, 2, 3, 4, 5):
        previous = f"_DHANZ_SPREADSHEET_TOOLS_VERSION = {version}"
        if previous in current:
            if current.count("    _install_spreadsheet_tools()") != 1:
                raise ValueError("Unknown spreadsheet startup hook. Nothing changed.")
            updated = current.replace(previous, MARKER)
            if "    _install_spreadsheet_routes(app)" in updated:
                return updated
            return updated.replace(
                "    _install_spreadsheet_tools()",
                "    _install_spreadsheet_tools()\n    from .spreadsheet_routes import install as _install_spreadsheet_routes\n    _install_spreadsheet_routes(app)",  # noqa: E501 - bootstrap hook text
            )
    if "_DHANZ_CONNECTED_OPERATIONS_VERSION = 1" not in current:
        raise ValueError("Install the existing 0.9.8 connected-operations backend first. Nothing changed.")
    anchor = "    _install_connected_operations(app)"
    if current.count(anchor) != 1:
        raise ValueError("Unknown bootstrap interface. Nothing changed.")
    updated = current.replace(
        anchor,
        anchor
        + "\n    from .spreadsheet_tools import install as _install_spreadsheet_tools\n    _install_spreadsheet_tools()\n    from .spreadsheet_routes import install as _install_spreadsheet_routes\n    _install_spreadsheet_routes(app)",  # noqa: E501 - descriptive tool text
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
                "spreadsheet_routes.py",
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
        "spreadsheet_routes.py",
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
        "spreadsheet_routes.py",
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
assert '/api/v1/spreadsheets/{document_id}' in application.openapi()['paths']
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
