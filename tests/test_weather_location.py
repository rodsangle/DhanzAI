"""Keep explicit user location through a tool call without changing privacy checks."""

import importlib.util
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


location = load("weather_location", "backend/app/services/weather_location.py")
installer = load("weather_location_install", "deploy/updaters/install_weather_location.py")


@dataclass(frozen=True)
class Spec:
    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class Tool:
    spec: Spec
    label: str
    run: object


class LocationTests(unittest.IsolatedAsyncioTestCase):
    def test_current_question_retains_texas_even_when_model_drops_it(self):
        for question in ("what is the weather in houston texas today?", "Weather in Houston, TX", "Houston in Texas"):
            result = location.bind_location({"city": "Houston"}, question)
            self.assertEqual(result["region"], "Texas")
            self.assertEqual(result["country_code"], "US")
        result = location.bind_location({"city": "Houston", "region": "Alaska"}, "weather in Houston Texas")
        self.assertEqual(result["region"], "Texas")

    def test_full_city_argument_is_normalized(self):
        result = location.bind_location({"city": "Houston, Texas"}, "")
        self.assertEqual(result, {"city": "Houston", "region": "Texas", "country_code": "US"})

    def test_ambiguous_negated_and_other_country_locations_are_not_guessed(self):
        args = {"city": "Houston"}
        self.assertEqual(location.bind_location(args, "Compare Houston Texas and Houston Alaska"), args)
        self.assertEqual(location.bind_location(args, "Not Houston Texas"), args)
        self.assertEqual(location.bind_location(args, "Houston in the morning"), args)
        foreign = {"city": "Houston", "country_code": "CA"}
        self.assertEqual(location.bind_location(foreign, "Houston Texas"), foreign)
        invalid = {"city": "Houston", "country_code": None}
        self.assertEqual(location.bind_location(invalid, "Houston Texas"), invalid)

    async def test_wrapper_preserves_original_run_and_other_tools(self):
        captured = []

        async def run(ctx, args):
            captured.append(args)
            if ctx.capability_report.get("ai_privacy_mode") == "local_only":
                raise ValueError("privacy denied")
            return {"status": "ok"}

        original = Tool(
            Spec("get_weather", "Weather", {"properties": {"city": {"type": "string"}}, "required": ["city"]}),
            "Weather",
            run,
        )
        namespace = {"TOOLS": {"get_weather": original, "other": "unchanged"}}
        location.install(namespace)
        new = namespace["TOOLS"]["get_weather"]
        self.assertEqual(namespace["TOOLS"]["other"], "unchanged")
        self.assertNotIn("region", original.spec.parameters["required"])
        self.assertIn("region", new.spec.parameters["required"])
        ctx = SimpleNamespace(weather_question="weather in Houston Texas", capability_report={})
        await new.run(ctx, {"city": "Houston"})
        self.assertEqual(captured[0]["region"], "Texas")
        ctx.capability_report = {"ai_privacy_mode": "local_only"}
        with self.assertRaisesRegex(ValueError, "privacy denied"):
            await new.run(ctx, {"city": "Houston"})

    def test_chat_patch_preserves_source_and_is_idempotent(self):
        source = "def f(toolbox, capabilities, turn):\n    toolbox.ctx.capability_report = capabilities\n"
        patched = installer.patch_chat(source)
        self.assertIn("    toolbox.ctx.weather_question = turn.question\n", patched)
        self.assertEqual(installer.patch_chat(patched), patched)
        with self.assertRaises(ValueError):
            installer.patch_chat("x = 1")

    def test_tool_patch_requires_existing_weather_and_does_not_replace_source(self):
        with self.assertRaises(ValueError):
            installer.patch_source("x = 1")
        original = "_register_dhanz_weather(globals())\n_DHANZ_WEATHER_FIX_VERSION = 1\n"
        patched = installer.patch_source(original)
        self.assertTrue(patched.startswith(original))
        self.assertEqual(installer.patch_source(patched), patched)

    def test_embedded_location_module_is_the_reviewed_source(self):
        self.assertEqual(installer.location_source(), (ROOT / "backend/app/services/weather_location.py").read_text())


if __name__ == "__main__":
    unittest.main()
