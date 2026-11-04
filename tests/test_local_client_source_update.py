import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("local_controls", ROOT / "deploy/updaters/apply_093_source.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class LocalSourceUpdateTests(unittest.TestCase):
    def test_updated_file_hashes_match_the_published_client(self):
        client = ROOT / "client_releases/0.9.3-controls"
        for name, hashes in helper.FILES.items():
            self.assertEqual(hashlib.sha256((client / name).read_bytes()).hexdigest(), hashes["after"], name)

    def test_updates_only_four_known_paths_and_no_credentials(self):
        self.assertEqual(
            set(helper.FILES),
            {
                "pubspec.yaml",
                "lib/features/chat/composer.dart",
                "lib/features/chat/message_tile.dart",
                "lib/features/chat/draft_spelling.dart",
            },
        )
        self.assertTrue(all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in helper.FILES))
        self.assertIsNone(helper.FILES["lib/features/chat/draft_spelling.dart"]["before"])


if __name__ == "__main__":
    unittest.main()
