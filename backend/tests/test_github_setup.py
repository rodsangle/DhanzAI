import importlib.util
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet


def test_local_setup_backs_up_database_and_preserves_key(tmp_path, monkeypatch, capsys):
    script = Path(__file__).resolve().parents[2] / "scripts" / "setup_github.py"
    spec = importlib.util.spec_from_file_location("setup_github_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    backend = tmp_path / "backend"
    backend.mkdir()
    database = backend / "test.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE user_data (value TEXT)")
        connection.execute("INSERT INTO user_data VALUES ('keep')")
    env = backend / ".env"
    env.write_text("OTHER_SETTING=preserved\n", encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(tmp_path / "scripts" / "setup_github.py"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///" + str(database))
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", "")
    monkeypatch.chdir(tmp_path)
    upgraded = []
    monkeypatch.setattr(module.command, "upgrade", lambda config, revision: upgraded.append(revision))
    module.main()
    initial = env.read_text(encoding="utf-8")
    key = initial.split("GITHUB_TOKEN_ENCRYPTION_KEY=")[1].strip()
    Fernet(key.encode())
    assert key not in capsys.readouterr().out
    monkeypatch.delenv("GITHUB_TOKEN_ENCRYPTION_KEY")
    module.main()
    assert env.read_text(encoding="utf-8") == initial
    assert "OTHER_SETTING=preserved" in initial
    assert upgraded == ["head", "head"]
    for backup in (tmp_path / ".tools" / "github-setup-backups").glob("*.db"):
        with sqlite3.connect(backup) as connection:
            assert connection.execute("SELECT value FROM user_data").fetchone() == ("keep",)
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", "invalid")
    with pytest.raises(SystemExit, match="invalid"):
        module.main()
    assert env.read_text(encoding="utf-8") == initial
