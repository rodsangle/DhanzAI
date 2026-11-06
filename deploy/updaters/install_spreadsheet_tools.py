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

PAYLOAD = "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"  # noqa: E501 - frozen public modules
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
