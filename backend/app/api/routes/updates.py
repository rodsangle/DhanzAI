"""App update check for the desktop and mobile apps."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import SettingsDep
from app.schemas import UpdateInfo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/app", tags=["updates"])

Platform = Literal["windows", "macos", "android", "ios"]


def parse_version(v: str) -> tuple[int, ...]:
    """'1.2.3+45' or 'v1.2.3-beta.1' → (1, 2, 3). Pre-release/build suffixes are ignored."""
    m = re.match(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", v.strip())
    if not m:
        return (0,)
    return tuple(int(x or 0) for x in m.groups())


def _load_manifest(path: str | None) -> dict:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("Update manifest %s could not be read", path)
        return {}


@router.get("/updates", response_model=UpdateInfo)
async def check_for_update(
    settings: SettingsDep,
    platform: Platform,
    version: str = Query(max_length=40),
) -> UpdateInfo:
    """Compare the app's version with the latest release for its platform.

    Manifest format (written by .github/workflows/release.yml as latest.json):
    {"version": "0.4.0", "notes": "...", "minimum_version": "0.3.0",
     "platforms": {"windows": {"url": "https://...setup.exe", "sha256": "..."}, "android": {"url": "..."}}}
    """
    manifest = _load_manifest(settings.update_manifest_file)
    entry = (manifest.get("platforms") or {}).get(platform) or {}
    latest = manifest.get("version")
    url = entry.get("url")
    if not latest or not isinstance(url, str) or not url.startswith("https://"):
        return UpdateInfo(platform=platform, current_version=version, latest_version=latest, update_available=False)
    current = parse_version(version)
    newer = parse_version(latest) > current
    minimum = manifest.get("minimum_version")
    return UpdateInfo(
        platform=platform,
        current_version=version,
        latest_version=latest,
        update_available=newer,
        mandatory=bool(newer and minimum and current < parse_version(minimum)),
        url=url if newer else None,
        sha256=entry.get("sha256") if newer else None,
        notes=manifest.get("notes") if newer else None,
    )
