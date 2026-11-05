"""Enable GitHub web updates and refresh for the installed Android/Windows PWA.

Prepare by default. --apply recreates only the API, with no migrations or model calls.
"""

import argparse
import base64
import gzip
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

PAYLOAD = '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'  # noqa: E501 - public frozen modules
MARKER = "_DHANZ_WEB_UPDATES_VERSION = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        return current
    if "_DHANZ_CONNECTED_OPERATIONS_VERSION = 1" not in current:
        raise ValueError("Install the existing 0.9.8 connected-operations backend first. Nothing changed.")
    anchor = "    _install_connected_operations(app)"
    if current.count(anchor) != 1:
        raise ValueError("Unknown bootstrap interface. Nothing changed.")
    updated = current.replace(
        anchor, anchor + "\n    from .web_updates import install as _install_web_updates\n    _install_web_updates(app)"
    )
    updated += "\n" + MARKER + "\n"
    compile(updated, "bootstrap.py", "exec")
    return updated


def host_setup():
    root = Path.home() / "dhanz-web-update-setup"
    root.mkdir(exist_ok=True, mode=0o700)
    root.chmod(0o700)
    for relative, content in payload().items():
        if relative.startswith("host/"):
            target = root / Path(relative).name
            target.write_text(content)
            target.chmod(0o600)
    print("Enabling the paired host's named web-update task and installing the checked web build...", flush=True)
    subprocess.run(["/usr/bin/python3", str(root / "provision_web_updates.py"), "--apply"], check=True, timeout=600)  # noqa: S603


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
print(json.dumps({'path':str(path),'source':base64.b64encode(path.read_bytes()).decode()}))
""",
        )
    )
    current = base64.b64decode(packet["source"]).decode()
    patched = patch_bootstrap(current)
    if patched == current:
        print("Web-update API is already installed.")
        if args.apply:
            host_setup()
        return
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/bootstrap.py"):
        raise ValueError("Unexpected operations-tool path. Nothing changed.")
    for mount in info["mounts"]:
        dest = mount["Destination"].rstrip("/")
        if path == dest or path.startswith(dest + "/"):
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
    work = Path(tempfile.mkdtemp(prefix="dhanz-web-updater-", dir=Path.home()))
    os.chmod(work, 0o700)
    (work / "bootstrap.before.py").write_text(current)
    (work / "bootstrap.py").write_text(patched)
    for name in ("web_updates.py", "web_release.py"):
        (work / name).write_text(payload()["app/assistant_studio/" + name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-web-updater-" + stamp
    image = "dhanz-api:web-updater-" + stamp
    docker("tag", info["image"], before)
    directory_path = str(Path(path).parent)
    dockerfile = "FROM " + before + "\nCOPY " + json.dumps(["bootstrap.py", path]) + "\n"
    for name in ("web_updates.py", "web_release.py"):
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
assert '/api/v1/operations/web-updates' in application.openapi()['paths']
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
    print("Web-update API installed and healthy. Existing server pairing and settings preserved.")
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
