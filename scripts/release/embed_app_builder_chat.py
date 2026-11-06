"""Freeze chat/mobile builder source and narrow live-image patch fragments."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
builder = (root / "server_extensions/assistant_studio/builder.py").read_text()
start = builder.index("    mobile = job.kind")
end = builder.index('    if job.kind == "repository":', start)
fragment = builder[start:end]
start = builder.index("    if mobile and not ")
end = builder.index('        raise BuildError("The generated app has no index.html.")', start)
anchor = "    app.include_router(router, prefix=app.state.settings.api_prefix)\n"
files = {
    "module": (root / "server_extensions/assistant_studio/app_builder_tools.py").read_text(),
    "builder_fragment": fragment,
    "builder_validation": builder[start:end],
    "boot_anchor": anchor,
    "boot_new": anchor
    + "    from .app_builder_tools import install as install_app_builder\n\n    install_app_builder()\n",
}
encoded = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_app_builder_chat.py"
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - frozen source",
        path.read_text(),
        flags=re.M,
    )
)
