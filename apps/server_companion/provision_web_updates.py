"""Enable the named web updater on an already paired host without changing its token."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path.home() / ".local/share/dhanz-web-updates"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    sources = {}
    for name in ("apply_web_release.py", "web_release.py"):
        path = root / name
        shutil.copyfile(Path(__file__).with_name(name), path)
        path.chmod(0o600)
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    recipe = {
        "description": "Install the latest verified GitHub web build. Preserves API, data and sign-in settings.",
        "argv": ["/usr/bin/python3", str(root / "apply_web_release.py"), "--apply"],
        "cwd": str(Path.home()),
        "timeout": 600,
        "verified_files": sources,
    }
    config_path = Path.home() / ".local/share/dhanz-server-companion/config.json"
    if config_path.is_file():
        if config_path.stat().st_mode & 0o077:
            raise ValueError("Companion config must be private (chmod 600).")
        config = json.loads(config_path.read_text())
        config["tasks"]["update_web"] = recipe
        with tempfile.NamedTemporaryFile(mode="w", dir=config_path.parent, delete=False) as stream:
            json.dump(config, stream, indent=2)
            temporary = Path(stream.name)
        temporary.chmod(0o600)
        os.replace(temporary, config_path)
        print("Paired companion web-update recipe enabled. Existing token and tasks were preserved.")
    else:
        print("No paired companion config was found. Pair this host first, then rerun this setup.")
    if args.apply:
        import subprocess

        subprocess.run(  # noqa: S603 - fixed locally installed, verified updater script and argument list
            ["/usr/bin/python3", str(root / "apply_web_release.py"), "--apply"], check=True, timeout=600
        )


if __name__ == "__main__":
    os.umask(0o077)
    main()
