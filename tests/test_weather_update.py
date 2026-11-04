"""Portable checks: python -m unittest discover -s tests -p test_weather_update.py."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


weather = load("weather", "backend/app/services/weather_tools.py")
installer = load("weather_install", "deploy/updaters/install_weather_tool.py")
PLACE = {
    "name": "Miami",
    "admin1": "Florida",
    "country": "United States",
    "country_code": "US",
    "latitude": 25.77,
    "longitude": -80.19,
}


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    async def test_city_forecast_and_units(self):
        requests = []

        def serve(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(200, json={"results": [PLACE]})
            return httpx.Response(
                200,
                json={
                    "timezone": "America/New_York",
                    "utc_offset_seconds": -18000,
                    "current": {"time": "2026-11-04T12:00", "temperature_2m": 80},
                    "current_units": {"temperature_2m": "°F"},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            result = await weather.lookup_weather(
                {"city": "Miami", "country_code": "US", "region": "Florida", "units": "imperial"}, client=client
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["current_units"]["temperature_2m"], "°F")
        self.assertEqual(requests[1].url.params["temperature_unit"], "fahrenheit")
        self.assertEqual(result["timezone"], "America/New_York")
        self.assertEqual(result["source"], weather.SOURCE_URL)

    async def test_ambiguous_place_does_not_get_forecast(self):
        requests = []

        def serve(request):
            requests.append(request)
            return httpx.Response(200, json={"results": [PLACE, {**PLACE, "admin1": "Oklahoma"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            result = await weather.lookup_weather({"city": "Miami"}, client=client)
        self.assertEqual(result["status"], "needs_location")
        self.assertEqual(len(requests), 1)

    async def test_region_disambiguates(self):
        def serve(request):
            if request.url.host.startswith("geocoding"):
                return httpx.Response(200, json={"results": [PLACE, {**PLACE, "admin1": "Oklahoma"}]})
            return httpx.Response(200, json={"current": {"time": "2026-11-04T12:00"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            result = await weather.lookup_weather({"city": "Miami", "region": "Florida"}, client=client)
        self.assertEqual(result["place"]["admin1"], "Florida")

    async def test_invalid_days_do_not_send_request(self):
        for days in (True, 0, 8, "3"):
            with self.assertRaises(ValueError):
                await weather.lookup_weather({"city": "Miami", "days": days})

    async def test_redirect_does_not_follow_untrusted_url(self):
        requests = []

        def serve(request):
            requests.append(request)
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve), follow_redirects=False) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                await weather.lookup_weather({"city": "Miami"}, client=client)
        self.assertEqual(len(requests), 1)

    async def test_privacy_and_provider_failure(self):
        class InputError(Exception):
            pass

        def tool_spec(*args):
            return SimpleNamespace(name=args[0], description=args[1], parameters=args[2])

        ns = {
            "TOOLS": {"existing": "unchanged"},
            "Tool": lambda *args: SimpleNamespace(run=args[2]),
            "ToolSpec": tool_spec,
            "ToolOutcome": lambda *args: args,
            "ToolInputError": InputError,
        }
        weather.register(ns)
        self.assertEqual(ns["TOOLS"]["existing"], "unchanged")
        with self.assertRaisesRegex(InputError, "local-only"):
            await ns["TOOLS"]["get_weather"].run(
                SimpleNamespace(capability_report={"ai_privacy_mode": "local_only"}), {"city": "Miami"}
            )
        original = weather.lookup_weather

        async def failed(args):
            raise httpx.ConnectError("private connection details")

        weather.lookup_weather = failed
        try:
            with self.assertRaises(InputError) as error:
                await ns["TOOLS"]["get_weather"].run(SimpleNamespace(capability_report={}), {"city": "Miami"})
            self.assertNotIn("private connection details", str(error.exception))
        finally:
            weather.lookup_weather = original


class InstallerTests(unittest.TestCase):
    def test_bundle_matches_reviewed_source(self):
        self.assertEqual(installer.weather_source(), (ROOT / "backend/app/services/weather_tools.py").read_text())

    def test_unknown_interface_is_rejected(self):
        with self.assertRaises(ValueError):
            installer.patch_source("x = 1")

    def test_additive_patch_and_idempotence(self):
        source = """
class Tool:
    spec: object
    label: str
    run: object
class ToolInputError(Exception): pass
class ToolOutcome: pass
class ToolBox:
    def specs(self): return [t.spec for t in TOOLS.values()]
    def run(self, name): return TOOLS.get(name)
"""
        patched = installer.patch_source(source)
        self.assertTrue(patched.startswith(source))
        self.assertEqual(installer.patch_source(patched), patched)


if __name__ == "__main__":
    unittest.main()
