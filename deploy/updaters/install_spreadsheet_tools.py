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
