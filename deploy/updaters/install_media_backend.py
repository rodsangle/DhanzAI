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

PAYLOAD = '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'  # noqa: E501 - reviewed media setup
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
