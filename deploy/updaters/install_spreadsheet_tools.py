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
MARKER = "_DHANZ_SPREADSHEET_TOOLS_VERSION = 7"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    for version in (1, 2, 3, 4, 5, 6):
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
                "website_tools.py",
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
        "website_tools.py",
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
        "website_tools.py",
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
assert 'open_website' in assistant_tools.TOOLS
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
