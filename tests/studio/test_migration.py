import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_additive_migration_keeps_existing_records_and_seeds_worker_lease(tmp_path):
    path = Path(__file__).resolve().parents[2]/'server_extensions/migrations/0011_assistant_studio.py'
    spec = importlib.util.spec_from_file_location('studio_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id CHAR(32) PRIMARY KEY, email TEXT)'))
        conn.execute(text('CREATE TABLE messages (id CHAR(32) PRIMARY KEY, content TEXT)'))
        conn.execute(text("INSERT INTO users VALUES ('existing', 'keep@example.test')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert conn.scalar(text('SELECT id FROM builder_leases')) == 1
        assert conn.scalar(text('SELECT email FROM users')) == 'keep@example.test'
        assert {'response_feedback','builder_projects','builder_leases'} <= set(inspect(conn).get_table_names())
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert conn.scalar(text('SELECT email FROM users')) == 'keep@example.test'
    engine.dispose()
