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
diagnostics = []
for line in (result.stdout + result.stderr).splitlines():
    match = re.search(r"(?:error|warning|info)\s+•\s+.*?\s+•\s+(.+?):(\d+):(\d+)\s+•\s+(\w+)\s*$", line)
    if match:
        path, row, column, code = match.groups()
        diagnostics.append(f"{path}:{row}:{column} {code}")
        # Standard source-check annotations; never upload analysis logs as release assets.
        print(f"::error file=apps/dhanz_flutter/{path},line={row},col={column}::{code}")
if diagnostics:
    print("::error title=All Flutter source diagnostics::" + "; ".join(diagnostics))
raise SystemExit(result.returncode)
