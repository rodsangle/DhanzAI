"""Freeze the local renderer modules and the combined host installer."""

import base64
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def embed(path, files):
    packet = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
    path.write_text(
        re.sub(
            r"^PAYLOAD = .+$",
            lambda _: "PAYLOAD = " + repr(packet) + "  # noqa: E501 - reviewed media setup",
            path.read_text(),
            flags=re.M,
        )
    )  # noqa: E501 - bounded fixed schema/filter or installer metadata


embed(
    ROOT / "deploy/updaters/install_media_backend.py",
    {
        name: (ROOT / "server_extensions/assistant_studio" / name).read_text()
        for name in ("media_engine.py", "media_studio.py")
    },
)
embed(
    ROOT / "deploy/updaters/install_media_studio.py",
    {
        "install_media_backend.py": (ROOT / "deploy/updaters/install_media_backend.py").read_text(),
        "apply_web_release.py": (ROOT / "apps/server_companion/apply_web_release.py").read_text(),
        "web_release.py": (ROOT / "server_extensions/assistant_studio/web_release.py").read_text(),
    },
)
