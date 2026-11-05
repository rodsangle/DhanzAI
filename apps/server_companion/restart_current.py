"""Restart only the live API; resolve current overlays immediately before execution."""

import json
import subprocess
from pathlib import Path


def main():
    labels = json.loads(
        subprocess.check_output(  # noqa: S603 - fixed Docker inspection
            [
                "/usr/bin/sudo",
                "-n",
                "/usr/bin/docker",
                "inspect",
                "deploy-api-1",
                "--format",
                "{{json .Config.Labels}}",
            ],
            text=True,
        )
    )
    directory = Path(labels["com.docker.compose.project.working_dir"])
    files = labels["com.docker.compose.project.config_files"].split(",")
    if (
        not directory.is_absolute()
        or not directory.is_dir()
        or not all(Path(f).is_absolute() and Path(f).is_file() for f in files)
    ):
        raise ValueError("Live Compose configuration is unavailable. Nothing restarted.")
    command = [
        "/usr/bin/sudo",
        "-n",
        "/usr/bin/docker",
        "compose",
        "--project-directory",
        str(directory),
        "-p",
        labels["com.docker.compose.project"],
    ]
    for filename in files:
        command += ["-f", filename]
    subprocess.run(  # noqa: S603 - live local Docker labels, fixed restart operation, no shell
        command + ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "api"],
        check=True,
        timeout=150,
    )


if __name__ == "__main__":
    main()
