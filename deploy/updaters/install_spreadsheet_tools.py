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
