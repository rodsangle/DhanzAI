#!/usr/bin/env python3
"""Install the AI engine files with GPT-5.5/5.6/6.x support into the running DHANZ API.

Run on the server from the repository checkout, as the normal user:

    python3 scripts/server/deploy_ai_engine.py            # check only, changes nothing
    python3 scripts/server/deploy_ai_engine.py --apply    # build, test, switch (keeps a rollback image)
    python3 scripts/server/deploy_ai_engine.py --rollback dhanz-api:rollback-YYYYmmdd-HHMMSS

What --apply does:
1. Reads the AI engine files inside the running API and checks each one is an unmodified version
   from this repository's history. Anything else (a hand edit, a server-only patch) stops it.
2. Builds a new image FROM the running image, replacing only those files.
3. Tests the new image before using it: the backend still imports, and a simulated GPT-6 reply
   (refused temperature, then refused tools) completes.
4. Tags the running image as a rollback image, gives the new image the running image's name, and
   recreates only the API with the compose files it was started with. Then checks /health.
Data, settings, the database and the other containers are not touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ("providers/openai.py", "orchestrator.py", "types.py")  # relative to the dhanz_ai package
MARKER = "ADAPTIVE_PARAMS = True"

SMOKE_TEST = r"""
import asyncio, json, httpx
import app.main  # the backend still starts with these files
from dhanz_ai import ChatMessage, GenerationParams, ToolSpec
from dhanz_ai.providers.openai import ADAPTIVE_PARAMS, OpenAIProvider
assert ADAPTIVE_PARAMS
seen = []
def handler(request):
    body = json.loads(request.content)
    seen.append(body)
    if "temperature" in body:
        msg = "Unsupported value: 'temperature' ... Only the default (1) value is supported."
        return httpx.Response(400, json={"error": {"message": msg}})
    if body.get("tools") and body.get("reasoning_effort") != "none":
        msg = "Function tools with reasoning_effort are not supported. Set reasoning_effort to 'none'."
        return httpx.Response(400, json={"error": {"message": msg}})
    chunk = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
    return httpx.Response(200, content=("data: " + chunk + "\n\ndata: [DONE]\n\n").encode())
async def main():
    p = OpenAIProvider("test", ["gpt-6.1-sol"], client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    tool = ToolSpec("get_time", "time", {"type": "object", "properties": {}})
    out = [c async for c in p.stream("gpt-6.1-sol", [ChatMessage("user", "hi")], GenerationParams(), [tool])]
    assert "".join(c.text for c in out) == "ok", out
asyncio.run(main())
print("SMOKE TEST OK after", len(seen), "requests")
"""


def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, text=True, **kwargs)  # noqa: S603 - fixed argv, no shell


def output(argv: list[str]) -> str:
    return run(argv, capture_output=True).stdout


def docker(*args: str) -> list[str]:
    return (["docker"] if os.geteuid() == 0 else ["sudo", "docker"]) + list(args)


def api_container() -> dict:
    names = output(docker("ps", "--filter", "label=com.docker.compose.service=api", "--format", "{{.Names}}")).split()
    if len(names) != 1:
        raise SystemExit(f"Expected one running API container, found {len(names)}. Nothing was changed.")
    info = json.loads(output(docker("inspect", names[0])))[0]
    labels = info["Config"]["Labels"]
    return {
        "name": names[0],
        "image_name": info["Config"]["Image"],
        "image_id": info["Image"],
        "files": labels["com.docker.compose.project.config_files"].split(","),
        "workdir": labels["com.docker.compose.project.working_dir"],
        "env": info["Config"]["Env"],
    }


def package_dir(container: str) -> str:
    code = "import dhanz_ai, os; print(os.path.dirname(dhanz_ai.__file__))"
    return output(docker("exec", container, "python", "-c", code)).strip()


def repo_versions(relative: str) -> set[str]:
    """SHA-256 of every committed version of ai_engine/dhanz_ai/<relative>."""
    path = "ai_engine/dhanz_ai/" + relative
    commits = output(["git", "-C", str(ROOT), "rev-list", "HEAD", "--", path]).split()
    digests = set()
    for commit in commits:
        blob = subprocess.run(  # noqa: S603 - fixed argv
            ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],  # noqa: S607
            capture_output=True,
            check=False,
        )
        if blob.returncode == 0:
            digests.add(hashlib.sha256(blob.stdout).hexdigest())
    return digests


def plan(container: str, pkg: str) -> dict[str, str]:
    """Per file: 'replace', 'current' (already new) or 'unknown' (not a repository version)."""
    states = {}
    for relative in FILES:
        live = subprocess.run(  # noqa: S603 - fixed argv
            docker("exec", container, "cat", f"{pkg}/{relative}"), capture_output=True, check=True
        ).stdout
        new = (ROOT / "ai_engine/dhanz_ai" / relative).read_bytes()
        digest = hashlib.sha256(live).hexdigest()
        if live == new:
            states[relative] = "current"
        elif digest in repo_versions(relative):
            states[relative] = "replace"
        else:
            states[relative] = "unknown"
    return states


def compose(api: dict, *args: str) -> None:
    argv = docker("compose")
    for config in api["files"]:
        argv += ["-f", config]
    run([*argv, *args], cwd=api["workdir"])


def healthy(container: str) -> bool:
    check = "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status)"
    for _ in range(30):
        probe = subprocess.run(  # noqa: S603 - fixed argv
            docker("exec", container, "python", "-c", check), capture_output=True, text=True, check=False
        )
        if probe.stdout.strip() == "200":
            return True
        time.sleep(2)
    return False


def apply(api: dict, pkg: str) -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    new_tag, rollback_tag = f"dhanz-api:gpt6-{stamp}", f"dhanz-api:rollback-{stamp}"
    # Keep the running image under a rollback name first; the new image is built from it.
    run(docker("tag", api["image_id"], rollback_tag))
    with tempfile.TemporaryDirectory(prefix="dhanz-ai-engine-") as folder:
        dockerfile = [f"FROM {rollback_tag}"]
        for relative in FILES:
            name = relative.replace("/", "__")
            (Path(folder) / name).write_bytes((ROOT / "ai_engine/dhanz_ai" / relative).read_bytes())
            dockerfile.append(f"COPY {name} {pkg}/{relative}")
        (Path(folder) / "Dockerfile").write_text("\n".join(dockerfile) + "\n")
        print("Building", new_tag, "from the running image (only the AI engine files change).", flush=True)
        run(docker("build", "-q", "-t", new_tag, folder))
    print("Testing the new image before switching (with the running API's own settings).", flush=True)
    with tempfile.NamedTemporaryFile("w", prefix="dhanz-api-env-", suffix=".list") as env_file:
        Path(env_file.name).chmod(0o600)
        env_file.write("\n".join(api["env"]) + "\n")
        env_file.flush()
        run(docker("run", "--rm", "--env-file", env_file.name, "--entrypoint", "python", new_tag, "-c", SMOKE_TEST))
    run(docker("tag", new_tag, api["image_name"]))
    print("Switching the API to the new image.", flush=True)
    compose(api, "up", "-d", "--no-deps", "--force-recreate", "api")
    rollback = f"python3 {Path(__file__).relative_to(ROOT)} --rollback {rollback_tag}"
    if not healthy(api["name"]):
        print("The API did not report healthy. Roll back with:\n  " + rollback)
        return 1
    print("Done. The API is healthy on the new AI engine files.")
    print("Next: sudo python3 scripts/server/upgrade_models.py   (report only)")
    print("Rollback if needed:\n  " + rollback)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="build, test and switch to the new image")
    parser.add_argument("--rollback", metavar="TAG", help="switch back to a rollback image printed by --apply")
    args = parser.parse_args(argv)
    api = api_container()
    if args.rollback:
        run(docker("tag", args.rollback, api["image_name"]))
        compose(api, "up", "-d", "--no-deps", "--force-recreate", "api")
        print("Rolled back to", args.rollback, "- healthy" if healthy(api["name"]) else "- check the API logs")
        return 0
    pkg = package_dir(api["name"])
    states = plan(api["name"], pkg)
    print(f"API container {api['name']} ({api['image_name']}), AI engine at {pkg}")
    for relative, state in states.items():
        print(f"  {relative}: {state}")
    if "unknown" in states.values():
        print("A file differs from every version in this repository. Nothing was changed; share this output.")
        return 2
    if all(state == "current" for state in states.values()):
        print("The API already has GPT-6 support. Nothing to do.")
        return 0
    if not args.apply:
        print("Check passed. Run again with --apply to build, test and switch (a rollback image is kept).")
        return 0
    return apply(api, pkg)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Step failed ({' '.join(exc.cmd[:4])} ...). The running API was not switched unless stated above.")
