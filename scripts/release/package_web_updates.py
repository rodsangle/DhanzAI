"""Package compiled web assets only, after the client build workflow passes."""

import hashlib
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "client_releases/0.10.0-updates"
WEB = APP / "build/web"
OUTPUT = ROOT / "dist/web-updates"
RELEASE = "web-updates-0.10.1-preview.1"
PACKAGE = "dhanz-web-0.10.1-update.zip"


def main():
    for name in (
        "index.html",
        "main.dart.js",
        "flutter_bootstrap.js",
        "version.json",
        "update.html",
        "force_update.js",
    ):
        if not (WEB / name).is_file():
            raise ValueError("A complete compiled browser build is required.")
    metadata = json.loads((WEB / "version.json").read_text())
    if metadata.get("version") != "0.10.1" or str(metadata.get("build_number")) != "31":
        raise ValueError("Unexpected browser version/build.")
    digest = hashlib.sha256()
    for path in sorted(APP.rglob("*")):
        relative = path.relative_to(APP)
        if path.is_file() and relative.parts[0] in {
            "lib",
            "web",
            "assets",
            "pubspec.yaml",
            "pubspec.lock",
            "analysis_options.yaml",
        }:
            digest.update(str(relative).replace("\\", "/").encode() + b"\0" + path.read_bytes() + b"\0")
    (WEB / "release.json").write_text(
        json.dumps(
            {
                "release_id": RELEASE,
                "source_sha256": digest.hexdigest(),
                "base_release_id": "20261103T041017Z-5fb2c2e2a5c5",
                "base_version": "0.9.9+27",
                "source_commit": os.environ.get("GITHUB_SHA"),
                "web_update_protocol": 1,
                "source_subdirectory": "client_releases/0.10.0-updates",
            },
            indent=2,
        )
        + "\n"
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    package = OUTPUT / PACKAGE
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        for path in sorted(WEB.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(WEB).as_posix())
    (OUTPUT / (PACKAGE + ".sha256")).write_text(
        hashlib.sha256(package.read_bytes()).hexdigest() + "  " + PACKAGE + "\n"
    )
    (OUTPUT / "latest-web.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "protocol": 1,
                "version": "0.10.1",
                "build": 31,
                "release": RELEASE,
                "asset": PACKAGE,
                "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                "source_commit": os.environ["GITHUB_SHA"],
            },
            indent=2,
        )
        + "\n"
    )
    print("Packaged checked web build, checksum and public web-update channel manifest.")


if __name__ == "__main__":
    main()
