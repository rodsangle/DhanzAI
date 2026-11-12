"""Enable routine decision autonomy for one account on the running Dhanz server.

No API image changes, model calls, dependency installs or upstream scripts run.
"""

import argparse
import base64
import gzip
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

PAYLOAD = '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'  # noqa: E501 - reviewed account setting


def bundle():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def store(packet):
    source = bundle()["store_source"]
    result = subprocess.run(  # noqa: S603 - fixed Docker argv, public code via -c, account selection via stdin only
        ["/usr/bin/sudo", "/usr/bin/docker", "exec", "-i", "deploy-api-1", "python", "-c", source],
        input=json.dumps(packet),
        text=True,
        capture_output=True,
        timeout=60,
    )
    if result.returncode:
        raise ValueError("Could not reach the live Dhanz skill store. Raw output withheld; share this message.")
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise ValueError("The skill store returned an unexpected response. Raw output withheld.") from None
    if data.get("error"):
        raise ValueError(data["error"] + (" Type: " + data["error_type"] if data.get("error_type") else ""))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--email", help="Dhanz sign-in email, only needed if multiple accounts exist.")
    parser.add_argument(
        "--replace", action="store_true", help="Replace same-named skills; a private backup is saved first."
    )
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    data = bundle()
    skills = data["skills"]
    names = [s["name"] for s in skills]
    if args.rollback:
        backup = json.loads(args.rollback.read_text())
        if backup["names"] != names or backup["after_digest"] != fingerprint(skills):
            raise ValueError("Rollback file does not match this reviewed pack. Nothing changed.")
        print(store({"mode": "restore", **backup}))
        return
    inspected = store({"mode": "inspect", "email": args.email, "names": names})
    if inspected.get("needs_account"):
        email = input("More than one active account. Enter your Dhanz sign-in email (not a password): ").strip()
        if not email:
            raise ValueError("No account selected. Nothing changed.")
        inspected = store({"mode": "inspect", "email": email, "names": names})
    if not args.apply:
        print("Autonomy preference checked. Rerun with --apply to save them to the selected account.")
        return
    root = Path(tempfile.mkdtemp(prefix="dhanz-autonomy-setting-", dir=Path.home()))
    root.chmod(0o700)
    for name, text in data["files"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Invalid pack path. Nothing changed.")
        target = root.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    backup = {
        "user_id": inspected["user_id"],
        "names": names,
        "before": inspected["before"],
        "after_digest": fingerprint(skills),
    }
    backup_path = root / "skills-before.json"
    backup_path.write_text(json.dumps(backup))
    result = store(
        {
            "mode": "install",
            "user_id": inspected["user_id"],
            "skills": skills,
            "before_digest": inspected["before_digest"],
            "replace": args.replace,
        }
    )
    print("Use discretion enabled for the selected Dhanz account. Changed:", result["changed"])
    print("Start a new chat or Codex task. Routine decisions use discretion; existing grants still govern external actions.")  # noqa: E501 - complete account-setting message
    print("API, web app, existing skills and server pairing preserved. No provider credits were used for installation.")
    print("Use discretion can be turned off in the chat or Codex toolbar. No new external permission was granted.")
    print("Rollback: " + shlex.join(["python3", str(Path(__file__).resolve()), "--rollback", str(backup_path)]))


def fingerprint(rows):
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda r: r["name"]), sort_keys=True).encode()).hexdigest()


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired):
        # Re-raise only reviewed error text; never print Docker output or settings.
        import sys

        error = sys.exc_info()[1]
        if isinstance(error, ValueError):
            raise SystemExit(str(error)) from None
        raise SystemExit(
            "The local installer could not complete. No automatic retry was made; share this message."
        ) from None
