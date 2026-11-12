"""Freeze reviewed PDF layout and handwriting tools into the standalone installer."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {
    "app/assistant_studio/" + name: (root / "server_extensions/assistant_studio" / name).read_text()
    for name in ("pdf_excel.py", "pdf_table_layout.py", "pdf_handwriting.py", "pdf_turn.py")
}
encoded = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_pdf_layout.py"
source = re.sub(
    r"^PAYLOAD = .+$",
    lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - frozen public modules",
    path.read_text(),
    flags=re.M,
)
path.write_text(source)
