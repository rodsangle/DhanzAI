"""Outbound-only Linux companion. Runs owner-defined argv recipes, not model commands."""

import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def origin(value):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
    ):
        raise ValueError("Use an HTTPS origin without a path or credentials.")
    return value.rstrip("/")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect rejected; server credentials were not forwarded.")


def call(config, path, data):
    request = urllib.request.Request(  # noqa: S310 - validated HTTPS origin; redirects disabled
        origin(config["origin"]) + "/api/v1/operations/companion/" + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-Dhanz-Server-Token": config["token"]},
        method="POST",
    )
    with urllib.request.build_opener(NoRedirects()).open(request, timeout=25) as response:
        raw = response.read(128001)
        if len(raw) > 128000:
            raise ValueError("Response exceeded limit.")
        return json.loads(raw)


def recipe_hash(recipe):
    return hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(recipe):
    command = recipe.get("argv")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and "\0" not in x for x in command):
        raise ValueError("Recipe requires a fixed argv list.")
    if not Path(command[0]).is_absolute() or not Path(recipe.get("cwd", "")).is_absolute():
        raise ValueError("Executable and working directory must be absolute.")
    if not 1 <= recipe.get("timeout", 120) <= 1800:
        raise ValueError("Recipe timeout must be 1–1800 seconds.")
    for filename, expected in recipe.get("verified_files", {}).items():
        path = Path(filename)
        if not path.is_absolute() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Approved command file changed. Reapprove it locally before executing.")


def run_job(config, job, journal):
    identifier = str(__import__("uuid").UUID(job["id"]))
    existing = journal.execute("SELECT status FROM receipts WHERE id=?", (identifier,)).fetchone()
    if existing:
        return existing[0] if existing[0] != "executing" else "uncertain"
    recipe = config["tasks"].get(job["task"])
    if not recipe or recipe_hash(recipe) != job["manifest_hash"]:
        return "failed"
    validate(recipe)
    journal.execute("INSERT INTO receipts(id,status) VALUES(?,?)", (identifier, "executing"))
    journal.commit()  # fsync the intent BEFORE launching any command
    try:
        # Output stays on the server. Neither model nor API sees secrets from stdout/stderr.
        result = subprocess.run(  # noqa: S603 - exact locally approved argv, no shell, no remote arguments
            recipe["argv"],
            cwd=recipe["cwd"],
            timeout=recipe.get("timeout", 120),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env={
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "HOME": str(Path.home()),
                "LANG": "C.UTF-8",
            },
        )
        status = "completed" if result.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        status = "uncertain"  # children may have acted; never retry
    except OSError:
        status = "failed"
    journal.execute("UPDATE receipts SET status=? WHERE id=?", (status, identifier))
    journal.commit()
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    if args.config.stat().st_mode & 0o077:
        raise ValueError("Companion configuration must be private (chmod 600).")
    lock = args.config.with_suffix(".lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    journal = sqlite3.connect(str(args.config.with_suffix(".sqlite3")))
    journal.execute("PRAGMA synchronous=FULL")
    journal.execute("CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,status TEXT NOT NULL)")
    journal.commit()
    pending = None
    print("Dhanz server companion running. Only locally defined tasks are available.", flush=True)
    while True:
        try:
            config = json.loads(args.config.read_text())
            for recipe in config["tasks"].values():
                validate(recipe)
            if pending:
                call(config, "jobs/" + pending[0] + "/result", {"status": pending[1]})
                pending = None
            tasks = [
                {"name": name, "description": recipe["description"], "manifest_hash": recipe_hash(recipe)}
                for name, recipe in config["tasks"].items()
            ]
            call(config, "heartbeat", {"tasks": tasks})
            job = call(config, "claim", {}).get("job")
            if job:
                pending = (job["id"], run_job(config, job, journal))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise SystemExit("Server connection revoked. Pair it again to reconnect.") from None
            print("API unavailable; polling/result reporting only will be retried.", flush=True)
        except (urllib.error.URLError, ValueError, OSError):
            print("Connection or recipe unavailable. No command is replayed.", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    os.umask(0o077)
    main()
