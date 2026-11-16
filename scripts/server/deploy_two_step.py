#!/usr/bin/env python3
"""Install two-step verification (authenticator app, recovery codes, remember this device) into the
running DHANZ API, for servers that predate the built-in one.

Run on the server from the repository checkout, as the normal user:

    python3 scripts/server/deploy_two_step.py            # check only, changes nothing
    python3 scripts/server/deploy_two_step.py --apply    # build, test, switch (keeps a rollback image)
    python3 scripts/server/deploy_two_step.py --rollback dhanz-api:rollback-YYYYmmdd-HHMMSS

The live API has its own database history and patched core files, so this adds a self-contained
package (server_extensions/two_step -> app/two_step) with its own tables, and two small hooks:
  - main.py: the package's install(app) call, just before create_app() returns;
  - api/routes/auth.py: in login(), right before session tokens are issued, a check that returns
    "enter your code" for accounts with two-step verification on.
The `users` table and the database's migration history are not changed.
What --apply does:
1. Checks both hooks can be placed exactly (one create_app with a final `return app`; one login()
   that issues tokens once with `db`, `settings`, `request` and `user` in scope).
2. Builds a new image FROM the running one with the package and the hooks.
3. Tests the new image with the running API's own settings: the app builds, the new routes exist,
   the login hook is in place, and the server's own key encrypts and decrypts a secret.
4. Creates the three new tables if missing (existing tables are not changed).
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
import deploy_conversation_extras as extras  # noqa: E402  - app_dir, live_file, run_in_image, network

ROOT = base.ROOT
PACKAGE = ROOT / "server_extensions/two_step"
MAIN_MARK = "_install_two_step"
MAIN_HOOK = (
    "    from app.two_step import install as _install_two_step  # DHANZ two-step verification\n"
    "    _install_two_step(app)\n"
)
LOGIN_MARK = "_two_step_login_hook"
LOGIN_HOOK = (
    "    from app.two_step import login_hook as _two_step_login_hook  # DHANZ two-step verification\n"
    "    _two_step = await _two_step_login_hook(db, settings, request, user)\n"
    "    if _two_step is not None:\n"
    "        return _two_step\n"
)
LOGIN_ANCHOR = "    tokens = await issue_tokens("

SMOKE_TEST = r"""
import inspect
from app.main import create_app
from app.core.config import get_settings
from app.api.routes import auth
from app.two_step import core
app = create_app()
paths = set(app.openapi()["paths"])
needed = {"/api/v1/auth/mfa/verify", "/api/v1/users/me/mfa/setup", "/api/v1/users/me/mfa/enable",
          "/api/v1/users/me/mfa/disable", "/api/v1/users/me/trusted-devices"}
missing = needed - paths
assert not missing, missing
assert "_two_step_login_hook" in inspect.getsource(auth.login), "login hook missing"
assert any(m.cls.__name__ == "StatusMiddleware" for m in app.user_middleware), "status middleware missing"
settings = get_settings()
assert core.decrypt_secret(settings, core.encrypt_secret(settings, "JBSWY3DPEHPK3PXP")) == "JBSWY3DPEHPK3PXP"
secret = core.new_secret()
assert core.match_step(secret, core.code_at(secret, core.current_step())) is not None
print("SMOKE TEST OK: routes, login hook, status middleware, secret encryption")
"""

CREATE_TABLES = r"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
import app.models  # registers users, which the new tables point to
from app.db.base import Base
from app.two_step.models import TABLES
async def main():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=list(TABLES), checkfirst=True))
    await engine.dispose()
    print("TABLES OK:", ", ".join(t.name for t in TABLES))
asyncio.run(main())
"""


def _function(source: str, signature: str) -> tuple[int, int]:
    """Start and end offsets of the top-level function whose line starts with `signature`."""
    matches = [m.start() for m in re.finditer(r"^" + re.escape(signature), source, flags=re.MULTILINE)]
    if len(matches) != 1:
        raise SystemExit(
            f"Expected one `{signature}` but found {len(matches)}. Nothing was changed; share this output."
        )
    start = matches[0]
    after_def = source.index("\n", start) + 1
    following = re.search(r"^[A-Za-z_@]", source[after_def:], flags=re.MULTILINE)
    return start, after_def + following.start() if following else len(source)


def hook_main(source: str) -> str:
    """Insert install(app) before create_app()'s final `return app`."""
    if MAIN_MARK in source:
        return source
    start, end = _function(source, "def create_app(")
    returns = [m.start() for m in re.finditer(r"^    return app\s*$", source[start:end], flags=re.MULTILINE)]
    if not returns:
        raise SystemExit("create_app() has no final `return app`. Nothing was changed; share this output.")
    at = start + returns[-1]
    return source[:at] + MAIN_HOOK + source[at:]


def hook_login(source: str) -> str:
    """Insert the two-step check in login() right before it issues session tokens."""
    if LOGIN_MARK in source:
        return source
    start, end = _function(source, "async def login(")
    header = source[start : source.index(":\n", start)]
    for name in ("request", "db", "settings"):
        if not re.search(rf"\b{name}\s*:", header):
            raise SystemExit(f"login() has no `{name}` parameter. Nothing was changed; share this output.")
    body = source[start:end]
    if body.count(LOGIN_ANCHOR) != 1 or "user = await" not in body:
        raise SystemExit(
            "login() does not issue tokens exactly once for `user`. Nothing was changed; share this output."
        )
    at = start + body.index(LOGIN_ANCHOR)
    return source[:at] + LOGIN_HOOK + source[at:]


def package_current(container: str, target: str) -> bool:
    for path in PACKAGE.glob("*.py"):
        live = subprocess.run(  # noqa: S603 - fixed argv
            base.docker("exec", container, "cat", f"{target}/{path.name}"), capture_output=True, check=False
        )
        if live.returncode != 0 or base.normalized(live.stdout) != base.normalized(path.read_bytes()):
            return False
    return True


def apply(api: dict, appdir: str, main_src: str, auth_src: str) -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    new_tag, rollback_tag = f"dhanz-api:two-step-{stamp}", f"dhanz-api:rollback-{stamp}"
    base.run(base.docker("tag", api["image_id"], rollback_tag))
    with tempfile.TemporaryDirectory(prefix="dhanz-two-step-") as folder:
        work = Path(folder)
        (work / "pkg").mkdir()
        for path in PACKAGE.glob("*.py"):
            (work / "pkg" / path.name).write_bytes(path.read_bytes())
        (work / "main.py").write_text(hook_main(main_src))
        (work / "auth.py").write_text(hook_login(auth_src))
        (work / "Dockerfile").write_text(
            f"FROM {rollback_tag}\n"
            f"COPY pkg/ {appdir}/two_step/\n"
            f"COPY main.py {appdir}/main.py\n"
            f"COPY auth.py {appdir}/api/routes/auth.py\n"
        )
        print("Building", new_tag, "from the running image (package plus two small hooks).", flush=True)
        base.run(base.docker("build", "-q", "-t", new_tag, folder))
    print("Testing the new image with the running API's own settings.", flush=True)
    extras.run_in_image(new_tag, api, SMOKE_TEST)
    print("Creating the three new tables if they are missing (existing tables are not changed).", flush=True)
    extras.run_in_image(new_tag, api, CREATE_TABLES, network=extras.container_network(api["name"]))
    base.run(base.docker("tag", new_tag, api["image_name"]))
    print("Switching the API to the new image.", flush=True)
    base.compose(api, "up", "-d", "--no-deps", "--force-recreate", "api")
    rollback = f"python3 {Path(__file__).relative_to(ROOT)} --rollback {rollback_tag}"
    if not base.healthy(api["name"]):
        print("The API did not report healthy. Roll back with:\n  " + rollback)
        return 1
    print("Done. Turn it on in the app: Settings -> Security -> Two-step verification.")
    print("Rollback if needed:\n  " + rollback)
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
    appdir = extras.app_dir(api["name"])
    main_src = extras.live_file(api["name"], f"{appdir}/main.py")
    auth_src = extras.live_file(api["name"], f"{appdir}/api/routes/auth.py")
    print(f"API container {api['name']} ({api['image_name']}), backend at {appdir}")
    if "/mfa/verify" in auth_src and LOGIN_MARK not in auth_src:
        print("This API already has built-in two-step verification. Nothing to do.")
        return 0
    installed = MAIN_MARK in main_src and LOGIN_MARK in auth_src
    if installed and package_current(api["name"], f"{appdir}/two_step"):
        print("Two-step verification is already installed. Nothing to do.")
        return 0
    hook_main(main_src)  # each raises with a clear message when its hook cannot be placed
    hook_login(auth_src)
    env = dict(item.split("=", 1) for item in api["env"] if "=" in item)
    print("  main.py: install hook can be placed before create_app()'s final `return app`")
    print("  api/routes/auth.py: two-step check can be placed in login() before tokens are issued")
    print("  new tables: two_step_settings, two_step_recovery_codes, two_step_devices (created only if missing)")
    if not env.get("DATA_ENCRYPTION_KEY"):
        print(
            "  note: secrets will be encrypted with JWT_SECRET (no DATA_ENCRYPTION_KEY set). Changing JWT_SECRET "
            "later would stop authenticator codes working; set DATA_ENCRYPTION_KEY first to avoid that."
        )
    if not args.apply:
        print("Check passed. Run again with --apply to build, test and switch (a rollback image is kept).")
        return 0
    return apply(api, appdir, main_src, auth_src)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Step failed ({' '.join(exc.cmd[:4])} ...). The running API was not switched unless stated above.")
