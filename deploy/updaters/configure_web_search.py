"""Configure Tavily or Brave Search while preserving the current custom API image.

Enter the provider key only at the hidden AWS terminal prompt, never in chat.
Default: prepare settings only. --apply recreates only the API container.
"""

import argparse
import getpass
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

PROVIDERS = {"tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY"}


def docker(*args, **kwargs):
    return subprocess.run(  # noqa: S603 - fixed Docker executable, argument list, no shell.
        ["/usr/bin/sudo", "/usr/bin/docker", *args], check=True, text=True, capture_output=True, **kwargs
    ).stdout.strip()


def update_env(source, updates):
    lines = source.splitlines()
    for key, value in updates.items():
        pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=")
        lines = [line for line in lines if not pattern.match(line)]
        lines.append(key + "='" + value + "'")
    return "\n".join(lines) + "\n"


def atomic_private(path, content):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".dhanz-search-", delete=False) as handle:
        os.chmod(handle.name, 0o600)
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, default="tavily")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    info = json.loads(
        docker(
            "inspect",
            "deploy-api-1",
            "--format",
            '{"image":{{json .Image}},'
            '"files":{{json (index .Config.Labels "com.docker.compose.project.config_files")}},'
            '"directory":{{json (index .Config.Labels "com.docker.compose.project.working_dir")}},'
            '"project":{{json (index .Config.Labels "com.docker.compose.project")}}}',
        )
    )
    directory = Path(info["directory"])
    files = [Path(p) for p in info["files"].split(",")]
    env = directory / ".env"
    if (
        not info["project"]
        or not env.is_file()
        or env.is_symlink()
        or not all(p.is_absolute() and p.is_file() for p in files)
    ):
        raise ValueError("The original Compose configuration or .env is unavailable. Nothing was changed.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", info["image"]):
        raise ValueError("The current API image could not be identified. Nothing was changed.")
    field = PROVIDERS[args.provider]
    compatible = docker(
        "exec",
        "deploy-api-1",
        "python",
        "-c",
        "from app.core.config import get_settings; s=get_settings(); print(hasattr(s,'search_provider') and hasattr(s,"
        + repr(field.lower())
        + "))",
    )
    if compatible != "True":
        raise ValueError("This API does not support the selected search provider. Nothing was changed.")
    overlay = directory / "docker-compose.search.json"
    if overlay.exists() and json.loads(overlay.read_text()).get("x-dhanz-search") != 1:
        raise ValueError("An unrelated search overlay exists. Nothing was changed.")
    if not os.isatty(0):
        raise ValueError("Run this script directly in your AWS terminal for hidden key entry.")
    key = getpass.getpass(args.provider.title() + " API key (hidden; never paste in chat): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{16,256}", key):
        raise ValueError("The key format is unexpected. Nothing was changed. Copy only the provider key.")
    stamp = str(time.time_ns())
    work = Path.home() / ("dhanz-search-backup-" + stamp)
    work.mkdir(mode=0o700)
    original = env.read_text()
    atomic_private(work / ".env.before", original)
    before = "dhanz-api:before-search-" + stamp
    docker("tag", info["image"], before)
    old_overlay = overlay.read_text() if overlay.exists() else None
    if old_overlay:
        atomic_private(work / "search-overlay.before.json", old_overlay)
    updated = update_env(original, {"SEARCH_PROVIDER": args.provider, field: key})
    # The overlay contains variable names, not the credential. Standard .env
    # interpolation keeps later Compose operations and other updaters compatible.
    config = {
        "x-dhanz-search": 1,
        "services": {
            "api": {
                "image": before,
                "environment": {
                    "SEARCH_PROVIDER": args.provider,
                    field: "${" + field + ":?set the search provider key in .env}",
                },
            }
        },
    }
    atomic_private(env, updated)
    atomic_private(overlay, json.dumps(config, indent=2) + "\n")
    command = ["compose", "--project-name", info["project"], "--project-directory", str(directory)]
    for file in [p for p in files if p != overlay] + [overlay]:
        command += ["-f", str(file)]
    try:
        docker(*command, "config", "--quiet", cwd=directory)
    except subprocess.CalledProcessError:
        atomic_private(env, original)
        if old_overlay is None:
            overlay.unlink()
        else:
            atomic_private(overlay, old_overlay)
        raise ValueError(
            "Compose validation failed. Original settings were restored; the running API is unchanged."
        ) from None
    print("Search settings prepared. Your key was not printed. Private backup: " + str(work))
    if not args.apply:
        print("The running API is unchanged. Run again with --apply to activate (hidden key entry is required again).")
        return
    rollback = work / "rollback.json"
    atomic_private(
        rollback, json.dumps({"services": {"api": {"image": before, "environment": {"SEARCH_PROVIDER": "none"}}}})
    )
    rollback_command = command + [
        "-f",
        str(rollback),
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "--force-recreate",
        "api",
    ]
    atomic_private(work / "disable-search-command.txt", shlex.join(["sudo", "docker", *rollback_command]) + "\n")
    docker(*command, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "api", cwd=directory)
    for _ in range(30):
        state = json.loads(docker("inspect", "deploy-api-1", "--format", "{{json .State}}"))
        if state.get("Health", {}).get("Status") == "healthy":
            break
        if not state.get("Running"):
            raise ValueError("API stopped. Disable-search command: " + str(work / "disable-search-command.txt"))
        time.sleep(2)
    else:
        raise ValueError(
            "Health was not confirmed. Disable-search command: " + str(work / "disable-search-command.txt")
        )
    # Perform an actual provider query, not just a configuration-presence check.
    code = """import asyncio
from app.core.config import get_settings
from app.services.knowledge_service import build_knowledge_runtime
async def main():
    runtime = build_knowledge_runtime(get_settings())
    try:
        if runtime.search is None:
            print('Search test: NOT CONFIGURED')
            return
        try:
            results = await runtime.search.search('Python official documentation', count=2)
            print('Search provider:', runtime.search.name)
            print('Search test:', 'OK' if results else 'NO RESULTS')
        except Exception:
            print('Search test: FAILED. Check provider key, account quota and outbound access. No key was printed.')
    finally:
        await runtime.aclose()
asyncio.run(main())
"""
    print(docker("exec", "deploy-api-1", "python", "-c", code))
    print("API is healthy; the same image, weather and OCR settings were preserved.")
    print(
        "Enable Web search in chat when available. A saved skill does not override the search toggle or privacy mode."
    )
    print("Disable-search command: " + str(work / "disable-search-command.txt"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Docker step failed (exit {exc.returncode}). Configuration values were not printed."
        ) from None
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
