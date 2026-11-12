"""Private encrypted OAuth state and account-scoped connection records."""

import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

PROVIDERS = ("microsoft", "google")


class IntegrationError(ValueError):
    pass


def provider(value):
    if value not in PROVIDERS:
        raise IntegrationError("Choose Microsoft or Google.")
    return value


def owner(value):
    return str(uuid.UUID(str(value)))


def origin(value):
    p = urlsplit(value)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.path not in ("", "/")
        or p.query
        or p.fragment
        or p.port not in (None, 443)
    ):
        raise IntegrationError("Use the public HTTPS Dhanz domain without a path.")
    return value.rstrip("/")


class Store:
    def __init__(self, folder, clock=time.time):
        self.root = Path(folder)
        self.clock = clock
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        key = self.root / "oauth.key"
        if not key.exists():
            if (self.root / "connections.sqlite3").exists():
                raise IntegrationError("Restore the integration encryption key from your private backup.")
            temporary = self.root / ("key-" + secrets.token_hex(12))
            try:
                fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(Fernet.generate_key())
                try:
                    os.link(temporary, key)
                except FileExistsError:
                    pass
            finally:
                temporary.unlink(missing_ok=True)
        self.cipher = Fernet(key.read_bytes())
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS config(provider TEXT PRIMARY KEY,payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS connections(owner TEXT,provider TEXT,payload BLOB NOT NULL,
                    PRIMARY KEY(owner,provider));
                CREATE TABLE IF NOT EXISTS states(digest TEXT PRIMARY KEY,owner TEXT,provider TEXT,
                    expires REAL,payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS actions(owner TEXT,key TEXT,digest TEXT,status TEXT,payload BLOB,
                    created REAL,PRIMARY KEY(owner,key));
                CREATE TABLE IF NOT EXISTS epochs(owner TEXT,provider TEXT,value INTEGER,
                    PRIMARY KEY(owner,provider));
            """)
        (self.root / "connections.sqlite3").chmod(0o600)

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.root / "connections.sqlite3", timeout=15)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seal(self, value):
        return self.cipher.encrypt(json.dumps(value).encode())

    def unseal(self, value):
        return json.loads(self.cipher.decrypt(value))

    def configure(self, name, client_id, client_secret, public_origin):
        provider(name)
        if not all(
            isinstance(x, str) and 1 <= len(x) <= 4000 and not any(c.isspace() for c in x)
            for x in (client_id, client_secret)
        ):
            raise IntegrationError("Enter the application client ID and secret locally, without whitespace.")
        value = {"client_id": client_id, "client_secret": client_secret, "origin": origin(public_origin)}
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO config VALUES(?,?)", (name, self.seal(value)))

    def config(self, name):
        provider(name)
        with self.db() as db:
            row = db.execute("SELECT payload FROM config WHERE provider=?", (name,)).fetchone()
        if not row:
            raise IntegrationError("The Dhanz administrator must finish this provider’s application setup first.")
        return self.unseal(row[0])

    @staticmethod
    def revision(config):
        return hashlib.sha256((config["client_id"] + "\n" + config["origin"]).encode()).hexdigest()

    def connection(self, uid, name):
        with self.db() as db:
            row = db.execute(
                "SELECT payload FROM connections WHERE owner=? AND provider=?", (owner(uid), provider(name))
            ).fetchone()
        return self.unseal(row[0]) if row else None

    def save(self, uid, name, value, expected_epoch=None):
        value.setdefault("connection_id", uuid.uuid4().hex)
        with self.db() as db:
            epoch = db.execute(
                "SELECT value FROM epochs WHERE owner=? AND provider=?", (owner(uid), provider(name))
            ).fetchone()
            if expected_epoch is not None and expected_epoch != (epoch[0] if epoch else 0):
                raise IntegrationError(
                    "This connection was disconnected during sign-in. Start a new connection if intended."
                )
            db.execute(
                "INSERT OR REPLACE INTO connections VALUES(?,?,?)", (owner(uid), provider(name), self.seal(value))
            )

    def update_existing(self, uid, name, value):
        with self.db() as db:
            row = db.execute(
                "SELECT payload FROM connections WHERE owner=? AND provider=?", (owner(uid), provider(name))
            ).fetchone()
            if row is None or self.unseal(row[0]).get("connection_id") != value.get("connection_id"):
                raise IntegrationError("This account was disconnected or replaced. No connection was restored.")
            db.execute(
                "UPDATE connections SET payload=? WHERE owner=? AND provider=?", (self.seal(value), owner(uid), name)
            )

    def disconnect(self, uid, name):
        with self.db() as db:
            db.execute(
                "INSERT INTO epochs(owner,provider,value) VALUES(?,?,1) "
                "ON CONFLICT(owner,provider) DO UPDATE SET value=value+1",
                (owner(uid), provider(name)),
            )
            db.execute("DELETE FROM connections WHERE owner=? AND provider=?", (owner(uid), provider(name)))
            db.execute("DELETE FROM states WHERE owner=? AND provider=?", (owner(uid), name))

    def delete_account(self, uid):
        # Keep anonymous epoch tombstones so a consumed/in-flight OAuth callback
        # cannot recreate deleted credentials. Shared application config remains.
        for name in PROVIDERS:
            self.disconnect(uid, name)
        with self.db() as db:
            db.execute("DELETE FROM actions WHERE owner=?", (owner(uid),))

    def pending(self, uid, name, value):
        state = secrets.token_urlsafe(40)
        with self.db() as db:
            epoch = db.execute(
                "SELECT value FROM epochs WHERE owner=? AND provider=?", (owner(uid), provider(name))
            ).fetchone()
            value["epoch"] = epoch[0] if epoch else 0
            db.execute("DELETE FROM states WHERE expires<?", (self.clock(),))
            if db.execute("SELECT count(*) FROM states WHERE owner=?", (owner(uid),)).fetchone()[0] >= 5:
                raise IntegrationError("Several sign-ins are already pending. Finish one or wait ten minutes.")
            db.execute(
                "INSERT INTO states VALUES(?,?,?,?,?)",
                (
                    hashlib.sha256(state.encode()).hexdigest(),
                    owner(uid),
                    provider(name),
                    self.clock() + 600,
                    self.seal(value),
                ),
            )
        return state

    def consume(self, state, name, cookie):
        if not isinstance(state, str) or not 30 <= len(state) <= 100:
            raise IntegrationError("This connection attempt is invalid or expired. Start again in Integrations.")
        digest = hashlib.sha256(state.encode()).hexdigest()
        with self.db() as db:
            row = db.execute("SELECT owner,provider,expires,payload FROM states WHERE digest=?", (digest,)).fetchone()
            if row is None or row[1] != provider(name) or row[2] < self.clock():
                raise IntegrationError("This connection attempt is invalid or expired. Start again in Integrations.")
            value = self.unseal(row[3])
            if not secrets.compare_digest(
                value["cookie_digest"], hashlib.sha256(str(cookie or "").encode()).hexdigest()
            ):
                raise IntegrationError("Continue sign-in in the same browser where you opened Dhanz Integrations.")
            db.execute("DELETE FROM states WHERE digest=?", (digest,))
        return row[0], value

    def intent(self, uid, key, args):
        if not isinstance(key, str) or not 16 <= len(key) <= 100 or not all(c.isalnum() or c in "_-" for c in key):
            raise IntegrationError(
                "Use a unique operation key between 16 and 100 letters, digits, underscores or hyphens."
            )
        digest = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        with self.db() as db:
            db.execute("DELETE FROM actions WHERE created<?", (self.clock() - 30 * 86400,))
            row = db.execute(
                "SELECT digest,status,payload FROM actions WHERE owner=? AND key=?", (owner(uid), key)
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise IntegrationError("This operation key was already used for different input.")
                if row[1] == "complete":
                    return self.unseal(row[2])
                raise IntegrationError(
                    "A previous attempt has an uncertain outcome. Check the provider before explicitly "
                    "starting a new operation; nothing was retried."
                )
            db.execute(
                "INSERT INTO actions VALUES(?,?,?,?,?,?)", (owner(uid), key, digest, "started", None, self.clock())
            )
        return None

    def finish(self, uid, key, result):
        with self.db() as db:
            db.execute(
                "UPDATE actions SET status='complete',payload=? WHERE owner=? AND key=?",
                (self.seal(result), owner(uid), key),
            )
