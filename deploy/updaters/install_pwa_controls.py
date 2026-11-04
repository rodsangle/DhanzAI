"""Install the checked 0.9.3 browser build over the matched 0.9.2 PWA only.

No Flutter SDK, Docker image rebuild, API restart, database change or APK is needed.
Default validates/stages only; --apply backs up and installs the static app assets.
"""

import argparse
import hashlib
import io
import json
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile

RELEASE = "client-controls-0.9.3-preview.1"
PACKAGE = "dhanz-web-0.9.3-controls.zip"
BASE = "https://github.com/rodsangle/DhanzAI/releases/download/" + RELEASE + "/"
BASE_RELEASE = "20261103T041017Z-5fb2c2e2a5c5"
BASE_SOURCE = "5fb2c2e2a5c55542869eae5d31a453f156bd44dedacc06815ac81f971cd1dee3"


def target_app(mounts, home):
    live = [m for m in mounts if m.get("Type") == "bind" and m.get("Destination") == "/srv/web"]
    if len(live) != 1:
        raise ValueError("Expected one Caddy /srv/web bind mount. Nothing was changed.")
    root = Path(live[0]["Source"]).resolve()
    releases = (home / ".local/share/dhanz-server-sync/releases").resolve()
    if (
        root.name != "web-root"
        or root.parent.parent != releases
        or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12,64}", root.parent.name)
    ):
        raise ValueError("Unknown Caddy release folder. Nothing was changed.")
    app = root / "app"
    if app.resolve().parent != root or not all(
        (app / name).is_file()
        for name in ("index.html", "main.dart.js", "flutter_bootstrap.js", "version.json", "release.json")
    ):
        raise ValueError("The nested Flutter PWA layout differs. Nothing was changed.")
    return app


def mounts():
    return json.loads(
        subprocess.check_output(
            ["/usr/bin/sudo", "/usr/bin/docker", "inspect", "deploy-caddy-1", "--format", "{{json .Mounts}}"], text=True
        )
    )


def require_base(app):
    version = json.loads((app / "version.json").read_text())
    release = json.loads((app / "release.json").read_text())
    if (
        version.get("version") == "0.9.3"
        and str(version.get("build_number")) == "21"
        and release.get("release_id") == RELEASE
    ):
        return False
    if (
        version.get("version") != "0.9.2"
        or str(version.get("build_number")) != "20"
        or release.get("release_id") != BASE_RELEASE
        or release.get("source_sha256") != BASE_SOURCE
    ):
        raise ValueError("The active client is not the verified 0.9.2 build. Nothing was changed.")
    return True


def fingerprint(app):
    digest = hashlib.sha256()
    for name in ("index.html", "main.dart.js", "flutter_bootstrap.js", "version.json", "release.json"):
        digest.update((app / name).read_bytes())
    return digest.hexdigest()


def unpack(data, stage):
    with ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 5000 or sum(e.file_size for e in entries) > 200_000_000:
            raise ValueError("Web build is too large.")
        names = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.filename in names
            ):
                raise ValueError("Unsafe web archive.")
            names.add(entry.filename)
        if not {"index.html", "main.dart.js", "flutter_bootstrap.js", "version.json", "release.json"}.issubset(names):
            raise ValueError("Incomplete browser build.")
        archive.extractall(stage)  # noqa: S202 - archive entries and symlinks were checked above.
    version = json.loads((stage / "version.json").read_text())
    release = json.loads((stage / "release.json").read_text())
    if (
        version.get("version") != "0.9.3"
        or str(version.get("build_number")) != "21"
        or release.get("release_id") != RELEASE
    ):
        raise ValueError("Unexpected package metadata.")
    if '<base href="/app/">' not in (stage / "index.html").read_text():
        raise ValueError("The package was not built for /app/.")


def copy_assets(stage, app):
    files = [p for p in stage.rglob("*") if p.is_file()]
    for path in files:
        if not (app / path.relative_to(stage)).resolve().is_relative_to(app.resolve()):
            raise ValueError("A target symlink escapes the app folder.")
    for source in sorted(files, key=lambda p: p.relative_to(stage).as_posix() == "index.html"):
        target = app / source.relative_to(stage)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".dhanz-controls-", delete=False) as handle:
            with source.open("rb") as content:
                shutil.copyfileobj(content, handle)
            temporary = Path(handle.name)
        temporary.chmod(0o644)
        temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    app = target_app(mounts(), Path.home())
    if args.rollback:
        backup = args.rollback.resolve()
        if (
            not backup.is_relative_to(Path.home().resolve())
            or backup.name != "backup"
            or not (backup / "index.html").is_file()
            or not (backup / "release.json").is_file()
        ):
            raise ValueError("Use the private backup path printed by this updater.")
        old = json.loads((backup / "release.json").read_text())
        if old.get("release_id") != BASE_RELEASE:
            raise ValueError("Unknown backup release.")
        copy_assets(backup, app)
        print("Previous browser client restored. Backend services were not restarted.")
        return
    if not require_base(app):
        print("The 0.9.3 controls build is already installed. Refresh/reopen Dhanz.")
        return
    before = fingerprint(app)
    with urlopen(BASE + PACKAGE + ".sha256", timeout=30) as response:  # noqa: S310 - fixed HTTPS release URL.
        expected = response.read(1000).decode().split()
    with urlopen(BASE + PACKAGE, timeout=60) as response:  # noqa: S310 - fixed HTTPS release URL.
        data = response.read(100_000_001)
    if (
        len(data) > 100_000_000
        or len(expected) != 2
        or expected[1] != PACKAGE
        or hashlib.sha256(data).hexdigest() != expected[0]
    ):
        raise ValueError("Browser download checksum or size validation failed.")
    work = Path(tempfile.mkdtemp(prefix="dhanz-pwa-controls-", dir=Path.home()))
    stage = work / "stage"
    stage.mkdir()
    unpack(data, stage)
    print("Checked browser package staged at: " + str(stage))
    if not args.apply:
        print("Website unchanged. Run with --apply to install.")
        return
    if target_app(mounts(), Path.home()) != app or fingerprint(app) != before:
        raise ValueError("The live release changed during preparation. Nothing was installed.")
    backup = work / "backup"
    shutil.copytree(app, backup)
    backup.chmod(0o700)
    print("Private browser backup: " + str(backup), flush=True)
    try:
        copy_assets(stage, app)
    except (OSError, ValueError):
        copy_assets(backup, app)
        raise ValueError("Installation failed; previous browser files were restored.") from None
    print("Dhanz 0.9.3 web controls installed. Backend, search, weather, OCR and wrapper were unchanged.")
    print("Refresh Edge with Ctrl+F5. Close and reopen the Android web app.")
    print("Use the speaker under finished replies and Spelling options beside Attach files.")
    print("Rollback: python3 " + str(Path(__file__).resolve()) + " --rollback " + str(backup))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
