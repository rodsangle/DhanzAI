"""Account-scoped, durable queue for an outbound-only ROG renderer.

No shell commands, API provider keys or other users' jobs reach a paired worker.
Claimed jobs are never automatically reclaimed after a disconnect.
"""
import contextlib
import hashlib
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

MODEL = 'wan-rog-1.3b-preview'
MAX_BYTES = 32 * 1024 * 1024
LIFETIME = 110 * 60


class QueueError(ValueError):
    pass


def identifier(value):
    return str(uuid.UUID(str(value)))


class Queue:
    def __init__(self, folder, clock=time.time):
        self.root = Path(folder)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.clock = clock
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS workers (
                    owner TEXT PRIMARY KEY, digest TEXT NOT NULL UNIQUE,
                    expires REAL NOT NULL, seen REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, prompt TEXT NOT NULL,
                    created REAL NOT NULL, status TEXT NOT NULL, claim TEXT,
                    sha256 TEXT, error TEXT
                );
            ''')
        (self.root / 'queue.sqlite3').chmod(0o600)

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.root / 'queue.sqlite3', timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def expire(self, db):
        db.execute("UPDATE jobs SET status='FAILED', error='ROG render timed out; no automatic retry.' "
                   "WHERE status IN ('PENDING','RUNNING') AND created<?", (self.clock() - LIFETIME,))

    def pair(self, owner):
        owner = identifier(owner)
        token = secrets.token_urlsafe(48)
        with self.db() as db:
            self.expire(db)
            if db.execute("SELECT 1 FROM jobs WHERE owner=? AND status IN ('PENDING','RUNNING')", (owner,)).fetchone():
                raise QueueError('Finish or cancel the current video before replacing its worker.')
            db.execute('INSERT OR REPLACE INTO workers(owner,digest,expires,seen) VALUES(?,?,?,0)',
                       (owner, hashlib.sha256(token.encode()).hexdigest(), self.clock() + 90 * 86400))
        return token

    def authenticate(self, token):
        if not isinstance(token, str) or not 40 <= len(token) <= 128:
            raise QueueError('Worker token is invalid or expired.')
        with self.db() as db:
            row = db.execute('SELECT owner FROM workers WHERE digest=? AND expires>?',
                             (hashlib.sha256(token.encode()).hexdigest(), self.clock())).fetchone()
        if row is None:
            raise QueueError('Worker token is invalid or expired.')
        return row['owner']

    def revoke(self, owner):
        owner = identifier(owner)
        with self.db() as db:
            db.execute('DELETE FROM workers WHERE owner=?', (owner,))
            db.execute("UPDATE jobs SET status='CANCELLED' WHERE owner=? AND status IN ('PENDING','RUNNING')", (owner,))

    def status(self, owner):
        with self.db() as db:
            worker = db.execute('SELECT seen,expires FROM workers WHERE owner=?', (identifier(owner),)).fetchone()
        return {'paired': bool(worker and worker['expires'] > self.clock()),
                'online': bool(worker and worker['expires'] > self.clock() and worker['seen'] > self.clock()-45),
                'model': MODEL, 'duration': 5, 'resolution': '512x288', 'audio': False}

    def heartbeat(self, owner):
        with self.db() as db:
            db.execute('UPDATE workers SET seen=? WHERE owner=?', (self.clock(), identifier(owner)))

    def submit(self, task, owner, prompt):
        task, owner = identifier(task), identifier(owner)
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
            raise QueueError('Use a video prompt between 1 and 4000 characters.')
        with self.db() as db:
            self.expire(db)
            old = db.execute('SELECT * FROM jobs WHERE id=?', (task,)).fetchone()
            if old:
                if old['owner'] != owner or old['prompt'] != prompt:
                    raise QueueError('The video request identity has changed.')
                return task
            worker = db.execute('SELECT * FROM workers WHERE owner=?', (owner,)).fetchone()
            if not worker or worker['expires'] <= self.clock() or worker['seen'] < self.clock() - 45:
                raise QueueError('Your paired ROG video worker is offline. Start it on your ROG before generating.')
            if db.execute("SELECT 1 FROM jobs WHERE owner=? AND status IN ('PENDING','RUNNING')", (owner,)).fetchone():
                raise QueueError('Your ROG already has a video queued or rendering. Wait for it to finish.')
            db.execute('INSERT INTO jobs(id,owner,prompt,created,status) VALUES(?,?,?,?,?)',
                       (task, owner, prompt, self.clock(), 'PENDING'))
        return task

    def claim(self, owner):
        owner = identifier(owner)
        with self.db() as db:
            self.expire(db)
            if db.execute("SELECT 1 FROM jobs WHERE owner=? AND status='RUNNING'", (owner,)).fetchone():
                return None
            row = db.execute("SELECT * FROM jobs WHERE owner=? AND status='PENDING' ORDER BY created LIMIT 1", (owner,)).fetchone()
            if row is None:
                return None
            claim = secrets.token_hex(24)
            db.execute("UPDATE jobs SET status='RUNNING',claim=? WHERE id=?", (claim, row['id']))
            return {'id': row['id'], 'prompt': row['prompt'], 'claim': claim, 'model': MODEL}

    def owned_claim(self, task, owner, claim):
        with self.db() as db:
            self.expire(db)
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (identifier(task), identifier(owner))).fetchone()
        if row is None or not secrets.compare_digest(str(row['claim'] or ''), str(claim)):
            raise QueueError('Video claim does not belong to this worker.')
        return dict(row)

    def finish(self, task, owner, claim, digest=None):
        row = self.owned_claim(task, owner, claim)
        if row['status'] == 'SUCCEEDED' and digest and row['sha256'] == digest:
            return
        if row['status'] != 'RUNNING':
            raise QueueError('The video is no longer awaiting this worker.')
        with self.db() as db:
            result = db.execute("UPDATE jobs SET status=?,sha256=?,error=? WHERE id=? AND status='RUNNING' AND claim=?",
                               ('SUCCEEDED' if digest else 'FAILED', digest,
                                None if digest else 'ROG rendering failed. Check the local worker log.', row['id'], claim))
            if result.rowcount != 1:
                raise QueueError('The video changed while receiving its result.')

    def upload(self, task, owner, claim, digest, temporary):
        """Serialize completion with cancellation and competing result deliveries."""
        with self.db() as db:
            self.expire(db)
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',
                             (identifier(task), identifier(owner))).fetchone()
            if row is None or not secrets.compare_digest(str(row['claim'] or ''), str(claim)):
                raise QueueError('Video claim does not belong to this worker.')
            if row['status'] == 'SUCCEEDED' and row['sha256'] == digest:
                return
            if row['status'] != 'RUNNING':
                raise QueueError('The video no longer accepts this result.')
            Path(temporary).replace(self.content_path(task))
            db.execute("UPDATE jobs SET status='SUCCEEDED',sha256=? WHERE id=?", (digest, row['id']))

    def worker_status(self, task, owner):
        with self.db() as db:
            self.expire(db)
            row = db.execute('SELECT status FROM jobs WHERE id=? AND owner=?',
                             (identifier(task), identifier(owner))).fetchone()
        if row is None:
            raise QueueError('Video task not found for this account.')
        return row['status']

    def poll(self, task):
        with self.db() as db:
            self.expire(db)
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identifier(task),)).fetchone()
        if row is None:
            raise QueueError('Video task not found.')
        result = {'status': row['status']}
        if row['status'] == 'SUCCEEDED':
            result['output'] = ['rog-video:' + row['id']]
        return result

    def cancel(self, task):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='CANCELLED' WHERE id=? AND status IN ('PENDING','RUNNING')", (identifier(task),))

    def content_path(self, task):
        return self.root / (identifier(task) + '.mp4')

    def prune(self):
        with self.db() as db:
            self.expire(db)
            old = list(db.execute('SELECT id FROM jobs WHERE created<?', (self.clock()-7*86400,)))
            for row in old:
                self.content_path(row['id']).unlink(missing_ok=True)
                db.execute('DELETE FROM jobs WHERE id=?', (row['id'],))
