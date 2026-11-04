"""Package compiled web assets only, after the client build workflow passes."""

import hashlib
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "client_releases/0.9.5-coding"
WEB = APP / "build/web"
OUTPUT = ROOT / "dist/coding-workspace"
RELEASE = "coding-workspace-0.9.5-preview.1"
PACKAGE = "dhanz-web-0.9.5-coding.zip"


def main():
    for name in ("index.html", "main.dart.js", "flutter_bootstrap.js", "version.json"):
        if not (WEB / name).is_file():
            raise ValueError("A complete compiled browser build is required.")
    metadata = json.loads((WEB / "version.json").read_text())
    if metadata.get("version") != "0.9.5" or str(metadata.get("build_number")) != "23":
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
                "base_version": "0.9.4+22",
                "source_commit": os.environ.get("GITHUB_SHA"),
                "source_subdirectory": "client_releases/0.9.5-coding",
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
    print("Packaged the checked browser build and checksum; no source archive or logs included.")


if __name__ == "__main__":
    main()
