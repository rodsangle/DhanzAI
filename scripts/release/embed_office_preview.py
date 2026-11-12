"""Build a single reviewed installer for the Office-preview API and web client."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {
    name: (root / "deploy/updaters" / name).read_text()
    for name in ("install_spreadsheet_tools.py", "install_chat_preview.py")
}
encoded = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_office_preview.py"
source = re.sub(
    r"^PAYLOAD = .+$",
    lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - frozen reviewed installers",
    path.read_text(),
    flags=re.M,
)
path.write_text(source)

website = root / "deploy/updaters/install_website_opening.py"
if website.exists():
    website.write_text(
        re.sub(
            r"^PAYLOAD = .+$",
            lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - frozen reviewed installers",
            website.read_text(),
            flags=re.M,
        )
    )
