"""Install a private SearXNG search service for the current custom Dhanz API.

No paid search API key is required. Default prepares only; --apply starts search,
recreates only the API, verifies a real search and restores the old search setting
if validation fails. Uses the existing API image and Docker network.
"""

import argparse
import json
import re
import secrets
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

IMAGE = "searxng/searxng@sha256:892ed5710603e38f9dc201e6a0b2f3f14dbdb8108edcadac30e55b165c979fb7"
SERVICE = "dhanz-search"
SEARCH_URL = "http://dhanz-search:8080"
METADATA = (
    '{"image":{{json .Image}},'
    '"files":{{json (index .Config.Labels "com.docker.compose.project.config_files")}},'
    '"directory":{{json (index .Config.Labels "com.docker.compose.project.working_dir")}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"networks":{{json .NetworkSettings.Networks}}}'
)
PROBE = (
    "import json; from app.core.config import get_settings; s=get_settings(); "
    "print(json.dumps({'supported':hasattr(s,'search_provider') and hasattr(s,'searxng_url'),"
    "'provider':getattr(s,'search_provider','none'),"
    "'ours':getattr(s,'searxng_url',None)=='http://dhanz-search:8080'}))"
)
QUERY = """import asyncio,json
from app.core.config import get_settings
from app.services.knowledge_service import build_knowledge_runtime
async def main():
    runtime = build_knowledge_runtime(get_settings())
    try:
        if runtime.search is None or runtime.search.name != 'searxng':
            print(json.dumps({'ok':False,'reason':'adapter_not_configured'}))
            return
        counts = {}
        for label, query, news in [('web_results','Python official documentation',False),
                                   ('news_results','Houston Texas local news',True)]:
            try:
                results = await runtime.search.search(query, count=2, news=news)
                counts[label] = len(results)
            except Exception:
                counts[label] = 0
        counts['ok'] = bool(counts['web_results'] or counts['news_results'])
        print(json.dumps(counts))
    finally:
        await runtime.aclose()
asyncio.run(main())
"""


def docker(*args, directory=None):
    return subprocess.run(  # noqa: S603 - fixed Docker executable, argument array, no shell.
        ["/usr/bin/sudo", "/usr/bin/docker", *args], check=True, text=True, capture_output=True, cwd=directory
    ).stdout.strip()


def choose_network(info, requested=None):
    networks = info.get("networks") or {}
    if requested:
        if requested not in networks:
            raise ValueError("The requested network is not attached to the API. Nothing was changed.")
        return requested
    default = info["project"] + "_default"
    if default in networks:
        return default
    if len(networks) == 1:
        return next(iter(networks))
    raise ValueError("The API has multiple non-default networks; choose one with --network. Nothing was changed.")


def settings_text(secret):
    # Limit the engine set to ordinary web searches and three news providers.
    return f"""use_default_settings:
  engines:
    keep_only:
      - duckduckgo
      - bing
      - brave
      - google
      - duckduckgo news
      - bing news
      - google news
engines:
  - name: duckduckgo
    disabled: false
  - name: bing
    disabled: false
  - name: brave
    disabled: false
  - name: google
    disabled: false
  - name: duckduckgo news
    disabled: false
  - name: bing news
    disabled: false
  - name: google news
    disabled: false
server:
  secret_key: {json.dumps(secret)}
  bind_address: "0.0.0.0"
  port: 8080
  limiter: false
  image_proxy: false
search:
  safe_search: 1
  formats:
    - html
    - json
outgoing:
  request_timeout: 5.0
  max_request_timeout: 8.0
  pool_connections: 20
  pool_maxsize: 4
"""


def compose_config(api_image, network, settings):
    return {
        "x-dhanz-searxng": 1,
        "services": {
            "api": {"image": api_image, "environment": {"SEARCH_PROVIDER": "searxng", "SEARXNG_URL": SEARCH_URL}},
            SERVICE: {
                "image": IMAGE,
                "restart": "unless-stopped",
                "expose": ["8080"],
                "mem_limit": "384m",
                "cpus": 0.75,
                "pids_limit": 128,
                "security_opt": ["no-new-privileges:true"],
                "environment": {
                    "SEARXNG_SETTINGS_PATH": "/etc/searxng/settings.yml",
                    "GRANIAN_WORKERS": "1",
                    "FORCE_OWNERSHIP": "false",
                },
                "volumes": [str(settings) + ":/etc/searxng/settings.yml:ro"],
                "networks": {"dhanz_search_link": {"aliases": [SERVICE]}},
            },
        },
        "networks": {"dhanz_search_link": {"name": network, "external": True}},
    }


def write_private(path, text):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".dhanz-search-", delete=False) as handle:
        temporary = Path(handle.name)
        temporary.chmod(0o600)
        handle.write(text)
    temporary.replace(path)


def api_healthy():
    for _ in range(30):
        state = json.loads(docker("inspect", "deploy-api-1", "--format", "{{json .State}}"))
        if state.get("Health", {}).get("Status") == "healthy":
            return True
        if not state.get("Running") or state.get("Health", {}).get("Status") == "unhealthy":
            return False
        time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--network")
    args = parser.parse_args()
    info = json.loads(docker("inspect", "deploy-api-1", "--format", METADATA))
    status = json.loads(docker("exec", "deploy-api-1", "python", "-c", PROBE))
    if not status.get("supported"):
        raise ValueError("This API does not support SearXNG search. Nothing was changed.")
    directory = Path(info["directory"])
    files = [Path(p) for p in (info.get("files") or "").split(",") if p]
    if not directory.is_dir() or not files or not all(p.is_absolute() and p.is_file() for p in files):
        raise ValueError("Original Compose files are unavailable. Nothing was changed.")
    if not info.get("project") or not re.fullmatch(r"sha256:[0-9a-f]{64}", info["image"]):
        raise ValueError("Cannot identify the API image/project. Nothing was changed.")
    network = choose_network(info, args.network)
    overlay = directory / "docker-compose.searxng.json"
    if overlay.exists() and json.loads(overlay.read_text()).get("x-dhanz-searxng") != 1:
        raise ValueError("An unrelated SearXNG overlay exists. Nothing was changed.")
    if status.get("provider") == "searxng":
        if not status.get("ours") or not overlay.exists():
            raise ValueError(
                "Another SearXNG endpoint is already configured. It was preserved; inspect it before replacing."
            )
        check = json.loads(docker("exec", "deploy-api-1", "python", "-c", QUERY))
        if check.get("ok"):
            print(
                "SearXNG is already configured. Web results: "
                + str(check.get("web_results", 0))
                + "; news results: "
                + str(check.get("news_results", 0))
            )
            return
        raise ValueError("Existing SearXNG search did not pass its live query. Configuration was preserved.")
    # Fail early rather than overloading the small Lightsail instance during a
    # concurrent Flutter build. This limit is deliberately conservative.
    available = next(
        (
            int(line.split()[1])
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        ),
        0,
    )
    if available < 512 * 1024:
        raise ValueError("Less than 512 MiB is available. Finish other builds or free memory before installing search.")
    stamp = str(time.time_ns())
    work = Path.home() / ("dhanz-searxng-" + stamp)
    work.mkdir(mode=0o700)
    settings = work / "settings.yml"
    write_private(settings, settings_text(secrets.token_hex(32)))
    # The containing directory is private; the container's unprivileged process
    # must be able to read this bind-mounted file. No user/API keys are in it.
    settings.chmod(0o644)
    before = "dhanz-api:before-searxng-" + stamp
    docker("tag", info["image"], before)
    print("Downloading the pinned official SearXNG image...", flush=True)
    docker("pull", IMAGE)
    old_overlay = overlay.read_text() if overlay.exists() else None
    if old_overlay:
        write_private(work / "overlay.before.json", old_overlay)
    write_private(overlay, json.dumps(compose_config(before, network, settings), indent=2) + "\n")
    command = ["compose", "--project-name", info["project"], "--project-directory", str(directory)]
    for file in [p for p in files if p != overlay] + [overlay]:
        command += ["-f", str(file)]
    try:
        docker(*command, "config", "--quiet", directory=directory)
    except subprocess.CalledProcessError:
        if old_overlay:
            write_private(overlay, old_overlay)
        else:
            overlay.unlink()
        raise ValueError(
            "Compose validation failed; the original overlay was restored and running services were unchanged."
        ) from None
    rollback = work / "rollback.json"
    old_provider = status.get("provider") or "none"
    if old_provider not in {"none", "brave", "tavily"}:
        raise ValueError("The previous provider is unfamiliar. The running API is unchanged.")
    write_private(
        rollback, json.dumps({"services": {"api": {"image": before, "environment": {"SEARCH_PROVIDER": old_provider}}}})
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
    write_private(work / "rollback-command.txt", shlex.join(["sudo", "docker", *rollback_command]) + "\n")
    if not args.apply:
        print("Prepared a private search service, memory limit and API image snapshot. Running services are unchanged.")
        print("To install: python3 " + shlex.quote(str(Path(__file__).resolve())) + " --apply")
        return
    docker(*command, "up", "-d", "--no-deps", "--no-build", "--pull", "never", SERVICE, directory=directory)
    health_code = """import httpx
try:
    response = httpx.get('http://dhanz-search:8080/healthz', timeout=3, trust_env=False)
    print('ready' if response.status_code == 200 else 'waiting')
except httpx.HTTPError:
    print('waiting')
"""
    ready = False
    for _ in range(30):
        if docker("exec", "deploy-api-1", "python", "-c", health_code) == "ready":
            ready = True
            break
        time.sleep(2)
    if not ready:
        docker(*command, "stop", SERVICE, directory=directory)
        raise ValueError(
            "SearXNG did not become ready and was stopped. Your API was not restarted. Share this message."
        )
    try:
        docker(
            *command,
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "api",
            directory=directory,
        )
        if not api_healthy():
            raise ValueError("API health was not confirmed.")
        check = json.loads(docker("exec", "deploy-api-1", "python", "-c", QUERY))
        if not check.get("ok"):
            raise ValueError(
                "A live search returned no usable results; upstream engines may be blocked or unavailable."
            )
    except (subprocess.CalledProcessError, ValueError):
        docker(*rollback_command, directory=directory)
        docker(*command, "stop", SERVICE, directory=directory)
        print("Search validation failed. Previous API image and search provider restored; SearXNG stopped.")
        print("API health after restoration: " + ("healthy" if api_healthy() else "NOT CONFIRMED"))
        raise ValueError("Share this final message; no working search connection is being claimed.") from None
    print(
        "SearXNG installed. API is healthy. Live web results: "
        + str(check.get("web_results", 0))
        + "; news results: "
        + str(check.get("news_results", 0))
    )
    if not check.get("news_results"):
        print("Daily Local News was NOT verified: upstream news engines returned no usable results.")
    if not check.get("web_results"):
        print("Ordinary web search was NOT verified: upstream web engines returned no usable results.")
    print("No search API key or public search port was added. Weather, OCR and the API image were preserved.")
    print("Refresh dhanzai.com and select Web: Auto or Web: Always.")
    print("Rollback command: " + str(work / "rollback-command.txt"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Docker step failed (exit {exc.returncode}). No secrets or resolved configuration were printed."
        ) from None
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
