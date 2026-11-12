"""Public web-only release channel. Shared by API checks and the local installer."""

import json
import re
import time
import urllib.request

CHANNEL_URL = "https://github.com/rodsangle/DhanzAI/releases/download/web-update-channel/latest-web.json"
PREFIX = "https://github.com/rodsangle/DhanzAI/releases/download/"


def version_key(version, build=0):
    if not isinstance(version, str) or not re.fullmatch(r"\d{1,5}\.\d{1,5}\.\d{1,5}", version):
        raise ValueError("Invalid web version.")
    if isinstance(build, bool) or not isinstance(build, int) or not 0 <= build <= 2_000_000_000:
        raise ValueError("Invalid web build number.")
    return (*map(int, version.split(".")), build)


def validate_release(data):
    if (
        not isinstance(data, dict)
        or type(data.get("schema")) is not int
        or type(data.get("protocol")) is not int
        or data.get("schema") != 1
        or data.get("protocol") != 1
    ):
        raise ValueError("This web release requires a different updater protocol.")
    version_key(data.get("version"), data.get("build"))
    for key, pattern in (
        ("release", r"web-updates-\d+\.\d+\.\d+-preview\.\d+"),
        ("asset", r"dhanz-web-\d+\.\d+\.\d+-update\.zip"),
        ("sha256", r"[0-9a-f]{64}"),
        ("source_commit", r"[0-9a-f]{40}"),
    ):
        if not isinstance(data.get(key), str) or not re.fullmatch(pattern, data[key]):
            raise ValueError("Invalid web release " + key + ".")
    if data["asset"] != "dhanz-web-" + data["version"] + "-update.zip":
        raise ValueError("Asset version differs from release version.")
    if not data["release"].startswith("web-updates-" + data["version"] + "-preview."):
        raise ValueError("Release tag version differs from manifest.")
    return {
        key: data[key]
        for key in ("schema", "protocol", "version", "build", "release", "asset", "sha256", "source_commit")
    }


def fetch_release():
    request = urllib.request.Request(  # noqa: S310 - fixed public HTTPS GitHub release channel, no credentials
        CHANNEL_URL + "?check=" + str(int(time.time())), headers={"Cache-Control": "no-cache"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:  # noqa: S310
        data = response.read(16385)
    if len(data) > 16384:
        raise ValueError("Web release manifest exceeds its size limit.")
    return validate_release(json.loads(data))


def package_url(release):
    release = validate_release(release)
    return PREFIX + release["release"] + "/" + release["asset"]
