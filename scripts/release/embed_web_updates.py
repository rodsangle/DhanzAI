"""Freeze public updater modules and host scripts; never includes runtime credentials."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {}
for name in ("web_updates.py", "web_release.py"):
    files["app/assistant_studio/" + name] = (root / "server_extensions/assistant_studio" / name).read_text()
for name in ("apply_web_release.py", "provision_web_updates.py"):
    files["host/" + name] = (root / "apps/server_companion" / name).read_text()
files["host/web_release.py"] = (root / "server_extensions/assistant_studio/web_release.py").read_text()
path = root / "deploy/updaters/install_web_updates.py"
encoded = base64.b64encode(gzip.compress(json.dumps(files, sort_keys=True).encode(), mtime=0)).decode()
path.write_text(
    re.sub(
        r"^PAYLOAD = .*$",
        "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - public frozen modules",
        path.read_text(),
        count=1,
        flags=re.M,
    )
)
print("Embedded web API, release validation and named host updater.")
