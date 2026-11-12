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
