"""Apply the latest verified GitHub web-channel build to the existing nested PWA.

No Flutter SDK, Docker image rebuild, API restart, database change or APK is needed.
Default validates/stages only; --apply backs up and installs the static app assets.
"""

import argparse
import fcntl
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

from web_release import fetch_release, package_url, version_key


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


KNOWN_BASES = {
    ("0.9.9", "27", "background-uploads-0.9.9-preview.1", "b687878ce6b40672e4ba471aeebd3a15eae81824"),
    ("0.9.8", "26", "connected-operations-0.9.8-preview.1", "3b8e9cc6033ec9362add2a0a405fbc054860cf47"),
    ("0.9.7", "25", "conversational-coding-0.9.7-preview.1", "ad3676339468124dcb8f3f88a8df61890b32c68e"),
    ("0.9.4", "22", "assistant-studio-0.9.4-preview.1", "26a7383513133bbe969ea36f81ca3225e14f6579"),
    ("0.9.5", "23", "coding-workspace-0.9.5-preview.1", "f3bb9e23721d1231e56c6327ea204fd7355a29ab"),
    ("0.9.6", "24", "reply-sharing-0.9.6-preview.1", "6acef27b4765d7e442bd930daee48d32d1a53358"),
}


def verified_base(app):
    version = json.loads((app / "version.json").read_text())
    release = json.loads((app / "release.json").read_text())
    legacy = (
        version.get("version"),
        str(version.get("build_number")),
        release.get("release_id"),
        release.get("source_commit"),
    ) in KNOWN_BASES
    modern = (
        release.get("web_update_protocol") == 1
        and re.fullmatch(r"[0-9a-f]{40}", str(release.get("source_commit", "")))
        and re.fullmatch(
            r"web-updates-" + re.escape(version.get("version", "")) + r"-preview\.\d+",
            str(release.get("release_id", "")),
        )
    )
    version_key(version.get("version"), int(version.get("build_number")))
    return bool(legacy or modern)


def require_base(app, release):
    if not verified_base(app):
        raise ValueError("The active client is not a supported web release. Nothing changed.")
    version = json.loads((app / "version.json").read_text())
    return version_key(release["version"], release["build"]) > version_key(
        version["version"], int(version["build_number"])
    )


def fingerprint(app):
    digest = hashlib.sha256()
    for name in ("index.html", "main.dart.js", "flutter_bootstrap.js", "version.json", "release.json"):
        digest.update((app / name).read_bytes())
    return digest.hexdigest()


def unpack(data, stage, expected):
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
        if not {
            "index.html",
            "main.dart.js",
            "flutter_bootstrap.js",
            "version.json",
            "release.json",
            "update.html",
            "force_update.js",
        }.issubset(names):
            raise ValueError("Incomplete browser build.")
        archive.extractall(stage)  # noqa: S202 - archive entries and symlinks were checked above.
    version = json.loads((stage / "version.json").read_text())
    release = json.loads((stage / "release.json").read_text())
    if (
        version.get("version") != expected["version"]
        or int(version.get("build_number")) != expected["build"]
        or release.get("release_id") != expected["release"]
        or release.get("source_commit") != expected["source_commit"]
        or release.get("web_update_protocol") != 1
    ):
        raise ValueError("Unexpected package metadata or web-update protocol.")
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
    lock_root = Path.home() / ".local/share/dhanz-web-updates"
    lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_root.chmod(0o700)
    lock = (lock_root / "update.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
        if not verified_base(backup):
            raise ValueError("Unknown backup release.")
        copy_assets(backup, app)
        print("Previous browser client restored. Backend services were not restarted.")
        return
    release = fetch_release()
    if not require_base(app, release):
        print("The served web app is already current. Refresh the phone app.")
        return
    check = subprocess.check_output(
        [
            "/usr/bin/sudo",
            "/usr/bin/docker",
            "exec",
            "deploy-api-1",
            "python",
            "-c",
            "import httpx; print(httpx.get('http://127.0.0.1:8000/api/v1/operations/web-updates').status_code)",
        ],
        text=True,
    ).strip()
    if check != "401":
        raise ValueError("Install the coding-workspace backend first. Browser unchanged.")
    before = fingerprint(app)
    with urlopen(package_url(release), timeout=60) as response:  # noqa: S310 - validated fixed GitHub repo URL
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != release["sha256"]:
        raise ValueError("Browser download checksum or size validation failed.")
    work = Path(tempfile.mkdtemp(prefix="dhanz-web-updates-", dir=Path.home()))
    stage = work / "stage"
    stage.mkdir()
    unpack(data, stage, release)
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
    (lock_root / "last-update.json").write_text(
        json.dumps(
            {
                "version": release["version"],
                "build": release["build"],
                "backup": str(backup),
                "sha256": release["sha256"],
            }
        )
    )
    print("GitHub web build " + release["version"] + " installed. API, data and wrapper were preserved.")
    print("Refresh Edge with Ctrl+F5. Close and reopen the Android web app.")
    print("Use Settings > App update > Update to check GitHub, install on your host and refresh the phone app.")
    print("Rollback: python3 " + str(Path(__file__).resolve()) + " --rollback " + str(backup))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
