"""Install app-building model discovery and recommended coding-model defaults.

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

PAYLOAD = "H4sIAAAAAAACA3VWbW/bNhD+KzejgKhWVpw06wcP7uAm2RpsbYMh2xfLMxiJjtjSpEZSSdwk/313pOSXJLVhWBSP9/Lc3cO7H6xM1SoxGMOgCN9T6UpzIyzwphletVJVUl8DSgnlYGnNCnwtQNxJ52nDLJeylFzBl0bo6TmURmtReml0HvUVutBy1RjroeauVvJqs7Zi8+jlSuxKet/c0XpxMj35eAYTuH/Exacvp2d/4sKKvDSrRirBbDH497rxQ1YU1Rv267gocnpKX6e4GOKvRM/vHlYcf1LLB821eUCJ++PHIf0d9X9p+vpVMUjJaKErsQQnFAayiJEzWbl0XGjAT4zrwoololS21grtMe6AE1eSO+F+AS0IQ6lvaJNrOD8FQ+tStZUA1wgCza9B6KoxUnu3gYtMlFxXsuJeOApd85WAJR4PD1IDOgNyCdJJ7TzXpWC0k4HzNkVjFbCohj4RtHzZKrXivqyDaAo72u6LQQBpSAANFVn1xSDDOAnYY7P7HGSKwWPUnz4SWPREgDVWGiv9OloYb10IdjGQl13ZyiFiDgsHJX3bYG4RFqbTGDk5Gg7NDue5a5T0LMmTNCUcon7MkgB2nMEovCTdOaJjvbuVvmZJDCBJO8FR9qJl1j++IRHUlc7Gb+dbSbfiSqHcEdlIqJoSci1gGRQfhg2C6cnGaEeJ5o2rjUc9V8YohvXsBLeICJbz8KXqfEVJCHDteG2Fb60GloT0JaBRY2cy6yAc6i18XWRpFoPIIBliWyTbI71bnaU+t50Zh40pKrYtzQy+ifWkzzrhNJrH9uFurctQE133OOGJLTYtFHgkD+xCXRKb/gMtz6w1treM+hGi/nBukGK4XPBGLnAnilCmMWySxDifil5hMy5aq3KLrSEblhxg/n+aQEIE48YHB6irkyVGObg5TMbP8J3N+6Ysa7GIPnVUlruaH/38juHLXGhKA0vTvBZ3lbzGLmLpzsmKOiDQWX4tPNtoSzeBdGLUwPFxNprD+8CN+cpgmEbLkqXPPVRIxqw7cjjvFHq73pGMKaFOiOSaT+nFiZLIT4wsmNZPjrDil0Ypc7uwopIW+c9NfuNYvUgrDsogvaM0uuAao7G+J8BvufSdVIhxX5I+Pwb+IJZKkkEtOFaFm9wn09bXWFzfOd0nyRiSD9glWDAJdici97ivP33ZsdxyiVWAbbBAOvCtY08EsZh5uFQ6+a/OaJbOEnqfzPdlu3LbYV6SykIG0vHzeINt+IerVoTKZsm5vsFLooqdEc4lT/whdp88uX5m0otVwDSRVRI5kV5R8wb/968D2sqgkqVP+3IQd6VoPLCY/Y+XlxfBoWzHuQz+EOvu6XLdxJd75Rai2fYpS6bPhgS0GgeINSw53tBVDie1KL/1A8L04hx4WQrnQqFfSaXwbE4xESl8NlpsGkIJzWLLpPB+AofvdnzpWqkxDdPizlPIthfuSTIuZ5tWmxPBP20nrKW3o1FPmHTPp3u8h2+2Q0FAWCmGw9GEXN0ntJ7JcHfRkdvCI8EjVXbLntm6Zd7NVZOOKOPmdYsEi2kkb7cBJ0Whn8M9hjKgG94iNTb9qEbgtpgtmtaWEvmvi0f0pRfuBXFLzjriTn6NbevQzNZiqxXliVSgKhx2amNwugGOSV7i9EOzDVVwrzOHy1qgTWzS7YS4k/foWhZaiJNxtd6z57HAyMHTmuvvvcpPm0YhbZVB+3QeK0wu1/Bfa7D6ifrbUFQ4XAAGImzgjBwurLmRVfCdW+TkPXsYOnrgzd6Jv0TMYelbHGu/miuItBEQjWNdqbjEORgZPiBXiUaZ9YrQIIJFJiUyaRUOdZ21Lcdvcttd1s9KJf/97/PT6eeTs13y/qEQvJlsVBZ68Pg/jk+oX9ALAAA="  # noqa: E501 - frozen app-building model catalog
MODULES = ("bootstrap.py", "app_building_models.py", "app_builder_tools.py")
MARKER = "_DHANZ_APP_MODELS_VERSION = 1"


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_bootstrap(current):
    if MARKER in current:
        if current.count("    _install_app_building_models(app)") != 1:
            raise ValueError("Unknown App-building model startup hook. Nothing changed.")
        return current
    anchor = "    app.include_router(router, prefix=app.state.settings.api_prefix)"
    if current.count(anchor) != 1:
        raise ValueError(
            "The existing builder startup hook is required; nothing was changed. "
            "Nothing changed; share this message."
        )
    updated = (
        current.replace(
            anchor,
            anchor
            + "\n    from .app_building_models import install as _install_app_building_models"
            + "\n    _install_app_building_models(app)",
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


def patch_tools(current):
    old = (
        'model = args.get("model") or next(\n'
        '                            (name for name in ("gpt-4.1-mini", "gpt-4.1") if name in names), '
        'names[0] if names else ""\n                        )'
    )
    new = 'model = args.get("model") or (names[0] if names else "")'
    if current.count(new) == 1:
        return current
    if current.count(old) != 1:
        raise ValueError("The installed builder default was customized. Nothing changed.")
    updated = current.replace(old, new)
    compile(updated, "app_builder_tools.py", "exec")
    return updated


def image_sources(current, tools):
    return {'bootstrap.py': patch_bootstrap(current), 'app_building_models.py': payload()['module'],
            'app_builder_tools.py': patch_tools(tools)}


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
module=path.with_name('app_building_models.py')
result={'path':str(path),'source':base64.b64encode(path.read_bytes()).decode(),
        'tools_source':base64.b64encode(path.with_name('app_builder_tools.py').read_bytes()).decode(),
        'module_sha':hashlib.sha256(module.read_bytes()).hexdigest() if module.exists() else None}
print(json.dumps(result))
""",
        )
    )
    source = payload()["module"]
    expected = hashlib.sha256(source.encode()).hexdigest()
    if packet["module_sha"] not in (None, expected):
        raise ValueError("The App-building model module was customized. Nothing changed.")
    current = base64.b64decode(packet["source"]).decode()
    updated = patch_bootstrap(current)
    tools_source = base64.b64decode(packet["tools_source"]).decode()
    tools_updated = patch_tools(tools_source)
    if tools_updated == tools_source and updated == current and packet["module_sha"] == expected:
        print("App-building model support is already installed. No external action was performed.")
        return
    sources = image_sources(current, tools_source)
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
    work = Path(tempfile.mkdtemp(prefix="dhanz-app-models-", dir=Path.home()))
    os.chmod(work, 0o700)
    for name in MODULES:
        (work / name).write_text(sources[name])
    stamp = str(time.time_ns())
    before = "dhanz-api:before-app-models-" + stamp
    image = "dhanz-api:app-models-" + stamp
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
    from app.assistant_studio import app_building_models, builder
    application=create_app(Settings(app_env='test',_env_file=None))
    assert builder.models is app_building_models.models
    assert app_building_models.select_models(['gpt-4.1-mini','gpt-5.1-codex','gpt-image-1'])[0]=='gpt-5.1-codex'
    print('App-building model startup checks passed. No model generation or provider call was started.')
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
        "App-building model support installed. API healthy; existing connections, permissions "
        "and saved skills preserved."
    )
    print(
        "Apps and agents use the recommended available OpenAI coding model by default. "
        "Your existing key is preserved. No generation was started; API usage charges apply when you build."
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
