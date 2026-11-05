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
