"""Repair structured project output and safe builder error messages, preserving the live image.

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

PAYLOAD = "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"
BASE_SHA = "eb4db0b6d82f3417c542c287a9050ef34fc2c4e92fb03dd97b04f7b276078a21"


def source():
    return gzip.decompress(base64.b64decode(PAYLOAD)).decode()


def supported(current):
    digest = hashlib.sha256(current.encode()).hexdigest()
    if digest == hashlib.sha256(source().encode()).hexdigest():
        return False
    if digest != BASE_SHA:
        raise ValueError(
            "The installed builder differs from the supported 0.9.4 release. Nothing changed; share this message."
        )
    return True


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
        print((await db.execute(text("SELECT count(*) FROM builder_projects WHERE status IN ('queued','running')"))).scalar())
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
from app.assistant_studio import builder
path=pathlib.Path(builder.__file__)
print(json.dumps({'path':str(path),'source':base64.b64encode(path.read_bytes()).decode()}))
""",
        )
    )
    current = base64.b64decode(packet["source"]).decode()
    if not supported(current):
        print("Builder protocol fix is already installed. No project was retried.")
        return
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/builder.py"):
        raise ValueError("Unexpected builder path. Nothing changed.")
    for mount in info["mounts"]:
        dest = mount["Destination"].rstrip("/")
        if path == dest or path.startswith(dest + "/"):
            raise ValueError("Builder source is mounted over the image. Nothing changed.")
    labels = info["labels"]
    files = labels["com.docker.compose.project.config_files"].split(",")
    directory = Path(labels["com.docker.compose.project.working_dir"])
    project = labels["com.docker.compose.project"]
    if not directory.is_dir() or not project or not all(Path(p).is_absolute() and Path(p).is_file() for p in files):
        raise ValueError("The active Compose configuration is unavailable. Nothing changed.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", info["image"]):
        raise ValueError("Cannot identify the current API image.")
    if busy():
        raise ValueError("A builder job is queued or running. Wait for it to finish, then rerun; nothing changed.")
    work = Path(tempfile.mkdtemp(prefix="dhanz-builder-protocol-", dir=Path.home()))
    os.chmod(work, 0o700)
    (work / "builder.before.py").write_text(current)
    (work / "builder.py").write_text(source())
    stamp = str(time.time_ns())
    before = "dhanz-api:before-builder-protocol-" + stamp
    image = "dhanz-api:builder-protocol-" + stamp
    docker("tag", info["image"], before)
    (work / "Dockerfile").write_text("FROM " + before + "\nCOPY " + json.dumps(["builder.py", path]) + "\n")
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
from app.assistant_studio.builder import PROJECT_TOOL, BuildError, failure_message, archive, _DHANZ_BUILDER_PROTOCOL_VERSION
assert _DHANZ_BUILDER_PROTOCOL_VERSION == 2
assert PROJECT_TOOL['strict'] is True
assert failure_message(BuildError('specific cause')) == 'specific cause'
assert archive([{'path':'agent.py','content':'print(1)'}]).startswith(b'PK')
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
        print("Previous API image restored. No project was retried.")
        raise
    print(
        "Builder protocol fix installed. API is healthy. Existing projects, browser, search, weather and OCR were preserved."
    )
    print(
        "No API generation was requested or retried. Create ONE small new test build; new failures show a specific safe cause."
    )
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
