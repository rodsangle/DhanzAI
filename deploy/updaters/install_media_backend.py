"""Install bounded local video editing, narration and sound exports.

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

PAYLOAD = "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"  # noqa: E501 - reviewed media setup
MODULES = ("bootstrap.py", "media_engine.py", "media_studio.py")
MARKER = "_DHANZ_MEDIA_STUDIO_VERSION = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        if current.count("    _install_media_studio(app)") != 1:
            raise ValueError("Unknown Media studio startup hook. Nothing changed.")
        return current
    anchor = "    _install_connected_operations(app)"
    if current.count(anchor) != 1:
        raise ValueError("The connected-operations startup interface differs. Nothing changed; share this message.")
    updated = (
        current.replace(
            anchor,
            anchor + "\n    from .media_studio import install as _install_media_studio\n    _install_media_studio(app)",
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
            '{"image":{{json .Image}},"user":{{json .Config.User}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}}}',  # noqa: E501 - bounded fixed schema/filter or installer metadata
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
modules={name:path.with_name(name) for name in ('media_engine.py','media_studio.py')}
result={'path':str(path),'source':base64.b64encode(path.read_bytes()).decode(),
        'module_shas':{name:hashlib.sha256(module.read_bytes()).hexdigest() if module.exists() else None
                       for name,module in modules.items()},
        'storage':str(pathlib.Path(__import__('app.core.config',fromlist=['get_settings']).get_settings().storage_dir).resolve())}
print(json.dumps(result))
""",
        )
    )
    modules = payload()
    for name, source in modules.items():
        expected = hashlib.sha256(source.encode()).hexdigest()
        if packet["module_shas"][name] not in (None, expected):
            raise ValueError("A media module was customized. Nothing changed.")
    storage = packet["storage"]
    if not any(
        m.get("RW", False)
        and (storage == m["Destination"].rstrip("/") or storage.startswith(m["Destination"].rstrip("/") + "/"))
        for m in info["mounts"]
    ):
        raise ValueError("The media storage directory needs an existing writable persistent mount. Nothing changed.")
    current = base64.b64decode(packet["source"]).decode()
    updated = patch_bootstrap(current)
    if updated == current and all(
        packet["module_shas"][name] == hashlib.sha256(source.encode()).hexdigest() for name, source in modules.items()
    ):  # noqa: E501 - bounded fixed schema/filter or installer metadata
        print("Media studio support is already installed. No external action was performed.")
        return
    sources = {"bootstrap.py": updated, **modules}
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
    work = Path(tempfile.mkdtemp(prefix="dhanz-media-studio-", dir=Path.home()))
    os.chmod(work, 0o700)
    for name in MODULES:
        (work / name).write_text(sources[name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-media-studio-" + stamp
    image = "dhanz-api:media-studio-" + stamp
    docker("tag", info["image"], before)
    configured_user = info["user"] or "root"
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", configured_user):
        raise ValueError("Unexpected configured image user. Nothing changed.")
    dockerfile = image_dockerfile(before, path, MODULES)
    dockerfile += (
        "USER root\nRUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng "
        "&& rm -rf /var/lib/apt/lists/*\nUSER " + configured_user + "\n"
    )
    (work / "Dockerfile").write_text(dockerfile)
    print("Building a small update from the current API image...", flush=True)
    docker("build", "-t", image, str(work), timeout=900)
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
    import shutil,asyncio,tempfile,pathlib
    from app.assistant_studio.media_engine import Edit,render,probe
    application=create_app(Settings(app_env='test',_env_file=None))
    paths=application.openapi()['paths']
    endpoint=application.state.settings.api_prefix.rstrip('/')+'/media-studio/jobs'
    assert {'get','post'}.issubset(paths[endpoint])
    assert shutil.which('ffmpeg') and shutil.which('ffprobe') and shutil.which('espeak-ng')
    async def check():
        with tempfile.TemporaryDirectory() as temp:
            output=await render(pathlib.Path(temp),Edit(mode='narration',narration='Hello from Dhanz.'))
            assert output.stat().st_size>100 and (await probe(output))[1]>0
    asyncio.run(check())
    print('Media startup checks passed. No provider or GitHub requests were made.')
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
    print("Media studio support installed. API healthy; existing connections, permissions and saved skills preserved.")
    print("Local media rendering is available. No provider credits or new external permissions were used.")
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
