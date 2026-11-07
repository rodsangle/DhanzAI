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
