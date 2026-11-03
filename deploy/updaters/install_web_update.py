"""Install a checked Dhanz web build while preserving its bind-mounted directory and backup."""

import argparse
import hashlib
import io
import json
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile

RELEASE = "updates-2026-11-03-preview.5"
BASE = f"https://github.com/rodsangle/DhanzAI/releases/download/{RELEASE}/"
PACKAGE = f"dhanz-web-{RELEASE}.zip"


def unpack(data, destination):
    with ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 5000 or sum(e.file_size for e in entries) > 200_000_000:
            raise ValueError("Web archive exceeds the supported size.")
        names = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise ValueError("Unsafe web archive path.")
            if entry.filename in names:
                raise ValueError("Duplicate web archive entry.")
            names.add(entry.filename)
        if not {"index.html", "main.dart.js", "flutter_bootstrap.js"}.issubset(names):
            raise ValueError("This archive is not a complete Flutter web build.")
        archive.extractall(destination)  # noqa: S202 - every path and symlink was validated above.


def install(stage, target):
    files = [p for p in stage.rglob("*") if p.is_file()]
    for path in files:
        destination = target / path.relative_to(stage)
        if not destination.resolve().is_relative_to(target.resolve()):
            raise ValueError("A target symlink leads outside the web directory. Nothing was installed.")
    backup = target.parent / ("web-backup-" + str(time.time_ns()))
    shutil.copytree(target, backup)
    backup.chmod(0o700)
    # Preserve the root directory inode used by Caddy's bind mount. Copy the
    # entry page last; existing assets remain available to already open tabs.
    for source in sorted(files, key=lambda p: p.relative_to(stage).as_posix() == "index.html"):
        destination = target / source.relative_to(stage)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".dhanz-web-", delete=False) as handle:
            with source.open("rb") as content:
                shutil.copyfileobj(content, handle)
            temporary = Path(handle.name)
        temporary.chmod(0o644)
        temporary.replace(destination)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path.home() / "DhanzAI"
    target = root / "apps/dhanz_flutter/build/web"
    mounts = json.loads(
        subprocess.check_output(  # noqa: S603 - fixed local Docker command, no shell.
            ["/usr/bin/sudo", "/usr/bin/docker", "inspect", "deploy-caddy-1", "--format", "{{json .Mounts}}"], text=True
        )
    )
    active = [m for m in mounts if m.get("Destination") == "/srv/web" and m.get("Type") == "bind"]
    if (
        len(active) != 1
        or Path(active[0]["Source"]).resolve() != target.resolve()
        or not (target / "index.html").is_file()
    ):
        raise ValueError("The live web mount differs from the expected Flutter build directory. Nothing was changed.")
    changed = subprocess.check_output(  # noqa: S603 - fixed Git query with argument array.
        [
            "/usr/bin/git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--untracked-files=normal",
            "--",
            "apps/dhanz_flutter/lib",
        ],
        text=True,
    )
    if changed.strip():
        raise ValueError(
            "Local Flutter source changes need review before replacing the browser build. Nothing was changed."
        )
    with urlopen(BASE + PACKAGE + ".sha256", timeout=30) as response:  # noqa: S310 - fixed HTTPS repository release URL.
        expected = response.read(1000).decode().split()
    with urlopen(BASE + PACKAGE, timeout=60) as response:  # noqa: S310 - fixed HTTPS repository release URL.
        data = response.read(100_000_001)
    if (
        len(data) > 100_000_000
        or len(expected) != 2
        or expected[1] != PACKAGE
        or hashlib.sha256(data).hexdigest() != expected[0]
    ):
        raise ValueError("Web package checksum or size validation failed. Nothing was changed.")
    stage = Path(tempfile.mkdtemp(prefix="dhanz-web-stage-", dir=Path.home()))
    unpack(data, stage)
    if not args.apply:
        print(f"Verified web build staged at {stage}. The live website is unchanged.")
        print("Run this helper with --apply to back up and update the live browser build.")
        return
    backup = install(stage, target)
    print("Web client updated. API, database, Caddy configuration and credentials were not replaced.")
    print(f"Previous browser build backed up at {backup}")
    print("Refresh dhanzai.com with Ctrl+Shift+R to load the new client.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
