"""Portable checks for the custom-server frontend updater."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reader_install", ROOT / "deploy/updaters/install_read_aloud.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

BASELINE = """import 'markdown_view.dart';
class MessageTile {
  Widget _assistant(BuildContext context) {
    if (!streaming) {
                    if (isLast && !busy)
      regenerate();
    }
  }
}
"""


class ReadAloudInstallerTests(unittest.TestCase):
    def test_patch_only_import_and_assistant_action(self):
        patched = helper.patch_tile(BASELINE)
        self.assertIn("import 'reply_reader.dart';", patched)
        self.assertIn("ReadAloudButton(key: ValueKey(message.id), text: message.content)", patched)
        restored = patched.replace("import 'reply_reader.dart';\n", "").replace(
            "                    if (message.content.trim().isNotEmpty)\n"
            "                      ReadAloudButton(key: ValueKey(message.id), text: message.content),\n",
            "",
        )
        self.assertEqual(restored, BASELINE)

    def test_unknown_or_already_updated_layout_refuses(self):
        for source in (
            "class Other {}",
            BASELINE + " ReadAloudButton(",
            BASELINE.replace("if (!streaming)", "if (streaming)"),
        ):
            with self.assertRaises(ValueError):
                helper.patch_tile(source)

    def test_bundled_widget_and_tests_match_source(self):
        for name, relative in (
            ("reply_reader.dart", "lib/features/chat/reply_reader.dart"),
            ("read_aloud_test.dart", "test/read_aloud_test.dart"),
        ):
            self.assertEqual(helper.asset(name), (ROOT / "apps/dhanz_flutter" / relative).read_text())

    def test_install_keeps_bind_mount_inode_and_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            stage, live = base / "stage", base / "live"
            stage.mkdir()
            live.mkdir()
            for name in ("index.html", "main.dart.js", "flutter_bootstrap.js"):
                (stage / name).write_text("new")
                (live / name).write_text("old")
            inode = live.stat().st_ino
            backup = helper.deploy_files(stage, live)
            self.assertEqual(live.stat().st_ino, inode)
            self.assertEqual((live / "index.html").read_text(), "new")
            self.assertEqual((backup / "index.html").read_text(), "old")

    def test_symlink_escape_refuses_before_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            stage, live, outside = base / "stage", base / "live", base / "outside"
            stage.mkdir()
            live.mkdir()
            outside.mkdir()
            for name in ("index.html", "main.dart.js", "flutter_bootstrap.js"):
                (stage / name).write_text("new")
            (stage / "assets").mkdir()
            (stage / "assets/file.txt").write_text("new")
            (live / "assets").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                helper.deploy_files(stage, live)
            self.assertEqual(list(outside.iterdir()), [])

    def test_fingerprint_detects_concurrent_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "lib").mkdir()
            path = root / "lib/a.dart"
            path.write_text("old")
            before = helper.source_fingerprint(root)
            path.write_text("new")
            self.assertNotEqual(helper.source_fingerprint(root), before)


if __name__ == "__main__":
    unittest.main()
