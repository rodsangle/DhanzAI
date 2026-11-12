"""The combined updater changes only known controls and protects live Local News."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("chat_controls_setup", ROOT / "deploy/updaters/install_chat_controls.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
BASELINE = """import 'chat_controller.dart';
class _ComposerState {
  final _controller = TextEditingController();
  Widget build() {
          TextField(
            controller: _controller,
          );
                    IconButton(
                      tooltip: 'Attach files',
                    );
  }
}
"""


class ControlsTests(unittest.TestCase):
    def test_spelling_patch_preserves_legacy_composer_interface(self):
        patched = helper.patch_composer(BASELINE)
        self.assertIn("autocorrect: _deviceAutocorrect", patched)
        self.assertIn("enableSuggestions: _deviceAutocorrect", patched)
        self.assertIn("DraftSpellingButton(", patched)
        self.assertNotIn("chat.sending", patched)
        self.assertEqual(helper.patch_composer(patched), patched)

    def test_queue_aware_composer_disables_spelling_for_pending_send(self):
        patched = helper.patch_composer(
            BASELINE.replace("          TextField(\n", "          TextField(\n            readOnly: chat.sending,\n")
        )
        self.assertIn("enabled: !chat.sending", patched)

    def test_existing_custom_spelling_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            helper.patch_composer(
                BASELINE.replace("            controller:", "            autocorrect: false,\n            controller:")
            )
        with self.assertRaises(ValueError):
            helper.patch_composer("unknown composer")

    def test_known_read_aloud_patch_is_not_duplicated(self):
        text = "import 'reply_reader.dart';\nReadAloudButton(text: message.content)"
        self.assertEqual(helper.patch_tile(text), text)

    def test_all_four_bundled_assets_match_reviewed_files(self):
        for name, relative in {
            "reply_reader.dart": "lib/features/chat/reply_reader.dart",
            "read_aloud_test.dart": "test/read_aloud_test.dart",
            "draft_spelling.dart": "lib/features/chat/draft_spelling.dart",
            "draft_spelling_test.dart": "test/draft_spelling_test.dart",
        }.items():
            self.assertEqual(helper.asset(name), (ROOT / "apps/dhanz_flutter" / relative).read_text())

    def test_compiled_local_news_cannot_be_replaced_with_stale_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "lib").mkdir()
            target = root / "build/web"
            target.mkdir(parents=True)
            (target / "main.dart.js").write_text('button("Daily local news")')
            with self.assertRaises(ValueError):
                helper.require_current_features(root, target)
            (root / "lib/news.dart").write_text('button("Daily local news")')
            helper.require_current_features(root, target)

    def test_synced_app_mount_and_base_href_preserve_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            mounted = home / ".local/share/dhanz-server-sync/releases/20261103T041017Z-5fb2c2e2a5c5/web-root"
            target = mounted / "app"
            target.mkdir(parents=True)
            (mounted / "index.html").write_text("outer wrapper")
            for name in ("index.html", "main.dart.js", "flutter_bootstrap.js"):
                (target / name).write_text('<base href="/app/">')
            mounts = [{"Type": "bind", "Source": str(mounted), "Destination": "/srv/web"}]
            self.assertEqual(helper.mounted_flutter_root(mounts, home), target)
            self.assertEqual(helper.current_base_href(target), "/app/")
            stage = home / "checked-build"
            stage.mkdir()
            for name in ("index.html", "main.dart.js", "flutter_bootstrap.js"):
                (stage / name).write_text("new")
            private = home / "private-backups"
            private.mkdir(mode=0o700)
            inode = target.stat().st_ino
            backup = helper.deploy_files(stage, target, backup_parent=private)
            self.assertEqual(target.stat().st_ino, inode)
            self.assertEqual((mounted / "index.html").read_text(), "outer wrapper")
            self.assertEqual(backup.parent, private)
            self.assertEqual((backup / "main.dart.js").read_text(), '<base href="/app/">')

    def test_arbitrary_or_incomplete_mount_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            mounts = [{"Type": "bind", "Source": str(home / "unrelated"), "Destination": "/srv/web"}]
            with self.assertRaises(ValueError):
                helper.mounted_flutter_root(mounts, home)
            mounts[0]["Source"] = str(home / "DhanzAI/apps/dhanz_flutter/build/web")
            with self.assertRaises(ValueError):
                helper.mounted_flutter_root(mounts, home)

    def test_old_source_cannot_replace_new_live_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pubspec.yaml").write_text("version: 0.8.0+8\n")
            (root / "version.json").write_text(json.dumps({"version": "0.9.2", "build_number": "12"}))
            with self.assertRaises(ValueError):
                helper.require_matching_version(root, root)
            (root / "pubspec.yaml").write_text("version: 0.9.2+12\n")
            helper.require_matching_version(root, root)

    def test_base_href_must_be_local_and_is_not_shared_between_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "index.html").write_text('<base href="/app/">')
            self.assertEqual(helper.current_base_href(target), "/app/")
            (target / "index.html").write_text('<base href="/">')
            self.assertEqual(helper.current_base_href(target), "/")
            (target / "index.html").write_text('<base href="https://other.example/">')
            with self.assertRaises(ValueError):
                helper.current_base_href(target)


if __name__ == "__main__":
    unittest.main()
