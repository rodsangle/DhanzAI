"""Freeze the reviewed argument/scope bridge into its standalone updater."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
data = {"module": (root / "server_extensions/assistant_studio/github_compat.py").read_text()}
encoded = base64.b64encode(gzip.compress(json.dumps(data).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_github_compat.py"
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - reviewed public bridge",
        path.read_text(),
        flags=re.M,
    )
)
