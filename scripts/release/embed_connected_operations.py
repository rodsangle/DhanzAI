"""Freeze only reviewed additive modules, migration and public companion scripts."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {}
for name in (
    "operations_models.py",
    "operations_service.py",
    "operations_routes.py",
    "operations_tools.py",
    "folder_uploads.py",
):
    files["app/assistant_studio/" + name] = (root / "server_extensions/assistant_studio" / name).read_text()
files["alembic/versions/0013_connected_operations.py"] = (
    root / "server_extensions/migrations/0013_connected_operations.py"
).read_text()
for name in ("server_companion.py", "configure_aws.py", "restart_current.py"):
    files["companion/" + name] = (root / "apps/server_companion" / name).read_text()
path = root / "deploy/updaters/install_connected_operations.py"
encoded = base64.b64encode(gzip.compress(json.dumps(files, sort_keys=True).encode(), mtime=0)).decode()
path.write_text(re.sub(r"^PAYLOAD = .*$", "PAYLOAD = " + repr(encoded), path.read_text(), count=1, flags=re.M))
print("Embedded additive operations, folder support and public companion only.")
