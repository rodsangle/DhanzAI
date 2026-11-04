"""Apply the reviewed four-file update to the original laptop source only.

Does not deploy or access AWS, read secrets, or build an APK. Default stages;
--apply writes only the four verified files with private backups.
"""

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen

BASE = "https://raw.githubusercontent.com/rodsangle/DhanzAI/102ed7a35347319a5a01ee6cc3e9341219dc3d58/client_releases/0.9.3-controls/"
FILES = {
    "pubspec.yaml": {
        "before": "5414b4967997a03a6af936df7686ecb7bdd7b2d363cdedb0f3f88cd8c302eb17",
        "after": "8ed6d23ce1743e9ea40940b0d83db5a3251d993b1efaf88a24cd41fcdedb97f7",
    },
    "lib/features/chat/composer.dart": {
        "before": "9c158f868cf530b5c1c24f161a2af1530f2e4640a12279dca88211bbc0b4820e",
        "after": "25c03e47b528fec625c8e9f1c655b154ce7c7913cac9561a22c14d646ec2a9d8",
    },
    "lib/features/chat/message_tile.dart": {
        "before": "b65a61bd6336f8909a7fb1c9af462f9e072e2a895b044097a53d209d29c84279",
        "after": "c744f533d2c12a26b5e4c8f09bd4144bb33645a9967d07df06427bbbe9c97392",
    },
    "lib/features/chat/draft_spelling.dart": {
        "before": None,
        "after": "9f6b6051439e9638fd6a77fcf18e034ca765287a3e4f18a5861a086dd324e903",
    },
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    if not (source / "pubspec.yaml").is_file():
        raise ValueError("Select the original Flutter app source folder.")
    for name, hashes in FILES.items():
        if digest(source / name) not in {hashes["before"], hashes["after"]}:
            raise ValueError("Source changed since upload; inspect before replacing: " + name)
    work = Path(tempfile.mkdtemp(prefix="dhanz-client-source-", dir=Path.home()))
    for name, hashes in FILES.items():
        with urlopen(BASE + name, timeout=30) as response:  # noqa: S310 - fixed HTTPS repository URL.
            data = response.read(1_000_001)
        if len(data) > 1_000_000 or hashlib.sha256(data).hexdigest() != hashes["after"]:
            raise ValueError("Source download verification failed: " + name)
        target = work / "new" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if not args.apply:
        print("Verified source staged at: " + str(work / "new") + ". Project unchanged.")
        return
    for name, hashes in FILES.items():
        target = source / name
        current = digest(target)
        if current == hashes["after"]:
            continue
        if current != hashes["before"]:
            raise ValueError("Source changed during preparation; stopped at: " + name)
        if target.exists():
            backup = work / "before" / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            handle.write((work / "new" / name).read_bytes())
            temporary = Path(handle.name)
        temporary.replace(target)
    print("Original laptop source updated to 0.9.3 controls. No deployment was performed.")
    print("Source backups: " + str(work / "before"))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
