"""Install the account-scoped outbound ROG Wan worker connection.

Prepare by default. --apply recreates only the API, without migrations or video generation.
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

PAYLOAD = "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"  # noqa: E501 - frozen ROG worker support
MODULES = ("bootstrap.py", "rog_queue.py", "rog_video.py")
MARKER = "_DHANZ_ROG_WORKER_HOOK = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        if current.count("    _install_rog_worker(app)") != 1:
            raise ValueError("Unknown ROG worker startup hook. Nothing changed.")
        return current
    anchor = "    _install_reference_video(app)"
    if current.count(anchor) != 1:
        raise ValueError(
            "Install local Media editor support first; its startup interface is required. "
            "Nothing changed; share this message."
        )
    updated = (
        current.replace(
            anchor,
            anchor
            + "\n    from .rog_video import install as _install_rog_worker"
            + "\n    _install_rog_worker(app)",
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
                     " + (SELECT count(*) FROM operation_jobs WHERE status IN ('queued','executing'))"
                     " + (SELECT count(*) FROM generation_jobs WHERE status IN ('queued','processing'))")
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
modules=[path.with_name(name) for name in ('rog_queue.py','rog_video.py')]
result={'path':str(path),'source':base64.b64encode(path.read_bytes()).decode(),
        'module_sha':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in modules},
        'storage':str(pathlib.Path(__import__('app.core.config',fromlist=['get_settings']).get_settings().storage_dir).resolve())}
print(json.dumps(result))
""",
        )
    )
    bundle = payload()
    for name, source in bundle.items():
        expected = hashlib.sha256(source.encode()).hexdigest()
        if packet["module_sha"].get(name) not in (None, expected):
            raise ValueError("The ROG worker module was customized. Nothing changed.")
    current = base64.b64decode(packet["source"]).decode()
    updated = patch_bootstrap(current)
    sources = {"bootstrap.py": updated, **bundle}
    if updated == current and all(packet["module_sha"].get(n) == hashlib.sha256(s.encode()).hexdigest() for n, s in bundle.items()):
        print("ROG worker support is already installed. No video was submitted.")
        return
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/assistant_studio/bootstrap.py"):
        raise ValueError("Unexpected bootstrap path. Nothing changed.")
    for mount in info["mounts"]:
        dest = mount["Destination"].rstrip("/")
        targets = [str(Path(path).with_name(name)) for name in MODULES]
        if any(target == dest or target.startswith(dest + "/") for target in targets):
            raise ValueError("Bootstrap source is mounted over the image. Nothing changed.")
    if not any(packet["storage"] == m["Destination"].rstrip("/") or packet["storage"].startswith(m["Destination"].rstrip("/") + "/") for m in info["mounts"]):
        raise ValueError("Private upload storage is not persistent. Nothing changed.")
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
    work = Path(tempfile.mkdtemp(prefix="dhanz-rog-worker-", dir=Path.home()))
    os.chmod(work, 0o700)
    for name in MODULES:
        (work / name).write_text(sources[name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-rog-worker-" + stamp
    image = "dhanz-api:rog-worker-" + stamp
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
    from app.assistant_studio.rog_video import router, RogVideoProvider
    import tempfile
    from types import SimpleNamespace
    from app.assistant_studio.rog_queue import Queue
    with tempfile.TemporaryDirectory() as folder:
        q=Queue(folder)
        import uuid
        owner=uuid.uuid4()
        token=q.pair(owner)
        assert q.authenticate(token)==str(owner)
        q.heartbeat(owner)
        task=q.submit(uuid.uuid4(),owner,"Moonlit forest")
        claim=q.claim(owner)
        assert claim["id"]==task
        assert q.claim(owner) is None
        q.cancel(task)
        assert q.poll(task)["status"]=="CANCELLED"
    application=create_app(Settings(app_env='test',_env_file=None))
    paths=application.openapi()['paths']
    endpoint=application.state.settings.api_prefix.rstrip('/')+'/rog-worker/pair'
    assert 'post' in paths[endpoint]
    print('ROG worker startup checks passed. No model download or generation was started.')
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
    print(
        "ROG worker support installed. API healthy; existing connections, permissions and saved skills preserved."
    )
    print(
        "ROG renders the tested five-second silent preview. Storage, image generation and content screening were preserved. No old video job was retried."
    )
    print("Rollback command: " + str(work / "rollback-command.txt"))
    # Readiness checks do not render a video or retry existing jobs. Preserve the
    # current moderation/storage configuration and report actual availability.
    checks = docker("exec", "-i", "deploy-api-1", "python", "-c", """
import asyncio
from app.core.config import get_settings
from app.content_moderation import build_moderator
from app.media_storage import build_storage
async def main():
    settings=get_settings()
    moderator=build_moderator(settings)
    storage=build_storage(settings)
    try:
        try:
            if moderator is None: raise ValueError('unconfigured')
            await moderator.check('A peaceful moonlit forest with gently moving mist.',None,None)
            print('Content screening: ready')
        except Exception:
            print('Content screening: unavailable; video generation remains blocked')
        key=None
        try:
            import io
            from PIL import Image
            buffer=io.BytesIO()
            Image.new('RGB',(2,2),(20,40,60)).save(buffer,format='PNG')
            value=buffer.getvalue()
            key=await storage.put(value)
            assert await storage.get(key)==value
            print('Private media storage: ready')
        except Exception:
            print('Private media storage: unavailable; video delivery needs repair')
        finally:
            if key is not None:
                try: await storage.delete(key)
                except Exception: pass
    finally:
        for component in (moderator,storage):
            close=getattr(component,'aclose',None)
            if close is not None:
                try: await close()
                except Exception: pass
asyncio.run(main())
""", timeout=180)
    for line in checks.splitlines():
        if line.startswith(('Content screening:', 'Private media storage:')):
            print(line)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit(
            "An installer step failed; raw output was withheld to protect secrets. Share this message."
        ) from None
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from None
