"""Run Flutter analysis and attach diagnostic codes/locations to the CI check."""

import re
import shutil
import subprocess

result = subprocess.run(  # noqa: S603 - fixed Flutter analysis command, no shell.
    [shutil.which("flutter") or "/missing-flutter", "analyze", "--no-pub", "lib", "test"],
    capture_output=True,
    text=True,
)
print(result.stdout, end="")
print(result.stderr, end="")
for line in (result.stdout + result.stderr).splitlines():
    match = re.search(r"(?:error|warning|info)\s+•\s+.*?\s+•\s+(.+?):(\d+):(\d+)\s+•\s+(\w+)\s*$", line)
    if match:
        path, row, column, code = match.groups()
        # Standard source-check annotations; never upload analysis logs as release assets.
        print(f"::error file=client_releases/0.9.7-conversation/{path},line={row},col={column}::{code}")
raise SystemExit(result.returncode)
