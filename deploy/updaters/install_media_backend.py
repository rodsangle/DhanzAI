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
