"""Freeze the cloud-account service and prerequisite-preserving web installer."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]


def embed(path, value):
    data = base64.b64encode(gzip.compress(json.dumps(value).encode(), mtime=0)).decode()
    path.write_text(
        re.sub(
            r"^PAYLOAD = .+$",
            lambda _: "PAYLOAD = " + json.dumps(data) + "  # noqa: E501 - frozen integration support",
            path.read_text(),
            flags=re.M,
        )
    )


embed(
    root / "deploy/updaters/install_integrations_backend.py",
    {
        "modules": {
            name: (root / "server_extensions/assistant_studio" / name).read_text()
            for name in ("integration_store.py", "integration_service.py", "integrations.py")
        },
        "wizard": (root / "apps/server_companion/configure_integrations.py").read_text(),
    },
)
embed(
    root / "deploy/updaters/install_integrations.py",
    {
        "install_integrations_backend.py": (root / "deploy/updaters/install_integrations_backend.py").read_text(),
        "apply_web_release.py": (root / "apps/server_companion/apply_web_release.py").read_text(),
        "web_release.py": (root / "server_extensions/assistant_studio/web_release.py").read_text(),
    },
)
