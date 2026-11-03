import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest

spec = importlib.util.spec_from_file_location(
    "build_update_bundle",
    Path(__file__).resolve().parents[1] / "scripts/release/build_update_bundle.py",
)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


@pytest.mark.parametrize("name", [".env", "deploy/.env.backup-123", "key.pem", "automation-session.bin", ".venv/file"])
def test_private_files_are_rejected(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("must not be packaged")
    with pytest.raises(ValueError):
        bundle.safe_entries(tmp_path, [name])


def test_symlink_outside_checkout_is_rejected(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside").write_text("private")
    (root / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError):
        bundle.safe_entries(root, ["link"])


def test_archive_contains_only_selected_files_and_is_reproducible(tmp_path):
    (tmp_path / "public.md").write_text("public")
    (tmp_path / ".env").write_text("private")
    entries = bundle.safe_entries(tmp_path, ["public.md"])
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    bundle.archive(first, tmp_path, entries, "source/")
    bundle.archive(second, tmp_path, entries, "source/")
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        assert archive.namelist() == ["source/public.md"]
        assert archive.read("source/public.md") == b"public"
