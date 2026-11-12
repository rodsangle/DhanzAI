"""Build Dhanz skill records from the pinned, MIT-licensed Replica source."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "skills/replica-pack"


def build():
    provenance = json.loads((PACK / "provenance.json").read_text())
    for name, digest in provenance["files"].items():
        if hashlib.sha256((PACK / "upstream" / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Pinned upstream source changed: " + name)
    compatibility = (PACK / "DHANZ_COMPATIBILITY.md").read_text()
    license_text = (PACK / "upstream/LICENSE").read_text()
    skills = []
    for path in sorted((PACK / "upstream").glob("replica-*/SKILL.md")):
        _, front, body = path.read_text().split("---", 2)
        name = next(line.removeprefix("name:").strip() for line in front.splitlines() if line.startswith("name:"))
        description = " ".join(line.strip() for line in front.split("description: >-", 1)[1].splitlines())
        description = description.strip()
        if len(description) > 500:
            description = description.split(". ", 1)[0] + "."
        if len(description) > 500:
            raise ValueError("Description exceeds Dhanz limits: " + name)
        references = []
        for reference in sorted(path.parent.iterdir()):
            if reference.name != "SKILL.md" and reference.suffix in (".md", ".csv", ".json", ".ts"):
                if len(reference.read_text()) <= 2500:
                    references.append("\n### Reference: " + reference.name + "\n\n" + reference.read_text())
        text = (
            compatibility
            + "\n\n## Original Replica workflow\n"
            + body
            + "\n".join(references)
            + "\n\n## Provenance and license\nSource: "
            + provenance["repository"]
            + "\nPinned commit: "
            + provenance["commit"]
            + "\n\n"
            + license_text
        )
        text = text.strip()
        if not 10 <= len(text) <= 12000:
            raise ValueError("Skill exceeds Dhanz limits: " + name)
        skills.append(dict(name=name, description=description, instructions=text, enabled=True))
    if len(skills) != 11:
        raise ValueError("Expected all eleven upstream skills.")
    (PACK / "skills.json").write_text(json.dumps(skills, ensure_ascii=False, indent=2) + "\n")
    return skills


if __name__ == "__main__":
    result = build()
    print("Prepared", len(result), "skills; largest:", max(len(s["instructions"]) for s in result), "characters.")
