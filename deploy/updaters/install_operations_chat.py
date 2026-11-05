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

PAYLOAD = "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"  # noqa: E501 - frozen public tool module
BASE_SHA = "c5a4d81ef40d95c9c6939d3cfe84df8db01cfa1be4a3cfa9e83bdccc20e6eee6"


def source():
    return gzip.decompress(base64.b64decode(PAYLOAD)).decode()


def supported(current):
    digest = hashlib.sha256(current.encode()).hexdigest()
    if digest == hashlib.sha256(source().encode()).hexdigest():
        return False
    if digest != BASE_SHA:
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
        print("Server-task chat fix is already installed. No task was queued or retried.")
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
assert _DHANZ_OPERATIONS_CHAT_VERSION == 2
install_tools()
spec=assistant_tools.TOOLS['run_connected_task'].spec
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
        "Server-task chat fix installed. API is healthy. Browser, paired servers, grants and settings were preserved."
    )
    print("Request keys are generated internally. No server task was queued or retried. Start a new chat to test.")
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
