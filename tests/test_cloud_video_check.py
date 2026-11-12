import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(ROOT / "deploy/updaters/check_cloud_video.py"))
KEY = "key_" + "example" * 6


def opener(data):
    def open_request(request, timeout):
        assert request.full_url == "https://api.dev.runwayml.com/v1/organization"
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") == "Bearer " + KEY
        return io.StringIO(json.dumps(data))

    return open_request


class CloudVideoCheckTests(unittest.TestCase):
    def test_runway_read_only_validation_and_credit_check(self):
        self.assertEqual(module["organization"](KEY, opener({"creditBalance": 100})), 100)
        for value in (0, -1, None, True, "100"):
            with self.subTest(balance=value), self.assertRaises(ValueError):
                module["organization"](KEY, opener({"creditBalance": value}))

    def test_errors_never_echo_provider_body_or_key(self):
        def reject(request, timeout):
            raise HTTPError(request.full_url, 401, "secret " + KEY, {}, io.BytesIO(KEY.encode()))

        with self.assertRaises(ValueError) as error:
            module["organization"](KEY, reject)
        self.assertIn("401", str(error.exception))
        self.assertNotIn(KEY, str(error.exception))
        with self.assertRaises(ValueError):
            module["validate_key"]("sk-proj-" + "a" * 40)

    def test_private_key_permissions_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private/runway.key"
            module["save_key"](path, KEY)
            self.assertEqual(path.read_text(), KEY)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            path.unlink()
            path.symlink_to(Path(directory) / "outside")
            with self.assertRaises(ValueError):
                module["save_key"](path, KEY)


if __name__ == "__main__":
    unittest.main()
