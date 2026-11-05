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
    host_setup()
    print("Rollback command: " + str(work / "rollback-command.txt"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit(
            "An installer step failed; raw output was withheld to protect secrets. Share this message."
        ) from None
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from None
