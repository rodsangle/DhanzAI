"""Freeze the reviewed CSV agent and chat adapter into its additive updater."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
package = {
    "module": (root / "server_extensions/assistant_studio/csv_totals_tools.py").read_text(),
    "engine": (root / "server_extensions/assistant_studio/csv_totals_agent.py").read_text(),
}
encoded = base64.b64encode(gzip.compress(json.dumps(package).encode(), mtime=0)).decode()
path = root / "deploy/updaters/install_csv_totals_agent.py"
path.write_text(
    re.sub(
        r"^PAYLOAD = .+$",
        lambda _: "PAYLOAD = " + json.dumps(encoded) + "  # noqa: E501 - frozen CSV totals agent",
        path.read_text(),
        flags=re.M,
    )
)
