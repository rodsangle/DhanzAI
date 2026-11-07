"""Install account-scoped routine decision preferences for chat and coding.

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

PAYLOAD = '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'  # noqa: E501 - reviewed autonomy support
MODULES = ("bootstrap.py", "autonomy.py")
MARKER = "_DHANZ_AUTONOMY_VERSION = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        if current.count("    _install_autonomy(app)") != 1:
            raise ValueError("Unknown Autonomy startup hook. Nothing changed.")
        return current
    anchor = "    _install_connected_operations(app)"
    if current.count(anchor) != 1:
        raise ValueError("The connected-operations startup interface differs. Nothing changed; share this message.")
    updated = (
        current.replace(
            anchor,
            anchor + "\n    from .autonomy import install as _install_autonomy\n    _install_autonomy(app)",
        )
        + "\n"
        + MARKER
        + "\n"
    )
    compile(updated, "bootstrap.py", "exec")
    return updated


def image_dockerfile(before, path, names):
    parent = str(Path(path).parent)
    return (
        "FROM "
        + before
        + "\n"
        + "".join("COPY --chmod=0755 " + json.dumps([name, parent + "/" + name]) + "\n" for name in names)
    )


def docker(*args, **kwargs):
    try:
        return subprocess.run(  # noqa: S603 - fixed Docker argv; no shell
            ["/usr/bin/sudo", "/usr/bin/docker", *args], check=True, capture_output=True, text=True, **kwargs
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        if args and args[0] == "run":
            for line in (exc.stdout or "").splitlines():
                if line.startswith(("OFFLINE_CHECK_FAILED:", "MODULE:", "FRAME:")):
                    print(line[:240], flush=True)
        raise


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
import json,pathlib,hashlib,base64
from app.assistant_studio import bootstrap
path=pathlib.Path(bootstrap.__file__)
module=path.with_name('autonomy.py')
result={'path':str(path),'source':base64.b64encode(path.read_bytes()).decode(),
        'module_sha':hashlib.sha256(module.read_bytes()).hexdigest() if module.exists() else None}
print(json.dumps(result))
""",
        )
    )
    source = payload()["module"]
    expected = hashlib.sha256(source.encode()).hexdigest()
    if packet["module_sha"] not in (None, expected):
        raise ValueError("The Autonomy module was customized. Nothing changed.")
    current = base64.b64decode(packet["source"]).decode()
    updated = patch_bootstrap(current)
    if updated == current and packet["module_sha"] == expected:
        print("Autonomy support is already installed. No external action was performed.")
        return
    sources = {"bootstrap.py": updated, "autonomy.py": source}
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/bootstrap.py"):
        raise ValueError("Unexpected bootstrap path. Nothing changed.")
    for mount in info["mounts"]:
        dest = mount["Destination"].rstrip("/")
        targets = [str(Path(path).with_name(name)) for name in MODULES]
        if any(target == dest or target.startswith(dest + "/") for target in targets):
            raise ValueError("Bootstrap source is mounted over the image. Nothing changed.")
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
    work = Path(tempfile.mkdtemp(prefix="dhanz-autonomy-", dir=Path.home()))
    os.chmod(work, 0o700)
    for name in MODULES:
        (work / name).write_text(sources[name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-autonomy-" + stamp
    image = "dhanz-api:autonomy-" + stamp
    docker("tag", info["image"], before)
    dockerfile = image_dockerfile(before, path, MODULES)
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
try:
    from app.main import create_app
    from app.core.config import Settings
    from app.assistant_studio.autonomy import POLICY
    application=create_app(Settings(app_env='test',_env_file=None))
    paths=application.openapi()['paths']
    endpoint=application.state.settings.api_prefix.rstrip('/')+'/assistant-studio/autonomy'
    assert {'get','put'}.issubset(paths[endpoint])
    assert 'not a new permission' in POLICY
    print('Autonomy startup checks passed. No provider or GitHub requests were made.')
except Exception as exc:
    import traceback
    print('OFFLINE_CHECK_FAILED:'+type(exc).__name__)
    if isinstance(exc,ImportError):print('MODULE:'+str(exc.name))
    for frame in traceback.extract_tb(exc.__traceback__)[-4:]:print('FRAME:'+frame.filename+':'+str(frame.lineno))
    raise SystemExit(1)
""",
        timeout=60,
    )
    overlay = work / "compose.json"
    overlay.write_text(
        json.dumps(
            {
                "services": {
                    "api": {
                        "image": image,
                        "pull_policy": "never",
                    }
                }
            }
        )
    )
    rollback_file = work / "rollback.json"
    rollback_file.write_text(
        json.dumps(
            {
                "services": {
                    "api": {
                        "image": before,
                        "pull_policy": "never",
                    }
                }
            }
        )
    )
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
    print("Autonomy support installed. API healthy; existing connections, permissions and saved skills preserved.")
    print("The account setting is enabled separately; no task was started and no external permission was added.")
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
