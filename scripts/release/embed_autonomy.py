"""Freeze the account-scoped autonomy module in its additive backend installer."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
data = {"module": (root / "server_extensions/assistant_studio/autonomy.py").read_text()}
encoded = base64.b64encode(gzip.compress(json.dumps(data).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_autonomy_backend.py"
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - reviewed autonomy support",
        path.read_text(),
        flags=re.M,
    )
)
