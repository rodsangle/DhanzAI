"""Run the browser tests; expose bounded test assertions as ordinary CI annotations."""

import json
import shutil
import subprocess

tests = {}
process = subprocess.Popen(  # noqa: S603 - fixed Flutter test command, no shell
    [shutil.which("flutter") or "/missing-flutter", "test", "--no-pub", "--reporter=json"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)


def escape(value):
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


for line in process.stdout:
    try:
        event = json.loads(line)
    except ValueError:
        print(line, end="", flush=True)
        continue
    if event.get("type") == "testStart":
        tests[event["test"]["id"]] = event["test"]["name"]
    elif event.get("type") == "error":
        name = tests.get(event.get("testID"), "Flutter test")
        message = str(event.get("error", "Failed")).strip()[:700]
        print("::error title=" + escape(name[:120]) + "::" + escape(message), flush=True)
    elif event.get("type") == "done":
        print("Flutter tests completed; success:", event.get("success"), flush=True)
raise SystemExit(process.wait())
