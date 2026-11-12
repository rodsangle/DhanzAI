"""Locally approve a fixed command for the existing outbound server companion."""

import hashlib
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path


def prepare(tasks, name, description, command, cwd, timeout=120):
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", name) or name in tasks:
        raise ValueError("Use a new unique task name: 3–40 lowercase letters, digits or underscores.")
    if not 1 <= len(description) <= 200:
        raise ValueError("Description must be 1–200 characters.")
    argv = shlex.split(command)
    if not argv or not 1 <= timeout <= 1800:
        raise ValueError("Enter a command and timeout of 1–1800 seconds.")
    executable = shutil.which(argv[0])
    directory = Path(cwd).expanduser().resolve(strict=True)
    if not executable or not directory.is_dir():
        raise ValueError("Executable or working directory not found.")
    argv[0] = str(Path(executable).resolve(strict=True))
    verified = {}
    # Pin existing script arguments to their approved contents and absolute paths.
    for index, value in enumerate(argv[1:], 1):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = directory / path
        if path.is_file() and path.suffix in (".py", ".sh", ".bash", ".js", ".mjs"):
            path = path.resolve(strict=True)
            argv[index] = str(path)
            verified[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    recipe = {"argv": argv, "cwd": str(directory), "timeout": timeout, "description": description}
    if verified:
        recipe["verified_files"] = verified
    return recipe


def main():
    path = Path.home() / ".local/share/dhanz-server-companion/config.json"
    if path.stat().st_mode & 0o077:
        raise ValueError("Paired configuration must be private (chmod 600).")
    config = json.loads(path.read_text())
    print(
        "Add a fixed AWS command. No shell expansion or model-supplied arguments. Output remains private on the host; Dhanz receives execution status only."  # noqa: E501 - descriptive tool text
    )
    name = input("New task name (for example disk_check): ").strip()
    description = input("Describe this command: ").strip()
    cwd = input("Working directory (Enter for home): ").strip() or str(Path.home())
    command = input("Exact command (for example /usr/bin/df -h): ").strip()
    timeout = int(input("Timeout seconds (Enter for 120): ").strip() or "120")
    recipe = prepare(config["tasks"], name, description, command, cwd, timeout)
    print("Command:", shlex.join(recipe["argv"]))
    print("Directory:", recipe["cwd"])
    if input("Type ADD to save this exact command: ").strip() != "ADD":
        print("Nothing changed.")
        return
    # Refuse concurrent configuration changes instead of losing another task.
    original = path.read_bytes()
    latest = json.loads(original)
    if latest != config:
        raise ValueError("Configuration changed during setup. Rerun; nothing changed.")
    config["tasks"][name] = recipe
    fd, temp = tempfile.mkstemp(prefix=".command-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(config, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        if path.read_bytes() != original:
            raise ValueError("Configuration changed. Rerun; nothing changed.")
        os.replace(temp, path)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()
    print(
        "Saved. Wait for the next companion heartbeat, then authorize "
        + name
        + " in Connected operations. Pairing and existing tasks were preserved."
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
