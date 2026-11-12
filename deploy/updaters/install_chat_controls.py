"""Build read-aloud and draft-spelling controls from the AWS Flutter source.

Does not replace the backend, database or server settings. Default: build and test
only. --apply backs up and installs the checked static web build in place.
"""

import argparse
import base64
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from html.parser import HTMLParser
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
    "draft_spelling.dart": (
        "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"
        "+i5j4H/e2h39F/bzzH8GGwAA"
    ),
    "draft_spelling_test.dart": (
        "H4sIAAAAAAACA9VY32/iOBB+718x6kuC1MI7Zel1W1bqQ3WrLben0/XUuvEk8TXYOduBshX/+40dBwILlPux2u4LxLFnPPPN"
        "N58NYlIqbSEqWfLEMuzznMkv90z0UmS20mh6Sc5sj2uW2ntTYlEImXU50zY6OxIbxmlRWYu6N2H0KVjxyrp7i8b22oPG4Giq"
        "BIcJEzLuwMsRgJuMo0RNJkrCSGaFMDnYeakMlBQk6ilCwgwCkxxmuaD1tBlGJxAcAOBziYmN/TOAqbKMfF65vG5DWnE0xhwm"
        "aAxmeCcBZszAp9Hl9ejz6ApmIrfAQGMisLTdqHMSXEXjHL0VW7MaXddWNq+tUDir2qhz1g5peywfC3QJKZ0xKejB0i6JKlSl"
        "KVPLCpVV6KKAQ1e6PRf0uYTTYpJLkbACrHpCaTx4KcoEOdlzAlMjwatonUXexjJR0lgQsqwsvAswEBCW4MutLU2/16PnLj6z"
        "SVlgz2NGFaJ3P4V3XaolmKdTcv/nKb0/9SG4FfdUefrquepDtHL+4LwLSeDgw518eHgo5zZX8k669+/gOGxy7OfuZBhGZ62A"
        "a7wpu3bMBNYbihnFMuZ97PDQU+2bjA4hlN+CNvacWQ2+ooVmMzBWV4nrfx6q7KgR2s990dDspkeqNMSpkI5Z+OyIAr9HL8e0"
        "3XF/lfSCTKIBF9MhTQx67sG9SSpdLCvSQt5Vx81vQBf90ey6P30XCCXuv2qwFqvEP1Qu14FTnSFMVCVt/KvgGdox+UHtgUF9"
        "AmOyHnFhyeGlklaroqDZZPl4Ai+fWVHhJalohnzwqFQxPAclxyrLClx04N0wxFq77JbVpKy3ipe0uQnyeVGWq5cAuZpgH24T"
        "lqaq4O0ZgEfF531Yy/g9yaqS68ugFWu/HffGKo5TkeBFZVWiNCFt+0CEwM1lSl5tLgyZ95c5w/k5xPdUo8W6dac9bA2Wj1sq"
        "o2k3nG0rTQeYmcskMIHNmLANwpaVjou8+zgfUzmsKOOowQhUaQVJQ9QJnFizdLW5kPwWrS0w3rZi6dvRKo4++figOSYhFc94"
        "uO9F04J1fiaO6jKQOnsguUIDUlmCYabphCPBp2PsceKckoj5I9p14TZE6mZcFZw6aCuXfZv06yYLB2EUwndcPgeU7LFA3s6o"
        "7pemRdrN0HCgD/HUtYWjf+OBIqjfnX2nkpHveYnxZY7JE/KPqqzKG5TVtcXJ4NZq2mp4+BZBeUJuJyDMB1YYXJ9dQeP5crIV"
        "5q/2CupQn2C34gvy9+q5a3KK8CluImy55sLQtajh1ErYl6z6q8KK8Pd8MXRDkEAmLu4VcYM78w3ptCvPoz0auFsBD9S/Q9Tv"
        "IO3bp3zb1C4Qow+po8Wr0rftlhigmnmYBku+1mk2jB2ucXvHok6n+0MQlaiZYOEu+F5Wm4u+8XKntMg8C7+17u0XubVF4XwK"
        "gaxB2jol7OrngruKuRnzs8Q67f9aiI0T6dJDGP1jIXsjDGBlWcwh8Z1lqOlosDzq/JVUpSlqA5Xk6u1SYF+BLnyG//LGsK9c"
        "bZK9HsYvDsAfliWBEEgldQdb5VQuVIIEzt+Z1BS1uzVZlG+XKBt4UgDRzRwkziiYWua+H6E2Atmhbg4l+g3sf2/+5v6AqCtT"
        "dzDfKXf/P0cWR38D0tqC39oSAAA="
    ),
}


def asset(name):
    return gzip.decompress(base64.b64decode(_PAYLOADS[name])).decode()


def patch_tile(source):
    if "ReadAloudButton(" in source:
        if "import 'reply_reader.dart';" in source:
            return source
        raise ValueError("A different read-aloud integration exists. Nothing was changed.")
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


def patch_composer(source):
    if "DraftSpellingButton(" in source:
        if "import 'draft_spelling.dart';" in source and "autocorrect: _deviceAutocorrect" in source:
            return source
        raise ValueError("A different spelling integration exists. Nothing was changed.")
    controller = "  final _controller = TextEditingController();"
    field = "            controller: _controller,"
    toolbar = "                    IconButton(\n                      tooltip: 'Attach files',"
    if "class _ComposerState" not in source or any(
        source.count(anchor) != 1 for anchor in (controller, field, toolbar)
    ):
        raise ValueError("The current composer layout is unsupported. Nothing was changed.")
    if "_deviceAutocorrect" in source or "autocorrect:" in source or "enableSuggestions:" in source:
        raise ValueError("Existing spelling configuration needs review. Nothing was changed.")
    if source.count("import 'chat_controller.dart';") != 1:
        raise ValueError("The composer imports differ. Nothing was changed.")
    locked = "                      enabled: !chat.sending,\n" if "readOnly: chat.sending" in source else ""
    return (
        source.replace(
            "import 'chat_controller.dart';", "import 'chat_controller.dart';\nimport 'draft_spelling.dart';"
        )
        .replace(controller, controller + "\n  bool _deviceAutocorrect = true;")
        .replace(
            field,
            field
            + "\n            autocorrect: _deviceAutocorrect,\n            enableSuggestions: _deviceAutocorrect,",
        )
        .replace(
            toolbar,
            "                    DraftSpellingButton(\n" + locked + "                      controller: _controller,\n"
            "                      deviceAutocorrect: _deviceAutocorrect,\n"
            "                      onDeviceAutocorrectChanged: (value) => setState(() => _deviceAutocorrect = value),\n"
            "                    ),\n" + toolbar,
        )
    )


def require_current_features(root, target):
    # Known live custom feature: do not rebuild a browser with Local News from
    # stale source that lacks it. This check does not reconstruct compiled-only
    # customizations; the source must remain the authoritative application.
    compiled = (target / "main.dart.js").read_text(errors="replace").lower()
    if "local news" in compiled:
        source = "\n".join(p.read_text(errors="replace").lower() for p in (root / "lib").rglob("*.dart"))
        if "local news" not in source:
            raise ValueError(
                "The live browser has Local News, but local Flutter source lacks it. "
                "Nothing was changed; synchronize the current UI source first."
            )


def mounted_flutter_root(mounts, home):
    live = [m for m in mounts if m.get("Destination") == "/srv/web" and m.get("Type") == "bind"]
    if len(live) != 1:
        raise ValueError("A single Caddy /srv/web bind mount is required. Nothing was changed.")
    mounted = Path(live[0]["Source"]).resolve()
    legacy = (home / "DhanzAI/apps/dhanz_flutter/build/web").resolve()
    releases = (home / ".local/share/dhanz-server-sync/releases").resolve()
    release_mount = (
        mounted.name == "web-root"
        and mounted.parent.parent == releases
        and re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12,64}", mounted.parent.name)
    )
    if mounted != legacy and not release_mount:
        raise ValueError("The mounted web folder is outside the known Dhanz locations. Nothing was changed.")
    required = ("index.html", "main.dart.js", "flutter_bootstrap.js")
    for target in (mounted, mounted / "app"):
        if all((target / name).is_file() for name in required) and target.resolve().is_relative_to(mounted):
            return target.resolve()
    raise ValueError("No complete Flutter build was found at the mount root or its app folder. Nothing was changed.")


def require_matching_version(root, target):
    metadata = target / "version.json"
    if not metadata.is_file():
        raise ValueError("Live Flutter version metadata is unavailable. Confirm source provenance before rebuilding.")
    current = json.loads(metadata.read_text())
    match = re.search(
        r"^version:\s*['\"]?([0-9]+\.[0-9]+\.[0-9]+)(?:\+([0-9]+))?", (root / "pubspec.yaml").read_text(), re.M
    )
    if (
        not match
        or str(current.get("version")) != match[1]
        or (match[2] and str(current.get("build_number")) != match[2])
    ):
        raise ValueError(
            "The live Flutter version differs from this source. Use matching source with --source; nothing was changed."
        )


def current_base_href(target):
    class BaseParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "base":
                self.hrefs.extend(value for key, value in attrs if key.lower() == "href")

    parser = BaseParser()
    parser.feed((target / "index.html").read_text())
    href = parser.hrefs[0] if parser.hrefs else ("/app/" if target.name == "app" else "/")
    if len(parser.hrefs) > 1 or not isinstance(href, str) or not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*", href):
        raise ValueError("The browser base URL needs review before rebuilding. Nothing was changed.")
    return href


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


def deploy_files(stage, target, *, backup_parent=None):
    files = [p for p in stage.rglob("*") if p.is_file()]
    if not {"index.html", "main.dart.js", "flutter_bootstrap.js"}.issubset({p.name for p in files}):
        raise ValueError("The checked web build is incomplete. Nothing was installed.")
    for p in files:
        destination = target / p.relative_to(stage)
        if not destination.resolve().is_relative_to(target.resolve()):
            raise ValueError("A target symlink escapes the web directory. Nothing was installed.")
    backup = (backup_parent or target.parent) / ("web-before-read-aloud-" + str(time.time_ns()))
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
    parser.add_argument("--source", type=Path, help="Flutter app source matching the live client")
    args = parser.parse_args()
    root = (args.source or Path.home() / "DhanzAI/apps/dhanz_flutter").resolve()
    tile = root / "lib/features/chat/message_tile.dart"
    composer = root / "lib/features/chat/composer.dart"
    if not tile.is_file() or not (root / "pubspec.lock").is_file():
        raise ValueError("The current Flutter source and dependency lock are required. Nothing was changed.")
    if "flutter_tts:" not in (root / "pubspec.yaml").read_text():
        raise ValueError("The existing speech plugin is missing. Nothing was changed.")
    for name in ("reply_reader.dart", "draft_spelling.dart"):
        existing = root / "lib/features/chat" / name
        if existing.exists() and existing.read_text() != asset(name):
            raise ValueError("An existing " + name + " differs from this update. Nothing was changed.")
    patched = patch_tile(tile.read_text())
    patched_composer = patch_composer(composer.read_text())
    if patched == tile.read_text() and patched_composer == composer.read_text():
        print("Chat controls are present in source; validating and rebuilding the browser application.")
    original_fingerprint = source_fingerprint(root)
    flutter = shutil.which("flutter")
    if flutter is None:
        flutter = next(
            (
                str(p)
                for p in (
                    Path.home() / "flutter/bin/flutter",
                    Path.home() / "tools/flutter/bin/flutter",
                    Path("/opt/flutter/bin/flutter"),
                )
                if p.is_file()
            ),
            None,
        )
    if flutter is None:
        raise ValueError("Flutter was not found. Nothing was changed; share this message for SDK setup help.")
    mounts = json.loads(
        subprocess.check_output(
            ["/usr/bin/sudo", "/usr/bin/docker", "inspect", "deploy-caddy-1", "--format", "{{json .Mounts}}"], text=True
        )
    )
    target = mounted_flutter_root(mounts, Path.home())
    require_matching_version(root, target)
    require_current_features(root, target)
    base_href = current_base_href(target)
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
    (project / "lib/features/chat/composer.dart").write_text(patched_composer)
    (project / "lib/features/chat/draft_spelling.dart").write_text(asset("draft_spelling.dart"))
    (project / "lib/features/chat/reply_reader.dart").write_text(asset("reply_reader.dart"))
    (project / "test").mkdir(exist_ok=True)
    (project / "test/read_aloud_test.dart").write_text(asset("read_aloud_test.dart"))
    (project / "test/draft_spelling_test.dart").write_text(asset("draft_spelling_test.dart"))
    print("Building from your current AWS Flutter source in a private staging directory...", flush=True)
    commands = [
        ["pub", "get", "--enforce-lockfile"],
        [
            "analyze",
            "--no-pub",
            "lib/features/chat/reply_reader.dart",
            "lib/features/chat/message_tile.dart",
            "lib/features/chat/composer.dart",
            "lib/features/chat/draft_spelling.dart",
            "test/draft_spelling_test.dart",
            "test/read_aloud_test.dart",
        ],
        ["test", "--no-pub", "test/read_aloud_test.dart", "test/draft_spelling_test.dart"],
        [
            "build",
            "web",
            "--release",
            "--no-pub",
            "--dart-define=DHANZ_API_URL=https://dhanzai.com",
            "--base-href=" + base_href,
        ],
    ]
    for command in commands:
        subprocess.run([flutter, *command], cwd=project, check=True)  # noqa: S603 - local SDK, argument list, no shell.
    print("Chat-control analysis, tests and browser build passed.")
    if not args.apply:
        print("Prepared at: " + str(project / "build/web") + ". Live website is unchanged.")
        return
    # Save the exact installed source as well as the live browser backup. Existing
    # unrelated Flutter source changes remain intact.
    latest_mounts = json.loads(
        subprocess.check_output(
            ["/usr/bin/sudo", "/usr/bin/docker", "inspect", "deploy-caddy-1", "--format", "{{json .Mounts}}"], text=True
        )
    )
    if mounted_flutter_root(latest_mounts, Path.home()) != target:
        raise ValueError(
            "Caddy switched releases during the build. Nothing was installed; retry against the current release."
        )
    if web_fingerprint(target) != original_web:
        raise ValueError("The live browser build changed during validation. Nothing was installed; retry.")
    if source_fingerprint(root) != original_fingerprint:
        raise ValueError(
            "Flutter source changed during the build. Nothing was installed; retry with the current source."
        )
    before = stage / "message_tile.before.dart"
    before.write_text(tile.read_text())
    (stage / "composer.before.dart").write_text(composer.read_text())
    backup = deploy_files(project / "build/web", target, backup_parent=stage)
    tile.write_text(patched)
    composer.write_text(patched_composer)
    (root / "lib/features/chat/draft_spelling.dart").write_text(asset("draft_spelling.dart"))
    (root / "lib/features/chat/reply_reader.dart").write_text(asset("reply_reader.dart"))
    print("Read aloud and spelling controls installed. API, search, weather, OCR and database were not restarted.")
    print("Browser backup: " + str(backup))
    print("Original message source: " + str(before))
    print("Refresh dhanzai.com. Use the speaker beneath replies and Spelling options beside the attachment button.")


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
