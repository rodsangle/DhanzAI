"""Freeze the reviewed backend updater and existing safe browser release installer."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {
    "install_app_builder_chat.py": (root / "deploy/updaters/install_app_builder_chat.py").read_text(),
    "apply_web_release.py": (root / "apps/server_companion/apply_web_release.py").read_text(),
    "web_release.py": (root / "server_extensions/assistant_studio/web_release.py").read_text(),
}
encoded = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_app_simulator.py"
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - reviewed source bundle",
        path.read_text(),
        flags=re.M,
    )
)
