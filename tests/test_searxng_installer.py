"""Portable orchestration checks; Docker and provider responses are simulated."""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("searxng_setup", ROOT / "deploy/updaters/install_searxng.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class SearxngTests(unittest.TestCase):
    def test_search_is_private_and_does_not_replace_api_networks(self):
        config = helper.compose_config("current-api", "existing_default", Path("/private/settings.yml"))
        service = config["services"][helper.SERVICE]
        self.assertNotIn("ports", service)
        self.assertNotIn("networks", config["services"]["api"])
        self.assertEqual(service["mem_limit"], "384m")
        self.assertEqual(service["cpus"], 0.75)
        self.assertEqual(service["image"], helper.IMAGE)
        self.assertIn("@sha256:", helper.IMAGE)
        self.assertEqual(config["networks"]["dhanz_search_link"], {"name": "existing_default", "external": True})

    def test_network_selection_never_attaches_api_to_a_new_network(self):
        info = {"project": "deploy", "networks": {"deploy_default": {}, "another": {}}}
        self.assertEqual(helper.choose_network(info), "deploy_default")
        with self.assertRaises(ValueError):
            helper.choose_network(info, "not-attached")
        with self.assertRaises(ValueError):
            helper.choose_network({"project": "deploy", "networks": {"one": {}, "two": {}}})

    def test_settings_include_json_web_and_news(self):
        text = helper.settings_text('fixture"key')
        self.assertIn('secret_key: "fixture\\"key"', text)
        self.assertIn("    - json", text)
        for name in ("google news", "bing news", "duckduckgo news"):
            self.assertIn("      - " + name, text)
        self.assertIn("limiter: false", text)

    def run_installer(self, *, working=True, ready=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        directory = home / "DhanzAI/deploy"
        directory.mkdir(parents=True)
        files = [directory / "prod.yml", directory / "ocr.json", directory / "weather.json"]
        for file in files:
            file.write_text("{}")
        info = {
            "project": "deploy",
            "image": "sha256:" + "a" * 64,
            "directory": str(directory),
            "files": ",".join(map(str, files)),
            "networks": {"deploy_default": {}},
        }
        calls = []

        def docker(*args, **kwargs):
            calls.append(args)
            if args[0] == "inspect":
                return json.dumps(
                    {"Running": True, "Health": {"Status": "healthy"}} if args[-1] == "{{json .State}}" else info
                )
            if args[:3] == ("exec", "deploy-api-1", "python"):
                if args[-1] == helper.PROBE:
                    return json.dumps({"supported": True, "provider": "none", "ours": False})
                if args[-1] == helper.QUERY:
                    return json.dumps(
                        {"ok": working, "web_results": 2 if working else 0, "news_results": 2 if working else 0}
                    )
                return "ready" if ready else "waiting"
            return ""

        actual_read = Path.read_text

        def read(path, *args, **kwargs):
            return "MemAvailable: 1048576 kB\n" if str(path) == "/proc/meminfo" else actual_read(path, *args, **kwargs)

        output = io.StringIO()
        with (
            patch.object(helper, "docker", docker),
            patch.object(helper.Path, "home", return_value=home),
            patch.object(helper.time, "sleep"),
            patch("sys.argv", ["install_searxng.py", "--apply"]),
            patch.object(Path, "read_text", read),
            redirect_stdout(output),
        ):
            try:
                helper.main()
                error = None
            except ValueError as exc:
                error = exc
        return calls, output.getvalue(), error, files

    def test_success_preserves_all_compose_overlays_and_verifies_real_query(self):
        calls, output, error, files = self.run_installer()
        self.assertIsNone(error)
        api_up = next(args for args in calls if args[0] == "compose" and "up" in args and args[-1] == "api")
        for file in files:
            self.assertIn(str(file), api_up)
        self.assertIn("--no-deps", api_up)
        self.assertIn("--pull", api_up)
        self.assertIn("news results: 2", output)
        self.assertTrue(any(args[-1] == helper.QUERY for args in calls))

    def test_no_results_restores_api_and_stops_search(self):
        calls, output, error, _ = self.run_installer(working=False)
        self.assertIsNotNone(error)
        self.assertIn("Previous API image and search provider restored", output)
        self.assertTrue(any("rollback.json" in " ".join(args) for args in calls))
        self.assertTrue(any(args[-2:] == ("stop", helper.SERVICE) for args in calls))
        self.assertNotIn("SearXNG installed", output)

    def test_failed_start_does_not_restart_api(self):
        calls, _, error, _ = self.run_installer(ready=False)
        self.assertIsNotNone(error)
        self.assertFalse(any("up" in args and args[-1] == "api" for args in calls))


if __name__ == "__main__":
    unittest.main()
