"""Build preview downloads from indexed source paths, never from a workspace dump."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root)  # noqa: S603,S607 - fixed Git operations, no shell.


def safe_entries(root, paths):
    result = []
    for relative in sorted(set(paths)):
        path = root / relative
        name = path.name.lower()
        if (
            name in {".env", "automation-session.bin", "companion.bin", "credentials.json"}
            or name.startswith(".env.backup-")
            or path.suffix.lower() in {".pem", ".key", ".jks", ".keystore", ".p12", ".pfx"}
            or any(
                part in {".git", ".venv", "__pycache__", ".dart_tool", "node_modules"}
                for part in path.relative_to(root).parts
            )
        ):
            raise ValueError(f"Refusing private/generated path: {relative}")
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"Refusing missing, linked or outside source path: {relative}")
        result.append(relative)
    return result


def archive(destination, root, paths, prefix):
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as output:
        for relative in paths:
            entry = ZipInfo(prefix + relative, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = ((0o755 if (root / relative).stat().st_mode & 0o111 else 0o644) | 0o100000) << 16
            output.writestr(entry, (root / relative).read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root, destination, version):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", version):
        raise ValueError("Version must be a filename-safe release identifier.")
    paths = safe_entries(root, git(root, "ls-files", "-z").decode().rstrip("\0").split("\0"))
    destination.mkdir(parents=True, exist_ok=False)
    files = []

    def package(label, selected, base=root, prefix=""):
        if not selected:
            raise ValueError(f"No indexed files selected for {label}")
        path = destination / f"dhanz-{label}-{version}.zip"
        archive(path, base, selected, prefix)
        files.append(path)

    package("source", paths, prefix=f"DhanzAI-{version}/")
    helper = [
        "automation_companion.py",
        "desktop_control.py",
        "task_control.py",
        "start-companion.cmd",
        "requirements-desktop.txt",
        "README.md",
    ]
    for name in helper:
        if "apps/windows_companion/" + name not in paths:
            raise ValueError(f"Missing indexed Windows helper file: {name}")
    package("windows-companion-source", helper, root / "apps/windows_companion", "dhanz-windows-companion/")
    updaters = [p.removeprefix("deploy/updaters/") for p in paths if p.startswith("deploy/updaters/")]
    package("server-updaters", updaters, root / "deploy/updaters", "dhanz-server-updaters/")
    skills = [p.removeprefix("skills/") for p in paths if p.startswith("skills/")]
    package("skills", skills, root / "skills", "dhanz-skills/")
    themes = [p.removeprefix("docs/themes/") for p in paths if p.startswith("docs/themes/")]
    package("theme-concepts", themes, root / "docs/themes", "dhanz-theme-concepts/")
    notes = destination / "RELEASE_NOTES.md"
    notes.write_bytes((root / "docs/UPDATE_PREVIEW.md").read_bytes())
    files.append(notes)
    guide = destination / "DOWNLOADS.md"
    guide.write_text(
        "# Dhanz update preview downloads\n\n"
        + "\n".join(f"- `{p.name}`" for p in files if p.suffix == ".zip")
        + "\n\nSource/helper packages are not Android APKs or full desktop-app installers. "
        "Extract the Windows companion source into a NEW folder and follow its README. "
        "Preserve the existing working helper and AWS configuration. Skills require import; "
        "themes are mockups only. See RELEASE_NOTES.md for validation and limitations.\n"
        "\nIf separate web/Windows executable build jobs pass, they add their own assets and checksum files.\n",
        encoding="utf-8",
    )
    files.append(guide)
    manifest = destination / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "release": version,
                "preview": True,
                "source_commit": git(root, "rev-parse", "HEAD").decode().strip(),
                "working_tree_dirty": bool(git(root, "status", "--porcelain").strip()),
                "automatic_deployment": False,
                "theme_status": "concepts-only",
                "skills_status": "instruction-pack-requires-import",
                "pdf_layout_engine": "not-implemented",
                "packages": [{"name": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in files],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    files.append(manifest)
    (destination / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p)}  {p.name}\n" for p in files),
        encoding="utf-8",
    )
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New output directory; must not already exist")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    files = build(root, args.output.resolve(), args.version)
    print(f"Prepared {len(files)} preview assets plus SHA256SUMS.txt in {args.output}")


if __name__ == "__main__":
    main()
