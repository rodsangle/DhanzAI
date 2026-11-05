"""Freeze reviewed public Excel tools and host wizard into the standalone installer."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {
    "app/assistant_studio/" + name: (root / "server_extensions/assistant_studio" / name).read_text()
    for name in ("spreadsheet_engine.py", "spreadsheet_package.py", "spreadsheet_tools.py", "operations_tools.py")
}
files["host/add_server_command.py"] = (root / "apps/server_companion/add_server_command.py").read_text()
encoded = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_spreadsheet_tools.py"
source = re.sub(
    r"^PAYLOAD = .+$",
    lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - frozen public modules",
    path.read_text(),
    flags=re.M,
)
path.write_text(source)
