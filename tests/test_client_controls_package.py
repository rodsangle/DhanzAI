import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("client_package", ROOT / "scripts/release/package_client_controls.py")
pkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkg)


class PackageTests(unittest.TestCase):
    def test_packages_only_compiled_assets_with_provenance_and_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "app"
            web = app / "build/web"
            out = Path(temp) / "out"
            web.mkdir(parents=True)
            (app / "lib").mkdir()
            (app / "lib/main.dart").write_text("client source")
            (web / "version.json").write_text(json.dumps({"version": "0.9.3", "build_number": "21"}))
            for name in ("index.html", "main.dart.js", "flutter_bootstrap.js"):
                (web / name).write_text("compiled")
            with patch.object(pkg, "APP", app), patch.object(pkg, "WEB", web), patch.object(pkg, "OUTPUT", out):
                pkg.main()
            file = out / pkg.PACKAGE
            with ZipFile(file) as archive:
                self.assertIn("main.dart.js", archive.namelist())
                self.assertNotIn("lib/main.dart", archive.namelist())
                metadata = json.loads(archive.read("release.json"))
                self.assertEqual(metadata["release_id"], pkg.RELEASE)
                self.assertEqual(metadata["base_version"], "0.9.2+20")
                self.assertEqual(metadata["source_subdirectory"], "client_releases/0.9.3-controls")
            self.assertEqual(
                (out / (pkg.PACKAGE + ".sha256")).read_text().split()[0], hashlib.sha256(file.read_bytes()).hexdigest()
            )

    def test_wrong_version_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temp:
            web = Path(temp)
            (web / "version.json").write_text(json.dumps({"version": "0.8.0", "build_number": "8"}))
            for name in ("index.html", "main.dart.js", "flutter_bootstrap.js"):
                (web / name).write_text("old")
            with patch.object(pkg, "WEB", web), self.assertRaises(ValueError):
                pkg.main()


if __name__ == "__main__":
    unittest.main()
