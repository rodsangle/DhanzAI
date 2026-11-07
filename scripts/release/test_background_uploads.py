"""Run the browser tests; expose bounded test assertions as ordinary CI annotations."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

tests = {}
arguments = sys.argv[1:]
if not arguments:
    arguments = [str(path) for path in sorted(Path("test").rglob("*_test.dart")) if "browser" not in path.parts]
process = subprocess.Popen(  # noqa: S603 - fixed Flutter test command, no shell
    [shutil.which("flutter") or "/missing-flutter", "test", "--no-pub", "--reporter=json", *arguments],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)


def escape(value):
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


for line in process.stdout:
    try:
        event = json.loads(line)
    except ValueError:
        print(line, end="", flush=True)
        if ": Error:" in line or "Error:" in line:
            print("::error title=Browser test compiler::" + escape(line.strip()[:700]), flush=True)
        continue
    if event.get("type") == "testStart":
        tests[event["test"]["id"]] = event["test"]["name"]
    elif event.get("type") == "print" and any(name in tests.get(event.get("testID"), "").lower() for name in ("simulator", "wake listening", "media editor")):
        # Flutter framework assertions are print events; the final error event
        # often says only "Test failed". Annotate only this mocked widget test.
        message = str(event.get("message", ""))
        if any(word in message for word in ("EXCEPTION", "Expected:", "Actual:", "overflowed", "assertion")):
            print("::error title=Client widget assertion::" + escape(message.strip()[:1800]), flush=True)
    elif event.get("type") == "error":
        name = tests.get(event.get("testID"), "Flutter test")
        message = str(event.get("error", "Failed")).strip()[:700]
        print("::error title=" + escape(name[:120]) + "::" + escape(message), flush=True)
    elif event.get("type") == "done":
        print("Flutter tests completed; success:", event.get("success"), flush=True)
raise SystemExit(process.wait())
