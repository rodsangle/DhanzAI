"""Embed reviewed coding modules and migration; never includes uploaded private source."""

import base64
import gzip
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {}
for name in ("coding_models.py", "coding_service.py", "coding_routes.py", "builder.py", "builder_simulation.py"):
    files["app/assistant_studio/" + name] = (root / "server_extensions/assistant_studio" / name).read_text()
files["alembic/versions/0012_coding_workspace.py"] = (
    root / "server_extensions/migrations/0012_coding_workspace.py"
).read_text()
path = root / "deploy/updaters/install_coding_workspace.py"
source = path.read_text()
encoded = base64.b64encode(gzip.compress(json.dumps(files, sort_keys=True).encode(), mtime=0)).decode()
source = re.sub(r"^PAYLOAD = .*$", "PAYLOAD = " + repr(encoded), source, count=1, flags=re.M)
digest = hashlib.sha256((root / "server_extensions/assistant_studio/bootstrap.py").read_bytes()).hexdigest()
source = re.sub(r"^BASE_BOOTSTRAP = .*$", "BASE_BOOTSTRAP = " + repr(digest), source, count=1, flags=re.M)
path.write_text(source)
print("Embedded reviewed coding modules and additive migration only.")
