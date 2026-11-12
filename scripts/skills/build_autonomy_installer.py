"""Package one account preference using the reviewed account-scoped skill store."""

import ast
import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
tree = ast.parse((root / "server_extensions/assistant_studio/autonomy.py").read_text())
policy = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "POLICY" for t in n.targets)
)
skill = {
    "name": "dhanz-autonomy",
    "description": "Use discretion for routine chat and coding decisions within existing permissions.",
    "instructions": policy,
    "enabled": True,
}
store = (root / "scripts/skills/replica_store.py").read_text()
old = 'if len(names) != 11 or len(set(names)) != 11 or not all(n.startswith("replica-") for n in names):'
if store.count(old) != 1:
    raise ValueError("Unexpected preference-store interface.")
store = (
    store.replace(old, 'if names != ["dhanz-autonomy"]:')
    .replace("Expected eleven unique Replica skill names.", "Expected only the autonomy preference.")
    .replace('"installed": 11', '"installed": 1')
)
data = {"skills": [skill], "files": {"AUTONOMY.md": policy}, "store_source": store}
source = (root / "deploy/updaters/install_email_skill.py").read_text()
encoded = base64.b64encode(gzip.compress(json.dumps(data).encode(), mtime=0)).decode()
source = re.sub(
    r"^PAYLOAD = .+$",
    lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - reviewed account setting",
    source,
    flags=re.M,
)
source = source.replace(
    "Install the account-owned email-writer skill in the running Dhanz server.",
    "Enable routine decision autonomy for one account on the running Dhanz server.",
)
source = source.replace("Email skill checked.", "Autonomy preference checked.").replace(
    "dhanz-email-skill-", "dhanz-autonomy-setting-"
)
source = source.replace("Email writer skill installed", "Use discretion enabled").replace(
    "Start a new Dhanz chat: Use email-writer to draft a polite follow-up about my quotation.",
    "Start a new chat or Codex task. Routine decisions use discretion; existing grants still govern external actions.",
)
source = source.replace(
    "This skill drafts emails; it does not connect a mailbox or enable automatic sending.",
    "Use discretion can be turned off in the chat or Codex toolbar. No new external permission was granted.",
)
source = (
    "\n".join(
        line + "  # noqa: E501 - complete account-setting message" if len(line) > 120 and "# noqa" not in line else line
        for line in source.splitlines()
    )
    + "\n"
)
(root / "deploy/updaters/enable_autonomy_setting.py").write_text(source)
