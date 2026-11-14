#!/usr/bin/env python3
"""Install live news (get_live_news) and automatic live weather into the running DHANZ API.

Run on the server from the repository checkout, as the normal user:

    python3 scripts/server/deploy_live_news.py            # check only, changes nothing
    python3 scripts/server/deploy_live_news.py --apply    # build, test, switch (keeps a rollback image)
    python3 scripts/server/deploy_live_news.py --rollback dhanz-api:rollback-YYYYmmdd-HHMMSS

The live API's tool module (app/services/assistant_tools.py) has its own changes, so this adds one
self-contained file (app/services/news_tools.py) and appends a two-line hook to the end of the tool
module, the same way the weather tool was installed. Nothing else in the image changes.
What --apply does:
1. Checks the tool module has the tool registry the hook needs.
2. Builds a new image FROM the running one with the file and the hook.
3. Tests the new image with the running API's own settings: the backend starts, get_live_news is
   registered and get_weather (when installed) is marked automatic. Then it runs one real news
   search through the server's own search provider and prints how many headlines came back.
4. Keeps the running image as a rollback image, switches only the API and checks /health.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_ai_engine as base  # noqa: E402  - shared container, compose and health helpers
import deploy_conversation_extras as extras  # noqa: E402  - app_dir, live_file, container_network

ROOT = base.ROOT
MODULE = ROOT / "backend/app/services/news_tools.py"
HOOK = (
    "\n\n# Live news (and automatic live weather when installed); added to the registry above.\n"
    "from app.services.news_tools import register as _register_dhanz_news  # noqa: E402\n\n"
    "_register_dhanz_news(globals())\n"
)
NEEDED = {"Tool", "ToolBox", "ToolOutcome", "ToolInputError"}

SMOKE_TEST = r"""
import app.main  # the backend still starts
from app.services import assistant_tools as m
assert "get_live_news" in m.TOOLS, sorted(m.TOOLS)
assert "without asking the user for permission" in m.TOOLS["get_live_news"].spec.description
weather = m.TOOLS.get("get_weather")
if weather is not None:
    assert "without asking the user for permission" in weather.spec.description
print("SMOKE TEST OK: live news registered; weather", "automatic" if weather else "not installed")
"""

LIVE_SEARCH = r"""
import asyncio
from app.core.config import get_settings
from app.services import news_tools
async def main():
    provider = news_tools.search_provider(get_settings())
    if provider is None:
        print("NEWS CHECK: web search is not configured, so live news will say it is unavailable.")
        return
    try:
        out = await news_tools.lookup_news({"max_results": 5}, provider)
    except Exception as exc:  # report only; the provider may be briefly down
        print("NEWS CHECK: the search provider did not answer:", type(exc).__name__)
        return
    finally:
        await provider.aclose()
    print(f"NEWS CHECK: {len(out['articles'])} headlines from {out['provider']}")
    for a in out["articles"][:3]:
        print("  -", a["title"][:90], "|", a["source"], "|", a["published_at"] or "no date")
asyncio.run(main())
"""


def registry_ok(source: str) -> bool:
    tree = ast.parse(source)
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    targets = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets += node.targets
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
    assigned = {t.id for t in targets if isinstance(t, ast.Name)}
    return NEEDED <= classes and "TOOLS" in assigned and "ToolSpec" in source


def hook(source: str) -> str:
    if "_register_dhanz_news" in source:
        return source
    patched = source.rstrip("\n") + "\n" + HOOK
    compile(patched, "assistant_tools.py", "exec")
    return patched


def module_current(container: str, target: str) -> bool:
    live = subprocess.run(  # noqa: S603 - fixed argv
        base.docker("exec", container, "cat", target), capture_output=True, check=False
    )
    return live.returncode == 0 and base.normalized(live.stdout) == base.normalized(MODULE.read_bytes())


def apply(api: dict, appdir: str, tools_src: str) -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    new_tag, rollback_tag = f"dhanz-api:news-{stamp}", f"dhanz-api:rollback-{stamp}"
    base.run(base.docker("tag", api["image_id"], rollback_tag))
    with tempfile.TemporaryDirectory(prefix="dhanz-news-") as folder:
        work = Path(folder)
        (work / "news_tools.py").write_bytes(MODULE.read_bytes())
        (work / "assistant_tools.py").write_text(hook(tools_src))
        (work / "Dockerfile").write_text(
            f"FROM {rollback_tag}\n"
            f"COPY news_tools.py {appdir}/services/news_tools.py\n"
            f"COPY assistant_tools.py {appdir}/services/assistant_tools.py\n"
        )
        print("Building", new_tag, "from the running image (one new file plus a two-line hook).", flush=True)
        base.run(base.docker("build", "-q", "-t", new_tag, folder))
    print("Testing the new image with the running API's own settings.", flush=True)
    extras.run_in_image(new_tag, api, SMOKE_TEST)
    print("Trying one real news search through the server's search provider.", flush=True)
    extras.run_in_image(new_tag, api, LIVE_SEARCH, network=extras.container_network(api["name"]))
    base.run(base.docker("tag", new_tag, api["image_name"]))
    print("Switching the API to the new image.", flush=True)
    base.compose(api, "up", "-d", "--no-deps", "--force-recreate", "api")
    rollback = f"python3 {Path(__file__).relative_to(ROOT)} --rollback {rollback_tag}"
    if not base.healthy(api["name"]):
        print("The API did not report healthy. Roll back with:\n  " + rollback)
        return 1
    print("Done. Ask DHANZ for today's news or the weather. Rollback if needed:\n  " + rollback)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="build, test and switch to the new image")
    parser.add_argument("--rollback", metavar="TAG", help="switch back to a rollback image printed by --apply")
    args = parser.parse_args(argv)
    api = base.api_container()
    if args.rollback:
        base.run(base.docker("tag", args.rollback, api["image_name"]))
        base.compose(api, "up", "-d", "--no-deps", "--force-recreate", "api")
        print("Rolled back to", args.rollback, "- healthy" if base.healthy(api["name"]) else "- check the API logs")
        return 0
    appdir = extras.app_dir(api["name"])
    tools_src = extras.live_file(api["name"], f"{appdir}/services/assistant_tools.py")
    print(f"API container {api['name']} ({api['image_name']}), backend at {appdir}")
    if "_register_dhanz_news" in tools_src and module_current(api["name"], f"{appdir}/services/news_tools.py"):
        print("Live news is already installed. Nothing to do.")
        return 0
    if not registry_ok(tools_src):
        print("The tool module does not have the expected tool registry. Nothing was changed; share this output.")
        return 2
    weather = "get_weather" in tools_src or "weather_tools" in tools_src
    print("  services/news_tools.py: will be added")
    print("  services/assistant_tools.py: two-line hook appended at the end (the rest is kept as it is)")
    print("  weather tool:", "installed; will be used without asking first" if weather else "not installed")
    if not args.apply:
        print("Check passed. Run again with --apply to build, test and switch (a rollback image is kept).")
        return 0
    return apply(api, appdir, tools_src)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Step failed ({' '.join(exc.cmd[:4])} ...). The running API was not switched unless stated above.")
