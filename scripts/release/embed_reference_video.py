"""Freeze reference-video support and the prerequisite-preserving installer."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]


def embed(path, data):
    value = base64.b64encode(gzip.compress(json.dumps(data).encode(), mtime=0)).decode()
    path.write_text(
        re.sub(
            r"^PAYLOAD = .+$",
            lambda _: "PAYLOAD = " + json.dumps(value) + "  # noqa: E501 - frozen reference support",
            path.read_text(),
            flags=re.M,
        )
    )


embed(
    root / "deploy/updaters/install_reference_backend.py",
    {"module": (root / "server_extensions/assistant_studio/reference_video.py").read_text()},
)
embed(
    root / "deploy/updaters/install_reference_video.py",
    {
        "install_media_backend.py": (root / "deploy/updaters/install_media_backend.py").read_text(),
        "install_reference_backend.py": (root / "deploy/updaters/install_reference_backend.py").read_text(),
        "apply_web_release.py": (root / "apps/server_companion/apply_web_release.py").read_text(),
        "web_release.py": (root / "server_extensions/assistant_studio/web_release.py").read_text(),
    },
)
