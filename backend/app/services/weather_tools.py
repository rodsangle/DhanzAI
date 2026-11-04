"""City-based live weather. No GPS collection and no user-selected network URLs."""

from datetime import UTC, datetime

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_URL = "https://open-meteo.com/"
MAX_RESPONSE_BYTES = 256_000


async def _json(client, url, params):
    async with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        body = bytearray()
        async for part in response.aiter_bytes():
            body.extend(part)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("Weather provider response is too large.")
    import json

    data = json.loads(body)
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("Weather provider returned an error.")
    return data


async def lookup_weather(args, *, client=None):
    city = args.get("city")
    country = args.get("country_code", "")
    region = args.get("region", "")
    units = args.get("units", "metric")
    days = args.get("days", 3)
    if not isinstance(city, str) or not 2 <= len(city.strip()) <= 100:
        raise ValueError("Supply a city name (2–100 characters).")
    if not isinstance(country, str) or (
        country and (len(country) != 2 or not country.isascii() or not country.isalpha())
    ):
        raise ValueError("country_code must be a two-letter country code, such as US.")
    if not isinstance(region, str) or len(region) > 100:
        raise ValueError("Supply a state or region name up to 100 characters.")
    if units not in {"metric", "imperial"}:
        raise ValueError("Units must be metric or imperial.")
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError("Forecast days must be an integer from 1 to 7.")
    if client is None:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as owned:
            return await lookup_weather(args, client=owned)
    params = {"name": city.strip(), "count": 10, "language": "en", "format": "json"}
    if country:
        params["countryCode"] = country.upper()
    geocoding = await _json(client, GEOCODING_URL, params)
    results = geocoding.get("results", [])
    if not isinstance(results, list):
        raise ValueError("Invalid location response.")
    places = [p for p in results if isinstance(p, dict)]
    if country:
        places = [p for p in places if p.get("country_code", "").upper() == country.upper()]
    if region:
        places = [p for p in places if str(p.get("admin1", "")).casefold() == region.strip().casefold()]
    if not places:
        return {"status": "not_found", "message": "Ask for the city, state/region and country.", "source": SOURCE_URL}
    if len(places) > 1:
        return {
            "status": "needs_location",
            "message": "Ask which place; no weather lookup has been made.",
            "places": [{k: p.get(k) for k in ("name", "admin1", "country", "country_code")} for p in places],
            "source": SOURCE_URL,
        }
    place = places[0]
    lat, lon = place.get("latitude"), place.get("longitude")
    if type(lat) not in (float, int) or type(lon) not in (float, int) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Weather provider returned invalid coordinates.")
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
        "forecast_days": days,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
        "temperature_unit": "fahrenheit" if units == "imperial" else "celsius",
        "wind_speed_unit": "mph" if units == "imperial" else "kmh",
        "precipitation_unit": "inch" if units == "imperial" else "mm",
    }
    forecast = await _json(client, FORECAST_URL, params)
    if not isinstance(forecast.get("current"), dict) or not forecast["current"].get("time"):
        raise ValueError("Current weather is unavailable; do not invent conditions.")
    return {
        "status": "ok",
        "place": {k: place.get(k) for k in ("name", "admin1", "country", "country_code")},
        "source": SOURCE_URL,
        "provider": "Open-Meteo (modelled weather, not a station observation)",
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "timezone": forecast.get("timezone"),
        "utc_offset_seconds": forecast.get("utc_offset_seconds"),
        "current": forecast["current"],
        "current_units": forecast.get("current_units", {}),
        "daily": forecast.get("daily", {}),
        "daily_units": forecast.get("daily_units", {}),
        "limitations": "No severe-weather alert feed. Do not claim no warnings exist. Report the provider timestamp.",
    }


def register(namespace):
    """Use the host's existing Tool classes without replacing its registry."""
    tools = namespace["TOOLS"]
    if "get_weather" in tools:
        raise ValueError("A get_weather tool already exists; inspect it before replacing it.")
    Tool, ToolSpec = namespace["Tool"], namespace["ToolSpec"]
    ToolOutcome, ToolInputError = namespace["ToolOutcome"], namespace["ToolInputError"]

    async def run(ctx, args):
        report = getattr(ctx, "capability_report", None) or {}
        if report.get("ai_privacy_mode") == "local_only":
            raise ToolInputError(
                "Live weather sends the requested city to Open-Meteo and is disabled in local-only mode."
            )
        count = getattr(ctx, "_weather_requests", 0)
        if count >= 2:
            raise ToolInputError("At most two weather lookups per reply. Ask for a clearer location.")
        ctx._weather_requests = count + 1
        try:
            result = await lookup_weather(args)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ToolInputError(
                "Live weather lookup failed or the inputs were invalid. "
                "Check the city and retry later; do not invent weather."
            ) from None
        return ToolOutcome(result, "Weather: " + result["status"])

    tools["get_weather"] = Tool(
        ToolSpec(
            "get_weather",
            "Look up live modelled weather and a 1–7 day forecast by city. Sends only the requested city/region to "
            "Open-Meteo; never uses GPS or the server location. Ask for missing or ambiguous places. "
            "Include source, timestamp, timezone and units. Not a severe-weather alert service.",
            {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name supplied by the user."},
                    "country_code": {"type": "string", "description": "Two-letter country code, for example US."},
                    "region": {
                        "type": "string",
                        "description": "State/region, for example Florida; use to disambiguate.",
                    },
                    "units": {"type": "string", "enum": ["metric", "imperial"]},
                    "days": {"type": "integer", "minimum": 1, "maximum": 7},
                },
                "required": ["city"],
            },
        ),
        "Checking live weather",
        run,
    )
