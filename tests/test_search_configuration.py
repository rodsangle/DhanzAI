"""Verify search settings do not change unrelated secrets or serialize keys into overlays."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("search_setup", ROOT / "deploy/updaters/configure_web_search.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class SearchSetupTests(unittest.TestCase):
    def test_update_preserves_unrelated_lines_and_removes_duplicate_fields(self):
        before = "# existing config\nJWT_SECRET=keep-this\nSEARCH_PROVIDER=none\nexport SEARCH_PROVIDER=brave\nTAVILY_API_KEY=old\nOPENAI_API_KEY=keep-that\n"
        updated = helper.update_env(before, {"SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": "test-key"})
        self.assertIn("JWT_SECRET=keep-this\n", updated)
        self.assertIn("OPENAI_API_KEY=keep-that\n", updated)
        self.assertEqual(updated.count("SEARCH_PROVIDER="), 1)
        self.assertEqual(updated.count("TAVILY_API_KEY="), 1)
        self.assertIn("TAVILY_API_KEY='test-key'", updated)

    def test_private_atomic_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            helper.atomic_private(path, "private")
            self.assertEqual(path.read_text(), "private")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
