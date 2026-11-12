"""Freeze chat/mobile builder source and narrow live-image patch fragments."""

import ast
import base64
import gzip
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = root / "deploy/updaters/install_app_builder_chat.py"
tree = ast.parse(path.read_text())
encoded = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "PAYLOAD" for t in n.targets)
)
previous = json.loads(gzip.decompress(base64.b64decode(encoded)))
builder = (root / "server_extensions/assistant_studio/builder.py").read_text()
start = builder.index("    mobile = job.kind")
end = builder.index('    if job.kind == "repository":', start)
fragment = builder[start:end]
start = builder.index("    if mobile and not ")
end = builder.index('        raise BuildError("The generated app has no index.html.")', start)
validation = builder[start:end]
start = builder.index("    from .builder_simulation import revision_context")
end = builder.index("    response = await client.post(", start)
anchor = "    app.include_router(router, prefix=app.state.settings.api_prefix)\n"
files = {
    "module": (root / "server_extensions/assistant_studio/app_builder_tools.py").read_text(),
    "extra_modules": {
        name: (root / "server_extensions/assistant_studio" / name).read_text()
        for name in ("app_simulator.py", "builder_simulation.py")
    },
    "builder_fragment": fragment,
    "builder_validation": validation,
    "revision_fragment": builder[start:end],
    "old_input": '"input": f"Project type: {job.kind}\\nName: {job.name}\\nTask: {job.prompt}",',
    "new_input": '"input": f"Project type: {job.kind}\\nName: {job.name}\\nTask: {job.prompt}" + previous_source,',
    "previous_builder_fragment": previous.get("previous_builder_fragment", previous["builder_fragment"]),
    "previous_builder_validation": previous.get("previous_builder_validation", previous["builder_validation"]),
    "previous_tool_sha": previous.get("previous_tool_sha", hashlib.sha256(previous["module"].encode()).hexdigest()),
    "boot_anchor": anchor,
    "boot_new": anchor
    + "    from .app_builder_tools import install as install_app_builder\n\n    install_app_builder(app)\n",
}
encoded = base64.b64encode(gzip.compress(json.dumps(files).encode(), mtime=0)).decode()
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - frozen source",
        path.read_text(),
        flags=re.M,
    )
)
