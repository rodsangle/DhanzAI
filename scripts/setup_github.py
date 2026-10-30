"""Prepare a local SQLite backend for GitHub connections without printing any secrets.

Run with the backend's Python environment. Remote/production database upgrades remain a
deployment administrator's responsibility; see docs/GITHUB.md.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    from app.core.config import Settings

    os.chdir(backend)
    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise SystemExit("This helper is for local SQLite only. Follow docs/GITHUB.md for a deployed backend.")
    database = Path(url.database).resolve()
    env_path = backend / ".env"
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    key = settings.github_token_encryption_key
    if key:
        try:
            Fernet(key.encode())
        except ValueError:
            raise SystemExit(
                "Existing encryption key is invalid. No changes made; recover it before continuing."
            ) from None
    else:
        key = Fernet.generate_key().decode()

    if database.exists():
        backups = root / ".tools" / "github-setup-backups"
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f"backend-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.db"
        with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        print(f"Database backup saved: {backup}")
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    cfg.attributes["database_url"] = settings.database_url
    command.upgrade(cfg, "head")

    line = "GITHUB_TOKEN_ENCRYPTION_KEY=" + key
    pattern = r"(?m)^\s*GITHUB_TOKEN_ENCRYPTION_KEY\s*=[^\r\n]*"
    updated = (
        re.sub(pattern, lambda _: line, current)
        if re.search(pattern, current)
        else current.rstrip() + "\n" + line + "\n"
    )
    if updated != current:
        env_path.write_text(updated, encoding="utf-8")
    print("GitHub database and encryption settings are ready. No token has been connected.")
    print("Restart your DHANZ backend, then connect in the updated app: Settings > GitHub repositories.")


if __name__ == "__main__":
    main()
