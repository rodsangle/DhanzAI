"""Freeze the backend, per-account preference installer and existing web updater."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {
    name: (root / "deploy/updaters" / name).read_text()
    for name in ("install_autonomy_backend.py", "enable_autonomy_setting.py")
}
files.update(
    {
        "apply_web_release.py": (root / "apps/server_companion/apply_web_release.py").read_text(),
        "web_release.py": (root / "server_extensions/assistant_studio/web_release.py").read_text(),
    }
)
encoded = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_autonomy.py"
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - reviewed discretion setup",
        path.read_text(),
        flags=re.M,
    )
)
