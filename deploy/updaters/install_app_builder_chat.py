"""Build apps and agents from chat, including Flutter mobile source projects.

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

PAYLOAD = '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'  # noqa: E501 - frozen source
MODULES = ("bootstrap.py", "builder.py", "app_builder_tools.py")
MARKER = "_DHANZ_APP_BUILDER_VERSION = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    data = payload()
    if MARKER in current:
        if current.count("    install_app_builder()") != 1:
            raise ValueError("Unknown app-builder startup hook. Nothing changed.")
        return current
    if data["boot_new"] in current:
        return current + "\n" + MARKER + "\n"
    if current.count(data["boot_anchor"]) != 1:
        raise ValueError("Unknown builder startup interface. Nothing changed.")
    result = current.replace(data["boot_anchor"], data["boot_new"]) + "\n" + MARKER + "\n"
    compile(result, "bootstrap.py", "exec")
    return result


def patch_builder(current):
    data = payload()
    if MARKER in current:
        if data["builder_fragment"] not in current or data["builder_validation"] not in current:
            raise ValueError("Unknown mobile builder implementation. Nothing changed.")
        return current
    if data["builder_fragment"] in current and data["builder_validation"] in current:
        return current + "\n" + MARKER + "\n"
    anchor = "    response = await client.post(\n"
    validation = '    if job.kind == "app" and not any(f["path"] == "index.html" for f in files):\n'
    if current.count(anchor) != 1 or current.count(validation) != 1:
        raise ValueError("Unknown project generation interface. Nothing changed.")
    result = current.replace(anchor, data["builder_fragment"] + anchor)
    result = result.replace(validation, data["builder_validation"]) + "\n" + MARKER + "\n"
    compile(result, "builder.py", "exec")
    return result


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
source={name:base64.b64encode(path.with_name(name).read_bytes()).decode()
        for name in ("bootstrap.py","builder.py")}
extra=path.with_name("app_builder_tools.py")
result={'path':str(path),'source':source,
        'tool_sha':hashlib.sha256(extra.read_bytes()).hexdigest() if extra.exists() else None}
print(json.dumps(result))
""",
        )
    )
    current = {name: base64.b64decode(value).decode() for name, value in packet["source"].items()}
    module = payload()["module"]
    if packet["tool_sha"] not in (None, hashlib.sha256(module.encode()).hexdigest()):
        raise ValueError("App-builder chat tool was customized. Nothing changed.")
    sources = {
        "bootstrap.py": patch_bootstrap(current["bootstrap.py"]),
        "builder.py": patch_builder(current["builder.py"]),
        "app_builder_tools.py": module,
    }
    if all(sources[name] == current[name] for name in current) and packet["tool_sha"]:
        print("Chat app/mobile builder is already installed. No project was started or retried.")
        return
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/bootstrap.py"):
        raise ValueError("Unexpected builder module path. Nothing changed.")
    for mount in info["mounts"]:
        dest = mount["Destination"].rstrip("/")
        targets = [str(Path(path).with_name(name)) for name in MODULES]
        if any(target == dest or target.startswith(dest + "/") for target in targets):
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
        raise ValueError(
            "A build or server task is queued/running. Wait for it to finish, then rerun; nothing changed."
        )
    work = Path(tempfile.mkdtemp(prefix="dhanz-app-builder-", dir=Path.home()))
    os.chmod(work, 0o700)
    for name in MODULES:
        (work / name).write_text(sources[name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-app-builder-" + stamp
    image = "dhanz-api:app-builder-" + stamp
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
    from app.services import assistant_tools
    from app.assistant_studio import builder
    from app.assistant_studio.app_builder_tools import build_instructions
    create_app(Settings(app_env='test',_env_file=None))
    assert 'build_app' in assistant_tools.TOOLS
    assert builder._DHANZ_APP_BUILDER_VERSION == 1
    assert build_instructions('Vehicle demo','flutter').startswith('[DHANZ_RUNTIME:flutter]')
    print('Chat/mobile builder startup check passed. No provider request was made.')
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
    print("Chat app/mobile builder installed. API healthy; existing settings and services preserved.")
    print("Start a new chat and ask Dhanz to build your app. Source projects appear in App & agent builder.")
    print("Flutter source is not a compiled APK. Generation uses the configured OpenAI API and may use credits.")
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
