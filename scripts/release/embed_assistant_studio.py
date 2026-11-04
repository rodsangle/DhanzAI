"""Embed only reviewed extension source in the single-file server installer."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = {}
for path in sorted((root / "server_extensions/assistant_studio").glob("*.py")):
    files["app/assistant_studio/" + path.name] = path.read_text()
files["alembic/versions/0011_assistant_studio.py"] = (
    root / "server_extensions/migrations/0011_assistant_studio.py"
).read_text()
encoded = base64.b64encode(gzip.compress(json.dumps(files, sort_keys=True).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_assistant_studio.py"
source = path.read_text()
source, n = re.subn(r"^PAYLOAD = .*?$", "PAYLOAD = " + repr(encoded), source, count=1, flags=re.M)
assert n == 1
path.write_text(source)
print("Embedded reviewed extension source only.")
