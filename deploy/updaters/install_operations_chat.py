"""Generate chat server-task request keys internally, preserving the live API image.

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

PAYLOAD = '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'  # noqa: E501 - frozen public tool module
BASE_SHA = "c5a4d81ef40d95c9c6939d3cfe84df8db01cfa1be4a3cfa9e83bdccc20e6eee6"
BASE_SHAS = {BASE_SHA, "0572c8cc05a2542f0b18d97494d575d02f559124343f45c261d70f4607e78237"}


def source():
    return gzip.decompress(base64.b64decode(PAYLOAD)).decode()


def supported(current):
    digest = hashlib.sha256(current.encode()).hexdigest()
    if digest == hashlib.sha256(source().encode()).hexdigest():
        return False
    if digest not in BASE_SHAS:
        raise ValueError(
            "The operations chat tool differs from the supported 0.9.8 release. Nothing changed; share this message."
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
from app.assistant_studio import operations_tools
path=pathlib.Path(operations_tools.__file__)
print(json.dumps({'path':str(path),'source':base64.b64encode(path.read_bytes()).decode()}))
""",
        )
    )
    current = base64.b64decode(packet["source"]).decode()
    if not supported(current):
        print("GitHub and server chat workflows are already installed. No task was queued or retried.")
        return
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/operations_tools.py"):
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
    work = Path(tempfile.mkdtemp(prefix="dhanz-operations-chat-", dir=Path.home()))
    os.chmod(work, 0o700)
    (work / "operations_tools.before.py").write_text(current)
    (work / "operations_tools.py").write_text(source())
    stamp = str(time.time_ns())
    before = "dhanz-api:before-operations-chat-" + stamp
    image = "dhanz-api:operations-chat-" + stamp
    docker("tag", info["image"], before)
    (work / "Dockerfile").write_text("FROM " + before + "\nCOPY " + json.dumps(["operations_tools.py", path]) + "\n")
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
from app.assistant_studio.operations_tools import install_tools, request_key, _DHANZ_OPERATIONS_CHAT_VERSION
from app.services import assistant_tools
from types import SimpleNamespace
import uuid
assert _DHANZ_OPERATIONS_CHAT_VERSION == 3
install_tools()
spec=assistant_tools.TOOLS['run_connected_task'].spec
assert 'github_workspace' in assistant_tools.TOOLS
assert spec.parameters['required'] == ['grant_id']
assert 'request_key' not in spec.parameters['properties']
ctx=SimpleNamespace(user_id=uuid.uuid4(),conversation_id=uuid.uuid4(),assistant_message_id=uuid.uuid4())
grant=uuid.uuid4()
assert request_key(ctx,grant)==request_key(ctx,grant)
assert len(request_key(ctx,grant))==37

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
        "GitHub/server chat workflows installed. API healthy. Browser, server pairing and grants preserved."
    )
    print("GitHub coding can start from chat. No task was queued or retried by installation. Start a new chat to test.")
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
