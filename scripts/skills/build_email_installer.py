"""Freeze the email skill with the existing tested account-scoped store."""

import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
text = (root / "skills/email-writer/SKILL.md").read_text().split("---", 2)[2].strip()
skill = {
    "name": "email-writer",
    "description": "Write, reply to, improve, and proofread professional or personal emails.",
    "instructions": text,
    "enabled": True,
}
store = (root / "scripts/skills/replica_store.py").read_text()
old = 'if len(names) != 11 or len(set(names)) != 11 or not all(n.startswith("replica-") for n in names):'
if store.count(old) != 1:
    raise ValueError("Unexpected skill store interface.")
store = store.replace(old, 'if names != ["email-writer"]:').replace(
    "Expected eleven unique Replica skill names.", "Expected only the email-writer skill."
)
store = store.replace('"installed": 11', '"installed": 1').replace(
    "Replica skills were edited", "Email skill was edited"
)
data = {
    "skills": [skill],
    "files": {"SKILL.md": (root / "skills/email-writer/SKILL.md").read_text()},
    "store_source": store,
}
source = (root / "deploy/updaters/install_replica_skills.py").read_text()
encoded = base64.b64encode(gzip.compress(json.dumps(data).encode(), mtime=0)).decode()
source = re.sub(
    r"^PAYLOAD = .+$",
    lambda _: "PAYLOAD = " + repr(encoded) + "  # noqa: E501 - reviewed email skill",
    source,
    flags=re.M,
)
source = source.replace(
    "Install the pinned Replica pack as eleven account-owned Dhanz saved skills.",
    "Install the account-owned email-writer skill in the running Dhanz server.",
)
source = source.replace("Replica pack checked: 11 skills.", "Email skill checked.").replace(
    "dhanz-replica-skills-", "dhanz-email-skill-"
)
source = source.replace("Replica: 11 saved skills installed", "Email writer skill installed")
source = source.replace(
    "Start a new Dhanz chat: Use replica-recon to plan my own version of [app name or URL].",
    "Start a new Dhanz chat: Use email-writer to draft a polite follow-up about my quotation.",
)
source = source.replace('    print("Python helpers and original MIT license archived at: " + str(root))\n', "")
source = source.replace(
    '    print("Helpers are not automatically executable chat tools; skills grant no new permissions.")',
    '    print("This skill drafts emails; it does not connect a mailbox or enable automatic sending.")',
)
(root / "deploy/updaters/install_email_skill.py").write_text(source)
(root / "skills/email-writer/skill.json").write_text(json.dumps(skill, indent=2) + "\n")
