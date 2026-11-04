import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pwa_setup", ROOT / "deploy/updaters/install_pwa_controls.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def metadata(version="0.9.2", build="20", release=None, sha=None):
    return {
        "version.json": json.dumps({"version": version, "build_number": build}),
        "release.json": json.dumps(
            {"release_id": release or helper.BASE_RELEASE, "source_sha256": sha or helper.BASE_SOURCE}
        ),
        "index.html": '<base href="/app/">',
        "main.dart.js": "old app",
        "flutter_bootstrap.js": "bootstrap",
    }


class PwaTests(unittest.TestCase):
    def test_resolves_verified_nested_app_without_touching_wrapper(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            root = home / ".local/share/dhanz-server-sync/releases" / helper.BASE_RELEASE / "web-root"
            app = root / "app"
            app.mkdir(parents=True)
            for name, value in metadata().items():
                (app / name).write_text(value)
            (root / "index.html").write_text("wrapper")
            mounts = [{"Type": "bind", "Source": str(root), "Destination": "/srv/web"}]
            self.assertEqual(helper.target_app(mounts, home), app)
            self.assertTrue(helper.require_base(app))
            stage = home / "stage"
            stage.mkdir()
            for name, value in metadata("0.9.3", "21", helper.RELEASE).items():
                (stage / name).write_text(value)
            inode = app.stat().st_ino
            helper.copy_assets(stage, app)
            self.assertEqual(app.stat().st_ino, inode)
            self.assertEqual((root / "index.html").read_text(), "wrapper")
            self.assertFalse(helper.require_base(app))

    def test_refuses_unknown_release_even_with_same_version(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp)
            for name, value in metadata(release="some-other-release").items():
                (app / name).write_text(value)
            with self.assertRaises(ValueError):
                helper.require_base(app)

    def test_checked_package_is_complete_and_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            stage.mkdir()
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as z:
                for name, value in metadata("0.9.3", "21", helper.RELEASE).items():
                    z.writestr(name, value)
            helper.unpack(buffer.getvalue(), stage)
            self.assertEqual(json.loads((stage / "version.json").read_text())["version"], "0.9.3")
            bad = io.BytesIO()
            with ZipFile(bad, "w") as z:
                z.writestr("../escape", "bad")
            with self.assertRaises(ValueError):
                helper.unpack(bad.getvalue(), stage)
            self.assertFalse((Path(temp) / "escape").exists())

    def test_target_symlinks_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stage = base / "stage"
            app = base / "app"
            outside = base / "outside"
            stage.mkdir()
            app.mkdir()
            outside.mkdir()
            (stage / "assets").mkdir()
            (stage / "assets/a").write_text("new")
            (app / "assets").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                helper.copy_assets(stage, app)
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
