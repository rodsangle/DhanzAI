"""Run Flutter analysis and attach diagnostic codes/locations to the CI check."""

import re
import subprocess

result = subprocess.run(["flutter", "analyze", "--no-pub", "lib", "test"], capture_output=True, text=True)
print(result.stdout, end="")
print(result.stderr, end="")
for line in (result.stdout + result.stderr).splitlines():
    match = re.search(r"(?:error|warning|info)\s+•\s+.*?\s+•\s+(.+?):(\d+):(\d+)\s+•\s+(\w+)\s*$", line)
    if match:
        path, row, column, code = match.groups()
        # Standard source-check annotations; never upload analysis logs as release assets.
        print(f"::error file=client_releases/0.9.4-studio/{path},line={row},col={column}::{code}")
raise SystemExit(result.returncode)
