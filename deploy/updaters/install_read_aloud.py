"""Build a read-aloud update from the AWS machine's current Flutter source.

Does not replace the backend, database or server settings. Default: build and test
only. --apply backs up and installs the checked static web build in place.
"""

import argparse
import base64
import gzip
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

_PAYLOADS = {
    "reply_reader.dart": (
        "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"
    ),
    "read_aloud_test.dart": (
        "H4sIAAAAAAACA+1XS2/jNhC+51fMosWKCgw56dF5tLvZBj10u0CcoockSGhpbDGmSYGkkjhF/nuHDz/k5rUpFr3sxZY5r29m"
        "Pg3HYtZo4yCruHEDbueqzPa2tkQ6bXg55RMcVDVX95dc9MfIXWvQ9suau77BRs4vDfIKTeE9kO2m6Vi2zqHpzzh9Ci5f0Lt0"
        "aF1//cfCYKuU3Fo45lM88XGHDWJZA/mROEPlLKwf/70FMBaKS7CNnqKCA9gfOiPU5PDsYo+ER9obUpD9Gy2qw5+hQVWR2MtG"
        "WksYcyHJasylRYoO8Iu+QWNEhfR83PoyRFOKgHzKondweOfyEB5AjIF5NzkYJH2VzApyow0ZUEl+DY/Zn4rfkCIfSczyfC9Y"
        "R+AFryoWnMbTBJOQbWTAkkIKlfTeFeMQ08sens/C6YblEDiQ8FMBha2j42DsNZenKyWqctkaQ00gWGt1XEerWin3llVZqL+L"
        "Anj/Ht6ls0LYRWZVvvBblOloAYbgBDAzLlSC4snCssZoizBFbCxITaFLrZwPxVUFnqq+xiCFmgKVG6XNerCRi682ITYrOp3S"
        "Cct+gN9QSg3b27fayGp7+1ydfdKlvWC1c40d9Pt4xz1MjzY/V1dXV9f2XFksqSeEo8JwlqVG4V2DpQu97QWUlIplWYwRIoD3"
        "vuRDR1/YP7RjK6sFAtJ+jfoappVFzJ4iV5bS/13QuzdBhYZoynZ/2tmhQokcDg4h8zo/iiwvrjWVP4Os46GsWzW13QoehTMW"
        "nHcBRu1Copq4ugcT6hFx+pQmDtvNH1VFYvCcsTJgKZMl7B/A7s7OTu6TPTUtPmq6xNuDFZSHPLzfkT/2Vriy9pz16AVaKLkq"
        "iSfgaoTG4I3QrY2pAenWuqU6SuTx7ScdhbegFUZebbxOYR6FAXWwOclYp4ZxqJJW0DgJv1g07eiNhbGerF9G1z7NjoyarIn0"
        "jwuD4UmrQpvCAHd6MpHIgqAH2XHwHPJctJffcuE6U6OoUPI5VuxTSzQRWhX3aHS39Mm9sD4LKlKMsNmndciPwYoSwjWMWf0X"
        "YFF9UYHnwca4T7AqNqSIk7oHZ52ibWK96ERPgcLUTTHWxctCvBrdsb+olndAvJIFIbOLmbli+V+imqCjMeD1YER3rVYwIlcz"
        "ovuQEIVhyRcEKqUop+F+sIm9ntveEZpvyfBYiRinaNpZE3GzIAT4nDaKD02zOAKoKYcBDEs+HmtZrc79pV7NB+DjfJC6rT6G"
        "rMN4HEAcupRVBDVI33lvab98TA+PQXS8IW6rqhjNT2mDcKJhmY8H3AdczvF/pcW6pNp0ERpiYsP94PJy+0VhrMYLhIyJXbwW"
        "bjfWGwGv5/wE3KdaS3yj92co7rH6qO8KW9NUnbL8q2k90zeLcUyctrRgfufvN+fv25r6ErsSpdMmGVYZ2hi/khGppWHxtt6z"
        "pD0I0s4tpHDzOPKoird+gzbzt1KkKNIfB0e3xXe+vHZ8eFxHcT3199qaH2o4tOt/j56fgP/7MHrY+gdHBogbVA8AAA=="
    ),
}


def asset(name):
    return gzip.decompress(base64.b64decode(_PAYLOADS[name])).decode()


def patch_tile(source):
    if "ReadAloudButton(" in source:
        raise ValueError("Read-aloud controls already exist. Nothing was changed; inspect the current version.")
    anchor = "                    if (isLast && !busy)"
    if source.count(anchor) != 1 or source.count("Widget _assistant(BuildContext context)") != 1:
        raise ValueError("The reply layout is different. Nothing was changed; inspect it first.")
    if source.index(anchor) < source.index("Widget _assistant(BuildContext context)"):
        raise ValueError("The reply action anchor is outside the assistant reply. Nothing was changed.")
    if "if (!streaming)" not in source or "import 'markdown_view.dart';" not in source:
        raise ValueError("The streaming/import interface is different. Nothing was changed.")
    return source.replace(
        "import 'markdown_view.dart';", "import 'markdown_view.dart';\nimport 'reply_reader.dart';"
    ).replace(
        anchor,
        "                    if (message.content.trim().isNotEmpty)\n"
        "                      ReadAloudButton(key: ValueKey(message.id), text: message.content),\n" + anchor,
    )


def source_fingerprint(root):
    digest = hashlib.sha256()
    candidates = [root / "pubspec.yaml", root / "pubspec.lock"]
    for name in ("lib", "web", "assets"):
        directory = root / name
        if directory.is_dir():
            candidates.extend(p for p in directory.rglob("*") if p.is_file())
    for path in sorted(candidates):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def web_fingerprint(target):
    digest = hashlib.sha256()
    for name in ("index.html", "main.dart.js", "flutter_bootstrap.js"):
        digest.update((target / name).read_bytes())
    return digest.hexdigest()


def deploy_files(stage, target):
    files = [p for p in stage.rglob("*") if p.is_file()]
    if not {"index.html", "main.dart.js", "flutter_bootstrap.js"}.issubset({p.name for p in files}):
        raise ValueError("The checked web build is incomplete. Nothing was installed.")
    for p in files:
        destination = target / p.relative_to(stage)
        if not destination.resolve().is_relative_to(target.resolve()):
            raise ValueError("A target symlink escapes the web directory. Nothing was installed.")
    backup = target.parent / ("web-before-read-aloud-" + str(time.time_ns()))
    shutil.copytree(target, backup)
    backup.chmod(0o700)
    for source in sorted(files, key=lambda p: p.relative_to(stage).as_posix() == "index.html"):
        destination = target / source.relative_to(stage)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".dhanz-reader-", delete=False) as handle:
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
    root = Path.home() / "DhanzAI/apps/dhanz_flutter"
    tile = root / "lib/features/chat/message_tile.dart"
    if not tile.is_file() or not (root / "pubspec.lock").is_file():
        raise ValueError("The current Flutter source and dependency lock are required. Nothing was changed.")
    if "flutter_tts:" not in (root / "pubspec.yaml").read_text():
        raise ValueError("The existing speech plugin is missing. Nothing was changed.")
    if (root / "lib/features/chat/reply_reader.dart").exists():
        raise ValueError("An existing reply_reader.dart needs review before updating. Nothing was changed.")
    patched = patch_tile(tile.read_text())
    original_fingerprint = source_fingerprint(root)
    flutter = shutil.which("flutter")
    if flutter is None:
        flutter = next(
            (str(p) for p in (Path.home() / "flutter/bin/flutter", Path("/opt/flutter/bin/flutter")) if p.is_file()),
            None,
        )
    if flutter is None:
        raise ValueError("Flutter was not found. Nothing was changed; share this message for SDK setup help.")
    mounts = json.loads(
        subprocess.check_output(
            ["/usr/bin/sudo", "/usr/bin/docker", "inspect", "deploy-caddy-1", "--format", "{{json .Mounts}}"], text=True
        )
    )
    live = [m for m in mounts if m.get("Destination") == "/srv/web" and m.get("Type") == "bind"]
    target = root / "build/web"
    if len(live) != 1 or Path(live[0]["Source"]).resolve() != target.resolve() or not (target / "index.html").is_file():
        raise ValueError("The live Caddy web mount is different. Nothing was changed.")
    original_web = web_fingerprint(target)
    stage = Path(tempfile.mkdtemp(prefix="dhanz-reader-build-", dir=Path.home()))
    stage.chmod(0o700)
    project = stage / "app"
    shutil.copytree(
        root,
        project,
        ignore=shutil.ignore_patterns("build", ".dart_tool", ".git", ".env", ".env.*", "ephemeral", ".gradle"),
    )
    (project / "lib/features/chat/message_tile.dart").write_text(patched)
    (project / "lib/features/chat/reply_reader.dart").write_text(asset("reply_reader.dart"))
    (project / "test").mkdir(exist_ok=True)
    (project / "test/read_aloud_test.dart").write_text(asset("read_aloud_test.dart"))
    print("Building from your current AWS Flutter source in a private staging directory...", flush=True)
    commands = [
        ["pub", "get", "--enforce-lockfile"],
        [
            "analyze",
            "--no-pub",
            "lib/features/chat/reply_reader.dart",
            "lib/features/chat/message_tile.dart",
            "test/read_aloud_test.dart",
        ],
        ["test", "--no-pub", "test/read_aloud_test.dart"],
        ["build", "web", "--release", "--no-pub", "--dart-define=DHANZ_API_URL=https://dhanzai.com"],
    ]
    for command in commands:
        subprocess.run([flutter, *command], cwd=project, check=True)  # noqa: S603 - local SDK, argument list, no shell.
    print("Read-aloud analysis, tests and browser build passed.")
    if not args.apply:
        print("Prepared at: " + str(project / "build/web") + ". Live website is unchanged.")
        return
    # Save the exact installed source as well as the live browser backup. Existing
    # unrelated Flutter source changes remain intact.
    if web_fingerprint(target) != original_web:
        raise ValueError("The live browser build changed during validation. Nothing was installed; retry.")
    if source_fingerprint(root) != original_fingerprint:
        raise ValueError(
            "Flutter source changed during the build. Nothing was installed; retry with the current source."
        )
    before = stage / "message_tile.before.dart"
    before.write_text(tile.read_text())
    backup = deploy_files(project / "build/web", target)
    tile.write_text(patched)
    (root / "lib/features/chat/reply_reader.dart").write_text(asset("reply_reader.dart"))
    print("Read aloud installed. API, weather, OCR and database were not restarted.")
    print("Browser backup: " + str(backup))
    print("Original message source: " + str(before))
    print("Refresh dhanzai.com, then click the speaker icon beneath a finished reply.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Build or validation failed (exit {exc.returncode}). "
            "The live website is changed only after validation passes."
        ) from None
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
