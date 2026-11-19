"""scripts/server/deploy_dhanz_gpt.py: Caddy block, database bootstrap and container settings."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/server"))
spec = importlib.util.spec_from_file_location("deploy_dhanz_gpt", ROOT / "scripts/server/deploy_dhanz_gpt.py")
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)

LIVE = (ROOT / "deploy/Caddyfile").read_text()


def test_block_added_once_and_replaced_not_duplicated():
    once = dg.with_block(LIVE, "gpt.dhanzai.com")
    assert once.startswith(LIVE.rstrip("\n"))
    assert once.count(dg.BEGIN) == 1 and once.count(dg.END) == 1
    assert "gpt.dhanzai.com {" in once and "reverse_proxy dhanz-gpt:3000" in once
    assert "flush_interval -1" in once
    twice = dg.with_block(once, "gpt.dhanzai.com")
    assert twice == once
    moved = dg.with_block(once, "gpt.example.org")
    assert moved.count(dg.BEGIN) == 1 and "gpt.dhanzai.com {" not in moved and "gpt.example.org {" in moved


def test_block_removed_leaves_the_original():
    assert dg.without_block(dg.with_block(LIVE, "gpt.dhanzai.com")) == LIVE.rstrip("\n") + "\n"
    assert dg.without_block(LIVE) == LIVE


def test_broken_markers_stop_instead_of_guessing():
    with pytest.raises(SystemExit):
        dg.without_block(LIVE + "\n" + dg.BEGIN + "\ngpt.x {\n}\n")


def test_bootstrap_is_idempotent_sql_and_refuses_odd_passwords():
    sql = dg.bootstrap_sql("abc_DEF-123")
    assert "if not exists (select 1 from pg_roles where rolname = 'dhanz_gpt')" in sql
    assert "create role service_role nologin bypassrls" in sql
    assert "grant anon, authenticated, service_role to dhanz_gpt" in sql
    assert "drop" not in sql.lower()
    with pytest.raises(ValueError):
        dg.bootstrap_sql("x'; drop database dhanz; --")


def test_env_takes_only_provider_keys_from_the_api():
    secret = {"DHANZ_GPT_DB_PASSWORD": "pw", "APP_TOKEN_KEY": "k" * 44, "CRON_SECRET": "c"}
    api_env = [
        "OPENAI_API_KEY=sk-o",
        "ANTHROPIC_API_KEY=sk-a",
        "CREATIVE_IMAGE_MODEL=img-x",
        "POSTGRES_PASSWORD=secret",
        "JWT_SECRET=nope",
    ]
    lines = dg.env_lines(secret, api_env, "dhanzai.com")
    assert "AUTH_MODE=dhanz" in lines
    assert "DHANZ_API_URL=http://api:8000/api/v1" in lines
    assert "APP_URL=https://gpt.dhanzai.com" in lines
    assert "DATABASE_URL=postgres://dhanz_gpt:pw@db:5432/dhanz_gpt" in lines
    assert "OPENAI_API_KEY=sk-o" in lines and "ANTHROPIC_API_KEY=sk-a" in lines
    assert "IMAGE_MODEL=img-x" in lines
    assert "SELF_CRON=1" in lines and "CRON_SECRET=c" in lines
    assert not any(line.startswith(("POSTGRES_PASSWORD", "JWT_SECRET")) for line in lines)


def test_new_secrets_shape():
    s = dg.new_secrets()
    import base64

    assert len(base64.b64decode(s["APP_TOKEN_KEY"])) == 32
    assert len(s["DHANZ_GPT_DB_PASSWORD"]) >= 40
    dg.bootstrap_sql(s["DHANZ_GPT_DB_PASSWORD"])  # always acceptable to the bootstrap


def test_caddy_mount_and_network_detection():
    caddy = {
        "Mounts": [{"Type": "bind", "Source": "/srv/dhanz/deploy/Caddyfile", "Destination": "/etc/caddy/Caddyfile"}]
    }
    assert dg.caddyfile_source(caddy) == Path("/srv/dhanz/deploy/Caddyfile")
    assert dg.caddyfile_source({"Mounts": [{"Type": "volume", "Destination": "/etc/caddy/Caddyfile"}]}) is None
    assert dg.network_of({"NetworkSettings": {"Networks": {"deploy_default": {}}}}) == "deploy_default"


def test_admin_creates_the_untrusted_extension():
    assert "create extension if not exists vector;" in dg.EXTENSIONS_SQL
    assert "pgcrypto" in dg.EXTENSIONS_SQL and "pg_trgm" in dg.EXTENSIONS_SQL
