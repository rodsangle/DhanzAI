"""Freeze the reviewed upstream pack and account-scoped installer support."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
pack = root / "skills/replica-pack"
files = {p.relative_to(pack).as_posix(): p.read_text() for p in sorted(pack.rglob("*")) if p.is_file()}
data = {
    "skills": json.loads((pack / "skills.json").read_text()),
    "files": files,
    "store_source": (root / "scripts/skills/replica_store.py").read_text(),
}
encoded = base64.b64encode(gzip.compress(json.dumps(data).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_replica_skills.py"
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - reviewed MIT skill pack",
        path.read_text(),
        flags=re.M,
    )
)
