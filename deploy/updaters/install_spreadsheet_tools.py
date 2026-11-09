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


def image_dockerfile(before, path, names):
    """BuildKit must not inherit private host permissions for importable modules."""
    parent = str(Path(path).parent)
    files = [("bootstrap.py", path)] + [(name, parent + "/" + name) for name in names]
    return (
        "FROM "
        + before
        + "\n"
        + "".join("COPY --chmod=0755 " + json.dumps([name, destination]) + "\n" for name, destination in files)
    )


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
    dockerfile = image_dockerfile(
        before,
        path,
        (
            "spreadsheet_engine.py",
            "spreadsheet_package.py",
            "spreadsheet_workflow.py",
            "spreadsheet_routes.py",
            "website_tools.py",
            "spreadsheet_tools.py",
            "operations_tools.py",
        ),
    )
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
