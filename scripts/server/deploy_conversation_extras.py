#!/usr/bin/env python3
"""Install branch, archive and share-link support into the running DHANZ API.

Run on the server from the repository checkout, as the normal user:

    python3 scripts/server/deploy_conversation_extras.py            # check only, changes nothing
    python3 scripts/server/deploy_conversation_extras.py --apply    # build, test, switch (keeps a rollback image)
    python3 scripts/server/deploy_conversation_extras.py --rollback dhanz-api:rollback-YYYYmmdd-HHMMSS

The live API image has patched core files, so this adds a self-contained package
(backend/app/conversation_extras) and two one-line, append-only hooks:
  - main.py: the package's install(app) call, just before create_app() returns
  - models/__init__.py: an import of the package's two models
What --apply does:
1. Checks the hooks can be placed (exactly one create_app with a final `return app`).
2. Builds a new image FROM the running one with the package and the two hooks.
3. Tests the new image with the running API's own settings: the app builds and has the new routes.
4. Creates the two new tables (conversation_archives, shared_conversations) if missing.
   Only new tables are added; existing tables are not changed. Their foreign keys delete
   archive marks and share links together with the chat or the account.
5. Keeps the running image as a rollback image, switches only the API and checks /health.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_ai_engine as base  # noqa: E402  - shared container, compose and health helpers

ROOT = base.ROOT
PACKAGE = ROOT / "backend/app/conversation_extras"
MAIN_HOOK = (
    "    from app.conversation_extras import install as _install_conversation_extras  # DHANZ conversation extras\n"
    "    _install_conversation_extras(app)\n"
)
MODELS_HOOK = (
    "\n# DHANZ conversation extras (branch, archive, share)\n"
    "from app.conversation_extras.models import ConversationArchive, SharedConversation  # noqa: E402,F401\n"
)

SMOKE_TEST = r"""
from app.main import create_app
app = create_app()
paths = set(app.openapi()["paths"])  # every route, however it was included
needed = {"/api/v1/conversation-extras/archived", "/api/v1/conversation-extras/{conversation_id}/branch",
          "/api/v1/conversation-extras/{conversation_id}/share", "/api/v1/shared/{token}"}
missing = needed - paths
assert not missing, missing
print("SMOKE TEST OK: routes present")
"""

CREATE_TABLES = r"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
import app.models  # registers users and conversations, which the new tables point to
from app.conversation_extras.models import ConversationArchive, SharedConversation
from app.db.base import Base
async def main():
    engine = create_async_engine(get_settings().database_url)
    tables = [ConversationArchive.__table__, SharedConversation.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables, checkfirst=True))
    await engine.dispose()
    print("TABLES OK")
asyncio.run(main())
"""


def live_file(container: str, path: str) -> str:
    return base.output(base.docker("exec", container, "cat", path))


def app_dir(container: str) -> str:
    code = "import app, os; print(os.path.dirname(app.__file__))"
    return base.output(base.docker("exec", container, "python", "-c", code)).strip()


def hook_main(source: str) -> str:
    """Insert the install call before create_app()'s final `return app` (indented 4 spaces)."""
    if "_install_conversation_extras" in source:
        return source
    start = source.find("def create_app(")
    if start < 0:
        raise SystemExit("main.py has no create_app(). Nothing was changed; share this output.")
    after_def = source.index("\n", start) + 1
    # The function ends at the next line that starts in column 0 (a new top-level statement).
    following = re.search(r"^[A-Za-z_@]", source[after_def:], flags=re.MULTILINE)
    end = after_def + following.start() if following else len(source)
    body = source[start:end]
    returns = [m.start() for m in re.finditer(r"^    return app\s*$", body, flags=re.MULTILINE)]
    if not returns:
        raise SystemExit("create_app() has no final `return app`. Nothing was changed; share this output.")
    at = start + returns[-1]
    return source[:at] + MAIN_HOOK + source[at:]


def hook_models(source: str) -> str:
    return source if "app.conversation_extras.models" in source else source.rstrip("\n") + "\n" + MODELS_HOOK


def package_current(container: str, target: str) -> bool:
    for path in PACKAGE.glob("*.py"):
        live = subprocess.run(  # noqa: S603 - fixed argv
            base.docker("exec", container, "cat", f"{target}/{path.name}"), capture_output=True, check=False
        )
        if live.returncode != 0 or base.normalized(live.stdout) != base.normalized(path.read_bytes()):
            return False
    return True


def container_network(name: str) -> str:
    return base.output(
        base.docker("inspect", name, "--format", "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}")
    ).split()[0]


def run_in_image(image: str, api: dict, script: str, network: str | None = None) -> None:
    with tempfile.NamedTemporaryFile("w", prefix="dhanz-api-env-", suffix=".list") as env_file:
        Path(env_file.name).chmod(0o600)
        env_file.write("\n".join(api["env"]) + "\n")
        env_file.flush()
        argv = ["run", "--rm", "--env-file", env_file.name]
        if network:
            argv += ["--network", network]
        base.run(base.docker(*argv, "--entrypoint", "python", image, "-c", script))


def apply(api: dict, appdir: str, main_src: str, models_src: str) -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    new_tag, rollback_tag = f"dhanz-api:extras-{stamp}", f"dhanz-api:rollback-{stamp}"
    base.run(base.docker("tag", api["image_id"], rollback_tag))
    with tempfile.TemporaryDirectory(prefix="dhanz-extras-") as folder:
        work = Path(folder)
        (work / "pkg").mkdir()
        for path in PACKAGE.glob("*.py"):
            (work / "pkg" / path.name).write_bytes(path.read_bytes())
        (work / "main.py").write_text(hook_main(main_src))
        (work / "models__init__.py").write_text(hook_models(models_src))
        (work / "Dockerfile").write_text(
            f"FROM {rollback_tag}\n"
            f"COPY pkg/ {appdir}/conversation_extras/\n"
            f"COPY main.py {appdir}/main.py\n"
            f"COPY models__init__.py {appdir}/models/__init__.py\n"
        )
        print("Building", new_tag, "from the running image (package plus two one-line hooks).", flush=True)
        base.run(base.docker("build", "-q", "-t", new_tag, folder))
    print("Testing the new image with the running API's own settings.", flush=True)
    run_in_image(new_tag, api, SMOKE_TEST)
    print("Creating the two new tables if they are missing (existing tables are not changed).", flush=True)
    run_in_image(new_tag, api, CREATE_TABLES, network=container_network(api["name"]))
    base.run(base.docker("tag", new_tag, api["image_name"]))
    print("Switching the API to the new image.", flush=True)
    base.compose(api, "up", "-d", "--no-deps", "--force-recreate", "api")
    rollback = f"python3 {Path(__file__).relative_to(ROOT)} --rollback {rollback_tag}"
    if not base.healthy(api["name"]):
        print("The API did not report healthy. Roll back with:\n  " + rollback)
        return 1
    print("Done. Branch, archive and share links are available. Rollback if needed:\n  " + rollback)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="build, test and switch to the new image")
    parser.add_argument("--rollback", metavar="TAG", help="switch back to a rollback image printed by --apply")
    args = parser.parse_args(argv)
    api = base.api_container()
    if args.rollback:
        base.run(base.docker("tag", args.rollback, api["image_name"]))
        base.compose(api, "up", "-d", "--no-deps", "--force-recreate", "api")
        print("Rolled back to", args.rollback, "- healthy" if base.healthy(api["name"]) else "- check the API logs")
        return 0
    appdir = app_dir(api["name"])
    main_src = live_file(api["name"], f"{appdir}/main.py")
    models_src = live_file(api["name"], f"{appdir}/models/__init__.py")
    installed = "_install_conversation_extras" in main_src and "app.conversation_extras.models" in models_src
    print(f"API container {api['name']} ({api['image_name']}), backend at {appdir}")
    if installed and package_current(api["name"], f"{appdir}/conversation_extras"):
        print("Branch, archive and share links are already installed. Nothing to do.")
        return 0
    hook_main(main_src)  # raises with a clear message when the hook cannot be placed
    print("  main.py: install hook can be placed before create_app()'s final `return app`")
    print("  models/__init__.py: model import will be appended")
    print("  new tables: conversation_archives, shared_conversations (created only if missing)")
    if not args.apply:
        print("Check passed. Run again with --apply to build, test and switch (a rollback image is kept).")
        return 0
    return apply(api, appdir, main_src, models_src)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Step failed ({' '.join(exc.cmd[:4])} ...). The running API was not switched unless stated above.")
