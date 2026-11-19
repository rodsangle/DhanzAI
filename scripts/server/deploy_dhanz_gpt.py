#!/usr/bin/env python3
"""Install or update Dhanz GPT (apps/dhanz_gpt) on the DHANZ AI server, at gpt.<your domain>.

Run on the server from the repository checkout, as the normal user (it uses sudo for docker like the
other server scripts):
    python3 scripts/server/deploy_dhanz_gpt.py             # check only, changes nothing
    python3 scripts/server/deploy_dhanz_gpt.py --apply     # build, migrate, start, add the Caddy site
    python3 scripts/server/deploy_dhanz_gpt.py --rollback dhanz-gpt:YYYYmmdd-HHMMSS
    python3 scripts/server/deploy_dhanz_gpt.py --uninstall # stop it, remove the Caddy site; keeps its data

Dhanz GPT is a separate Next.js app. It does not change the DHANZ API, its database or the dhanzai.com site:
  - its own container `dhanz-gpt` on the API's Docker network (it calls the API at http://api:8000/api/v1
    to sign people in with their DHANZ AI accounts, including two-step verification);
  - its own database `dhanz_gpt` (and login role) in the same PostgreSQL server;
  - its own volume `dhanz-gpt-data` for uploaded files;
  - a `dhanz-gpt-backup` container: nightly database dump and weekly files archive into the API's ./backups;
  - one extra site block in the Caddyfile for gpt.<domain> (Caddy gets its certificate once DNS points here).
Secrets it generates (database password, token encryption key) are kept in ~/.config/dhanz-gpt/dhanz-gpt.env
(mode 600). The AI provider keys are copied from the running API's settings at each --apply; none are printed.

What --apply does:
1. Checks the API, database and Caddy containers, the Caddyfile mount and the domain.
2. Builds the image from apps/dhanz_gpt (or uses --image), tagged with the time, and keeps the running one
   as the rollback image.
3. Creates the database role and database if missing (existing ones are not changed), then runs the app's
   own migrations and sets sign-up to "one workspace per account".
4. Starts the new container, checks /api/health (database reachable, DHANZ sign-in mode); if it fails the
   previous container comes back.
5. Adds the Caddy site block (backup kept), validates it, reloads Caddy; restores the backup if Caddy refuses.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_ai_engine as base  # noqa: E402  - shared docker, run and output helpers

ROOT = base.ROOT
APP_DIR = ROOT / "apps/dhanz_gpt"
CONTAINER = "dhanz-gpt"
BACKUP_CONTAINER = "dhanz-gpt-backup"
VOLUME = "dhanz-gpt-data"
IMAGE = "dhanz-gpt"
DB_NAME = "dhanz_gpt"
DB_ROLE = "dhanz_gpt"
SECRETS = Path.home() / ".config/dhanz-gpt/dhanz-gpt.env"
CADDY_PATH = "/etc/caddy/Caddyfile"
BEGIN = "# >>> dhanz-gpt (managed by scripts/server/deploy_dhanz_gpt.py)"
END = "# <<< dhanz-gpt"
# Copied from the API's settings so Dhanz GPT answers, draws and transcribes with the same accounts.
PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


# --- pure helpers (unit-tested) -------------------------------------------------------------------------


def site_block(host: str, upstream: str = f"{CONTAINER}:3000") -> str:
    return (
        f"{BEGIN}\n"
        f"{host} {{\n"
        "\tencode zstd gzip\n"
        f"\treverse_proxy {upstream} {{\n"
        "\t\t# Streaming replies must reach the browser as they are written.\n"
        "\t\tflush_interval -1\n"
        "\t\ttransport http {\n"
        "\t\t\tread_timeout 10m\n"
        "\t\t}\n"
        "\t}\n"
        "\theader {\n"
        "\t\t-Server\n"
        "\t}\n"
        "}\n"
        f"{END}\n"
    )


def with_block(caddyfile: str, host: str) -> str:
    """The Caddyfile with exactly one current Dhanz GPT block (replacing an older one)."""
    return without_block(caddyfile).rstrip("\n") + "\n\n" + site_block(host)


def without_block(caddyfile: str) -> str:
    if BEGIN not in caddyfile:
        return caddyfile
    head, rest = caddyfile.split(BEGIN, 1)
    if END not in rest:
        raise SystemExit("The Caddyfile has the Dhanz GPT start marker but not the end marker. Fix it by hand.")
    tail = rest.split(END, 1)[1]
    return (head.rstrip("\n") + "\n" + tail.lstrip("\n")).rstrip("\n") + "\n"


def bootstrap_sql(password: str) -> str:
    """Roles and login for the app. Idempotent; never changes an existing database or its data."""
    if not password.replace("-", "").replace("_", "").isalnum():
        raise ValueError("password must be URL-safe")
    # Only constants and the URL-safe password checked above go into this text.
    return f"""
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = '{DB_ROLE}') then
    create role {DB_ROLE} login password '{password}';
  else
    alter role {DB_ROLE} login password '{password}';
  end if;
end $$;
grant anon, authenticated, service_role to {DB_ROLE};
"""  # noqa: S608 - constants and a validated URL-safe password only


# Created by the server's admin role inside the app's database: `vector` isn't a trusted extension,
# so the app's own login role can't create it during its migrations.
EXTENSIONS_SQL = "\n".join(f"create extension if not exists {e};" for e in ("pgcrypto", "pg_trgm", "vector")) + "\n"


def env_lines(secret: dict[str, str], api_env: list[str], domain: str) -> list[str]:
    api = {}
    for item in api_env:
        key, _, value = item.partition("=")
        api[key.upper()] = value
    lines = [
        "NODE_ENV=production",
        "AUTH_MODE=dhanz",
        "DHANZ_API_URL=http://api:8000/api/v1",
        f"DATABASE_URL=postgres://{DB_ROLE}:{secret['DHANZ_GPT_DB_PASSWORD']}@db:5432/{DB_NAME}",
        f"APP_TOKEN_KEY={secret['APP_TOKEN_KEY']}",
        f"APP_URL=https://gpt.{domain}",
        "STORAGE_DRIVER=local",
        # Nothing calls /api/cron/* on our own server, so the app runs its schedule itself.
        "SELF_CRON=1",
        f"CRON_SECRET={secret['CRON_SECRET']}",
    ]
    lines += [f"{k}={api[k]}" for k in PROVIDER_KEYS if api.get(k)]
    if api.get("CREATIVE_IMAGE_MODEL"):
        lines.append(f"IMAGE_MODEL={api['CREATIVE_IMAGE_MODEL']}")  # the image model the API already uses
    return lines


def new_secrets() -> dict[str, str]:
    return {
        "DHANZ_GPT_DB_PASSWORD": secrets.token_urlsafe(32),
        "APP_TOKEN_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "CRON_SECRET": secrets.token_urlsafe(32),
    }


# --- server inspection --------------------------------------------------------------------------------


def service(name: str) -> dict | None:
    ids = base.output(base.docker("ps", "--filter", f"label=com.docker.compose.service={name}", "-q")).split()
    if len(ids) != 1:
        return None
    return json.loads(base.output(base.docker("inspect", ids[0])))[0]


def env_of(info: dict) -> dict[str, str]:
    out = {}
    for item in info["Config"]["Env"] or []:
        key, _, value = item.partition("=")
        out[key] = value
    return out


def network_of(info: dict) -> str:
    return next(iter(info["NetworkSettings"]["Networks"]))


def caddyfile_source(caddy: dict) -> Path | None:
    for m in caddy.get("Mounts", []):
        if m.get("Destination") == CADDY_PATH and m.get("Type") == "bind":
            return Path(m["Source"])
    return None


def backups_dir() -> Path | None:
    info = service("backup")
    for m in (info or {}).get("Mounts", []):
        if m.get("Destination") == "/backups":
            return Path(m["Source"])
    return None


def resolve(host: str) -> set[str]:
    try:
        return {a[4][0] for a in socket.getaddrinfo(host, 443)}
    except socket.gaierror:
        return set()


def container_image(name: str) -> str | None:
    probe = subprocess.run(  # noqa: S603 - fixed argv
        base.docker("inspect", name, "--format", "{{.Config.Image}}"), capture_output=True, text=True, check=False
    )
    if probe.returncode != 0:
        return None
    return probe.stdout.strip() or None


def load_secrets() -> dict[str, str]:
    if SECRETS.exists():
        out = {}
        for line in SECRETS.read_text().splitlines():
            key, _, value = line.partition("=")
            if key:
                out[key] = value
        return out
    return {}


def save_secrets(values: dict[str, str]) -> None:
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.parent.chmod(0o700)
    SECRETS.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    SECRETS.chmod(0o600)


class EnvFile:
    """A temporary env file (mode 600) for docker --env-file, deleted afterwards."""

    def __init__(self, lines: list[str]):
        self.lines = lines

    def __enter__(self) -> str:
        fd, self.path = tempfile.mkstemp(prefix="dhanz-gpt-env-", suffix=".list")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(self.lines) + "\n")
        return self.path

    def __exit__(self, *exc) -> None:
        Path(self.path).unlink(missing_ok=True)


def gather(args) -> dict:
    api, db, caddy = service("api"), service("db"), service("caddy")
    missing = [n for n, v in (("api", api), ("db", db), ("caddy", caddy)) if v is None]
    if missing:
        raise SystemExit(f"Expected one running container for: {', '.join(missing)}. Nothing was changed.")
    domain = args.domain or env_of(caddy).get("DHANZ_DOMAIN") or env_of(api).get("DHANZ_DOMAIN")
    if not domain:
        raise SystemExit(
            "Couldn't find the site's domain (DHANZ_DOMAIN). Pass --domain dhanzai.com. Nothing was changed."
        )
    return {
        "api": api,
        "db": db,
        "caddy": caddy,
        "domain": domain,
        "host": f"gpt.{domain}",
        "network": network_of(api),
        "caddyfile": caddyfile_source(caddy),
        "backups": backups_dir(),
    }


def report(s: dict) -> None:
    api_env = {k.upper() for k in env_of(s["api"])}
    keys = [k for k in PROVIDER_KEYS if k in api_env]
    site, gpt = resolve(s["domain"]), resolve(s["host"])
    print(f"API container:       {s['api']['Name'].lstrip('/')} on network {s['network']}")
    print(f"Database container:  {s['db']['Name'].lstrip('/')} (Dhanz GPT gets its own database '{DB_NAME}')")
    print(f"Caddyfile:           {s['caddyfile'] or 'NOT a bind mount: the site block must be added by hand'}")
    print(f"Backups folder:      {s['backups'] or 'not found (no backup container will be added)'}")
    print(f"Site:                https://{s['host']}")
    gpt_ips, site_ips = ", ".join(sorted(gpt)) or "not set yet", ", ".join(sorted(site)) or "?"
    print(f"DNS for {s['host']}: {gpt_ips} (main site: {site_ips})")
    if not gpt or (site and not gpt & site):
        print(f"  -> Add a DNS record: {s['host']} pointing at this server, like {s['domain']}.")
        print("     HTTPS starts by itself once it resolves here.")
    print(f"Provider keys found: {', '.join(keys) or 'none (answers would use the built-in demo model)'}")
    running = container_image(CONTAINER)
    print(f"Running now:         {running or 'not installed'}")
    print(f"Secrets file:        {SECRETS} ({'exists' if SECRETS.exists() else 'will be created'})")


# --- the steps ------------------------------------------------------------------------------------------


def psql(db: dict, sql: str, database: str = "postgres") -> str:
    env = env_of(db)
    user = env.get("POSTGRES_USER", "postgres")
    return base.run(
        base.docker(
            "exec", "-i", db["Name"].lstrip("/"), "psql", "-v", "ON_ERROR_STOP=1", "-qAt", "-U", user, "-d", database
        ),
        input=sql,
        capture_output=True,
    ).stdout


def ensure_database(db: dict, password: str) -> None:
    psql(db, bootstrap_sql(password))
    exists = psql(db, f"select 1 from pg_database where datname = '{DB_NAME}';").strip()  # noqa: S608 - constant
    if not exists:
        psql(db, f"create database {DB_NAME} owner {DB_ROLE};")
        print(f"Created database {DB_NAME}.")
    psql(db, EXTENSIONS_SQL, database=DB_NAME)
    psql(db, f"revoke connect on database {DB_NAME} from public;")


def health(name: str) -> dict | None:
    probe = "fetch('http://127.0.0.1:3000/api/health').then(r=>r.json()).then(j=>console.log(JSON.stringify(j))).catch(()=>console.log('{}'))"
    for _ in range(45):
        out = subprocess.run(  # noqa: S603 - fixed argv
            base.docker("exec", name, "node", "-e", probe), capture_output=True, text=True, check=False
        ).stdout.strip()
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            data = {}
        if data.get("ok"):
            return data
        time.sleep(2)
    return None


def start(image: str, s: dict, env_path: str) -> None:
    base.run(
        base.docker(
            "run",
            "-d",
            "--name",
            CONTAINER,
            "--network",
            s["network"],
            "--restart",
            "unless-stopped",
            "--env-file",
            env_path,
            "-v",
            f"{VOLUME}:/app/.data",
            "--label",
            "dhanz.app=dhanz-gpt",
            image,
        ),
        capture_output=True,
    )


def switch(image: str, s: dict, lines: list[str]) -> bool:
    previous = container_image(CONTAINER)
    with EnvFile(lines) as path:
        if previous:
            base.run(base.docker("rm", "-f", CONTAINER), capture_output=True)
        start(image, s, path)
        ok = health(CONTAINER)
        if ok and ok.get("auth") == "dhanz":
            print(f"Dhanz GPT is running ({image}, {ok.get('migrations')} migrations).")
            return True
        print("The new container didn't pass its health check.", file=sys.stderr)
        subprocess.run(base.docker("logs", "--tail", "40", CONTAINER), check=False)  # noqa: S603
        base.run(base.docker("rm", "-f", CONTAINER), capture_output=True)
        if previous:
            start(previous, s, path)
            print(f"Put back the previous container ({previous}).", file=sys.stderr)
        return False


def install_caddy(s: dict) -> bool:
    src = s["caddyfile"]
    if src is None:
        print("\nCaddy's file isn't mounted from the host. Add this block to the Caddyfile yourself:\n")
        print(site_block(s["host"]))
        return False
    caddy = s["caddy"]["Name"].lstrip("/")
    current = base.output(base.docker("exec", caddy, "cat", CADDY_PATH))
    wanted = with_block(current, s["host"])
    if wanted == current:
        print("Caddy site block already in place.")
        return True
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = f"{src}.bak-{stamp}"
    base.run(["sudo", "cp", "-p", str(src), backup] if os.geteuid() else ["cp", "-p", str(src), backup])
    # Write through the bind mount in place (same inode, so the container sees it).
    base.run(base.docker("exec", "-i", caddy, "sh", "-c", f"cat > {CADDY_PATH}"), input=wanted)
    check = subprocess.run(  # noqa: S603 - fixed argv
        base.docker("exec", caddy, "caddy", "validate", "--config", CADDY_PATH, "--adapter", "caddyfile"),
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        base.run(base.docker("exec", "-i", caddy, "sh", "-c", f"cat > {CADDY_PATH}"), input=current)
        print(f"Caddy refused the new block, so the old Caddyfile is back:\n{check.stderr[-800:]}", file=sys.stderr)
        return False
    base.run(base.docker("exec", caddy, "caddy", "reload", "--config", CADDY_PATH, "--adapter", "caddyfile"))
    print(f"Caddy now serves https://{s['host']} (backup: {backup}).")
    return True


def install_backup(s: dict, password: str) -> None:
    if s["backups"] is None:
        print("No backups folder found; skipping the Dhanz GPT backup container.")
        return
    if container_image(BACKUP_CONTAINER):
        base.run(base.docker("rm", "-f", BACKUP_CONTAINER), capture_output=True)
    loop = (
        "while true; do "
        "pg_dump -Fc -f /backups/dhanz-gpt-$(date +%Y%m%d-%H%M).dump && echo 'database backup done'; "
        "find /backups -name 'dhanz-gpt-*.dump' -mtime +14 -delete; "
        "if [ $(date +%u) = 7 ]; then tar -czf /backups/dhanz-gpt-files-$(date +%Y%m%d).tgz -C /data . && "
        "ls -1t /backups/dhanz-gpt-files-*.tgz | tail -n +5 | xargs -r rm -f; fi; "
        "sleep 86400; done"
    )
    with EnvFile([f"PGPASSWORD={password}", "PGHOST=db", f"PGUSER={DB_ROLE}", f"PGDATABASE={DB_NAME}"]) as path:
        base.run(
            base.docker(
                "run",
                "-d",
                "--name",
                BACKUP_CONTAINER,
                "--network",
                s["network"],
                "--restart",
                "unless-stopped",
                "--env-file",
                path,
                "-v",
                f"{s['backups']}:/backups",
                "-v",
                f"{VOLUME}:/data:ro",
                "--entrypoint",
                "/bin/sh",
                s["db"]["Config"]["Image"],
                "-c",
                loop,
            ),
            capture_output=True,
        )
    print(f"Nightly backups of Dhanz GPT go to {s['backups']} (database daily, files weekly).")


def apply(s: dict, args) -> int:
    secret = load_secrets()
    if not all(secret.get(k) for k in ("DHANZ_GPT_DB_PASSWORD", "APP_TOKEN_KEY", "CRON_SECRET")):
        secret = {**new_secrets(), **{k: v for k, v in secret.items() if v}}
        save_secrets(secret)
        print(f"Saved new secrets to {SECRETS}.")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    image = args.image
    if not image:
        if not (APP_DIR / "Dockerfile").exists():
            raise SystemExit(f"{APP_DIR}/Dockerfile not found: run this from the repository checkout.")
        image = f"{IMAGE}:{stamp}"
        print(f"Building {image} (a few minutes)...")
        base.run(base.docker("build", "-t", image, "-t", f"{IMAGE}:latest", str(APP_DIR)))

    previous = container_image(CONTAINER)
    ensure_database(s["db"], secret["DHANZ_GPT_DB_PASSWORD"])
    lines = env_lines(secret, s["api"]["Config"]["Env"] or [], s["domain"])
    with EnvFile(lines) as path:
        for step in (["platform"], ["migrate"], ["signup-mode", "personal"]):
            base.run(
                base.docker(
                    "run",
                    "--rm",
                    "--network",
                    s["network"],
                    "--env-file",
                    path,
                    "--entrypoint",
                    "node",
                    image,
                    "scripts/db.mjs",
                    *step,
                )
            )
    if not switch(image, s, lines):
        return 1
    install_backup(s, secret["DHANZ_GPT_DB_PASSWORD"])
    caddy_ok = install_caddy(s)
    if previous and previous != image:
        print(f"\nTo go back: python3 scripts/server/deploy_dhanz_gpt.py --rollback {previous}")
    print("Images on this server: sudo docker images dhanz-gpt")
    return 0 if caddy_ok else 2


def rollback(s: dict, image: str) -> int:
    secret = load_secrets()
    if not secret:
        raise SystemExit(f"{SECRETS} is missing; nothing to roll back to.")
    return 0 if switch(image, s, env_lines(secret, s["api"]["Config"]["Env"] or [], s["domain"])) else 1


def uninstall(s: dict) -> int:
    for name in (CONTAINER, BACKUP_CONTAINER):
        if container_image(name):
            base.run(base.docker("rm", "-f", name), capture_output=True)
            print(f"Removed container {name}.")
    if s["caddyfile"] is not None:
        caddy = s["caddy"]["Name"].lstrip("/")
        current = base.output(base.docker("exec", caddy, "cat", CADDY_PATH))
        if BEGIN in current:
            base.run(base.docker("exec", "-i", caddy, "sh", "-c", f"cat > {CADDY_PATH}"), input=without_block(current))
            base.run(base.docker("exec", caddy, "caddy", "reload", "--config", CADDY_PATH, "--adapter", "caddyfile"))
            print("Removed the Caddy site block.")
    print(f"Kept: database {DB_NAME}, volume {VOLUME}, {SECRETS}, backups. Delete them by hand if you mean to.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="install or update")
    g.add_argument("--rollback", metavar="IMAGE", help="switch back to an earlier dhanz-gpt image tag")
    g.add_argument("--uninstall", action="store_true", help="stop Dhanz GPT and remove its Caddy site (keeps data)")
    p.add_argument("--image", help="use this image instead of building apps/dhanz_gpt")
    p.add_argument("--domain", help="the main site's domain if it can't be detected (e.g. dhanzai.com)")
    args = p.parse_args(argv)
    s = gather(args)
    report(s)
    if args.rollback:
        return rollback(s, args.rollback)
    if args.uninstall:
        return uninstall(s)
    if not args.apply:
        print("\nCheck only. Run again with --apply to install.")
        return 0
    return apply(s, args)


if __name__ == "__main__":
    raise SystemExit(main())
