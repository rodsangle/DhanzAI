import importlib.util
import io
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

spec = importlib.util.spec_from_file_location(
    "web_updater", Path(__file__).resolve().parents[1] / "deploy/updaters/install_web_update.py"
)
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


def archive(extra=None):
    output = io.BytesIO()
    with ZipFile(output, "w") as z:
        for name in ["index.html", "main.dart.js", "flutter_bootstrap.js", "assets/font.ttf"]:
            z.writestr(name, "new " + name)
        if extra:
            z.writestr(extra, "untrusted")
    return output.getvalue()


@pytest.mark.parametrize("path", ["../outside", "/outside", "assets/../../outside", "assets\\outside"])
def test_archive_paths_cannot_escape_staging(tmp_path, path):
    with pytest.raises(ValueError, match="Unsafe"):
        web.unpack(archive(path), tmp_path / "stage")
    assert not (tmp_path / "outside").exists()


def test_archive_symlinks_are_rejected(tmp_path):
    symlink = ZipInfo("assets/link")
    symlink.create_system = 3
    symlink.external_attr = 0o120777 << 16
    with pytest.raises(ValueError, match="Unsafe"):
        web.unpack(archive(symlink), tmp_path / "stage")


def test_install_backs_up_and_preserves_caddy_mount_inode_and_existing_assets(tmp_path):
    stage, target = tmp_path / "stage", tmp_path / "web"
    stage.mkdir()
    target.mkdir()
    (target / "index.html").write_text("previous client")
    (target / "old-asset.js").write_text("needed by open browser tabs")
    inode = target.stat().st_ino
    web.unpack(archive(), stage)
    backup = web.install(stage, target)
    assert target.stat().st_ino == inode
    assert (target / "index.html").read_text() == "new index.html"
    assert (backup / "index.html").read_text() == "previous client"
    assert (target / "old-asset.js").exists()
    assert (target / "assets/font.ttf").is_file()


def test_existing_target_symlink_cannot_redirect_install(tmp_path):
    stage, target, outside = tmp_path / "stage", tmp_path / "web", tmp_path / "outside"
    for path in [stage, target, outside]:
        path.mkdir()
    (target / "assets").symlink_to(outside, target_is_directory=True)
    web.unpack(archive(), stage)
    with pytest.raises(ValueError, match="outside"):
        web.install(stage, target)
    assert not list(outside.iterdir())
