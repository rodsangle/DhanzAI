"""The combined updater changes only known controls and protects live Local News."""

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
