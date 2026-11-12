"""Pair this AWS host. Captures active Compose files; never rebuilds/replaces images."""

import argparse
import getpass
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from server_companion import origin, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://dhanzai.com")
    parser.add_argument("--approve-updater", type=Path)
    args = parser.parse_args()
    server = origin(args.origin)
    token = getpass.getpass("Paste the server pairing token (hidden): ").strip()
    if len(token) < 40 or any(c.isspace() for c in token):
        raise ValueError("Invalid pairing token.")
    labels = json.loads(
        subprocess.check_output(  # noqa: S603 - fixed inspection argv
            ["/usr/bin/sudo", "/usr/bin/docker", "inspect", "deploy-api-1", "--format", "{{json .Config.Labels}}"],
            text=True,
        )
    )
    directory = Path(labels["com.docker.compose.project.working_dir"])
    files = labels["com.docker.compose.project.config_files"].split(",")
    if (
        not directory.is_absolute()
        or not directory.is_dir()
        or not all(Path(p).is_absolute() and Path(p).is_file() for p in files)
    ):
        raise ValueError("Active Compose configuration could not be verified.")
    root = Path.home() / ".local/share/dhanz-server-companion"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    restart = root / "restart_current.py"
    shutil.copyfile(Path(__file__).with_name("restart_current.py"), restart)
    tasks = {
        "health": {
            "description": "Check the public Dhanz readiness endpoint. Does not change services.",
            "argv": ["/usr/bin/curl", "-fsS", "--max-time", "25", server + "/api/v1/health/ready"],
            "cwd": str(directory),
            "timeout": 30,
        },
        "restart": {
            "description": "Restart the live Dhanz API with its current image and settings. Brief interruption.",
            "argv": ["/usr/bin/python3", str(restart)],
            "verified_files": {str(restart): hashlib.sha256(restart.read_bytes()).hexdigest()},
            "cwd": str(directory),
            "timeout": 180,
        },
    }
    if args.approve_updater:
        path = args.approve_updater.resolve(strict=True)
        if not path.is_file() or path.suffix != ".py":
            raise ValueError("Select a Python updater you have already reviewed.")
        tasks["deploy"] = {
            "description": "Apply the locally approved updater " + path.name + ". May interrupt services.",
            "argv": ["/usr/bin/python3", str(path), "--apply"],
            "cwd": str(directory),
            "timeout": 1800,
            "verified_files": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()},
        }
    for recipe in tasks.values():
        validate(recipe)
    root = Path.home() / ".local/share/dhanz-server-companion"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    config = root / "config.json"
    config.write_text(json.dumps({"origin": server, "token": token, "tasks": tasks}, indent=2))
    config.chmod(0o600)
    shutil.copyfile(Path(__file__).with_name("server_companion.py"), root / "server_companion.py")
    unit = root / "dhanz-server-companion.service"
    # Paths are quoted in systemd syntax; reject ambiguous control characters.
    if any(c in str(root) for c in '\n\r"%'):
        raise ValueError("Unsupported home directory path.")
    unit.write_text(
        "[Unit]\nDescription=Dhanz outbound server companion\nAfter=network-online.target docker.service\n"
        "[Service]\nType=simple\nUser=" + getpass.getuser() + "\nUMask=0077\n"
        'ExecStart=/usr/bin/python3 "' + str(root / "server_companion.py") + '" --config "' + str(config) + '"\n'
        "Restart=on-failure\nRestartSec=15\n[Install]\nWantedBy=multi-user.target\n"
    )
    print("Paired configuration saved privately. Enable the service with:")
    print("sudo cp " + str(unit) + " /etc/systemd/system/dhanz-server-companion.service")
    print("sudo systemctl daemon-reload")
    print("sudo systemctl enable --now dhanz-server-companion")
    print("Then refresh Connected operations in Dhanz and authorize the named tasks.")
    if not args.approve_updater:
        print(
            "Deployment stays unavailable until you rerun with --approve-updater /absolute/path/to/reviewed_updater.py"
        )


if __name__ == "__main__":
    os.umask(0o077)
    main()
