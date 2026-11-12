"""Bind an explicitly stated US city/state to the existing weather tool call."""

import re
from copy import deepcopy
from dataclasses import is_dataclass, replace

# Full names and postal codes, not IP address geolocation or saved personal data.
_STATES = (
    ("Alabama", "AL"),
    ("Alaska", "AK"),
    ("Arizona", "AZ"),
    ("Arkansas", "AR"),
    ("California", "CA"),
    ("Colorado", "CO"),
    ("Connecticut", "CT"),
    ("Delaware", "DE"),
    ("Florida", "FL"),
    ("Georgia", "GA"),
    ("Hawaii", "HI"),
    ("Idaho", "ID"),
    ("Illinois", "IL"),
    ("Indiana", "IN"),
    ("Iowa", "IA"),
    ("Kansas", "KS"),
    ("Kentucky", "KY"),
    ("Louisiana", "LA"),
    ("Maine", "ME"),
    ("Maryland", "MD"),
    ("Massachusetts", "MA"),
    ("Michigan", "MI"),
    ("Minnesota", "MN"),
    ("Mississippi", "MS"),
    ("Missouri", "MO"),
    ("Montana", "MT"),
    ("Nebraska", "NE"),
    ("Nevada", "NV"),
    ("New Hampshire", "NH"),
    ("New Jersey", "NJ"),
    ("New Mexico", "NM"),
    ("New York", "NY"),
    ("North Carolina", "NC"),
    ("North Dakota", "ND"),
    ("Ohio", "OH"),
    ("Oklahoma", "OK"),
    ("Oregon", "OR"),
    ("Pennsylvania", "PA"),
    ("Rhode Island", "RI"),
    ("South Carolina", "SC"),
    ("South Dakota", "SD"),
    ("Tennessee", "TN"),
    ("Texas", "TX"),
    ("Utah", "UT"),
    ("Vermont", "VT"),
    ("Virginia", "VA"),
    ("Washington", "WA"),
    ("West Virginia", "WV"),
    ("Wisconsin", "WI"),
    ("Wyoming", "WY"),
    ("District of Columbia", "DC"),
)
_CANONICAL = {alias.casefold(): name for name, abbreviation in _STATES for alias in (name, abbreviation)}
_FULL_NAMES = "|".join(re.escape(name) for name, _ in sorted(_STATES, key=lambda pair: -len(pair[0])))
# Avoid reading ordinary lowercase words such as "in" as postal abbreviations.
_ABBREVIATIONS = "|".join(
    "(?-i:" + abbreviation + ")" if abbreviation in {"IN", "OR", "ME", "HI", "OK"} else abbreviation
    for _, abbreviation in _STATES
)
_STATE_PATTERN = "(?:" + _FULL_NAMES + "|" + _ABBREVIATIONS + ")"
LOCATION_FIX_VERSION = 1


def bind_location(args, question):
    result = dict(args)
    city = args.get("city")
    if not isinstance(city, str) or not 2 <= len(city.strip()) <= 100:
        return result
    country = args.get("country_code", "")
    if not isinstance(country, str) or country.upper() not in {"", "US"}:
        return result
    city = city.strip()
    suffix = None
    if city.casefold() not in _CANONICAL:
        suffix = re.fullmatch(r"(.+?)(?:\s*,\s*|\s+)(" + _STATE_PATTERN + r")", city, re.I)
    if suffix:
        city = suffix[1].strip()
        result.update(city=city, region=_CANONICAL[suffix[2].casefold()], country_code="US")
    if not isinstance(question, str):
        return result
    pattern = re.compile(
        r"\b"
        + re.escape(city)
        + r"(?:[ \t]*,[ \t]*|[ \t]+)(?:(?:in the state of|in)[ \t]+)?("
        + _STATE_PATTERN
        + r")\b",
        re.I,
    )
    regions = set()
    for match in pattern.finditer(question[:12000]):
        prefix = question[max(0, match.start() - 40) : match.start()]
        if re.search(r"\b(?:not|not in|avoid|don't use|do not use)[ \t]+$", prefix, re.I):
            continue
        regions.add(_CANONICAL[match[1].casefold()])
    if len(regions) == 1:
        result.update(city=city, region=regions.pop(), country_code="US")
    return result


def install(namespace):
    tool = namespace["TOOLS"].get("get_weather")
    if tool is None or not is_dataclass(tool) or not is_dataclass(tool.spec):
        raise ValueError("The installed weather tool interface is unsupported.")
    parameters = deepcopy(tool.spec.parameters)
    parameters["properties"]["region"] = {
        "type": "string",
        "description": "State/region already stated by the user, e.g. Texas in 'Houston Texas'. "
        "Do not drop it or ask them to repeat it. Use an empty string only if no region was supplied.",
    }
    parameters["required"] = list(dict.fromkeys([*parameters.get("required", ["city"]), "region"]))

    async def run(ctx, args):
        return await tool.run(ctx, bind_location(args, getattr(ctx, "weather_question", "")))

    namespace["TOOLS"]["get_weather"] = replace(
        tool,
        spec=replace(
            tool.spec,
            parameters=parameters,
            description=tool.spec.description + " Weather works independently of web search. "
            "Carry the user's explicit state/region into the lookup. Do not ask for a state already provided.",
        ),
        run=run,
    )
